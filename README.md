# Coach Course : un assistant de course à pied qui se mesure

Projet IA générative 2026 (Dr. Issam Falih), parcours **Texte**.
Un assistant qui répond aux questions sur l'entraînement à la course à pied et planifie des séances,
construit en 4 niveaux comparés sur le même jeu de test.

| Niveau | Description | Fichier |
|---|---|---|
| 0 | LLM seul, prompt soigné | `src/levels/level0.py` |
| 1 | RAG : recherche hybride (dense + BM25), citations, abstention | `src/levels/level1_rag.py` |
| 2 | Agent outillé : allures, météo, calendrier .ics (écriture confirmée) | `src/levels/level2_agent.py` |
| 3 | Extension (à définir d'après les défauts mesurés au niveau 2) | `src/levels/level3_ext.py` |

## Installation

1. Installer [Ollama](https://ollama.com), puis :
   ```bash
   ollama pull qwen2.5:7b
   ollama pull bge-m3
   ```
2. Environnement Python :
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows  (source .venv/bin/activate sous Linux/macOS)
   pip install -r requirements.txt
   copy .env.example .env          # cp sous Linux/macOS
   ```

## Utilisation

```bash
python eval.py                     # tous les niveaux disponibles sur data/tests.jsonl
python eval.py --levels 0 --limit 5
streamlit run app.py               # interface
```

Résultats : `results/` (réponses brutes par niveau + tableau récapitulatif).
Traces d'exécution : `traces/*.jsonl` (étapes, outils, arguments, tokens, durée).

## Arborescence

```
data/corpus/        documents du RAG (figés et versionnés)
data/tests.jsonl    jeu de test (>= 40 cas)
src/llm.py          client Ollama minimal (sans framework)
src/tracing.py      traces JSONL
src/levels/         un module par niveau, même interface : answer(question) -> dict
eval.py             reproduit le tableau de résultats
app.py              interface Streamlit
```

## Contrat commun des niveaux

Chaque niveau expose `answer(question: str, trace: Trace) -> dict` qui renvoie :

```python
{"answer": str, "sources": list[str], "abstained": bool, "tool_calls": list}
```

C'est ce qui permet à `eval.py` et à l'interface de traiter tous les niveaux de la même façon.
