<div align="center">
  <h1>Capsule</h1>
  <p><b>Atomic, File-First Long-Term Memory with Bounded Drift for Autonomous AI Agents.</b></p>

  <p>
    <a href="https://pypi.org/project/kapsule/"><img src="https://img.shields.io/pypi/v/kapsule.svg?color=blue" alt="PyPI version" /></a>
    <a href="https://pypi.org/project/kapsule/"><img src="https://img.shields.io/pypi/pyversions/kapsule.svg" alt="Python versions" /></a>
    <a href="https://github.com/pisigmac/capsule/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" /></a>
    <img src="https://img.shields.io/badge/tests-59%20passed-brightgreen.svg" alt="Tests: 59 passed" />
    <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-compatible-purple.svg" alt="MCP Compatible" /></a>
  </p>
</div>

---

Autonomous AI agents need persistent memory across sessions. However, traditional Retrieval-Augmented Generation (RAG) using fixed-window text chunking over append-only vector databases suffers from three fundamental pathologies:
1. **Semantic Fragmentation**: Slicing text across arbitrary character or token boundaries breaks interdependent preconditions and facts, causing hallucinations in multi-hop reasoning.
2. **Append-Only Memory Bloat**: Every agent turn indiscriminately writes redundant observations to the vector store, creating $O(N)$ memory explosion and context pollution.
3. **Black-Box Inauditability**: Opaque vector embeddings cannot be diffed, audited, or version-controlled using standard Git workflows.

**Capsule** solves this by establishing an **atomic fact representation** (*"one fact per Markdown file"*), pairing persistent Git-traceable filesystem storage with derived high-speed hybrid search indexes (SQLite FTS5 / PostgreSQL `tsvector` + dense embeddings).

---

## 📊 Empirical Benchmarks

Capsule was benchmarked against traditional sliding-window chunking RAG across retrieval efficiency, frontier LLM reasoning, and multi-turn memory accumulation:

| Metric | Traditional Chunk RAG (Baseline) | Capsule Atomic Compose | Outcome / Improvement |
| :--- | :---: | :---: | :--- |
| **Prompt Token Cost** | 379.8 tokens | **239.6 tokens** | **36.9% reduction** |
| **Multi-Hop Fact Recall** | 93.3% | **100.0%** | **Zero omitted preconditions** |
| **Context Information Density** | 34.1% | **71.4%** | **+109% relative density** |
| **Downstream LLM Accuracy**<br>*(Gemini 2.5 Flash on Multi-Hop QA)* | 50.0% | **93.3%** | **+43.3% accuracy gain** |
| **Memory Bloat Pruning**<br>*(50-Step Agent Workflow)* | 100 records (4,095 tokens) | **15 records (1,974 tokens)** | **85.0% duplicate pruning**<br>**51.8% token savings** |

<div align="center">
  <img src="evals/results/memory_bloat_simulation.png" alt="Multi-Turn Agent Memory Bloat Simulation" width="800" />
  <p><i>Figure 1: Cumulative token storage over 50 autonomous agent steps. Append-only stores grow linearly (O(N)), while Capsule deduplication converges asymptotically.</i></p>
</div>

---

## ⚡ Quick Start

### 1. Install via PyPI

```bash
pip install kapsule
```

*(Also available as `pip install korn` or `pip install pykorn`)*

### 2. Initialize a Knowledge Vault

```bash
capsule init
```

This initializes the local `capsules/` directory and sets up the high-speed SQLite FTS5 search index (`capsule.db`).

### 3. CLI Operations

```bash
# Record an atomic insight or architectural invariant
capsule new "Auth middleware bypass in staging" -t auth -t bug -c high

# Fast hybrid search across titles, tags, and content
capsule search "JWT"

# Compose an optimal context window packed to a strict token budget
capsule compose --query "database concurrency and auth" --budget 300

# Launch Model Context Protocol (MCP) server for Claude / Cursor
capsule mcp
```

---

## 🧠 Core Architecture & Features

