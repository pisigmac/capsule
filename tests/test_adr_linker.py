"""
Unit and integration tests for AdrCrossLayerLinker.
Verifies reference extraction (# ADR, # SPEC, # INVARIANT, [[WikiLinks]]),
knowledge resolution, and bidirectional implements/implemented_by graph linkage.
"""

from pathlib import Path
import pytest

from services.ingest.parsers.adr_linker import AdrCrossLayerLinker, AdrReference
from services.ingest.code_decomposer import CodeDecomposer
from services.store.store import CapsuleStore
from services.shared.models import Capsule


def test_extract_references_from_text():
    sample_text = """
    \"\"\"
    Handles atomic storage of capsules.
    # ADR: 001 (File-First Vault)
    # INVARIANT: Database is a derived disposable search index
    See also [[Postgres is the shared index]] and [[Search uses integer FTS5 rowids|FTS5]].
    @spec Dynamic Schema
    \"\"\"
    """
    refs = AdrCrossLayerLinker.extract_references_from_text(sample_text)
    extracted = [(r.source_kind, r.target_text) for r in refs]

    # Verify WikiLinks
    assert ("wikilink", "Postgres is the shared index") in extracted
    assert ("wikilink", "Search uses integer FTS5 rowids") in extracted

    # Verify Tagged patterns
    assert any("File-First Vault" in r.target_text for r in refs if r.source_kind == "pattern")
    assert any("Database is a derived disposable search index" in r.target_text for r in refs if r.source_kind == "pattern")
    assert any("Dynamic Schema" in r.target_text for r in refs if r.source_kind == "pattern")


def test_resolve_target_capsule(db_session, tmp_path: Path):
    store = CapsuleStore(db=db_session, capsules_dir=tmp_path / "capsules")
    adr_cap = store.create(
        topic="Capsule stores one fact per file",
        content="Canonical markdown on disk.",
        tags=["architecture", "adr-001"],
        category="architecture",
        confidence="high",
    )
    postgres_cap = store.create(
        topic="Postgres is the shared index",
        content="PostgreSQL tsvector + GIN.",
        tags=["architecture", "postgres"],
        category="architecture",
        confidence="high",
    )

    linker = AdrCrossLayerLinker(store)

    # 1. Exact topic match
    assert linker.resolve_target_capsule("Capsule stores one fact per file").id == adr_cap.id

    # 2. Case-insensitive / normalized match
    assert linker.resolve_target_capsule("capsule stores one fact per file").id == adr_cap.id

    # 3. ID match
    assert linker.resolve_target_capsule(adr_cap.id).id == adr_cap.id
    assert linker.resolve_target_capsule(adr_cap.id[:8]).id == adr_cap.id

    # 4. Tag match
    assert linker.resolve_target_capsule("adr-001").id == adr_cap.id

    # 5. Keyword substring match
    assert linker.resolve_target_capsule("shared index").id == postgres_cap.id


def test_cross_layer_bidirectional_linking(db_session, tmp_path: Path):
    store = CapsuleStore(db=db_session, capsules_dir=tmp_path / "capsules")
    
    # 1. Create Knowledge ADR Capsule
    adr = store.create(
        topic="File-First Architecture",
        content="Markdown files on disk are the canonical source of truth.",
        tags=["architecture", "adr"],
        category="architecture",
        confidence="high",
    )

    # 2. Create sample source file referencing ADR
    src_file = tmp_path / "engine.py"
    src_file.write_text(
        '"""\nEngine module.\n# ADR: File-First Architecture\n"""\n'
        'class StoreEngine:\n'
        '    """\n    Engine class.\n    [[File-First Architecture]]\n    """\n'
        '    def sync(self):\n'
        '        """\n        Synchronizes vault.\n        # INVARIANT: File-First Architecture\n        """\n'
        '        pass\n',
        encoding="utf-8",
    )

    # 3. Ingest with CodeDecomposer
    decomposer = CodeDecomposer(store)
    result = decomposer.ingest_code_path(src_file)

    assert result.total_files == 1
    assert result.total_classes == 1
    assert result.total_functions == 1
    assert result.relationships_linked > 0

    # 4. Verify bidirectional relationships
    file_cap = next(c for c in result.created_capsules if "File:" in c.topic)
    cls_cap = next(c for c in result.created_capsules if "Class:" in c.topic)
    fn_cap = next(c for c in result.created_capsules if "Function:" in c.topic)

    # Get updated capsules from store
    adr_updated = store.get(adr.id)
    assert adr_updated is not None

    # Check that ADR has implemented_by relationships targeting code entities
    adr_rel_targets = [r.to_capsule_id for r in adr_updated.outgoing_relationships if r.relationship_type == "implemented_by"]
    assert file_cap.id in adr_rel_targets or cls_cap.id in adr_rel_targets or fn_cap.id in adr_rel_targets

    # Check that code entities have implements relationship targeting ADR
    cls_updated = store.get(cls_cap.id)
    assert cls_updated is not None
    cls_rel_targets = [r.to_capsule_id for r in cls_updated.outgoing_relationships if r.relationship_type == "implements"]
    assert adr.id in cls_rel_targets
