"""
tests/test_phase14_15.py

Tests for Phase 1.4 (retrieval eval harness) and Phase 1.5 (RAG-aware generation).
Run with: pytest tests/test_phase14_15.py -v
"""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from services.translation_service.core.llm_engine import (
    AurolabLLMEngine,
    GeneratedProtocol,
    ProtocolStep,
    SafetyLevel,
    _format_context_block,
    _parse_llm_json,
    _pre_generation_safety_check,
    _post_generation_safety_check,
)
from services.translation_service.core.retrieval_eval import (
    EvalDataset,
    EvalHarness,
    EvalQuery,
    _reciprocal_rank,
    _ndcg_at_k,
    _recall_at_k,
    _precision_at_k,
    _hit_rate_at_k,
)
from services.translation_service.core.rag_engine import RetrievedChunk


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chunk(chunk_id: str, text: str = "Centrifuge at 13000 x g for 10 min.", score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        source="bca_protocol.pdf",
        section_title="2. Protocol",
        doc_type="protocol",
        page_start=2,
        page_end=2,
        score=score,
        rank=1,
    )


SAMPLE_VALID_JSON = json.dumps({
    "title": "BCA Protein Assay",
    "description": "Standard BCA assay for protein quantification.",
    "reagents": ["BCA Reagent A", "BCA Reagent B", "BSA standard"],
    "equipment": ["96-well plate", "plate reader", "pipette"],
    "steps": [
        {
            "step_number": 1,
            "instruction": "Pipette 25 µL of each sample into separate wells. [SOURCE_1]",
            "duration_seconds": None,
            "temperature_celsius": None,
            "volume_ul": 25.0,
            "citations": ["SOURCE_1"],
            "safety_note": None,
        },
        {
            "step_number": 2,
            "instruction": "Add 200 µL of BCA working reagent to each well. [SOURCE_1]",
            "duration_seconds": None,
            "temperature_celsius": None,
            "volume_ul": 200.0,
            "citations": ["SOURCE_1"],
            "safety_note": None,
        },
        {
            "step_number": 3,
            "instruction": "Incubate at 37°C for 30 minutes. [SOURCE_2]",
            "duration_seconds": 1800,
            "temperature_celsius": 37.0,
            "volume_ul": None,
            "citations": ["SOURCE_2"],
            "safety_note": None,
        },
    ],
    "safety_notes": [],
    "confidence_score": 0.88,
})


@pytest.fixture
def mock_rag_engine():
    engine = MagicMock()
    result = MagicMock()
    result.chunks = [_make_chunk("abc12345-0001"), _make_chunk("abc12345-0002", score=0.75)]
    result.retrieval_ms = 45.0
    engine.retrieve.return_value = result
    return engine


@pytest.fixture
def mock_llm_engine(mock_rag_engine):
    with patch("services.translation_service.core.llm_engine.Groq") as MockGroq:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = SAMPLE_VALID_JSON
        MockGroq.return_value.chat.completions.create.return_value = mock_resp
        engine = AurolabLLMEngine(
            groq_api_key="test_key",
            rag_engine=mock_rag_engine,
        )
        yield engine


# ---------------------------------------------------------------------------
# Metric unit tests
# ---------------------------------------------------------------------------

