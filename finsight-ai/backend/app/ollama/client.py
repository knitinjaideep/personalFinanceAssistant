"""
Async Ollama HTTP client.

Wraps the ollama Python SDK with:
- Async support
- Retry logic via tenacity
- Configurable per-call timeout (default from settings, overridable per call)
- Stall watchdog: cancels if token rate < 1 token/3s for >10s consecutive
- Structured error mapping to domain exceptions
- Connection health check
- Token rate + time-to-first-token logging
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.domain.errors import (
    LLMResponseParseError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStalledException,
)

# Watchdog constants
_STALL_WINDOW_SECONDS = 10    # how long with low rate before declaring a stall
_STALL_MIN_RATE = 1.0 / 3.0  # minimum tokens/second (1 token per 3s)

logger = structlog.get_logger(__name__)


class OllamaClient:
    """
    Async wrapper around the Ollama HTTP API.

    All LLM calls funnel through this class so we have a single place to
    handle retries, timeouts, and error mapping.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or settings.ollama.base_url
        # Import here to avoid top-level dependency if Ollama is not installed
        import ollama
        self._ollama = ollama
        self._async_client = ollama.AsyncClient(host=self._base_url)

    async def health_check(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            models = await self._async_client.list()
            logger.debug("ollama.health_check.ok", model_count=len(models.get("models", [])))
            return True
        except Exception as exc:
            logger.warning("ollama.health_check.failed", error=str(exc))
            return False

    async def list_models(self) -> list[str]:
        """Return list of available model names pulled in Ollama."""
        try:
            response = await self._async_client.list()
            return [m["name"] for m in response.get("models", [])]
        except Exception as exc:
            raise OllamaConnectionError(
                f"Failed to list Ollama models: {exc}"
            ) from exc

    @retry(
        retry=retry_if_exception_type(OllamaConnectionError),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        num_ctx: int | None = None,
        format: str | None = None,
        timeout: int | None = None,
    ) -> str:
        """
        Generate a completion from an Ollama model.

        Uses streaming internally to support the stall watchdog.  The full
        response text is accumulated and returned when generation finishes.

        Args:
            model: Ollama model name (e.g., "qwen3:8b")
            prompt: The user prompt
            system: Optional system message
            temperature: Sampling temperature (overrides config default)
            num_ctx: Context window size (overrides config default)
            format: Response format hint, e.g., "json"
            timeout: Hard timeout in seconds (overrides ``settings.ollama.timeout_seconds``)

        Returns:
            The generated text content as a string.

        Raises:
            OllamaConnectionError: On timeout or connection failure.
            OllamaStalledException: When token rate is below threshold for >10s.
            OllamaModelNotFoundError: When the requested model is not pulled.
        """
        hard_timeout = timeout or settings.ollama.timeout_seconds
        options: dict[str, Any] = {
            "temperature": temperature or settings.ollama.temperature,
            "num_ctx": num_ctx or settings.ollama.num_ctx,
        }

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        start_ts = time.monotonic()
        first_token_ts: float | None = None
        tokens: int = 0
        chunks: list[str] = []

        # Tracks when the token rate last exceeded the stall threshold
        last_good_rate_ts: float = start_ts

        try:
            logger.debug(
                "ollama.generate.start",
                model=model,
                prompt_len=len(prompt),
                timeout=hard_timeout,
            )

            async def _stream() -> str:
                nonlocal first_token_ts, tokens, last_good_rate_ts

                async for chunk in await self._async_client.chat(
                    model=model,
                    messages=messages,
                    stream=True,
                    options=options,
                    **({"format": format} if format else {}),
                ):
                    content_piece: str = chunk.get("message", {}).get("content", "")
                    if content_piece:
                        now = time.monotonic()
                        if first_token_ts is None:
                            first_token_ts = now
                            logger.debug(
                                "ollama.generate.first_token",
                                model=model,
                                ttft_ms=round((now - start_ts) * 1000),
                            )
                        tokens += len(content_piece.split())  # rough token count
                        elapsed = now - start_ts
                        rate = tokens / elapsed if elapsed > 0 else 0.0

                        # Watchdog: track when rate was last acceptable
                        if rate >= _STALL_MIN_RATE:
                            last_good_rate_ts = now
                        elif (now - last_good_rate_ts) > _STALL_WINDOW_SECONDS:
                            raise OllamaStalledException(
                                elapsed_seconds=elapsed,
                                tokens_so_far=tokens,
                            )
                        chunks.append(content_piece)

                return "".join(chunks)

            result = await asyncio.wait_for(_stream(), timeout=hard_timeout)

            elapsed = time.monotonic() - start_ts
            rate = tokens / elapsed if elapsed > 0 else 0.0
            logger.info(
                "ollama.generate.done",
                model=model,
                tokens=tokens,
                elapsed_s=round(elapsed, 2),
                token_rate=round(rate, 2),
                ttft_ms=(
                    round((first_token_ts - start_ts) * 1000) if first_token_ts else None
                ),
            )
            return result

        except asyncio.TimeoutError as exc:
            raise OllamaConnectionError(
                f"Ollama request timed out after {hard_timeout}s"
            ) from exc
        except OllamaStalledException:
            raise  # propagate as-is; caller handles fallback
        except self._ollama.ResponseError as exc:
            if "model" in str(exc).lower() and "not found" in str(exc).lower():
                raise OllamaModelNotFoundError(
                    f"Model '{model}' is not available in Ollama. "
                    f"Run: ollama pull {model}"
                ) from exc
            raise OllamaConnectionError(f"Ollama API error: {exc}") from exc
        except Exception as exc:
            raise OllamaConnectionError(f"Unexpected Ollama error: {exc}") from exc

    async def embed(self, model: str, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.

        Checks the EmbeddingCache before calling Ollama.  On a cache miss the
        vector is computed and then stored for future requests.

        Args:
            model: Embedding model name (e.g., "nomic-embed-text")
            text: Text to embed

        Returns:
            List of floats representing the embedding vector.
        """
        # Cache read — avoids redundant Ollama calls for identical (model, text)
        from app.services.cache_service import get_embedding_cache
        cache = get_embedding_cache()
        if cache is not None:
            cached = await cache.get(model, text)
            if cached is not None:
                return cached

        try:
            response = await self._async_client.embeddings(model=model, prompt=text)
            embedding: list[float] = response["embedding"]
        except self._ollama.ResponseError as exc:
            if "model" in str(exc).lower():
                raise OllamaModelNotFoundError(
                    f"Embedding model '{model}' not found. Run: ollama pull {model}"
                ) from exc
            raise OllamaConnectionError(f"Embedding error: {exc}") from exc
        except Exception as exc:
            raise OllamaConnectionError(f"Unexpected embedding error: {exc}") from exc

        # Cache write — store for subsequent identical requests
        if cache is not None:
            await cache.put(model, text, embedding)

        return embedding

    async def embed_batch(self, model: str, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts, serving cache hits without calling Ollama.

        For each text:
        1. Check the EmbeddingCache.
        2. Call Ollama only for cache-miss texts (concurrently).
        3. Fill the cache for each newly computed vector.
        """
        from app.services.cache_service import get_embedding_cache
        cache = get_embedding_cache()

        if cache is None:
            # No cache available — fall back to simple concurrent embedding.
            tasks = [self.embed(model, text) for text in texts]
            return await asyncio.gather(*tasks)

        # Phase 1: resolve cache hits
        results: list[list[float] | None] = [None] * len(texts)
        miss_indices: list[int] = []

        for i, text in enumerate(texts):
            cached = await cache.get(model, text)
            if cached is not None:
                results[i] = cached
            else:
                miss_indices.append(i)

        # Phase 2: embed only the misses concurrently (bypassing embed() cache
        # layer to avoid double-checking the same entries)
        if miss_indices:
            miss_texts = [texts[i] for i in miss_indices]
            miss_tasks = [
                self._embed_uncached(model, text) for text in miss_texts
            ]
            miss_vectors: list[list[float]] = await asyncio.gather(*miss_tasks)

            # Phase 3: back-fill results and populate the cache
            for idx, vector in zip(miss_indices, miss_vectors):
                results[idx] = vector
                await cache.put(model, texts[idx], vector)

        # All slots must be filled at this point
        return [v for v in results if v is not None]

    async def _embed_uncached(self, model: str, text: str) -> list[float]:
        """
        Call Ollama directly without touching the cache.

        Used internally by ``embed_batch`` to avoid redundant cache reads when
        we already know the entry is a miss.
        """
        try:
            response = await self._async_client.embeddings(model=model, prompt=text)
            return response["embedding"]
        except self._ollama.ResponseError as exc:
            if "model" in str(exc).lower():
                raise OllamaModelNotFoundError(
                    f"Embedding model '{model}' not found. Run: ollama pull {model}"
                ) from exc
            raise OllamaConnectionError(f"Embedding error: {exc}") from exc
        except Exception as exc:
            raise OllamaConnectionError(f"Unexpected embedding error: {exc}") from exc


# Module-level singleton for convenience
_client: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    """Return (or create) the module-level Ollama client singleton."""
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client
