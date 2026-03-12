"""
Async Ollama HTTP client.

Wraps the ollama Python SDK with:
- Async support
- Retry logic via tenacity
- Structured error mapping to domain exceptions
- Connection health check
"""

from __future__ import annotations

import asyncio
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
)

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
    ) -> str:
        """
        Generate a completion from an Ollama model.

        Args:
            model: Ollama model name (e.g., "qwen3:8b")
            prompt: The user prompt
            system: Optional system message
            temperature: Sampling temperature (overrides config default)
            num_ctx: Context window size (overrides config default)
            format: Response format hint, e.g., "json"

        Returns:
            The generated text content as a string.
        """
        options: dict[str, Any] = {
            "temperature": temperature or settings.ollama.temperature,
            "num_ctx": num_ctx or settings.ollama.num_ctx,
        }

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            logger.debug("ollama.generate.start", model=model, prompt_len=len(prompt))
            response = await asyncio.wait_for(
                self._async_client.chat(
                    model=model,
                    messages=messages,
                    options=options,
                    **({"format": format} if format else {}),
                ),
                timeout=settings.ollama.timeout_seconds,
            )
            content: str = response["message"]["content"]
            logger.debug("ollama.generate.done", model=model, response_len=len(content))
            return content

        except asyncio.TimeoutError as exc:
            raise OllamaConnectionError(
                f"Ollama request timed out after {settings.ollama.timeout_seconds}s"
            ) from exc
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

        Args:
            model: Embedding model name (e.g., "nomic-embed-text")
            text: Text to embed

        Returns:
            List of floats representing the embedding vector.
        """
        try:
            response = await self._async_client.embeddings(model=model, prompt=text)
            embedding: list[float] = response["embedding"]
            return embedding
        except self._ollama.ResponseError as exc:
            if "model" in str(exc).lower():
                raise OllamaModelNotFoundError(
                    f"Embedding model '{model}' not found. Run: ollama pull {model}"
                ) from exc
            raise OllamaConnectionError(f"Embedding error: {exc}") from exc
        except Exception as exc:
            raise OllamaConnectionError(f"Unexpected embedding error: {exc}") from exc

    async def embed_batch(self, model: str, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts concurrently."""
        tasks = [self.embed(model, text) for text in texts]
        return await asyncio.gather(*tasks)


# Module-level singleton for convenience
_client: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    """Return (or create) the module-level Ollama client singleton."""
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client
