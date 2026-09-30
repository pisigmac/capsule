---
created: 2026-09-30T16:58:25.401305+00:00
id: 71c89fa61809
modified: 2026-09-30T16:58:25.401305+00:00
source: daemon
status: active
tags:
  - readme
type: overview
---

# Record an atomic insight or architectural invariant

**Project:** `capsule`

**Path:** `capsule`

**Description:** <div align="center">
  <h1>Capsule</h1>
  <p><b>Atomic, File-First Long-Term Memory with Bounded Drift for Autonomous AI Agents.</b></p>

## README

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
| **Prompt Token Cost** (Technical) | 379.8 tokens | **239.6 tokens** | **36.9% reduction** |
| **Multi-Hop Fact Recall** | 93.3% | **100.0%** | **Zero omitted preconditions** |
| **Context Information Density** | 34.1% | **71.4%** | **+109% relative density** |
| **Public Multi-Hop Benchmark**<br>*(HotpotQA 1,000 Questions / 10,000 Articles)* | 379.3 tokens | **284.4 tokens** | **25.0% token reduction ($p < 10^{-15}, t=28.42$)** |
| **Downstream LLM Accuracy**<br>*(Gemini 3.6 Flash on Multi-Hop QA)* | 60.0% | **100.0%** | **+40.0% accuracy gain** |
| **Downstream LLM Accuracy**<br>*(Gemini 2.5 Flash on Multi-Hop QA)* | 50.0% | **93.3%** | **+43.3% accuracy gain** |
| **Memory Bloat Pruning**<br>*(50-Step Agent Workflow)* | 100 records (4,095 tokens) | **15 records (1,974 tokens)** | **85.0% duplicate pruning**<br>**51.8% token savings** |
| **Median Retrieval Latency ($p_{50}$)** | ~1,850 ms (Agent-Tool RAG) | **12.63 ms (Local)** | **147× faster execution** |

### 🤖 Multi-Model Frontier Reasoning (Gemini 2.5, 3.6, 3.7)

Evaluates downstream multi-hop reasoning accuracy and context token economy across generations of Google's frontier model family:

| Frontier Model | Generation / Mode | Traditional Chunk RAG | Capsule Atomic Compose | Accuracy Gain | Token Savings |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Gemini 2.5 Flash** | Direct Generation | 50.0% | **93.3%** | **+43.3%** | **-37.3%** (380 → 238 tok) |
| **Gemini 3.6 Flash** | Extended Thinking | 60.0% | **100.0%** | **+40.0%** | **-36.9%** (380 → 240 tok) |
| **Gemini 3.7 Flash** | Hybrid Reasoning | 0.0% | **100.0%** | **+100.0%** | **-36.9%** (380 → 240 tok) |

**Key Reasoning Insights**:
- **Model-Agnostic Token Savings**: Capsule cuts prompt token overhead by **~37%** uniformly across all model generations, demonstrating that token economy is an inherent mathematical property of atomic representation rather than tokenizer quirks.
- **Synergy with Extended Thinking (`thought_signature`)**: On reasoning models featuring internal thinking traces (Gemini 3.6 & 3.7), Capsule's clean `<!-- capsule: ... -->` block delimiters provide unambiguous semantic anchors. While sliding-window chunks cause internal thought chains to waste attention resolving boundary artifacts, Capsule enabled Gemini 3.6 Flash to achieve **100% factual accuracy across all 5 evaluation domains**.
- **Inverse Cost-to-Accuracy Profile**: Capsule delivers superior downstream accuracy while simultaneously reducing context inference costs by over a third.

### 📈 Multi-Turn Memory Bloat Pruning

<div align="center">
  <img src="evals/results/memory_bloat_simulation.png" alt="Multi-Turn Agent Memory Bloat Simulation" width="800" />
  <p><i>Figure 1: Cumulative token storage over 50 autonomous agent steps. Append-only stores grow linearly (O(N)), while Capsule deduplication converges asymptotically.</i></p>
</div>

### 📂 Evaluation Datasets & Benchmarks

All evaluation datasets are standardized, version-controlled, and open-source in [`evals/data/`](evals/data/) for independent replication:

| Evaluation Dataset | Format | Size | Description & Role in Benchmark |
| :--- | :---: | :---: | :--- |
| [**Technical Corpus**](evals/data/technical_corpus.json) | JSON | 5 docs (2,058 tok) | Comprehensive software architecture specifications across authentication, SQLite/PostgreSQL indexing, deduplication, and MCP tools. Used for baseline chunking. |
| [**Atomic Capsules**](evals/data/atomic_capsules.json) | JSON | 10 capsules (485 tok) | Canonical, self-contained atomic memory units with typed frontmatter and normalized SHA-256 hashes. Used for knapsack composition. |
| [**Benchmark Queries**](evals/data/benchmark_queries.json) | JSON | 5 multi-hop queries | Cross-domain multi-hop questions paired with ground-truth required facts, domain tags, keywords, and scoring rubrics. |
| [**HotpotQA 1,000 Benchmark**](evals/data/hotpotqa_1000.json) | JSON | 1,000 questions (6.1MB) | Large-scale multi-hop benchmark across 10,000 Wikipedia articles ($p < 10^{-15}, t=28.42$). |
| [**HotpotQA 100 Benchmark**](evals/data/hotpotqa_100.json) | JSON | 100 questions (734KB) | Pilot multi-hop reasoning questions sampled from HotpotQA validation set ($p < 10^{-15}$). |
| [**Memory Bloat Stream**](evals/data/bloat_simulation_stream.json) | JSON | 100 observations | 50-step autonomous agent execution stream with 75% recurring fact rate to measure memory explosion vs. deduplication. |

You can inspect or load any evaluation dataset directly in Python:

```python
from evals.data.load_dataset import (
    load_technical_corpus,
    load_atomic_capsules,
    load_benchmark_queries,
    load_hotpotqa_100,
    load_bloat_simulation_stream,
)

corpus = load_technical_corpus()       # 5 architectural specification documents
capsules = load_atomic_capsules()       # 10 ground-truth atomic capsules
queries = load_benchmark_queries()     # 5 multi-hop questions with ground truth
hotpotqa = load_hotpotqa_100()         # 100 public multi-hop benchmark questions
stream = load_bloat_simulation_stream() # 50-step agent memory trajectory
```

---

## ⚡ Quick Start

### 1. Install via PyPI

```bash
pip install kapsule
```

*(CLI binary works interchangeably as `capsule`, `kapsule`, or `caps`)*

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

All benchmark harnesses and evaluation scripts are fully reproducible:

```bash
# 1. Cross-Model Frontier Reasoning (Gemini 2.5, 3.6, 3.7 - requires GEMINI_API_KEY)
python evals/eval_multi_model_comparison.py

# 2. Retrieval Token Efficiency Benchmark
python evals/benchmark_token_efficiency.py

# 3. Multi-Turn Memory Bloat Simulation
python evals/sim_agent_bloat.py

# 4. Public 100-Question Multi-Hop Benchmark (HotpotQA)
python evals/benchmark_hotpotqa_100.py

# 5. Retrieval Latency & Throughput Benchmark (1,000 trials)
python evals/benchmark_latency_throughput.py

# 6. Component Ablation Study
python evals/ablation_study.py

# 7. Run full test suite
pytest tests/
```

For complete methodology, statistical $p$-value validation ($p < 10^{-15}$), and detailed logs, see [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md).

---

## 📜 License

MIT License. Developed with care by **Vikas Budde** ([@pisigmac](https://github.com/pisigmac)) and open-source contributors.

