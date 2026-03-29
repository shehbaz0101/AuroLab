"""
services/translation_service/api/routes.py

Consolidated API routes for the translation service.
Uses TranslationService facade to keep handlers thin.

Endpoints:
  POST /api/v1/upload                — Upload and ingest a PDF
  POST /api/v1/generate              — Generate a protocol from NL instruction
  GET  /api/v1/protocols/            — List all protocols (with search/filter)
  GET  /api/v1/protocols/{id}        — Get a specific protocol
  DELETE /api/v1/protocols/{id}      — Delete a protocol
  GET  /api/v1/protocols/{id}/export — Export as JSON or markdown
  GET  /api/v1/documents/            — List all ingested documents
  GET  /api/v1/rag/stats             — RAG collection stats

Note: These routes complement (and may overlap with) upload_router.py
and generate_router.py. They use the TranslationService facade whereas
the original routers access app.state directly.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Translation Service"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    instruction: str = Field(
        min_length=10, max_length=2000,
        description="Natural language lab instruction",
        examples=["Perform a BCA protein assay on 8 samples at 562nm"],
    )
    protocol_id: str | None = Field(
        default=None,
        description="Optional protocol ID. Auto-generated if not provided.",
    )


class SearchParams(BaseModel):
    query: str = ""
    safety_level: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_service(request: Request):
    """Get TranslationService from app state, with graceful fallback."""
    svc = getattr(request.app.state, "translation_service", None)
    if svc is None:
        # Fallback: use individual engines directly (backward-compatible)
        return None
    return svc


# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a PDF into the knowledge base",
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="PDF file to upload"),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await file.read()
    svc = _get_service(request)

    if svc:
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, svc.ingest_pdf, file.filename, file_bytes
            )
        except Exception as exc:
            log.error("upload_failed", filename=file.filename, error=str(exc))
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        # Backward-compatible path using raw engines
        from .upload_router import _ingest_bytes
        result = await _ingest_bytes(request, file.filename, file_bytes)

    return result


# ---------------------------------------------------------------------------
# Protocol generation
# ---------------------------------------------------------------------------

@router.post(
    "/generate",
    status_code=status.HTTP_200_OK,
    summary="Generate a validated robotic protocol from a natural language instruction",
)
async def generate_protocol(body: GenerateRequest, request: Request) -> dict:
    svc = _get_service(request)

    if svc:
        try:
            protocol = await asyncio.get_event_loop().run_in_executor(
                None,
                svc.generate_protocol,
                body.instruction,
                body.protocol_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.error("generate_failed", instruction=body.instruction[:60], error=str(exc))
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        # Also store in app.state.protocol_registry for execution layer
        registry: dict = request.app.state.protocol_registry
        registry[protocol.protocol_id] = protocol

        return protocol.model_dump(mode="json")

    else:
        # Forward to generate_router handler (backward-compatible)
        from .generate_router import generate
        return await generate(body, request)


# ---------------------------------------------------------------------------
# Protocol CRUD
# ---------------------------------------------------------------------------

@router.get(
    "/protocols/",
    summary="List all generated protocols",
)
async def list_protocols(
    request: Request,
    q: str = Query(default="", description="Text search"),
    safety_level: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    svc = _get_service(request)

    if svc:
        results, total = svc.search_protocols(
            query=q, safety_level=safety_level, limit=limit, offset=offset
        )
        return {"protocols": results, "total": total, "limit": limit, "offset": offset}

    # Fallback: read from protocol_registry directly
    registry: dict = request.app.state.protocol_registry
    protocols = [
        p.model_dump(mode="json") if hasattr(p, "model_dump") else dict(p)
        for p in registry.values()
    ]
    if q:
        q_lower = q.lower()
        protocols = [
            p for p in protocols
            if q_lower in p.get("title", "").lower()
            or q_lower in p.get("description", "").lower()
        ]
    return {"protocols": protocols[offset:offset+limit], "total": len(protocols)}


@router.get(
    "/protocols/{protocol_id}",
    summary="Get a specific protocol by ID",
)
async def get_protocol(protocol_id: str, request: Request) -> dict:
    svc = _get_service(request)

    if svc:
        p = svc.get_protocol(protocol_id)
    else:
        registry: dict = request.app.state.protocol_registry
        p = registry.get(protocol_id)
        if p and hasattr(p, "model_dump"):
            p = p.model_dump(mode="json")

    if not p:
        raise HTTPException(status_code=404, detail=f"Protocol {protocol_id} not found")
    return p


@router.delete(
    "/protocols/{protocol_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a protocol",
)
async def delete_protocol(protocol_id: str, request: Request) -> None:
    svc = _get_service(request)
    if svc:
        deleted = svc.delete_protocol(protocol_id)
    else:
        registry: dict = request.app.state.protocol_registry
        deleted = protocol_id in registry
        if deleted:
            del registry[protocol_id]

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Protocol {protocol_id} not found")


@router.get(
    "/protocols/{protocol_id}/export",
    summary="Export a protocol as JSON or Markdown",
)
async def export_protocol(
    protocol_id: str,
    request: Request,
    fmt: str = Query(default="json", pattern="^(json|markdown)$"),
) -> PlainTextResponse:
    svc = _get_service(request)

    if svc:
        content = svc.export_protocol(protocol_id, fmt=fmt)
    else:
        # Fallback: JSON only from registry
        registry: dict = request.app.state.protocol_registry
        p = registry.get(protocol_id)
        if p:
            import json
            data = p.model_dump(mode="json") if hasattr(p, "model_dump") else dict(p)
            content = json.dumps(data, indent=2)
        else:
            content = None

    if not content:
        raise HTTPException(status_code=404, detail=f"Protocol {protocol_id} not found")

    media_type = "text/markdown" if fmt == "markdown" else "application/json"
    ext = "md" if fmt == "markdown" else "json"
    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="protocol_{protocol_id}.{ext}"'},
    )


# ---------------------------------------------------------------------------
# Document list
# ---------------------------------------------------------------------------

@router.get(
    "/documents/",
    summary="List all documents in the knowledge base",
)
async def list_documents(request: Request) -> dict:
    svc = _get_service(request)
    if svc:
        docs = svc.document_list()
        return {"documents": docs, "total": len(docs)}

    # Fallback: read from registry directly
    registry: DocumentRegistry = request.app.state.registry  # type: ignore
    if hasattr(registry, "list_all"):
        docs = registry.list_all()
        return {"documents": docs, "total": len(docs)}

    return {"documents": [], "total": 0}


# ---------------------------------------------------------------------------
# RAG stats
# ---------------------------------------------------------------------------

@router.get(
    "/rag/stats",
    summary="RAG vector store statistics",
)
async def rag_stats(request: Request) -> dict:
    svc = _get_service(request)
    if svc:
        return svc.collection_stats()
    return request.app.state.rag_engine.collection_stats()


# ---------------------------------------------------------------------------
# Import helper for backward compatibility
# ---------------------------------------------------------------------------

try:
    from .upload_router import router as _upload_router
    from .generate_router import router as _generate_router
except ImportError:
    pass