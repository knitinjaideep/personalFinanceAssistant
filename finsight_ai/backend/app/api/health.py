"""Health check endpoint."""

from fastapi import APIRouter

from app.services.llm import check_health as check_ollama

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
async def health():
    """Health check — app + Ollama status."""
    ollama = await check_ollama()
    return {
        "status": "ok",
        "ollama": ollama,
    }
