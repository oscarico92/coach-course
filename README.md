# Coach Course : un assistant de course à pied qui se mesure

Projet IA générative 2026 (Dr. Issam Falih), parcours **Texte**.
Un assistant qui répond aux questions sur l'entraînement à la course à pied et planifie des séances,
construit en 4 niveaux comparés sur le même jeu de test.

| Niveau | Description | Fichier |
|---|---|---|
| 0 | LLM seul, prompt soigné | `src/levels/level0.py` |
| 1 | RAG : recherche hybride (dense + BM25), citations, abstention | `src/levels/level1_rag.py` |
| 2 | Agent outillé (agent seul) : allures, météo, calendrier .ics (écriture confirmée), règles du club vérifiées par le code | `src/levels/level2_agent.py` |
| 3 | Extension multi-agents : orchestrateur, agent documentaire (RAG) et agent actions (outils), rapports JSON | `src/levels/level3_ext.py` |

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

### Modèle API (OpenAI)

Pour utiliser le modèle fourni (`gpt-6-luna`) au lieu de qwen, dans `.env` (jamais versionné) :

```
LLM_PROVIDER=openai
LLM_MODEL=gpt-6-luna
OPENAI_API_KEY=...
```

Les embeddings restent locaux (`bge-m3` via Ollama) : la recherche du RAG est la même pour les deux modèles.
Le nom du modèle apparaît dans la colonne « Niveau » du tableau de `eval.py`.

## Utilisation

```bash
python eval.py                     # tous les niveaux sur data/tests.jsonl, avec pass^3 (tableau du rapport)
python eval.py --pass-k 0          # sans pass^3, plus rapide
python eval.py --levels 0 --limit 5
streamlit run app.py               # interface
```

Interface : conversation (historique de la session, « Régénérer »), choix du modèle et du niveau (3 par défaut),
confirmation de chaque ajout au calendrier, trace de chaque réponse, export du calendrier en .ics et prévisions
Open-Meteo à 7 jours. Option « Questions de suivi » : la question est réécrite en question autonome à partir des
derniers échanges (`src/conversation.py`) avant d'être passée au niveau, qui reste inchangé ; non mesurée par
`eval.py`, dont le jeu de test ne contient que des questions isolées.

```bash
```

Résultats : `results/` (réponses brutes par niveau + tableau récapitulatif).
Traces d'exécution : `traces/*.jsonl` (étapes, outils, arguments, tokens, durée).

## Résultats

Comparaison des niveaux, de l'architecture du niveau 2 et des modèles (qwen2.5:7b, gpt-6-luna) :
[`docs/RESULTATS.md`](docs/RESULTATS.md).

Le tableau du rapport compte deux runs de `python eval.py`, un par modèle :

| Modèle | Réglages (`.env`) | Résultats bruts et traces |
|---|---|---|
| qwen2.5:7b (défaut) | `LLM_PROVIDER=ollama`, `LLM_MODEL=qwen2.5:7b` | `resultats_finaux/qwen2.5-7b/` |
| gpt-6-luna | `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-6-luna`, `OPENAI_REASONING_EFFORT=none`, `OPENAI_API_KEY` | `resultats_finaux/gpt-6-luna/` |

`python eval.py --rescore <dossier>` recalcule un tableau archivé sans rappeler les modèles.

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
