"""
Unit tests for GoCodeParser, RustCodeParser, JavaCodeParser, and multi-language decomposition.
"""

from pathlib import Path
import tempfile
import pytest

from services.ingest.parsers.go_parser import GoCodeParser
from services.ingest.parsers.rust_parser import RustCodeParser
from services.ingest.parsers.java_parser import JavaCodeParser
from services.ingest.code_decomposer import CodeDecomposer
from services.store.store import CapsuleStore


def test_go_code_parser():
    go_src = """
    package store

    import (
        "fmt"
        "sync"
    )

    type CapsuleStore struct {
        mu sync.RWMutex
        db string
    }

    type Storage interface {
        Get(id string) (string, error)
        Save(id string, data string) error
    }

    func (s *CapsuleStore) Get(id string) (string, error) {
        s.mu.RLock()
        defer s.mu.RUnlock()
        return fmt.Sprintf("data-%s", id), nil
    }

    func NewStore(db string) *CapsuleStore {
        return &CapsuleStore{db: db}
    }
    """
    parser = GoCodeParser()
    info = parser.parse_code("pkg/store/store.go", go_src)

    assert info.package == "store"
    assert "fmt" in info.imports
    assert "sync" in info.imports
    assert "CapsuleStore" in info.types
    assert info.types["CapsuleStore"].kind == "struct"
    assert "Storage" in info.types
    assert info.types["Storage"].kind == "interface"

    func_names = [f.name for f in info.functions]
    assert "Get" in func_names
    assert "NewStore" in func_names


def test_rust_code_parser():
    rust_src = """
    use std::sync::Arc;
    use tokio::sync::RwLock;

    pub struct VaultStore {
        vault_path: String,
    }

    pub enum Status {
        Active,
        Archived,
    }

    pub trait StorageEngine {
        fn fetch(&self, id: &str) -> Option<String>;
    }

    pub async fn init_vault(path: &str) -> Arc<VaultStore> {
        Arc::new(VaultStore { vault_path: path.to_string() })
    }
    """
    parser = RustCodeParser()
    info = parser.parse_code("src/store.rs", rust_src)

    assert any("std::sync::Arc" in imp for imp in info.imports)
    assert "VaultStore" in info.types
    assert info.types["VaultStore"].kind == "struct"
    assert "Status" in info.types
    assert info.types["Status"].kind == "enum"
    assert "StorageEngine" in info.types
    assert info.types["StorageEngine"].kind == "trait"

    fn_names = [f.name for f in info.functions]
    assert "init_vault" in fn_names


def test_java_code_parser():
    java_src = """
    package com.capsule.engine;

    import java.util.List;
    import java.util.Optional;

    public class EngineService implements Service {
        private String endpoint;

        public String getEndpoint() {
            return this.endpoint;
        }

        public static void main(String[] args) {
            System.out.println("Capsule Engine");
        }
    }
    """
    parser = JavaCodeParser()
    info = parser.parse_code("src/main/java/com/capsule/engine/EngineService.java", java_src)

    assert info.package == "com.capsule.engine"
    assert "java.util.List" in info.imports
    assert "EngineService" in info.classes
    assert info.classes["EngineService"].kind == "class"
    assert "Service" in info.classes["EngineService"].implements

    method_names = [m.name for m in info.methods]
    assert "getEndpoint" in method_names
    assert "main" in method_names


def test_code_decomposer_multilang_ingest(db_session, tmp_path: Path):
    store = CapsuleStore(db=db_session, capsules_dir=tmp_path / "capsules")
    
    # Create multi-language repository layout
    repo = tmp_path / "multi_repo"
    repo.mkdir()
    
    (repo / "go_service").mkdir()
    (repo / "go_service" / "main.go").write_text("""
    package main
    type Config struct { Host string }
    func StartServer() {}
    """, encoding="utf-8")

    (repo / "rust_core").mkdir()
    (repo / "rust_core" / "lib.rs").write_text("""
    pub struct IndexEngine;
    pub fn rebuild_index() {}
    """, encoding="utf-8")

    (repo / "java_app").mkdir()
    (repo / "java_app" / "App.java").write_text("""
    package app;
    public class App {
        public static void main(String[] args) {}
    }
    """, encoding="utf-8")

    decomposer = CodeDecomposer(store)
    result = decomposer.ingest_code_path(repo)

    assert result.total_files == 3
    assert result.total_classes >= 3
    assert result.total_functions >= 3
    assert result.relationships_linked >= 3

    # Verify capsules created in database and correct categories
    caps = store.db.query(CapsuleStore).first() if hasattr(store, "list") else None
    
    topics = [c.topic for c in result.created_capsules]
    assert any("File: go_service/main.go" in t for t in topics)
    assert any("Struct: Config" in t for t in topics)
    assert any("File: rust_core/lib.rs" in t for t in topics)
    assert any("Struct: IndexEngine" in t for t in topics)
    assert any("File: java_app/App.java" in t for t in topics)
    assert any("Class: App" in t for t in topics)
