import os
from fastapi import APIRouter
from schemas.dispute_schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy",
        version=os.getenv("APP_VERSION", "1.0.0"),
        environment=os.getenv("ENVIRONMENT", "development"),
        database=os.getenv("DATABASE_URL", "sqlite").split("://")[0],
        llm_provider="groq",
        llm_model=os.getenv("LLM_MODEL", "llama3-8b-8192"),
    )
