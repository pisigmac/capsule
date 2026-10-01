"""Ingestion package for decomposing documentation, git history, and PRs into atomic capsules."""
from __future__ import annotations

from .ast_splitter import AstDocumentSplitter, AtomicUnit
from .code_decomposer import CodeDecomposer, CodeIngestResult
from .decomposer import DocumentDecomposer, IngestResult
from .git_harvester import GitHarvester, GitHarvestItem
from .llm_splitter import LlmDocumentSplitter
from .pr_harvester import PRHarvester

__all__ = [
    "AtomicUnit",
    "AstDocumentSplitter",
    "LlmDocumentSplitter",
    "DocumentDecomposer",
    "IngestResult",
    "CodeDecomposer",
    "CodeIngestResult",
    "GitHarvester",
    "GitHarvestItem",
    "PRHarvester",
]
