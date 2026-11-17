"""Juge LLM pour l'exactitude des réponses (cas « in_docs »).

À calibrer sur 20 cas annotés à la main (data/judge_annotations.jsonl) :
python eval.py --calibrate-judge   -> accord juge / humain.
"""
import json
import re

from src.llm import chat

JUDGE_PROMPT = """Tu évalues la réponse d'un assistant de course à pied.
On te donne la question, la réponse de référence et la réponse de l'assistant.
La réponse de l'assistant est CORRECTE si elle contient les informations essentielles de la référence
(mêmes chiffres, mêmes semaines, même conclusion) sans les contredire. Des détails en plus sont acceptés
s'ils ne contredisent pas la référence. Une réponse qui dit ne pas savoir est INCORRECTE.
Réponds uniquement par un JSON : {"correct": true} ou {"correct": false}."""


def judge(question, expected, answer):
    messages = [{"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": f"Question : {question}\nRéférence : {expected}\nRéponse de l'assistant : {answer}"}]
    res = chat(messages, temperature=0)
    m = re.search(r"\{.*?\}", res["content"], re.S)
    try:
        verdict = bool(json.loads(m.group(0))["correct"]) if m else False
    except (json.JSONDecodeError, KeyError):
        verdict = False
    return verdict, res["prompt_tokens"] + res["completion_tokens"]
