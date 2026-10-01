# Capsule Benchmark Evaluation Datasets

This directory contains the standardized evaluation datasets used across all Capsule empirical benchmarks, including token efficiency, downstream frontier LLM multi-hop reasoning, memory bloat simulations, and retrieval latency profiles.

---

## 📂 Directory Contents

| File | Description | Records | Primary Usage |
| :--- | :--- | :---: | :--- |
| [`technical_corpus.json`](./technical_corpus.json) | 5 full-length software architecture specification documents | 5 docs (2,058 tok) | Baseline sliding-window chunking RAG |
| [`atomic_capsules.json`](./atomic_capsules.json) | 10 ground-truth atomic capsules with YAML frontmatter & SHA-256 hashes | 10 capsules (485 tok) | Capsule atomic composition & knapsack packing |
| [`benchmark_queries.json`](./benchmark_queries.json) | 5 multi-hop technical questions with ground-truth required facts & keywords | 5 queries | Multi-hop reasoning & downstream LLM accuracy |
| [`hotpotqa_100.json`](./hotpotqa_100.json) | 100 verified multi-hop reasoning questions from the official HotpotQA validation set | 100 questions | Pilot open-domain benchmark ($p < 10^{-15}$ validation) |
| [`hotpotqa_1000.json`](./hotpotqa_1000.json) | 1,000 verified multi-hop reasoning questions across 10,000 Wikipedia articles | 1,000 questions (6.1MB) | Large-scale public multi-hop benchmark ($p < 10^{-15}, t=28.42$) |
| [`bloat_simulation_stream.json`](./bloat_simulation_stream.json) | 100-submission agent memory stream across 50 execution steps (75% redundancy) | 100 observations | Long-term memory bloat & deduplication evaluation |
| [`load_dataset.py`](./load_dataset.py) | Python helper module providing typed loader functions for all datasets | — | Seamless benchmark reproduction |

---

## 📊 Dataset Specifications & Schemas

### 1. Technical Corpus (`technical_corpus.json`)
Consists of five interconnected software engineering documents representing a complex modern microservice architecture:
- `doc_auth_incident`: Staging JWT bypass rules and mobile CI pipeline dependencies.
- `doc_database_arch`: SQLite FTS5 vs. PostgreSQL 16 GIN indexing and zero-loss index recovery.
- `doc_dedup_protocol`: Normalized SHA-256 content deduplication and HTTP 409 conflict handling.
- `doc_mcp_interface`: Model Context Protocol FastMCP server with stdio and Streamable HTTP modes.
- `doc_sync_watcher`: Real-time filesystem watchdog service with 250ms debouncing.

```json
{
  "id": "doc_auth_incident",
  "title": "Incident 4482: Auth Middleware in Staging",
  "domain": "Authentication & CI/CD",
  "text": "# Incident Postmortem: Auth Middleware in Staging...",
  "characters": 1152,
  "tokens": 248
}
```

### 2. Atomic Capsules (`atomic_capsules.json`)
The exact same technical knowledge decomposed into self-contained, canonical atomic units (*"one fact per capsule"*):

```json
{
  "id": "cap-auth-bypass",
  "topic": "Staging Auth Bypass via Header",
  "content": "Staging skips JWT verification when `X-Debug-Override` header is present. This is intentional for mobile E2E CI tests. Rejected with HTTP 400 in production.",
  "tags": ["auth", "staging", "ci", "jwt"],
  "confidence": "high",
  "source_doc_id": "doc_auth_incident",
  "tokens": 37,
  "hash": "b2f6..."
}
```

### 3. Multi-Hop Benchmark Queries (`benchmark_queries.json`)
Five challenging multi-hop queries designed such that answering correctly requires synthesizing facts from separate architectural subcomponents:

```json
{
  "id": "Q1",
  "query": "How does staging bypass JWT authentication, and what CI pipeline depends on it?",
  "search_terms": "staging JWT bypass",
  "domain": "Authentication & Continuous Integration",
  "tags": ["auth", "ci"],
  "required_facts": [
    "Staging skips JWT verification when `X-Debug-Override` header is present",
    "Mobile CI automation pipelines (Android/iOS integration suites) depend directly on the `X-Debug-Override` auth bypass"
  ],
  "keywords": ["staging", "JWT", "X-Debug-Override", "mobile", "CI"],
  "relevant_capsule_ids": ["cap-auth-bypass", "cap-auth-dep"]
}
```

### 4. Public Multi-Hop Benchmark (`hotpotqa_100.json`)
Contains 100 questions from the official HotpotQA validation set (distractor split). Each entry includes:
- `_id`: Unique HotpotQA question ID.
- `question`: Multi-hop natural language query.
- `answer`: Ground-truth answer string.
- `supporting_facts`: List of `[title, sentence_index]` pairs containing the necessary supporting evidence.
- `context`: 10 distinct Wikipedia paragraphs (2 gold supporting articles + 8 distractor articles).

### 5. Multi-Turn Bloat Stream (`bloat_simulation_stream.json`)
Chronological stream of 100 observations emitted by an autonomous agent over a 50-step iterative development cycle:
- **Redundancy Rate**: 75% recurring facts, simulating periodic status probes, retry loops, and environment re-checks.
- Used to benchmark cumulative disk and token storage growth of append-only vector databases vs. Capsule's asymptotic deduplication.

---

## 🚀 How to Load and Use in Python

```python
from evals.data.load_dataset import (
    load_technical_corpus,
    load_atomic_capsules,
    load_benchmark_queries,
    load_hotpotqa_100,
    load_bloat_simulation_stream,
)

# Load technical corpus and atomic capsules
corpus = load_technical_corpus()
capsules = load_atomic_capsules()
queries = load_benchmark_queries()

print(f"Loaded {len(corpus)} documents, {len(capsules)} capsules, {len(queries)} queries.")

# Load 100-question HotpotQA benchmark
hotpotqa_data = load_hotpotqa_100()
print(f"Loaded {len(hotpotqa_data)} HotpotQA questions.")

# Load 50-step agent memory stream
stream = load_bloat_simulation_stream()
print(f"Loaded {len(stream)} agent observations.")
```
