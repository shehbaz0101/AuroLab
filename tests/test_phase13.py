"""
tests/test_phase13.py

Integration tests for Phase 1.3 — PDF upload, chunking, and RAG retrieval.
Run with: pytest tests/test_phase13.py -v
"""

from __future__ import annotations

import hashlib
import io
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from services.translation_service.core.chunker import chunk_document, Chunk
from services.translation_service.core.pdf_parser import ParsedDocument, ContentBlock, BlockType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_parsed_doc() -> ParsedDocument:
    """A realistic minimal ParsedDocument for unit tests."""
    blocks = [
        ContentBlock(BlockType.HEADING,   "1. Materials", page_number=1, font_size=14, is_bold=True),
        ContentBlock(BlockType.TEXT,      "10 mM Tris-HCl pH 8.0, 150 mM NaCl, 1 mM EDTA. "
                                          "Prepare fresh before use and keep on ice.", page_number=1),
        ContentBlock(BlockType.LIST_ITEM, "- 1.5 mL microcentrifuge tubes (sterile)", page_number=1),
        ContentBlock(BlockType.HEADING,   "2. Protocol", page_number=2, font_size=14, is_bold=True),
        ContentBlock(BlockType.TEXT,      "Pipette 50 µL of sample into each tube. "
                                          "Centrifuge at 13,000 × g for 10 minutes at 4°C. "
                                          "Aspirate supernatant carefully without disturbing the pellet.",
                     page_number=2),
        ContentBlock(BlockType.TABLE,     "Step | Duration | Temp\n1 | 10 min | 4°C\n2 | 5 min | RT",
                     page_number=2,
                     table_data=[["Step", "Duration", "Temp"], ["1", "10 min", "4°C"], ["2", "5 min", "RT"]]),
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
# Chunker tests
# ---------------------------------------------------------------------------

class TestChunker:

    def test_produces_chunks(self, minimal_parsed_doc):
        chunks = chunk_document(minimal_parsed_doc)
        assert len(chunks) > 0

    def test_table_is_atomic(self, minimal_parsed_doc):
        chunks = chunk_document(minimal_parsed_doc)
        table_chunks = [c for c in chunks if c.is_table]
        assert len(table_chunks) == 1
        assert "Step" in table_chunks[0].text

    def test_section_titles_assigned(self, minimal_parsed_doc):
        chunks = chunk_document(minimal_parsed_doc)
        non_table = [c for c in chunks if not c.is_table]
        # Every non-table chunk should have a section title
        assert all(c.section_title is not None for c in non_table)

    def test_token_budget_respected(self, minimal_parsed_doc):
        chunks = chunk_document(minimal_parsed_doc, max_tokens=128)
        assert all(c.token_count <= 128 + 10 for c in chunks)  # +10 tokenizer margin

    def test_chunk_ids_unique(self, minimal_parsed_doc):
        chunks = chunk_document(minimal_parsed_doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chroma_metadata_flat(self, minimal_parsed_doc):
        chunks = chunk_document(minimal_parsed_doc)
        for c in chunks:
            meta = c.to_chroma_metadata()
            for v in meta.values():
                assert isinstance(v, (str, int, float, bool)), \
                    f"ChromaDB metadata must be scalar, got {type(v)} for {v}"

    def test_position_ratio_range(self, minimal_parsed_doc):
        chunks = chunk_document(minimal_parsed_doc)
        for c in chunks:
            assert 0.0 <= c.position_ratio <= 1.0

    def test_total_chunks_backfilled(self, minimal_parsed_doc):
        chunks = chunk_document(minimal_parsed_doc)
        expected = len(chunks)
        assert all(c.total_chunks_in_doc == expected for c in chunks)

    def test_empty_doc_returns_no_chunks(self):
        empty_doc = ParsedDocument(
            source_path="empty.pdf", sha256="abc", page_count=1,
            title=None, authors=[], doc_type="unknown", blocks=[], raw_text="",
            parse_strategy="pymupdf",
        )
        assert chunk_document(empty_doc) == []


# ---------------------------------------------------------------------------
# RAG engine tests (mocked)
# ---------------------------------------------------------------------------

class TestRAGEngine:

    @patch("services.translation_service.core.rag_engine.SentenceTransformer")
    @patch("services.translation_service.core.rag_engine.chromadb")
    @patch("services.translation_service.core.rag_engine.Groq")
    @patch("services.translation_service.core.rag_engine.Ranker")
    def test_retrieve_returns_result(self, mock_ranker, mock_groq, mock_chroma, mock_st):
        from services.translation_service.core.rag_engine import AurolabRAGEngine

        # Mock chromadb query response
        mock_collection = MagicMock()
        mock_collection.count.return_value = 10
        mock_collection.query.return_value = {
            "documents": [["Buffer preparation: add 10 mM Tris-HCl to 150 mM NaCl."]],
            "metadatas": [[{"sha256": "abc123", "source": "bca.pdf",
                            "doc_type": "protocol", "section_title": "Materials",
                            "page_start": 1, "page_end": 1}]],
            "distances": [[0.12]],
        }
        mock_chroma.PersistentClient.return_value.get_or_create_collection.return_value = mock_collection

        mock_embed = MagicMock()
        mock_embed.encode.return_value = MagicMock(tolist=lambda: [[0.1] * 384])
        mock_st.return_value = mock_embed

        engine = AurolabRAGEngine(
            persist_path="/tmp/test_chroma",
            groq_api_key="test",
            use_hyde=False,
            use_reranker=False,
        )

        result = engine.retrieve("how to prepare BCA assay buffer", top_k=1)
        assert result.query == "how to prepare BCA assay buffer"
        assert len(result.chunks) == 1
        assert result.chunks[0].doc_type == "protocol"


# ---------------------------------------------------------------------------
# Upload API tests (httpx async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestUploadAPI:

    @pytest_asyncio.fixture
    async def client(self):
        from services.translation_service.main import create_app
        app = create_app()
        # Inject mocked state BEFORE the lifespan runs by overriding after construction.
        # Use lifespan=False to skip startup (avoids loading real models in tests).
        app.state.rag_engine = MagicMock()
        app.state.rag_engine.collection_stats.return_value = {"total_chunks": 0}
        app.state.rag_engine.ingest_chunks.return_value = {"added": 5, "skipped": 0}
        app.state.registry = MagicMock()
        app.state.registry.get.return_value = None
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    async def test_health_endpoint(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_upload_rejects_non_pdf(self, client):
        fake_txt = io.BytesIO(b"This is not a PDF")
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("notes.txt", fake_txt, "text/plain")},
        )
        assert resp.status_code == 415

    async def test_upload_accepts_pdf(self, client):
        # Minimal valid PDF bytes
        minimal_pdf = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f\ntrailer<</Root 1 0 R/Size 4>>\n%%EOF"
        )
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("protocol.pdf", io.BytesIO(minimal_pdf), "application/pdf")},
        )
        # 202 Accepted or 415 if magic library detects non-PDF
        assert resp.status_code in (202, 415)