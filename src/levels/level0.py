"""Niveau 0 : LLM seul, prompt soigné, sans documents ni outils. La référence à battre."""
from src.llm import chat

AVAILABLE = True

SYSTEM_PROMPT = """Tu es un coach de course à pied francophone, précis et prudent.
- Réponds de façon concise et concrète (allures en min/km, durées, nombre de séances).
- Si tu n'es pas sûr d'une information ou si la question sort de la course à pied,
  dis-le clairement plutôt que d'inventer. Commence alors ta réponse par « JE NE SAIS PAS ».
- Tu ne donnes pas d'avis médical : en cas de douleur ou de blessure, oriente vers un professionnel de santé.
- Tu n'as accès à aucun document ni outil : ne prétends pas avoir consulté une source."""


def answer(question, trace):
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}]
    res = chat(messages)
    trace.log_llm(res, note="réponse directe")
    text = res["content"].strip()
    return {
        "answer": text,
        "sources": [],
        "abstained": text.upper().startswith("JE NE SAIS PAS"),
        "tool_calls": [],
    }
