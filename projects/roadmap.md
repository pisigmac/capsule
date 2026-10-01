---
created: 2026-10-01T04:30:00.000000+00:00
id: 73c8908cbf5c
modified: 2026-10-01T04:40:00.000000+00:00
source: daemon
status: active
tags:
  - roadmap
  - architecture
type: roadmap
---

# Capsule Project Roadmap & Engineering Milestones

## 🚀 High-Impact Improvement Tasks

### A. Cross-Layer Linking: Connect Knowledge ADRs to Code (`implements`)
- [x] **Automated ADR-to-Code Linker**: Scan docstrings and source comments for `# ADR: 001`, `[[Architecture]]`, or topic references to automatically generate `implements` or `verifies` edges:
  ```
  [Architecture: File-First Vault] ──(implemented_by)──▶ [Class: CapsuleStore]
  ```
- [x] **Unified Graph Highlighting**: In the Web UI Unified Graph view, clicking an Architecture node immediately highlights all corresponding code files, classes, and methods that implement it.

---

### B. Incremental Git Commit Ingestion (Zero-Overhead Sync)
- [x] **Git Hook Ingestor**: Added `caps hook install` command and `caps ingest --install-hook` / `caps ingest --git-diff <REV>`:
  ```bash
  caps ingest --git-diff HEAD~1
  ```
- [x] **Selective Re-Parsing**: Only parse and re-link the exact files and functions changed in the current commit, pruning stale capsules and keeping the Code Graph 100% updated in sub-15ms.

---

### C. Code Drift & Architectural Boundary Violation Detector
- [x] **`caps verify-drift` Command**:
  - **Dead Code Detection**: Flag functions or methods that have 0 incoming `calls` or `imports` edges across the entire repository.
  - **Architectural Boundary Violations**: Flag if frontend UI code or API route handlers directly bypass service layers or import private database internals.
- [x] **CI Linter Integration**: Connect drift checks to the GitHub Actions CI verifier (`capsule-ci`).

---

### D. Frontend Graph Canvas: Cluster Grouping & Convex Hulls
- [x] **Directory Clustering (Convex Hulls)**: Draw subtle translucent bounding boxes/clusters around nodes belonging to the same category (`architecture`, `benchmarks`, `code/python`, `code/typescript`).
- [x] **Interactive Folder Filter Pills**: Add toolbar toggle buttons for specific subfolders (`/benchmarks`, `/code/python`, `/architecture`) in addition to relationship types.
- [x] **Mini-Map Navigator**: Add a mini-map radar in the bottom corner of the canvas for large codebases (1,000+ nodes).

---

### E. Multi-Language Tree-Sitter Extension (Go, Rust, Java)
- [x] **Tree-Sitter Grammar Integration**: Integrated structural AST and regex parsers in `services/ingest/parsers/` supporting Go (`.go`), Rust (`.rs`), and Java (`.java`).
- [x] **Universal Code Decomposer**: Unified structural AST parsing while preserving deterministic `stable_id` hashing and language subfolder routing (`capsules/code/go/`, `capsules/code/rust/`, `capsules/code/java/`).

---

## ✅ Completed Milestones
- [x] **Separated Code Graph**: Multi-mode UI selector (🧠 Knowledge Graph, ⚡ Code Graph, 🌐 Unified View).
- [x] **Language Subtree Organization**: Routing code capsules into `capsules/code/python/...` and `capsules/code/typescript/...`.
- [x] **Deterministic AST Ingestion**: Native Python `ast` visitor, call-graph resolver, and TypeScript parser from Ledger & Aether.
- [x] **Multi-Language Parsing**: Go, Rust, Java, Python, and TypeScript/JavaScript AST decomposition.
- [x] **Incremental Git Commit Ingestion**: Zero-overhead git diff sync and post-commit hook automation (`caps ingest --git-diff HEAD~1`, `caps hook install`).
- [x] **Code Drift & Architectural Violations**: Dead code analysis and architectural boundary violation enforcement (`caps verify-drift`).
- [x] **Canonical Frontmatter Relationships**: Relationship persistence fix with `calls`, `defines`, `imports`, and `inherits` edges.
- [x] **Cross-Layer Linking**: Bidirectional `implements` and `implemented_by` linking between knowledge ADRs and AST code entities.
- [x] **Convex Hull Clustering & Radar Mini-Map**: 2D Hull geometry per directory cluster, folder filter pills, and interactive mini-map navigation.
