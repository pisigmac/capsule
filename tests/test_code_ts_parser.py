"""Tests for TypeScript/JS parser and Contract Linker."""
from services.ingest.parsers.typescript_parser import TypeScriptCodeParser
from services.ingest.parsers.contracts import ContractLinker


def test_parse_typescript_file():
    code = """
import { useState, useEffect } from 'react';
import { api, type Capsule, type Relationship } from './api';

export interface GraphNode {
  id: string;
  topic: string;
  confidence: string;
}

export type NodeFilter = 'all' | 'code' | 'knowledge';

export class GraphRenderer {
  canvas: HTMLCanvasElement;
  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
  }
}

export async function fetchCapsules(query: string): Promise<Capsule[]> {
  const res = await fetch(`/api/v1/search?q=${query}`);
  return res.json();
}
"""
    parser = TypeScriptCodeParser()
    info = parser.parse_code("frontend/src/graph.ts", code)

    assert info.path == "frontend/src/graph.ts"
    assert "react" in info.imports
    assert "./api" in info.imports
    assert "GraphNode" in info.interfaces
    assert "NodeFilter" in info.types
    assert "GraphRenderer" in info.classes
    assert "fetchCapsules" in [fn.name for fn in info.functions]
    assert "/api/v1/search" in info.http_endpoints


def test_contract_linker_binds_frontend_to_backend():
    ts_code = """
export async function getRelationships() {
  const res = await fetch('/api/v1/relationships');
  return res.json();
}
"""
    py_code = """
from fastapi import APIRouter
router = APIRouter()

@router.get('/api/v1/relationships')
def list_relationships():
    return []
"""
    ts_parser = TypeScriptCodeParser()
    ts_info = ts_parser.parse_code("frontend/src/api.ts", ts_code)

    linker = ContractLinker()
    contracts = linker.link_http_contracts(
        frontend_files=[ts_info],
        backend_routes=[{"path": "/api/v1/relationships", "file": "services/api/routes.py", "func": "list_relationships"}],
    )

    assert len(contracts) == 1
    assert contracts[0].route == "/api/v1/relationships"
    assert contracts[0].frontend_file == "frontend/src/api.ts"
    assert contracts[0].backend_file == "services/api/routes.py"