class TestMetrics:

    def test_mrr_first_hit(self):
        assert _reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0

    def test_mrr_second_hit(self):
        assert _reciprocal_rank(["x", "a", "c"], {"a"}) == pytest.approx(0.5)

    def test_mrr_no_hit(self):
        assert _reciprocal_rank(["x", "y", "z"], {"a"}) == 0.0

    def test_mrr_multiple_relevant_takes_first(self):
        assert _reciprocal_rank(["x", "a", "b"], {"a", "b"}) == pytest.approx(0.5)

    def test_ndcg_perfect(self):
        # All k retrieved are relevant
        result = _ndcg_at_k(["a", "b"], {"a", "b"}, k=2)
        assert result == pytest.approx(1.0)

    def test_ndcg_zero(self):
        assert _ndcg_at_k(["x", "y"], {"a", "b"}, k=2) == 0.0

    def test_ndcg_partial(self):
        score = _ndcg_at_k(["a", "x"], {"a", "b"}, k=2)
        assert 0.0 < score < 1.0

    def test_recall_full(self):
        assert _recall_at_k(["a", "b", "c"], {"a", "b"}, k=3) == 1.0

    def test_recall_partial(self):
        assert _recall_at_k(["a", "x", "y"], {"a", "b"}, k=3) == pytest.approx(0.5)

    def test_recall_zero(self):
        assert _recall_at_k(["x", "y"], {"a", "b"}, k=3) == 0.0

    def test_precision_at_k(self):
        assert _precision_at_k(["a", "x", "a2"], {"a", "a2"}, k=3) == pytest.approx(2/3)

    def test_hit_rate_true(self):
        assert _hit_rate_at_k(["x", "a", "y"], {"a"}, k=3) == 1.0

    def test_hit_rate_false(self):
        assert _hit_rate_at_k(["x", "y", "z"], {"a"}, k=3) == 0.0

    def test_hit_rate_outside_k(self):
        # relevant chunk is at position 4 but k=3 — should not count
        assert _hit_rate_at_k(["x", "y", "z", "a"], {"a"}, k=3) == 0.0


# ---------------------------------------------------------------------------
# Eval harness tests
# ---------------------------------------------------------------------------

class TestEvalHarness:

    def _make_mock_engine(self, returned_ids: list[str]) -> MagicMock:
        engine = MagicMock()
        chunks = [_make_chunk(cid) for cid in returned_ids]
        result = MagicMock()
        result.chunks = chunks
        engine.retrieve.return_value = result
        engine._use_hyde = True
        engine._use_reranker = True
        return engine

    def test_single_query_perfect_recall(self):
        engine = self._make_mock_engine(["q1c1", "q1c2", "q1c3"])
        harness = EvalHarness(engine)
        dataset = EvalDataset.from_list([{
            "query_id": "q1",
            "question": "how to run BCA assay",
            "relevant_chunk_ids": ["q1c1", "q1c2"],
        }])
        report = harness.run(dataset, k=5, variants=["C_full"])
        v = report.variants[0]
        assert v.mean_recall == pytest.approx(1.0)
        assert v.hit_rate == pytest.approx(1.0)
        assert v.mean_mrr == pytest.approx(1.0)  # first retrieved is relevant

    def test_single_query_no_recall(self):
        engine = self._make_mock_engine(["x1", "x2", "x3"])
        harness = EvalHarness(engine)
        dataset = EvalDataset.from_list([{
            "query_id": "q1",
            "question": "how to run BCA assay",
            "relevant_chunk_ids": ["missing1"],
        }])
        report = harness.run(dataset, k=5, variants=["C_full"])
        v = report.variants[0]
        assert v.mean_recall == 0.0
        assert v.hit_rate == 0.0
        assert v.mean_mrr == 0.0

    def test_multiple_variants_run(self):
        engine = self._make_mock_engine(["c1", "c2"])
        harness = EvalHarness(engine)
        dataset = EvalDataset.from_list([{
            "query_id": "q1",
            "question": "protocol steps",
            "relevant_chunk_ids": ["c1"],
        }])
        report = harness.run(dataset, k=3, variants=["A_dense_only", "B_hybrid", "C_full"])
        assert len(report.variants) == 3
        assert {v.variant for v in report.variants} == {"A_dense_only", "B_hybrid", "C_full"}

    def test_best_variant_selected(self):
        engine = self._make_mock_engine(["c1"])
        harness = EvalHarness(engine)
        dataset = EvalDataset.from_list([{"query_id": "q1", "question": "test", "relevant_chunk_ids": ["c1"]}])
        report = harness.run(dataset, k=3)
        # All variants use the same mock so scores are equal — best_variant should still return one
        assert report.best_variant().variant in {"A_dense_only", "B_hybrid", "C_full"}

    def test_report_to_dict_keys(self):
        engine = self._make_mock_engine(["c1"])
        harness = EvalHarness(engine)
        dataset = EvalDataset.from_list([{"query_id": "q1", "question": "test", "relevant_chunk_ids": ["c1"]}])
        report = harness.run(dataset, k=3, variants=["C_full"])
        d = report.to_dict()
        assert "variants" in d
        assert "best_by_mrr" in d
        variant_d = d["variants"][0]
        for key in ["MRR@k", "NDCG@k", "Recall@k", "HitRate@k", "mean_latency_ms"]:
            assert key in variant_d, f"Missing key: {key}"

    def test_failed_retrieval_handled_gracefully(self):
        engine = MagicMock()
        engine.retrieve.side_effect = RuntimeError("chroma connection error")
        engine._use_hyde = True
        engine._use_reranker = True
        harness = EvalHarness(engine)
        dataset = EvalDataset.from_list([{"query_id": "q1", "question": "test", "relevant_chunk_ids": ["c1"]}])
        report = harness.run(dataset, k=3, variants=["C_full"])
        assert report.variants[0].mean_mrr == 0.0


