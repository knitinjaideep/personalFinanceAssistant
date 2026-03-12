"""
Model router — maps task types to configured Ollama model names.

This allows different models to be used for different tasks without
changing application code. All model assignments live in config.py.

Usage:
    router = ModelRouter()
    model = router.for_classification()
    response = await client.generate(model=model, prompt=...)
"""

from __future__ import annotations

from enum import Enum

from app.config import settings
from app.ollama.client import OllamaClient, get_ollama_client


class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    ANALYSIS = "analysis"
    CHAT = "chat"
    EMBEDDING = "embedding"


class ModelRouter:
    """
    Routes task types to the appropriate Ollama model.

    Reads configuration from settings so models can be changed
    per-environment via environment variables without code changes.
    """

    def __init__(self, client: OllamaClient | None = None) -> None:
        self._client = client or get_ollama_client()
        self._task_model_map: dict[TaskType, str] = {
            TaskType.CLASSIFICATION: settings.ollama.classification_model,
            TaskType.EXTRACTION: settings.ollama.extraction_model,
            TaskType.ANALYSIS: settings.ollama.analysis_model,
            TaskType.CHAT: settings.ollama.chat_model,
            TaskType.EMBEDDING: settings.ollama.embedding_model,
        }

    def model_for(self, task: TaskType) -> str:
        """Return the configured model name for a given task type."""
        return self._task_model_map[task]

    def for_classification(self) -> str:
        return self._task_model_map[TaskType.CLASSIFICATION]

    def for_extraction(self) -> str:
        return self._task_model_map[TaskType.EXTRACTION]

    def for_analysis(self) -> str:
        return self._task_model_map[TaskType.ANALYSIS]

    def for_chat(self) -> str:
        return self._task_model_map[TaskType.CHAT]

    def for_embedding(self) -> str:
        return self._task_model_map[TaskType.EMBEDDING]

    async def generate(
        self,
        task: TaskType,
        prompt: str,
        system: str | None = None,
        format: str | None = None,
    ) -> str:
        """Convenience method: route task → model → generate."""
        model = self.model_for(task)
        return await self._client.generate(
            model=model, prompt=prompt, system=system, format=format
        )

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding using the configured embedding model."""
        model = self.model_for(TaskType.EMBEDDING)
        return await self._client.embed(model=model, text=text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self.model_for(TaskType.EMBEDDING)
        return await self._client.embed_batch(model=model, texts=texts)


# Module-level singleton
_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
