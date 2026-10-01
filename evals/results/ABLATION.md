# Capsule Component Ablation Matrix

| Architecture Configuration | Avg Prompt Tokens | Fact Recall | Information Density | Redundancy Rate | Finding |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Full Capsule System (Hybrid + Budget + Dedup)** | `238.8` tok | **100.0%** | `71.5%` | `0.0%` | Optimal balance of token budget and complete recall |
| **Ablation 1: Lexical Only (FTS5, No Vectors)** | `238.8` tok | **100.0%** | `71.5%` | `0.0%` | Degraded efficiency / redundancy |
| **Ablation 2: Fixed Top-K (No Token Budget Packing)** | `238.8` tok | **100.0%** | `71.5%` | `0.0%` | Degraded efficiency / redundancy |
| **Ablation 3: No Deduplication (Append-only Bloat)** | `477.6` tok | **100.0%** | `71.5%` | `50.0%` | Degraded efficiency / redundancy |
