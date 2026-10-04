# Developer Guide: How to Use Capsule & Core Benefits

Capsule is an **atomic, file-first knowledge engine** designed for autonomous AI agents, coding assistants (Cursor, Claude Desktop, Windsurf), and multi-agent systems (LangChain, CrewAI, LlamaIndex, PydanticAI).

This guide explains how developers use Capsule in practice and the architectural, economic, and reliability benefits it delivers.

---

## 🚀 1. How Developers Use Capsule

Capsule fits seamlessly into four developer workflows:

### Workflow A: The AI Coding Assistant (Cursor, Claude Desktop, Windsurf)

When building software with AI IDEs, developers often suffer from AI forgetting architectural rules or hallucinating outdated library APIs.

1. **One-Click Hookup**:
   ```bash
   pip install kapsule
   caps mcp install
   ```
   `caps mcp install` scans your machine, detects configuration files for Claude Desktop, Cursor, and Windsurf, and registers the Capsule Model Context Protocol (MCP) server automatically with zero manual JSON configuration.

2. **Ingest Codebase Knowledge & Architectural Invariants**:
   ```bash
   # Ingest source code (Python, TypeScript, Go, etc.) to extract models, API contracts & invariants
   caps ingest ./src/ --confidence high

   # Decompose existing markdown or rst specs into atomic facts
   caps ingest ./docs/architecture/

   # Harvest invariants and bug-fix lessons from merged PRs and git history
   caps ingest --git --limit 50
   caps ingest --pr --merged-only
   ```
   *(See [Codebase-to-Capsule Ingestion Guide](CODEBASE_INGESTION.md) for full architectural details.)*

3. **Autonomous Assistance**:
   While writing code, your IDE AI queries Capsule behind the scenes via MCP:
   * `"What are our PostgreSQL pool sizing rules?"` &rarr; Capsule returns the atomic `.caps.md` fact in <13ms.
   * `"Staging auth bypass invariant"` &rarr; Injected directly into the system prompt with zero noise.

---

### Workflow B: Multi-Agent Frameworks (LangChain, LlamaIndex, CrewAI, PydanticAI)

Instead of setting up external vector databases (Pinecone, Qdrant, Chroma), managing API keys, and dealing with embedding drift, developers add Capsule as memory in **3 lines of standard Python**.

#### 1. CrewAI Multi-Agent Shared Memory
```python
from crewai import Agent, Crew
from kapsule.adapters.crewai import CapsuleStorage

# Shared, git-trackable memory across all crew agents
shared_memory = CapsuleStorage(confidence_default="high")

researcher = Agent(role="Researcher", memory=True)
writer = Agent(role="Writer", memory=True)

crew = Crew(
    agents=[researcher, writer],
    memory=True,
    long_term_memory=shared_memory
)
```

#### 2. LangChain & LangGraph
```python
from kapsule.adapters.langchain import CapsuleMemory, CapsuleRetriever
from langchain.chains import ConversationalRetrievalChain

# Drop-in replacement for vector memory
memory = CapsuleMemory(confidence_min="high", max_tokens=800)
retriever = CapsuleRetriever(confidence_min="medium")

chain = ConversationalRetrievalChain.from_llm(
    llm=llm,
    retriever=retriever,
    memory=memory
)
```

#### 3. LlamaIndex RAG Pipeline
```python
from kapsule.adapters.llamaindex import CapsuleRetriever, CapsuleReader
from llama_index.core.query_engine import RetrieverQueryEngine

retriever = CapsuleRetriever(similarity_top_k=5, confidence_min="high")
query_engine = RetrieverQueryEngine.from_args(retriever)
```

#### 4. PydanticAI & LiteLLM Prompt Context Hook
```python
from pydantic_ai import Agent
from kapsule.adapters.pydantic_ai import capsule_context_hook

agent = Agent("openai:gpt-4o")

@agent.system_prompt
def add_capsules(ctx):
    # Dynamically inject knapsack-optimized verified facts into prompt hook
    return capsule_context_hook(ctx.prompt, max_tokens=500)
```

---

### Workflow C: Terminal Interactive Management & TUI

For developers who live in the terminal:

