"""
services/translation_service/core/document_loader.py

Document loading layer — validates, deduplicates, and routes PDF files
to the appropriate parser strategy before handing off to the chunker.

Responsibilities:
  1. Validate uploaded file (MIME type, size, extension)
  2. Compute SHA-256 for deduplication
  3. Choose parse strategy (PyMuPDF → pdfminer → OCR fallback)
  4. Return ParsedDocument ready for chunking

This is called by upload_router.py before chunking and embedding.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import BinaryIO

import structlog

log = structlog.get_logger(__name__)


def _get_parser():
    """Lazily import parse_pdf to avoid hard dependency at module load time."""
    try:
        from .pdf_parser import ParsedDocument, parse_pdf
        return ParsedDocument, parse_pdf
    except ImportError:
        pass
    try:
        from services.translation_service.core.pdf_parser import ParsedDocument, parse_pdf
        return ParsedDocument, parse_pdf
    except ImportError:
        pass
    from core.pdf_parser import ParsedDocument, parse_pdf  # type: ignore
    return ParsedDocument, parse_pdf

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_MB   = 50
ALLOWED_EXTENSIONS = {".pdf"}
ALLOWED_MIME_TYPES = {"application/pdf", "application/x-pdf"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class DocumentLoadError(Exception):
    """Raised when a document cannot be loaded or validated."""
    def __init__(self, message: str, code: str = "LOAD_ERROR") -> None:
        super().__init__(message)
        self.code = code


def _validate_file(
    filename: str,
    file_bytes: bytes,
    max_mb: float = MAX_FILE_SIZE_MB,
) -> None:
    """Raise DocumentLoadError if the file fails any validation check."""
    # Extension check
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentLoadError(
            f"Unsupported file type: {ext}. Only PDF files are accepted.",
            code="INVALID_EXTENSION",
        )

    # Size check
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > max_mb:
        raise DocumentLoadError(
            f"File too large: {size_mb:.1f} MB (max {max_mb} MB).",
            code="FILE_TOO_LARGE",
        )

    # PDF magic bytes check (first 4 bytes should be %PDF)
    if not file_bytes.startswith(b"%PDF"):
        raise DocumentLoadError(
            "File does not appear to be a valid PDF (missing %PDF header).",
            code="INVALID_PDF_HEADER",
        )


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_document(
    filename: str,
    file_bytes: bytes,
    source_label: str | None = None,
) -> "ParsedDocument":
    _validate_file(filename, file_bytes)
    ParsedDocument, parse_pdf = _get_parser()

    sha256 = _compute_sha256(file_bytes)
    label  = source_label or Path(filename).stem

    log.info("document_loading",
             filename=filename,
             size_kb=round(len(file_bytes) / 1024, 1),
             sha256=sha256[:8])

    doc = parse_pdf(file_bytes, source_path=filename)
    doc.sha256 = sha256

    log.info("document_loaded",
             filename=filename,
             pages=doc.page_count,
             blocks=len(doc.blocks),
             strategy=doc.parse_strategy)

    return doc


def load_document_from_path(file_path: str | Path) -> ParsedDocument:
    """
    Load a document from a local file path.
    Convenience wrapper for batch ingestion scripts.
    """
    path = Path(file_path)
    if not path.exists():
        raise DocumentLoadError(f"File not found: {file_path}", code="FILE_NOT_FOUND")
    file_bytes = path.read_bytes()
    return load_document(path.name, file_bytes)


def is_duplicate(sha256: str, registry) -> bool:
    """
    Check if a document with this SHA-256 has already been ingested.

    Args:
        sha256:   SHA-256 hex digest of the document.
        registry: DocumentRegistry instance.

    Returns:
        True if already in the registry.
    """
    existing = registry.get_by_sha256(sha256)
    return existing is not None