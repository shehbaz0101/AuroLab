"""
conftest.py

Shared pytest fixtures for all AuroLab test suites.
Place this file in the tests/ directory (or project root for global scope).

Fixtures provided:
  tmp_db_path          — temporary SQLite path (auto-cleaned)
  sample_protocol      — minimal GeneratedProtocol dict
  sample_plan          — minimal ExecutionPlan dict
  sample_telemetry     — SimulationResult telemetry dict
  sample_commands      — list of command dicts
  minimal_parsed_doc   — ParsedDocument for chunker tests
  mock_rag_engine      — mocked AurolabRAGEngine
  mock_llm_engine      — mocked AurolabLLMEngine with Groq patched
  async_client         — httpx AsyncClient wired to create_app()
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db_path(tmp_path) -> str:
    return str(tmp_path / "test_telemetry.db")


# ---------------------------------------------------------------------------
# Protocol / plan data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_protocol() -> dict:
    return {
        "protocol_id":    "test-proto-fixture",
        "title":          "BCA Protein Assay",
        "description":    "Standard BCA assay for protein quantification.",
        "steps": [
            {"step_number": 1, "instruction": "Pipette 50 µL BCA reagent from slot 1 well A1 to slot 2 well B1"},
            {"step_number": 2, "instruction": "Incubate at 37°C for 30 minutes"},
            {"step_number": 3, "instruction": "Read absorbance at 562 nm"},
        ],
        "reagents":  ["BCA reagent", "BSA standard", "96-well plate"],
        "equipment": ["plate reader", "incubator", "1.5 mL tubes"],
        "safety_level": "safe",
        "safety_notes": [],
        "sources_used": [],
        "confidence_score": 0.9,
        "generation_ms": 100.0,
        "model_used": "test",
    }


@pytest.fixture
def sample_commands() -> list[dict]:
    return [
        {"command_type": "home",            "command_index": 0, "protocol_step_ref": 0},
        {"command_type": "pick_up_tip",     "command_index": 1, "protocol_step_ref": 1, "tip_rack_slot": 11},
        {"command_type": "aspirate",        "command_index": 2, "protocol_step_ref": 1,
         "volume_ul": 50.0, "source": {"deck_slot": 1}, "flow_rate_ul_s": 150.0},
        {"command_type": "dispense",        "command_index": 3, "protocol_step_ref": 1,
         "volume_ul": 50.0, "destination": {"deck_slot": 2}},
        {"command_type": "drop_tip",        "command_index": 4, "protocol_step_ref": 1},
        {"command_type": "incubate",        "command_index": 5, "protocol_step_ref": 2,
         "duration_s": 1800, "temperature_celsius": 37.0, "slot": 7},
        {"command_type": "read_absorbance", "command_index": 6, "protocol_step_ref": 3,
         "wavelength_nm": 562, "slot": 3},
        {"command_type": "home",            "command_index": 7, "protocol_step_ref": 3},
    ]


@pytest.fixture
def sample_plan(sample_commands) -> dict:
    return {
        "plan_id":        "plan-fixture-001",
        "protocol_id":    "test-proto-fixture",
        "protocol_title": "BCA Protein Assay",
        "estimated_mins": 45.0,
        "estimated_total_duration_s": 2700.0,
        "status": "sim_passed",
        "command_count": len(sample_commands),
        "command_breakdown": {"home": 2, "pick_up_tip": 1, "aspirate": 1,
                               "dispense": 1, "drop_tip": 1, "incubate": 1,
                               "read_absorbance": 1},
        "validation_errors": 0,
        "sim_passed": True,
        "is_executable": True,
        "commands": sample_commands,
    }


@pytest.fixture
def sample_telemetry() -> dict:
    return {
        "commands_executed":         8,
        "tip_changes":               1,
        "total_volume_aspirated_ul": 50.0,
        "total_volume_dispensed_ul": 48.0,
        "total_distance_mm":         1200.0,
        "warnings":                  [],
        "physics_engine":            "mock_fallback",
    }


# ---------------------------------------------------------------------------
# PDF parser fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_parsed_doc():
    """Minimal ParsedDocument for chunker tests — no heavy imports at module level."""
    from services.translation_service.core.pdf_parser import (
        ParsedDocument, ContentBlock, BlockType,
    )
    blocks = [
        ContentBlock(BlockType.HEADING,   "1. Materials", page_number=1, font_size=14, is_bold=True),
        ContentBlock(BlockType.TEXT,
                     "10 mM Tris-HCl pH 8.0, 150 mM NaCl. Prepare fresh before use.",
                     page_number=1),
        ContentBlock(BlockType.LIST_ITEM, "- 1.5 mL microcentrifuge tubes (sterile)", page_number=1),
        ContentBlock(BlockType.HEADING,   "2. Protocol", page_number=2, font_size=14, is_bold=True),
        ContentBlock(BlockType.TEXT,
                     "Pipette 50 µL of sample. Centrifuge at 13,000 × g for 10 min. Aspirate supernatant.",
                     page_number=2),
        ContentBlock(BlockType.TABLE,
                     "Step | Duration | Temp\n1 | 10 min | 4°C\n2 | 5 min | RT",
                     page_number=2,
                     table_data=[["Step","Duration","Temp"],["1","10 min","4°C"],["2","5 min","RT"]]),
    ]
    return ParsedDocument(
        source_path="test_protocol.pdf",
        sha256=hashlib.sha256(b"test").hexdigest(),
        page_count=2,
        title="BCA Protein Assay Protocol",
        authors=[],
        doc_type="protocol",
        blocks=blocks,
        raw_text=" ".join(b.content for b in blocks),
        parse_strategy="pymupdf",
    )


# ---------------------------------------------------------------------------
# Mocked engine fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_rag_engine():
    engine = MagicMock()
    result = MagicMock()
    result.chunks = []
    result.retrieval_ms = 45.0
    engine.retrieve.return_value = result
    engine.collection_stats.return_value = {
        "collection": "aurolab_protocols",
        "total_chunks": 0,
        "embed_model": "all-MiniLM-L6-v2",
        "hyde_enabled": False,
        "reranker_enabled": False,
    }
    engine.ingest_chunks.return_value = {"added": 5, "skipped": 0}
    return engine


@pytest.fixture
def mock_llm_engine(mock_rag_engine):
    valid_json = json.dumps({
        "title":       "BCA Protein Assay",
        "description": "Standard BCA assay for protein quantification.",
        "reagents":    ["BCA Reagent A", "BSA standard"],
        "equipment":   ["96-well plate", "plate reader"],
        "steps": [
            {"step_number": 1, "instruction": "Pipette 25 µL into each well. [SOURCE_1]",
             "duration_seconds": None, "temperature_celsius": None,
             "volume_ul": 25.0, "citations": ["SOURCE_1"], "safety_note": None},
            {"step_number": 2, "instruction": "Incubate at 37°C for 30 min. [SOURCE_1]",
             "duration_seconds": 1800, "temperature_celsius": 37.0,
             "volume_ul": None, "citations": ["SOURCE_1"], "safety_note": None},
        ],
        "safety_notes":     [],
        "confidence_score": 0.88,
    })

    with patch("services.translation_service.core.llm_engine.Groq") as MockGroq:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = valid_json
        MockGroq.return_value.chat.completions.create.return_value = mock_resp

        from services.translation_service.core.llm_engine import AurolabLLMEngine
        engine = AurolabLLMEngine(
            groq_api_key="test_key",
            rag_engine=mock_rag_engine,
        )
        yield engine


# ---------------------------------------------------------------------------
# Async HTTP client fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client(mock_llm_engine, mock_rag_engine):
    """Full FastAPI app wired with mocked engines — no real API calls."""
    from services.translation_service.main import create_app

    app = create_app()

    # Inject mocks — skips heavy lifespan init
    app.state.rag_engine       = mock_rag_engine
    app.state.llm_engine       = mock_llm_engine
    app.state.registry         = MagicMock()
    app.state.registry.get.return_value = None
    app.state.protocol_registry = {}
    app.state.execution_plan_store = {}
    app.state.analytics_store  = {}
    app.state.analytics_engine = MagicMock()
    app.state.vision_engine    = MagicMock()
    app.state.current_lab_state = None
    app.state.robot_fleet      = MagicMock()
    app.state.current_fleet_schedule = None
    app.state.telemetry_store  = MagicMock()
    app.state.rl_optimiser     = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Pytest markers registration (used by pytest.ini)
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with -m 'not slow')")
    config.addinivalue_line("markers", "integration: marks end-to-end integration tests")
    config.addinivalue_line("markers", "pybullet: marks tests that require pybullet installed")
    config.addinivalue_line("markers", "live_api: marks tests that hit real external APIs")