# ---------------------------------------------------------------------------
# LLM engine unit tests
# ---------------------------------------------------------------------------

class TestLLMEngine:

    def test_format_context_block_populated(self):
        chunks = [_make_chunk("id1", "Pipette 50 µL of sample.")]
        block = _format_context_block(chunks)
        assert 'SOURCE_1' in block
        assert "bca_protocol.pdf" in block
        assert "Pipette 50" in block

    def test_format_context_block_empty(self):
        block = _format_context_block([])
        assert "SOURCE_NONE" in block

    def test_parse_llm_json_clean(self):
        data = _parse_llm_json('{"title": "test", "steps": []}')
        assert data["title"] == "test"

    def test_parse_llm_json_with_fences(self):
        data = _parse_llm_json('```json\n{"title": "test"}\n```')
        assert data["title"] == "test"

    def test_parse_llm_json_with_preamble(self):
        data = _parse_llm_json('Here is the JSON:\n{"title": "test"}')
        assert data["title"] == "test"

    def test_parse_llm_json_raises_on_garbage(self):
        with pytest.raises((ValueError, Exception)):
            _parse_llm_json("This is not JSON at all, sorry")

    def test_pre_safety_check_clean(self):
        level, reason = _pre_generation_safety_check("Perform a BCA assay on 8 samples")
        assert level == SafetyLevel.SAFE
        assert reason is None

    def test_pre_safety_check_blocked(self):
        level, reason = _pre_generation_safety_check("synthesis of nerve agent VX")
        assert level == SafetyLevel.BLOCKED
        assert reason is not None

    def test_post_safety_check_flags_high_concentration(self):
        protocol = GeneratedProtocol(
            protocol_id="test",
            title="Test",
            description="Test protocol",
            steps=[ProtocolStep(
                step_number=1,
                instruction="Add 12 M HCl to the solution carefully.",
                citations=[],
            )],
            confidence_score=0.5,
        )
        result = _post_generation_safety_check(protocol)
        assert result.safety_level == SafetyLevel.WARNING
        assert len(result.safety_notes) > 0

    def test_post_safety_check_clean(self):
        protocol = GeneratedProtocol(
            protocol_id="test",
            title="Test",
            description="Test protocol",
            steps=[ProtocolStep(
                step_number=1,
                instruction="Pipette 50 µL of buffer solution into the tube.",
                citations=[],
            )],
            confidence_score=0.5,
        )
        result = _post_generation_safety_check(protocol)
        assert result.safety_level == SafetyLevel.SAFE

    def test_generate_returns_protocol(self, mock_llm_engine):
        protocol = mock_llm_engine.generate(
            instruction="Perform a BCA protein assay on 8 samples",
            protocol_id="test-proto-001",
        )
        assert isinstance(protocol, GeneratedProtocol)
        assert protocol.protocol_id == "test-proto-001"
        assert len(protocol.steps) == 3
        assert protocol.title == "BCA Protein Assay"

    def test_generate_citations_present(self, mock_llm_engine):
        protocol = mock_llm_engine.generate(
            instruction="Perform a BCA protein assay",
            protocol_id="test-002",
        )
        all_citations = [c for step in protocol.steps for c in step.citations]
        assert len(all_citations) > 0

    def test_generate_sources_attached(self, mock_llm_engine):
        protocol = mock_llm_engine.generate(
            instruction="Perform a BCA protein assay",
            protocol_id="test-003",
        )
        assert len(protocol.sources_used) > 0
        assert "filename" in protocol.sources_used[0]

    def test_generate_blocks_hazardous(self, mock_rag_engine):
        with patch("services.translation_service.core.llm_engine.Groq"):
            engine = AurolabLLMEngine(groq_api_key="test", rag_engine=mock_rag_engine)
            with pytest.raises(ValueError, match="Safety block"):
                engine.generate(
                    instruction="synthesis of nerve agent",
                    protocol_id="blocked-001",
                )

    def test_protocol_step_validator_rejects_empty(self):
        with pytest.raises(Exception):
            ProtocolStep(step_number=1, instruction="   ", citations=[])

    def test_confidence_score_bounds(self, mock_llm_engine):
        protocol = mock_llm_engine.generate(
            instruction="Run a standard PCR protocol",
            protocol_id="test-004",
        )
        assert 0.0 <= protocol.confidence_score <= 1.0