1. **Interactive Demo**:
   ```bash
   caps demo
   ```
   Runs a self-contained 30-second guided tour demonstrating atomic ingestion, SHA-256 deduplication, knapsack context composition, and search.

2. **Fuzzy TUI Browser**:
   ```bash
   caps browse
   # or
   caps tui
   ```
   Interactive keyboard navigation (`j`/`k` to navigate, `Enter` to preview, `/` to filter, `a` to archive, `d` to delete).

3. **Command Line Utilities**:
   ```bash
   caps new "Stripe webhook idempotency key handling" -t payments -t stripe -c high
   caps search "postgres pool size"
   caps compose --query "database configuration" --budget 300
   ```

---

### Workflow D: Team Knowledge Sharing & CI Gatekeeping

1. **Curated Knowledge Packs**:
   ```bash
   # Pull community or organization knowledge packs
   caps pull python-modern
   caps pull docker-hardening
   caps pull postgres-tuning
   ```

2. **OCI / Container Registry Distribution**:
   ```bash
   # Push your team's verified vault to Docker Hub or GitHub Container Registry (GHCR)
   caps login ghcr.io -u <username> -p <token>
   caps push ghcr.io/my-org/knowledge-vault:v1.0.0
   ```

3. **CI Gatekeeper in GitHub Actions (`.github/workflows/ci.yml`)**:
   ```yaml
   - name: Verify Capsule Vault Quality Gate
     run: |
       pip install kapsule
       caps ci check --strict
       caps lint
   ```
   Fails pull requests that introduce broken WikiLinks, conflicting facts, or stale confidence levels.

4. **Obsidian Vault Bi-directional Sync**:
   ```bash
   caps link-vault ~/Documents/Obsidian/TeamKnowledge
   ```

---

## 💎 2. Concrete Benefits for Developers

| Benefit Dimension | Traditional Vector DB RAG | Capsule Atomic Knowledge Engine | Measurable Gain |
|---|---|---|---|
| **Token & Prompt Cost** | 1,500 – 4,000 tokens per chunk dump | 200 – 400 tokens per knapsack context | **70% to 85% cost reduction** |
| **Hallucination Drift** | Unbounded memory drift ($O(N)$ bloat) | SHA-256 content deduplication | **Mathematically bounded drift** |
| **Auditability** | Opaque floating point vectors | Plain Markdown files (`.caps.md`) | **100% Git reviewable (PR diffs)** |
| **Retrieval Latency** | ~1,850 ms (Remote Vector DB API) | 12.63 ms (Local SQLite FTS5) | **147× faster execution** |
| **Downstream Accuracy** | 50.0% – 60.0% on multi-hop QA | 93.3% – 100.0% on frontier LLMs | **+40.0% accuracy gain** |
| **Zero Infrastructure** | Remote clusters, Docker containers, API keys | Embedded local files + SQLite/Postgres | **Zero setup friction (`pip install`)** |

---

### Key Architectural Advantages Explained

### 1. The End of "Context Window Churn"
Traditional RAG slices documents or conversation transcripts across arbitrary character windows (e.g. 500 characters). This splits interdependent logic in half and fills 80% of prompt windows with conversational filler (*"Hi, let me help you with that..."*).

Capsule represents knowledge as **atomic facts** (one invariant per file) and solves a **0/1 Knapsack Optimization Problem** to pack the highest-confidence facts into your exact token budget.

### 2. SHA-256 Content-Addressable Deduplication
When autonomous agents run in loops, they repeatedly observe the same facts. In vector stores, this leads to duplicate accumulation and memory degradation.

In Capsule, every fact is normalized and hashed with SHA-256. Redundant agent submissions merge tags and increment revision counts with **zero duplicate files written to disk**.

### 3. Human-in-the-Loop Git Native Control
If an AI agent records an incorrect memory in a vector database, finding and deleting the offending embedding is nearly impossible.

In Capsule, every memory is a `.caps.md` file in your repository. You can inspect it, edit it in VS Code/Vim/Cursor, review it in a GitHub Pull Request, or revert it with `git revert`.

---

## 📚 Related Documentation
* [Architecture Specification](ARCHITECTURE.md)
* [Empirical Benchmarks & Statistical Validation](BENCHMARKS.md)
* [API Reference](API.md)
* [Database Schema](DB_SCHEMA.md)
