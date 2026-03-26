"""
aurolab/services/translation_service/main.py

Production FastAPI application for the Translation Service.
Initialises all singletons at startup via lifespan context manager.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .api.generate_router import router as generate_router
from .api.upload_router import router as upload_router
from .core.llm_engine import AurolabLLMEngine
from .core.rag_engine import AurolabRAGEngine
from .core.registry import DocumentRegistry

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise heavy singletons once at startup."""
    log.info("aurolab_starting")

    app.state.registry = DocumentRegistry(
        persist_path=os.getenv("REGISTRY_PATH", "./data/registry.json")
    )

    app.state.rag_engine = AurolabRAGEngine(
        persist_path=os.getenv("CHROMA_PERSIST", "./data/chroma"),
        groq_api_key=os.getenv("GROQ_API_KEY"),
        use_hyde=os.getenv("USE_HYDE", "true").lower() == "true",
        use_reranker=os.getenv("USE_RERANKER", "true").lower() == "true",
    )

    app.state.llm_engine = AurolabLLMEngine(
        groq_api_key=os.getenv("GROQ_API_KEY"),
        rag_engine=app.state.rag_engine,
    )

    app.state.protocol_registry = {}   # protocol_id → GeneratedProtocol (swap for Redis in prod)

    log.info("aurolab_ready")
    yield

    log.info("aurolab_shutdown")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="AuroLab Translation Service",
        description=(
            "Converts natural language lab instructions into validated robotic protocols "
            "using Groq LLMs, RAG over lab literature, and multi-layer safety validation."
        ),
        version="1.3.0",
        lifespan=lifespan,
    )

    # CORS (restrict in production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Routers
    app.include_router(upload_router)
    app.include_router(generate_router)

    # Minimal health check
    @app.get("/health", tags=["Observability"])
    async def health():
        stats = app.state.rag_engine.collection_stats()
        return {"status": "ok", "rag": stats}

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=os.getenv("ENV", "prod") == "dev",
        log_config=None,  # structlog handles logging
    )