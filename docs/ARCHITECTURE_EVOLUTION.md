# Capsule Architectural Evolution: Next-Generation Agent Memory Blueprint

This document outlines the strategic architectural roadmap and future evolutionary pillars for **Capsule**, transitioning it from a single-agent/local knowledge engine into an enterprise-grade, multi-agent operating system memory backbone.

---

## 🏛️ 1. Core Architectural Pillars (Immutable Foundations)

Capsule's architectural integrity rests on three non-negotiable principles:

1. **Storage Plane / Retrieval Plane Decoupling**:
   * **Storage Plane (Source of Truth)**: Canonical, human-readable Markdown files (`.caps.md`) on the filesystem with typed YAML frontmatter.
   * **Retrieval Plane (Derived Accelerators)**: Sub-millisecond SQLite FTS5 / PostgreSQL `tsvector` + GIN indexes and dense vector embeddings. If the database is dropped or corrupted, `caps reconcile` rebuilds the entire index from disk in milliseconds.
2. **Normalized Content-Addressable Deduplication**:
   * Facts are fingerprinted with SHA-256 digests. Redundant observations merge tags and update timestamps rather than creating duplicate file blobs, bounding index growth to $O(1)$ for repetitive tasks.
3. **Mathematical 0/1 Knapsack Optimization**:
   * Context injection is formulated as a token-bounded knapsack problem maximizing relevance subject to $\sum \text{tokens}(\mathcal{C}_i) \le B$, eliminating arbitrary middle-sentence boundary truncation.

---

## 🔮 2. Next-Generation Architectural Evolutions

```
┌────────────────────────────────────────────────────────────────────────┐
│               Capsule Next-Gen Architectural Pillars                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
│        Pillar 1         │ │        Pillar 2         │ │        Pillar 3         │
│   Graph-Aware Multi-Hop │ │  Automated Invariant    │ │  Reciprocal Rank Fusion │
│   Knapsack Composition  │ │  Supersession Engine    │ │     (RRF Calibration)   │
└─────────────────────────┘ └─────────────────────────┘ └─────────────────────────┘
```

---

### Pillar 1: Graph-Aware Multi-Hop Knapsack Composition

#### The Challenge
Currently, the knapsack optimization algorithm evaluates candidate capsules independently based on individual lexical/semantic relevance $S(q, \mathcal{C}_i)$. If Capsule A (*"Staging Auth Bypass"*) is selected, but its crucial prerequisite Capsule B (*"Debug Token Header Specification"*) has slightly lower independent semantic similarity to the query, Capsule B might be omitted, leading to incomplete agent context.

#### The Evolutionary Solution
Introduce **Graph-Aware Affinity Propagation** into the knapsack selection solver:

$$\text{Score}(\mathcal{C}_i) = S(q, \mathcal{C}_i) + \sum_{\mathcal{C}_j \in \text{Selected}} \alpha_{ij} \cdot \text{EdgeWeight}(\mathcal{C}_i, \mathcal{C}_j)$$

* Where $\alpha_{ij}$ is a relationship-type multiplier (`depends_on`: 1.5, `verifies`: 1.2, `relates_to`: 1.0).
* **Dependency Clustering**: If an atomic fact with outgoing `depends_on` edges is selected, the solver automatically pulls its dependency closure into the candidate knapsack pool.

---

### Pillar 2: Automated Invariant Contradiction & Supersession

#### The Challenge
Software architectures evolve. A rule recorded in January (*"PostgreSQL pool size max overflow is 20"*) may be superseded in March (*"PostgreSQL pool size max overflow upgraded to 50"*). While Capsule tracks temporal freshness, contradictory facts could theoretically both be retrieved if both match a broad query.

#### The Evolutionary Solution
Implement an **Active Invariant Supersession & Contradiction Resolver**:

1. **Semantic Contradiction Detection**: On ingestion of a new capsule whose topic and tags strongly overlap with an existing capsule, an NLI (Natural Language Inference) contradiction check is performed.
2. **Automated Supersession Linking**:
   ```yaml
   ---
   id: b8f4a102...
   topic: "PostgreSQL Connection Pool Sizing v2"
   relationships:
     - to: c1a82f90...
       type: "supersedes"
   confidence: high
   ---
   ```
3. **Dynamic Deprecation & Penalty**:
   * The superseded capsule has its confidence automatically downgraded to `deprecated` or `historical`.
   * Knapsack filtering automatically excludes superseded capsules from active prompt context unless explicitly queried with `--include-deprecated`.

---

### Pillar 3: Scale-Free Reciprocal Rank Fusion (RRF)

#### The Challenge
Combining lexical BM25/FTS5 scores (unbounded positive floats) with dense embedding cosine similarity (bounded $[-1, 1]$) requires sensitive heuristic threshold tuning across varying query lengths.

#### The Evolutionary Solution
Standardize the dual-plane retrieval engine on **Reciprocal Rank Fusion (RRF)**:

$$R(d) = \sum_{m \in \{\text{FTS5}, \text{Dense}\}} \frac{w_m}{k + \text{rank}_m(d)}$$

* **Constant Smoothing**: $k = 60$ (empirically validated standard).
* **Scale Independence**: Combines exact keyword precision (e.g. specific function names `CapsuleStore.reconcile`, error codes `409 Conflict`) with conceptual understanding without score calibration drift.

---

### Pillar 4: Multi-Agent Branchless CRDT Frontmatter Sync

#### The Challenge
When swarms of 50+ autonomous agents operate across concurrent Git branches, simultaneous updates to the same invariant's metadata (e.g. Agent A adds tag `#auth`, Agent B adds tag `#security`) could trigger Git merge conflicts on the YAML frontmatter.

#### The Evolutionary Solution
Incorporate **Conflict-Free Replicated Data Types (CRDT)** for Capsule YAML frontmatter:
* **Tags & Aliases**: Modeled as an Observed-Remove Set (OR-Set) allowing deterministic commutative union during Git merges.
* **Confidence & Timestamps**: Modeled as Last-Write-Wins (LWW) registers with monotonic epoch counters.
* **Custom Git Merge Driver (`caps merge-driver`)**: Automatically resolves frontmatter merges during `git merge` or `git rebase` without human intervention.

---

## 📊 Summary of Architectural Progression

| Capability | Current State (v0.5.0) | Next-Gen Architecture (v1.0.0+) |
|---|---|---|
| **Context Packing** | Standard 0/1 Knapsack | Graph-Aware Multi-Hop Affinity Knapsack |
| **Temporal Logic** | Timestamp decay & Stale warnings | Automated NLI Contradiction & Supersession |
| **Hybrid Search** | Lexical + Dense thresholding | Scale-Free Reciprocal Rank Fusion (RRF) |
| **Multi-Agent Sync** | File-per-fact isolation | CRDT Frontmatter Auto-Merge Driver |
| **Ecosystem Hooks** | LangChain, LlamaIndex, CrewAI, PydanticAI | Autonomous Multi-Agent Swarm Orchestration |

---

## 📚 Related Specifications
* [Architecture Specification](ARCHITECTURE.md)
* [Developer Guide & Workflows](DEVELOPER_GUIDE.md)
* [Codebase Ingestion Blueprint](CODEBASE_INGESTION.md)
* [Empirical Benchmarks](BENCHMARKS.md)
