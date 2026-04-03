"""
services/translation_service/main.py

AuroLab — Autonomous Physical AI Lab Automation System.
Production FastAPI application. Entry point for all services.

Start with:
    uvicorn services.translation_service.main:app --host 0.0.0.0 --port 8080 --reload

Environment variables:
    GROQ_API_KEY          — required for protocol generation
    AUROLAB_SIM_MODE      — mock | pybullet | live  (default: pybullet)
    AUROLAB_VISION_BACKEND— mock | groq | llava     (default: mock)
    CHROMA_PERSIST        — ChromaDB path           (default: ./data/chroma)
    REGISTRY_PATH         — document registry       (default: ./data/registry.json)
    TELEMETRY_DB          — SQLite telemetry DB     (default: ./data/telemetry.db)
    ENV                   — dev | prod              (default: prod)
    LOG_LEVEL             — DEBUG|INFO|WARNING      (default: INFO)
    PORT                  — HTTP port               (default: 8080)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

# Shared infrastructure
from shared.logger import configure_logging
from shared.middleware import add_middleware

# Translation service (relative — same package)
from .api.generate_router import router as generate_router
from .api.upload_router import router as upload_router
from .core.llm_engine import AurolabLLMEngine
from .core.rag_engine import AurolabRAGEngine
from .core.registry import DocumentRegistry

# Cross-service imports (absolute — match your services/ layout)
from services.execution_service.api.execution_router import router as execution_router
from services.vision_service.core.vision_engine import VisionEngine, VisionBackend
from services.vision_service.api.vision_router import router as vision_router
from services.analytics_service.core.analytics_engine import AnalyticsEngine
from services.analytics_service.api.analytics_router import router as analytics_router
from services.orchestration_service.core.fleet_models import RobotAgent
from services.orchestration_service.core.scheduler import RobotFleet
from services.orchestration_service.api.fleet_router import router as fleet_router
from services.rl_service.core.telemetry_store import TelemetryStore
from services.rl_service.core.rl_engine import ProtocolOptimiser, RewardModel
from services.rl_service.api.rl_router import router as rl_router

# Phase 8+ extensions — all new modules wired to REST
try:
    from api.extensions_router import router as extensions_router
    _HAS_EXTENSIONS = True
except ImportError as _ext_err:
    _HAS_EXTENSIONS = False
    import structlog as _sl
    _sl.get_logger(__name__).warning("extensions_router_unavailable", error=str(_ext_err))

# Configure structured logging at import time
configure_logging()
log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — initialise all singletons once at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("aurolab_starting",
             sim_mode=os.getenv("AUROLAB_SIM_MODE", "pybullet"),
             vision=os.getenv("AUROLAB_VISION_BACKEND", "mock"),
             env=os.getenv("ENV", "prod"))

    # Translation / RAG layer
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
    app.state.protocol_registry = {}
    # Protocol manager for extensions router (get/list protocols)
    try:
        from translation_service.core.protocol_manager import ProtocolManager
        app.state.protocol_manager = ProtocolManager()
    except Exception:
        app.state.protocol_manager = None

    # Vision layer
    app.state.vision_engine = VisionEngine(
        backend=VisionBackend(os.getenv("AUROLAB_VISION_BACKEND", "mock")),
        groq_api_key=os.getenv("GROQ_API_KEY"),
    )
    app.state.current_lab_state = None

    # Analytics layer
    app.state.analytics_engine = AnalyticsEngine()
    app.state.analytics_store = {}
    app.state.execution_plan_store = {}

    # Fleet orchestration
    app.state.robot_fleet = RobotFleet(robots=[
        RobotAgent(robot_id="robot_01", name="AuroBot Alpha", location="lab_bench_1"),
        RobotAgent(robot_id="robot_02", name="AuroBot Beta",  location="lab_bench_2"),
    ])
    app.state.current_fleet_schedule = None

    # RL optimisation
    app.state.telemetry_store = TelemetryStore(
        db_path=os.getenv("TELEMETRY_DB", "./data/telemetry.db")
    )
    app.state.rl_optimiser = ProtocolOptimiser(
        store=app.state.telemetry_store,
        reward_model=RewardModel(),
    )

    log.info("aurolab_ready",
             rag_chunks=app.state.rag_engine.collection_stats().get("total_chunks", 0))
    yield

    log.info("aurolab_shutdown")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="AuroLab",
        description=(
            "Autonomous Physical AI Lab Automation System. "
            "Converts natural language lab instructions into validated robotic protocols "
            "using RAG, LLM generation, PyBullet physics simulation, "
            "multi-robot orchestration, and RL-based optimisation."
        ),
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # AuroLab middleware (logging, error handling, correlation IDs)
    add_middleware(app)

    # Prometheus metrics
    app.mount("/metrics", make_asgi_app())

    # Routers — all services
    app.include_router(upload_router)
    app.include_router(generate_router)
    app.include_router(execution_router)
    app.include_router(vision_router)
    app.include_router(analytics_router)
    app.include_router(fleet_router)
    app.include_router(rl_router)

    # Phase 8+ extensions
    if _HAS_EXTENSIONS:
        app.include_router(extensions_router)
        log.info("extensions_router_registered",
                 routes=len([r for r in extensions_router.routes]))

    @app.get("/health", tags=["Observability"])
    async def health():
        stats = app.state.rag_engine.collection_stats()
        ext_status = {}
        if _HAS_EXTENSIONS:
            try:
                from api.extensions_router import (
                    _HAS_OT2, _HAS_DIFF, _HAS_INV, _HAS_TMPL,
                    _HAS_REPORT, _HAS_WF, _HAS_OPT, _HAS_REFLECT)
                ext_status = {
                    "opentrons": _HAS_OT2, "diff": _HAS_DIFF,
                    "inventory": _HAS_INV, "templates": _HAS_TMPL,
                    "report": _HAS_REPORT, "workflows": _HAS_WF,
                    "optimizer": _HAS_OPT, "reflection": _HAS_REFLECT,
                }
            except Exception:
                pass
        return {
            "status":     "ok",
            "version":    "2.0.0",
            "phase":      "8+",
            "sim_mode":   os.getenv("AUROLAB_SIM_MODE", "pybullet"),
            "rag":        stats,
            "extensions": ext_status,
        }

    @app.get("/", tags=["Observability"])
    async def root():
        return {
            "name":    "AuroLab",
            "version": "2.0.0",
            "docs":    "/docs",
            "health":  "/health",
        }

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "services.translation_service.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=os.getenv("ENV", "prod") == "dev",
        log_config=None,
    )