### 1. Atomic Knowledge Units (Markdown + Frontmatter)
Every memory unit is stored as a canonical Markdown file under `capsules/<slug>.capsule.md`:

```markdown
---
id: 7c2a9f14-6b81-4d3e-9a0c-1f8e2b4d6c70
title: "Auth middleware bypass in staging"
tags: [bug, auth, staging]
created: 2026-07-11T00:00:00
source: "incident-4482"
confidence: high
hash: a4f8b2c19e73...
---

Staging skips JWT verification when `X-Debug-Override` is present.
This is intentional for E2E tests. Do not remove; mobile CI depends on it.
```

- **Human-in-the-Loop Auditability**: Edit, diff, and revert agent memories using standard text editors and Git.
- **Zero Lock-In**: The vault remains 100% functional even if all databases are removed.

### 2. Normalized Content-Hash Deduplication
When an agent submits redundant observations, Capsule computes a normalized SHA-256 digest of the content body:
- Existing records are updated with bumped timestamps, revision counters, and merged tags.
- Eliminates duplicate entries and bounds index growth indefinitely.

### 3. Token-Bounded Knapsack Context Composition
Rather than truncating arbitrary chunks when context limits are reached, `capsule compose` solves a **0-1 Knapsack Optimization Problem**:
- Maximizes relevance score $S(q, \mathcal{C}_i)$ subject to $\sum \text{tokens}(\mathcal{C}_i) \le B$.
- Packs 100% complete units of thought into the prompt window with zero middle-sentence cuts.

### 4. Dual-Plane Engine
- **Storage Plane (Source of Truth)**: Canonical Markdown files on the filesystem.
- **Retrieval Plane (Derived Accelerators)**: SQLite FTS5 / PostgreSQL `tsvector` + GIN inverted indexes for sub-millisecond lexical search, combined with dense sentence embeddings.

---

## 🤖 Agent & MCP Integration

Capsule includes native support for the **Model Context Protocol (MCP)**, allowing agents in **Claude Desktop**, **Cursor**, **AgentDrive**, and autonomous frameworks to read and write memories seamlessly.

### MCP Configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "capsule": {
      "command": "capsule",
      "args": ["mcp"]
    }
  }
}
```

### Registered Agent Tools:
- `search_capsules`: Hybrid lexical and semantic search over vault facts.
- `compose_context`: Packs relevant atomic facts into a token-bounded context window.
- `create_capsule`: Creates a new atomic capsule or merges into an existing hash.
- `get_capsule`: Fetches a complete capsule by slug or ID.
- `list_stale`: Surfaces outdated memories requiring agent refresh or verification.

---

## 🛠️ Local Development & Web UI

### Local Setup
```bash
git clone https://github.com/pisigmac/capsule.git
cd capsule
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
capsule init

# Launch API backend
uvicorn services.api.main:app --host 127.0.0.1 --port 9100 --workers 1
```

### Launch React Web UI
```bash
cd frontend
npm install
npm run dev
```
- **Web UI**: http://localhost:5173
- **API Endpoints**: http://localhost:9100/api/v1
- **Interactive Swagger Docs**: http://localhost:9100/docs

### Docker Deployment (PostgreSQL + API + Sync + UI)
```bash
./install.sh
```

---

## 🔬 Running Benchmarks

All benchmark harnesses and simulation scripts are fully reproducible:

```bash
# 1. Retrieval Token Efficiency Benchmark (Table 1)
python evals/benchmark_token_efficiency.py

# 2. Multi-Turn Memory Bloat Simulation (Figure 1)
python evals/sim_agent_bloat.py

# 3. Downstream Frontier LLM Accuracy (requires GEMINI_API_KEY)
python evals/eval_llm_accuracy.py

# 4. Component Ablation Study
python evals/ablation_study.py

# 5. Run full test suite
pytest tests/
```

---

## 📜 License

MIT License. Developed with care by **Vikas Budde** ([@pisigmac](https://github.com/pisigmac)) and open-source contributors.
