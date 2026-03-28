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

# Vision layer imports (Phase 4)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vision_service.core.vision_engine import VisionEngine, VisionBackend
from vision_service.api.vision_router import router as vision_router

# Analytics layer (Phase 5)
from analytics_service.core.analytics_engine import AnalyticsEngine
from analytics_service.api.analytics_router import router as analytics_router

# Orchestration layer (Phase 6)
from orchestration_service.core.fleet_models import RobotAgent
from orchestration_service.core.scheduler import RobotFleet
from orchestration_service.api.fleet_router import router as fleet_router

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

    app.state.vision_engine = VisionEngine(
        backend=VisionBackend(os.getenv("AUROLAB_VISION_BACKEND", "mock")),
        groq_api_key=os.getenv("GROQ_API_KEY"),
    )
    app.state.current_lab_state = None

    app.state.analytics_engine = AnalyticsEngine()
    app.state.analytics_store = {}        # protocol_id → EfficiencyReport
    app.state.execution_plan_store = {}   # plan_id → ExecutionPlan

    # Default fleet: 2 robots — scale via POST /api/v1/fleet/robots
    app.state.robot_fleet = RobotFleet(robots=[
        RobotAgent(robot_id="robot_01", name="AuroBot Alpha", location="lab_bench_1"),
        RobotAgent(robot_id="robot_02", name="AuroBot Beta",  location="lab_bench_2"),
    ])
    app.state.current_fleet_schedule = None

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
    app.include_router(vision_router)
    app.include_router(analytics_router)
    app.include_router(fleet_router)

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