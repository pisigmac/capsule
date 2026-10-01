# Codebase-to-Capsule Ingestion: Transforming Source Code into Atomic Knowledge Graphs

Capsule allows developers to transform entire software repositories (**Python, TypeScript/JavaScript, Go, Rust, Java**) into **atomic knowledge capsules, relationship dependency graphs, and cross-layer ADR governance networks**.

Instead of dumping raw syntax and boilerplate into vector databases, Capsule extracts **architectural invariants, schema contracts, public APIs, structural dependency trees, and bidirectional links to Architecture Decision Records (ADRs)**.

---

## 🏗️ 1. Conceptual Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Source Codebase                               │
│           (Python, TypeScript/JavaScript, Go, Rust, Java)               │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
       [ AST Structural Parsers ]              [ Invariant & ADR Extractor ]
       • Python (ast + call graph)             • # ADR: <id|title>
       • TypeScript (classes/interfaces/fns)   • # SPEC: <name>
       • Go (structs/interfaces/receivers)     • # INVARIANT: <topic>
       • Rust (structs/enums/traits/fns)       • [[WikiLinks]]
       • Java (classes/interfaces/records)     • HTTP contracts ($fetch/axios)
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     ▼
       ┌───────────────────────────────────────────────────────────┐
       │             Deterministic Language Subtrees               │
       │  capsules/code/python/services/store/                     │
       │  capsules/code/typescript/frontend/src/                   │
       │  capsules/code/go/pkg/engine/                             │
       │  capsules/code/rust/src/                                  │
       │  capsules/code/java/com/capsule/                          │
       └─────────────────────────────┬─────────────────────────────┘
                                     ▼
       ┌───────────────────────────────────────────────────────────┐
       │           Derived Multi-Layer Relationship Graph          │
       │  • defines, calls, imports, inherits (Code-to-Code)       │
       │  • implements, implemented_by (Code-to-Knowledge)         │
       │  • contract_http (Frontend-to-Backend HTTP routes)        │
       └───────────────────────────────────────────────────────────┘
```

---

## 🔍 2. What Gets Extracted from Code?

1. **Multi-Language AST Entities**:
   * **Python**: Classes, methods, inheritance (`inherits`), module imports (`imports`), function calls (`calls`), cyclomatic complexity, and git blame.
   * **TypeScript / JavaScript**: ES6 modules, interfaces, type aliases, classes, exported async functions, and frontend HTTP endpoints (`fetch`, `axios`).
   * **Go**: Packages, imports, structs, interfaces, and receiver methods (`func (s *Store) Save(...)`).
   * **Rust**: Crates, `use` statements, `struct`, `enum`, `trait`, and `impl` functions.
   * **Java**: Packages, classes, interfaces, records, and method signatures with `extends` and `implements` hierarchies.
2. **Architectural Invariants & Cross-Layer Linking**:
   * Docstrings and comments referencing `# ADR: <title>`, `# SPEC: <name>`, `# INVARIANT: <topic>`, or `[[Topic Title]]` are automatically resolved and linked to knowledge capsules in `capsules/architecture/`.
   * Establishes bidirectional edges: `Code` ──[`implements`]──▶ `ADR` and `ADR` ──[`implemented_by`]──▶ `Code`.

---

## 📐 3. Code Drift & Architectural Boundary Verification (`caps verify-drift`)

Capsule provides an automated drift auditor to ensure codebases don't decay:

1. **Dead Code Detection (`dead-code/unreferenced-symbol`)**:
   * Flags functions and methods that have 0 incoming `calls` or `imports` across the entire repository.
2. **Layer Boundary Violations (`boundary/frontend-to-database`)**:
   * Alerts if frontend code directly imports private backend database schemas or models instead of using standard HTTP contracts.
3. **Circular Dependencies (`boundary/circular-dependency`)**:
   * Catches direct import cycles between modules (`A` ➔ `B` ➔ `A`).
4. **Unimplemented ADRs (`adr/unimplemented-decision`)**:
   * Surfaces Architecture Decisions that have no implementing code capsules.

---

## 🚀 4. CLI Usage Examples

```bash
# Ingest entire codebase with AST parsing and cross-layer linking
caps ingest ./services/ --code

# Ingest multi-language directories (Python, TypeScript, Go, Rust, Java)
caps ingest ./frontend/src/ --code
caps ingest ./pkg/store/ --code

# Incremental zero-overhead sync from git commits (sub-15ms)
caps ingest --git-diff HEAD~1
caps ingest --git-diff origin/main...HEAD
caps ingest --git-diff staged

# Install automated post-commit Git hook for continuous sync
caps hook install
caps hook status

# Run Code Drift and Boundary Verification
caps verify-drift

# Output structured JSON for CI/CD gates
caps verify-drift --json

# Strict enforcement (fail on dead code warnings as well)
caps verify-drift --fail-on-violation --strict
```

---

## ⚖️ 5. Why Capsule Code Ingestion Beats Raw Vector RAG

| Dimension | Raw Code Chunking in Vector DBs | Capsule Code-to-Atomic Extraction |
|---|---|---|
| **Storage Granularity** | Arbitrary text chunks (1,000s of tokens with noise) | Atomic files, classes, and functions (100–250 tokens) |
| **Interconnectedness** | Disconnected floating embeddings | Typed graph (`defines`, `calls`, `imports`, `implements`) |
| **Cross-Layer Governance**| No link between architectural decisions and code | Automatic bidirectional links from ADRs to Code |
| **Drift Auditing** | None | Automated dead code and boundary violation checks (`caps verify-drift`) |
| **Human Auditability** | Impossible to diff binary vectors | Plain Markdown files in Git (`.caps.md`) |