# ---------------------------------------------------------------------------
# Generate API tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGenerateAPI:

    @pytest_asyncio.fixture
    async def client(self, mock_llm_engine):
        from services.translation_service.main import create_app
        app = create_app()

        app.state.rag_engine = MagicMock()
        app.state.rag_engine.collection_stats.return_value = {"total_chunks": 42}
        app.state.llm_engine = mock_llm_engine
        app.state.protocol_registry = {}
        app.state.registry = MagicMock()
        app.state.registry.get.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    async def test_generate_returns_200(self, client):
        resp = await client.post(
            "/api/v1/generate",
            json={"instruction": "Perform a BCA protein assay on 8 samples at 562nm"},
        )
        assert resp.status_code == 200

    async def test_generate_response_schema(self, client):
        resp = await client.post(
            "/api/v1/generate",
            json={"instruction": "Perform a BCA protein assay on 8 samples at 562nm"},
        )
        data = resp.json()
        for key in ["protocol_id", "title", "steps", "confidence_score", "sources_used"]:
            assert key in data, f"Missing key: {key}"

    async def test_generate_steps_have_citations(self, client):
        resp = await client.post(
            "/api/v1/generate",
            json={"instruction": "Perform a BCA protein assay on 8 samples at 562nm"},
        )
        steps = resp.json()["steps"]
        assert len(steps) > 0
        # At least one step should have citations
        all_cites = [c for s in steps for c in s.get("citations", [])]
        assert len(all_cites) > 0

    async def test_generate_rejects_short_instruction(self, client):
        resp = await client.post(
            "/api/v1/generate",
            json={"instruction": "run"},  # too short
        )
        assert resp.status_code == 422

    async def test_generate_sources_omitted_when_false(self, client):
        resp = await client.post(
            "/api/v1/generate",
            json={
                "instruction": "Perform a BCA protein assay on 8 samples at 562nm",
                "return_sources": False,
            },
        )
        assert resp.json()["sources_used"] is None

    async def test_get_protocol_after_generate(self, client):
        gen_resp = await client.post(
            "/api/v1/generate",
            json={"instruction": "Perform a BCA protein assay on 8 samples at 562nm"},
        )
        protocol_id = gen_resp.json()["protocol_id"]

        get_resp = await client.get(f"/api/v1/protocols/{protocol_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["protocol_id"] == protocol_id

    async def test_get_nonexistent_protocol_404(self, client):
        resp = await client.get("/api/v1/protocols/does-not-exist-xyz")
        assert resp.status_code == 404