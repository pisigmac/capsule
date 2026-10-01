# Codebase-to-Capsule Ingestion: Transforming Source Code into Atomic Knowledge Graphs

Capsule allows developers to transform entire software repositories (Python, TypeScript, Go, Rust, etc.) into **atomic knowledge capsules and relationship dependency graphs**.

Instead of dumping raw syntax and boilerplate into vector databases, Capsule extracts **architectural invariants, schema contracts, public APIs, and structural dependency trees**.

---

## 🏗️ 1. Conceptual Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Source Codebase                         │
│            (Python, TypeScript, Go, Rust, etc.)             │
└──────────────────────────────┬──────────────────────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
     [ AST Structural Parsing ]       [ Invariant Extraction ]
     • Classes & Core Interfaces      • `# INVARIANT:` & Comments
     • Type Models (Pydantic, etc.)   • Preconditions & Assertions
     • Public Function Contracts      • Middleware & Route Configs
               │                               │
               └───────────────┬───────────────┘
                               ▼
     ┌──────────────────────────────────────────────────┐
     │       Generated Atomic Capsules (.caps.md)       │
     │  "Postgres Pool Max Overflow Invariant"          │
     │  "JWT Rotation & HttpOnly Security Policy"       │
     │  "Sliding Window Rate Limiter Specification"     │
     └─────────────────────────┬────────────────────────┘
                               ▼
     ┌──────────────────────────────────────────────────┐
     │           Derived Relationship Graph             │
     │  (Imports, Inherits, Calls, Depends-On Edges)    │
     └──────────────────────────────────────────────────┘
```

---

## 🔍 2. What Gets Extracted from Code?

1. **Architectural Invariants & Guardrails**:
   * Comments tagged with `# INVARIANT:`, `// RULE:`, or security assertions in middleware (e.g., *"All mutations must verify tenant ID before write"*).
2. **Data Models & Schema Contracts**:
   * Pydantic schemas, SQLAlchemy models, and TypeScript interfaces are extracted as atomic single-source-of-truth definitions.
3. **Subsystem Flow & Contracts**:
   * Function signatures, required preconditions, expected exceptions, and return contracts.
4. **Configuration Defaults & Sizing Limits**:
   * Hardcoded limits (e.g., connection pool max overflow, cache TTLs, rate limit ceilings).

---

## 🕸️ 3. Automatic Relationship Discovery from Code

When code is ingested, Capsule constructs an explicit **Knowledge Relationship Graph** by tracing:
* **Import & Dependency Trees**: When `AuthService` imports `TokenManager`, Capsule creates a `depends_on` edge.
* **Inheritance & Implementation**: When `PostgresStore` inherits from `BaseStore`, Capsule creates a `relates_to` or `implements` edge.
* **Call Chains**: Traces multi-hop flow from API routes &rarr; Service logic &rarr; Database queries.

---

## ⚖️ 4. Why Code-to-Capsule Beats Raw Code Vector RAG

| Dimension | Raw Code Chunking in Vector DBs | Capsule Code-to-Atomic Extraction |
|---|---|---|
| **What gets stored** | Long, syntax-heavy raw code blocks (1,000s of tokens) | Distilled behavioral rules, invariants, and API contracts (100–250 tokens) |
| **Token Efficiency** | Wastes 80% of prompt space on brackets, boilerplate, imports | Packs only the exact invariant needed by the AI coding assistant |
| **Interconnectedness** | Independent, disconnected embeddings | Fully linked dependency graph matching actual module imports |
| **Human Auditability** | Raw vector embeddings cannot be edited | Stored as `.caps.md` files that developers can tune or git-commit |

---

## 🚀 5. CLI Usage Examples

```bash
# Ingest entire source codebase
caps ingest ./services/ -t backend -t architecture

# Ingest specific subsystem
caps ingest ./services/store/ --confidence high

# Ingest and preview extracted atomic units without saving
caps ingest ./services/api/ --dry-run
```
