"""Ingestion package for decomposing existing documentation into atomic capsules."""
from __future__ import annotations

from .ast_splitter import AstDocumentSplitter, AtomicUnit
from .decomposer import DocumentDecomposer, IngestResult
from .llm_splitter import LlmDocumentSplitter

__all__ = [
    "AtomicUnit",
    "AstDocumentSplitter",
    "LlmDocumentSplitter",
    "DocumentDecomposer",
    "IngestResult",
]
