"""
aurolab/services/translation_service/api/upload_router.py

PDF upload endpoint for AuroLab.

POST /api/v1/documents/upload
  - Validates MIME type (PDF only)
  - SHA-256 dedup (skips re-ingestion of identical files)
  - Parses + chunks + embeds in background task
  - Returns immediate acknowledgment with job_id

GET /api/v1/documents/{sha256}/status
  - Polls ingestion status

GET /api/v1/documents/
  - Lists ingested documents with metadata

DELETE /api/v1/documents/{sha256}
  - Removes a document and all its chunks from ChromaDB
"""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Annotated

import magic
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from ..core.chunker import chunk_document
from ..core.pdf_parser import parse_pdf
from ..core.rag_engine import AurolabRAGEngine
from ..core.registry import DocumentRegistry  # defined below

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])

MAX_FILE_SIZE_MB = 50
ALLOWED_MIME_TYPES = {"application/pdf"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    job_id: str
    sha256: str
    filename: str
    size_kb: int
    status: str = "queued"
    message: str


class DocumentStatus(BaseModel):
    sha256: str
    filename: str
    doc_type: str
    status: str                         # "processing" | "ready" | "failed"
    chunk_count: int
    page_count: int
    parse_strategy: str
    ingested_at: float | None = None
    error: str | None = None


class DocumentList(BaseModel):
    total: int
    documents: list[DocumentStatus]


# ---------------------------------------------------------------------------
# Dependency: get RAG engine from app state
# ---------------------------------------------------------------------------

def get_rag_engine(request: Request) -> AurolabRAGEngine:
    return request.app.state.rag_engine


def get_registry(request: Request) -> DocumentRegistry:
    return request.app.state.registry


# ---------------------------------------------------------------------------
# Background ingestion task
# ---------------------------------------------------------------------------

async def _ingest_document(
    pdf_bytes: bytes,
    filename: str,
    sha256: str,
    job_id: str,
    rag_engine: AurolabRAGEngine,
    registry: DocumentRegistry,
) -> None:
    """Run parse → chunk → embed in background. Updates registry on completion."""
    registry.update_status(sha256, "processing")

    try:
        t0 = time.perf_counter()

        # Parse
        doc = parse_pdf(pdf_bytes, source_path=filename)
        log.info("background_parse_complete",
                 job_id=job_id, strategy=doc.parse_strategy, blocks=len(doc.blocks))

        # Chunk
        chunks = chunk_document(doc)
        log.info("background_chunk_complete", job_id=job_id, chunks=len(chunks))

        # Ingest into vector DB
        stats = rag_engine.ingest_chunks(chunks)
        elapsed = round((time.perf_counter() - t0) * 1000)

        registry.update_status(
            sha256,
            "ready",
            chunk_count=stats["added"] + stats.get("skipped", 0),
            page_count=doc.page_count,
            parse_strategy=doc.parse_strategy,
            doc_type=doc.doc_type,
            ingested_at=time.time(),
        )

        log.info("ingestion_complete",
                 job_id=job_id, sha256=sha256[:12],
                 chunks_added=stats["added"],
                 elapsed_ms=elapsed)

    except Exception as exc:
        log.error("ingestion_failed", job_id=job_id, error=str(exc), exc_info=True)
        registry.update_status(sha256, "failed", error=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a lab protocol PDF for ingestion",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="PDF file to ingest (max 50MB)")],
    request: Request,
) -> UploadResponse:
    rag_engine = get_rag_engine(request)
    registry = get_registry(request)

    # Size check
    pdf_bytes = await file.read()
    size_mb = len(pdf_bytes) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_FILE_SIZE_MB}MB limit ({size_mb:.1f}MB received)",
        )

    # MIME validation (don't trust the extension)
    mime = magic.from_buffer(pdf_bytes[:2048], mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Only PDF files accepted. Detected: {mime}",
        )

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    job_id = str(uuid.uuid4())
    filename = file.filename or "unknown.pdf"

    # Dedup: already in registry?
    existing = registry.get(sha256)
    if existing and existing.get("status") == "ready":
        return UploadResponse(
            job_id=job_id,
            sha256=sha256,
            filename=filename,
            size_kb=len(pdf_bytes) // 1024,
            status="duplicate",
            message=f"Document already ingested with {existing.get('chunk_count', 0)} chunks.",
        )

    # Register + enqueue background ingestion
    registry.register(sha256, filename)

    background_tasks.add_task(
        _ingest_document,
        pdf_bytes=pdf_bytes,
        filename=filename,
        sha256=sha256,
        job_id=job_id,
        rag_engine=rag_engine,
        registry=registry,
    )

    log.info("upload_accepted", job_id=job_id, sha256=sha256[:12], size_kb=len(pdf_bytes) // 1024)

    return UploadResponse(
        job_id=job_id,
        sha256=sha256,
        filename=filename,
        size_kb=len(pdf_bytes) // 1024,
        status="queued",
        message="Document queued for ingestion. Poll /status for progress.",
    )


@router.get(
    "/{sha256}/status",
    response_model=DocumentStatus,
    summary="Poll ingestion status for a document",
)
async def get_document_status(sha256: str, request: Request) -> DocumentStatus:
    registry = get_registry(request)
    record = registry.get(sha256)
    if not record:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentStatus(
        sha256=sha256,
        filename=record.get("filename", ""),
        doc_type=record.get("doc_type", "unknown"),
        status=record.get("status", "unknown"),
        chunk_count=record.get("chunk_count", 0),
        page_count=record.get("page_count", 0),
        parse_strategy=record.get("parse_strategy", ""),
        ingested_at=record.get("ingested_at"),
        error=record.get("error"),
    )


@router.get(
    "/",
    response_model=DocumentList,
    summary="List all ingested documents",
)
async def list_documents(request: Request) -> DocumentList:
    registry = get_registry(request)
    docs = registry.list_all()
    return DocumentList(
        total=len(docs),
        documents=[
            DocumentStatus(
                sha256=sha256,
                filename=d.get("filename", ""),
                doc_type=d.get("doc_type", "unknown"),
                status=d.get("status", "unknown"),
                chunk_count=d.get("chunk_count", 0),
                page_count=d.get("page_count", 0),
                parse_strategy=d.get("parse_strategy", ""),
                ingested_at=d.get("ingested_at"),
            )
            for sha256, d in docs.items()
        ],
    )


@router.delete(
    "/{sha256}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a document and all its chunks",
)
async def delete_document(sha256: str, request: Request) -> None:
    rag_engine = get_rag_engine(request)
    registry = get_registry(request)

    if not registry.get(sha256):
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove from ChromaDB by metadata filter
    rag_engine._collection.delete(where={"sha256": {"$eq": sha256}})
    registry.remove(sha256)
    log.info("document_deleted", sha256=sha256[:12])