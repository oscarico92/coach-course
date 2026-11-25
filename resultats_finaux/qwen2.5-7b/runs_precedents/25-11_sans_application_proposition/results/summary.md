| Niveau | Recall@5 | MRR | Exactitude | Sources citées | Abstention | Abst. à tort | Ambigus OK | Succès tâches | Tâches non vues | pass^k | Tokens / req. | Latence (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 · LLM seul (qwen2.5:7b) | — | — | 8% | 0% | 100% | 44% | 80% | — | — | — | 312 | 14.62 |
| 1 · RAG (qwen2.5:7b) | 100% | 0.89 | 100% | 96% | 100% | 0% | 60% | — | — | — | 1178 | 19.15 |
| 2 · Agent (qwen2.5:7b) | — | — | 20% | 0% | 80% | 60% | 100% | 75% | 100% | 59% | 4191 | 27.74 |
| 3 · Multi-agents (qwen2.5:7b) | — | — | 92% | 80% | 100% | 0% | 100% | 75% | 100% | 59% | 4092 | 26.23 |
