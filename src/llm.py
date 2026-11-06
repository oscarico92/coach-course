"""Client Ollama minimal, écrit sans framework (appels HTTP directs).

Renvoie le texte, les éventuels appels d'outils et les compteurs de tokens,
pour que chaque niveau puisse mesurer son coût de la même façon.
"""
import time
import requests

from config import OLLAMA_URL, LLM_MODEL, EMBED_MODEL, LLM_TEMPERATURE


def chat(messages, tools=None, model=LLM_MODEL, temperature=LLM_TEMPERATURE, seed=0):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "seed": seed},
    }
    if tools:
        payload["tools"] = tools
    t0 = time.perf_counter()
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    r.raise_for_status()
    data = r.json()
    msg = data.get("message", {})
    return {
        "content": msg.get("content", ""),
        "tool_calls": msg.get("tool_calls", []),
        "message": msg,
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "completion_tokens": data.get("eval_count", 0),
        "latency_s": time.perf_counter() - t0,
    }


def embed(texts, model=EMBED_MODEL):
    r = requests.post(f"{OLLAMA_URL}/api/embed", json={"model": model, "input": texts}, timeout=300)
    r.raise_for_status()
    return r.json()["embeddings"]
