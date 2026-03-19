"""
Ollama LLM client — thin wrapper over httpx for local model inference.

No langchain, no langgraph. Just HTTP calls to Ollama.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from app.config import settings
from app.domain.errors import OllamaConnectionError, OllamaModelNotFoundError, LLMResponseParseError

logger = structlog.get_logger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.ollama.base_url,
            timeout=httpx.Timeout(settings.ollama.timeout_seconds),
        )
    return _client


async def generate(
    prompt: str,
    model: str | None = None,
    system: str | None = None,
    temperature: float | None = None,
    format_json: bool = False,
) -> str:
    """Generate text from the local Ollama LLM.

    Args:
        prompt: The user prompt.
        model: Model name override (defaults to chat_model from config).
        system: Optional system prompt.
        temperature: Override temperature.
        format_json: If True, request JSON output format.

    Returns:
        The generated text response.
    """
    client = _get_client()
    model = model or settings.ollama.chat_model

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature if temperature is not None else settings.ollama.temperature,
            "num_ctx": settings.ollama.num_ctx,
        },
    }
    if system:
        payload["system"] = system
    if format_json:
        payload["format"] = "json"

    try:
        response = await client.post("/api/generate", json=payload)
        if response.status_code == 404:
            raise OllamaModelNotFoundError(f"Model '{model}' not found in Ollama")
        response.raise_for_status()
        data = response.json()
        return data.get("response", "")
    except httpx.ConnectError as exc:
        raise OllamaConnectionError(f"Cannot connect to Ollama at {settings.ollama.base_url}") from exc
    except OllamaModelNotFoundError:
        raise
    except httpx.HTTPStatusError as exc:
        raise OllamaConnectionError(f"Ollama returned {exc.response.status_code}") from exc


async def generate_json(
    prompt: str,
    model: str | None = None,
    system: str | None = None,
) -> dict[str, Any]:
    """Generate and parse JSON from the LLM."""
    raw = await generate(prompt, model=model, system=system, format_json=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMResponseParseError(f"Failed to parse LLM JSON: {raw[:200]}") from exc


async def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Generate embeddings for a list of texts.

    Returns:
        List of embedding vectors.
    """
    client = _get_client()
    model = model or settings.ollama.embedding_model

    try:
        response = await client.post("/api/embed", json={
            "model": model,
            "input": texts,
        })
        response.raise_for_status()
        data = response.json()
        return data.get("embeddings", [])
    except httpx.ConnectError as exc:
        raise OllamaConnectionError(f"Cannot connect to Ollama at {settings.ollama.base_url}") from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaConnectionError(f"Ollama embed returned {exc.response.status_code}") from exc


async def check_health() -> dict[str, Any]:
    """Check if Ollama is running and models are available."""
    client = _get_client()
    try:
        response = await client.get("/api/tags")
        response.raise_for_status()
        data = response.json()
        models = [m["name"] for m in data.get("models", [])]
        return {
            "status": "ok",
            "models": models,
            "chat_model_available": settings.ollama.chat_model in models,
            "embed_model_available": settings.ollama.embedding_model in models,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
