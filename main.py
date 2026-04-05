"""
main.py — AuroLab Root Entry Point

Place this file in AuroLab/ (project root).
Run with:
    uvicorn main:app --host 0.0.0.0 --port 8080 --reload

OR use the original translation_service entry point:
    uvicorn services.translation_service.main:app --port 8080 --reload

This file wraps the translation service and registers ALL routers
including Phase 8+ extensions from api/extensions_router.py
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import structlog
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader

log = structlog.get_logger(__name__)

# ── Optional API key auth ─────────────────────────────────────────────────────
_API_KEY        = os.getenv("AUROLAB_API_KEY", "")
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(_API_KEY_HEADER)):
    if not _API_KEY:
        return  # auth disabled
    if api_key != _API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("aurolab_startup", version="2.0.0")
    t0 = time.perf_counter()

    # ── RAG + LLM ─────────────────────────────────────────────────────────
    try:
        from services.translation_service.core.rag_engine import AurolabRAGEngine
        from services.translation_service.core.llm_engine import AurolabLLMEngine
        from services.translation_service.core.registry   import DocumentRegistry

        app.state.registry   = DocumentRegistry(
            os.getenv("REGISTRY_PATH", "./data/registry.json"))
        app.state.rag_engine = AurolabRAGEngine(
            persist_path=os.getenv("CHROMA_PERSIST", "./data/chroma"),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            use_hyde=True, use_reranker=True)
        app.state.llm_engine = AurolabLLMEngine(
            rag_engine=app.state.rag_engine,
            groq_api_key=os.getenv("GROQ_API_KEY", ""))
        chunks = app.state.rag_engine.collection_stats().get("total_chunks", 0)
        log.info("rag_llm_ready", chunks=chunks)
    except Exception as e:
        log.error("rag_llm_failed", error=str(e))
        app.state.rag_engine = None
        app.state.llm_engine = None

    # ── Protocol manager ──────────────────────────────────────────────────
    try:
        from services.translation_service.core.protocol_manager import ProtocolManager
        app.state.protocol_manager  = ProtocolManager("./data/protocols.db")
        app.state.protocol_registry = {}
        log.info("protocol_manager_ready",
                 protocols=app.state.protocol_manager.count())
    except Exception as e:
        log.error("protocol_manager_failed", error=str(e))
        app.state.protocol_manager  = None
        app.state.protocol_registry = {}

    # ── Execution / Physics ───────────────────────────────────────────────
    try:
        from services.execution_service.core.orchestrator import execute_protocol
        app.state.execute_fn = execute_protocol
        log.info("execution_ready")
    except Exception as e:
        log.warning("execution_unavailable", error=str(e))
        app.state.execute_fn = None

    # ── Vision ────────────────────────────────────────────────────────────
    try:
        from services.vision_service.core.vision_engine import VisionEngine, VisionBackend
        backend_str = os.getenv("AUROLAB_VISION_BACKEND", "mock").upper()
        backend     = getattr(VisionBackend, backend_str, VisionBackend.MOCK)
        app.state.vision_engine     = VisionEngine(backend=backend)
        app.state.current_lab_state = None
        log.info("vision_ready", backend=backend_str)
    except Exception as e:
        log.warning("vision_unavailable", error=str(e))
        app.state.vision_engine = None

    # ── Analytics ─────────────────────────────────────────────────────────
    try:
        from services.analytics_service.core.analytics_engine import AnalyticsEngine
        app.state.analytics_engine = AnalyticsEngine()
        app.state.analytics_store  = {}
        log.info("analytics_ready")
    except Exception as e:
        log.warning("analytics_unavailable", error=str(e))
        app.state.analytics_engine = None

    # ── Fleet ─────────────────────────────────────────────────────────────
    try:
        from services.orchestration_service.core.fleet_models import RobotAgent
        from services.orchestration_service.core.scheduler    import RobotFleet
        app.state.robot_fleet = RobotFleet(robots=[
            RobotAgent(robot_id=f"robot_0{i}", name=f"OT-2 Unit {i}", location=f"Bay {i}")
            for i in range(1, 5)
        ])
        app.state.current_fleet_schedule = None
        log.info("fleet_ready", robots=4)
    except Exception as e:
        log.warning("fleet_unavailable", error=str(e))
        app.state.robot_fleet = None

    # ── RL ────────────────────────────────────────────────────────────────
    try:
        from services.rl_service.core.telemetry_store import TelemetryStore
        from services.rl_service.core.rl_engine       import ProtocolOptimiser, RewardModel
        app.state.telemetry_store = TelemetryStore(
            os.getenv("TELEMETRY_DB", "./data/telemetry.db"))
        app.state.rl_optimiser = ProtocolOptimiser(
            store=app.state.telemetry_store,
            reward_model=RewardModel())
        log.info("rl_ready")
    except Exception as e:
        log.warning("rl_unavailable", error=str(e))
        app.state.telemetry_store = None
        app.state.rl_optimiser    = None

    elapsed = round((time.perf_counter() - t0) * 1000)
    log.info("aurolab_ready", startup_ms=elapsed)
    yield
    log.info("aurolab_shutdown")


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="AuroLab",
        description="Autonomous Physical AI — NL to validated robotic protocols",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request timing
    @app.middleware("http")
    async def add_timing(request: Request, call_next):
        t0   = time.perf_counter()
        resp = await call_next(request)
        resp.headers["X-Response-Time-Ms"] = str(round((time.perf_counter() - t0) * 1000))
        return resp

    # ── Register routers safely ────────────────────────────────────────────
    def _try_router(import_path: str, attr: str = "router"):
        try:
            mod    = __import__(import_path, fromlist=[attr])
            router = getattr(mod, attr)
            app.include_router(router)
            log.debug("router_registered", path=import_path)
            return True
        except Exception as e:
            log.warning("router_unavailable", path=import_path, error=str(e))
            return False

    # Core translation service routes
    _try_router("services.translation_service.api.routes")

    # Execution, vision, analytics, fleet, RL
    _try_router("services.execution_service.api.execution_router")
    _try_router("services.vision_service.api.vision_router")
    _try_router("services.analytics_service.api.analytics_router")
    _try_router("services.orchestration_service.api.fleet_router")
    _try_router("services.rl_service.api.rl_router")

    # Phase 8+ extensions
    _try_router("api.extensions_router")

    # ── Health + root ──────────────────────────────────────────────────────
    @app.get("/health", tags=["Observability"])
    async def health():
        rag_stats = {}
        if getattr(app.state, "rag_engine", None):
            try:
                rag_stats = app.state.rag_engine.collection_stats()
            except Exception:
                pass

        ext_status = {}
        try:
            from api.extensions_router import (
                _HAS_OT2, _HAS_DIFF, _HAS_INV, _HAS_TMPL,
                _HAS_REPORT, _HAS_WF, _HAS_OPT, _HAS_REFLECT,
                _HAS_BUNDLE, _HAS_BATCH, _HAS_NOTES)
            ext_status = {
                "opentrons": _HAS_OT2,    "diff":      _HAS_DIFF,
                "inventory": _HAS_INV,    "templates": _HAS_TMPL,
                "report":    _HAS_REPORT, "workflows": _HAS_WF,
                "optimizer": _HAS_OPT,    "reflection":_HAS_REFLECT,
                "bundle":    _HAS_BUNDLE, "batch":     _HAS_BATCH,
                "notes":     _HAS_NOTES,
            }
        except Exception:
            pass

        return {
            "status":      "ok",
            "version":     "2.0.0",
            "phase":       "8+",
            "sim_mode":    os.getenv("AUROLAB_SIM_MODE", "pybullet"),
            "auth_enabled":bool(_API_KEY),
            "rag":         rag_stats,
            "extensions":  ext_status,
            "services": {
                "rag_llm":   getattr(app.state, "rag_engine",       None) is not None,
                "execution": getattr(app.state, "execute_fn",       None) is not None,
                "vision":    getattr(app.state, "vision_engine",    None) is not None,
                "analytics": getattr(app.state, "analytics_engine", None) is not None,
                "fleet":     getattr(app.state, "robot_fleet",      None) is not None,
                "rl":        getattr(app.state, "rl_optimiser",     None) is not None,
            },
        }

    @app.get("/", tags=["Observability"])
    async def root():
        return {
            "name": "AuroLab", "version": "2.0.0", "phase": "8+",
            "docs": "/docs", "health": "/health",
            "pages": 19, "endpoints": 75,
        }

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=os.getenv("ENV", "prod") == "dev",
        log_config=None,
    )