"""Client LLM minimal, écrit sans framework (appels HTTP directs).

Deux fournisseurs, choisis par LLM_PROVIDER dans .env :
- ollama (défaut) : modèle local, ex. qwen2.5:7b ;
- openai : API OpenAI (Chat Completions), ex. gpt-6-luna, clé dans OPENAI_API_KEY (.env, jamais versionné).

Le reste du code ne voit qu'un format, celui d'Ollama : appels d'outils {"function": {"name", "arguments": dict}}
et messages d'outil {"role": "tool", "tool_name", "content"}. La conversion vers le format OpenAI (identifiants
d'appel, arguments en chaîne JSON) est faite ici.

Les embeddings restent locaux (Ollama, bge-m3) quel que soit le fournisseur : la recherche du RAG est identique,
seul le LLM change d'une mesure à l'autre.
"""
import json
import time

import requests

from config import (EMBED_MODEL, LLM_MODEL, LLM_PROVIDER, LLM_TEMPERATURE, OLLAMA_URL, OPENAI_API_KEY,
                    OPENAI_REASONING_EFFORT, OPENAI_URL)

# Valeurs par défaut modifiables à l'exécution (eval.py --pass-k fait varier la graine et la température ;
# l'interface choisit le fournisseur et le modèle dans sa barre latérale)
TEMPERATURE = LLM_TEMPERATURE
SEED = 0
PROVIDER = LLM_PROVIDER
MODEL = LLM_MODEL
# Paramètres refusés par le modèle OpenAI (temperature, seed, ou reasoning_effort pour un modèle sans
# raisonnement) : retirés après un refus
# et signalés une fois, car les mesures ne sont alors plus faites à la température demandée.
_UNSUPPORTED = set()


def chat(messages, tools=None, model=None, temperature=None, seed=None):
    model = MODEL if model is None else model
    temperature = TEMPERATURE if temperature is None else temperature
    seed = SEED if seed is None else seed
    t0 = time.perf_counter()
    if PROVIDER == "openai":
        out = _chat_openai(messages, tools, model, temperature, seed)
    else:
        out = _chat_ollama(messages, tools, model, temperature, seed)
    out["latency_s"] = time.perf_counter() - t0
    return out


# ------------------------------------------------------------------ Ollama
def _chat_ollama(messages, tools, model, temperature, seed):
    payload = {"model": model, "messages": messages, "stream": False,
               "options": {"temperature": temperature, "seed": seed}}
    if tools:
        payload["tools"] = tools
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    r.raise_for_status()
    data = r.json()
    msg = data.get("message", {})
    return {"content": msg.get("content", ""), "tool_calls": msg.get("tool_calls", []), "message": msg,
            "prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0)}


# ------------------------------------------------------------------ OpenAI
def to_openai_messages(messages):
    """Format Ollama -> format OpenAI. Les messages d'outil n'ont pas d'identifiant côté agent : ils reçoivent,
    dans l'ordre, ceux des appels du dernier message assistant (l'agent répond aux appels dans cet ordre)."""
    out, pending = [], []
    for k, m in enumerate(messages):
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = []
            for j, tc in enumerate(m["tool_calls"]):
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                calls.append({"id": tc.get("id") or f"call_{k}_{j}", "type": "function",
                              "function": {"name": fn.get("name", ""),
                                           "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}})
            pending = [c["id"] for c in calls]
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": calls})
        elif m.get("role") == "tool":
            out.append({"role": "tool", "tool_call_id": pending.pop(0) if pending else f"call_orphelin_{k}",
                        "content": m.get("content", "")})
        else:
            out.append({"role": m["role"], "content": m.get("content", "")})
    return out


def from_openai_message(msg):
    """Message OpenAI -> format Ollama (arguments décodés, identifiants gardés pour le tour suivant)."""
    calls = []
    for tc in msg.get("tool_calls") or []:
        args = tc.get("function", {}).get("arguments", "{}")
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except json.JSONDecodeError:
            pass  # chaîne laissée telle quelle : l'agent la traite (arguments vides) et le modèle reçoit l'erreur
        calls.append({"id": tc.get("id"), "function": {"name": tc.get("function", {}).get("name", ""), "arguments": args}})
    content = msg.get("content") or ""
    return content, calls, {"role": "assistant", "content": content, "tool_calls": calls}


def _chat_openai(messages, tools, model, temperature, seed):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY absente : l'ajouter dans .env (jamais dans le code ni dans un commit).")
    payload = {"model": model, "messages": to_openai_messages(messages), "temperature": temperature, "seed": seed}
    if tools:
        payload["tools"] = tools
        # gpt-6-luna : « Function tools with reasoning_effort are not supported … set reasoning_effort to 'none' »
        payload["reasoning_effort"] = "none"
    elif OPENAI_REASONING_EFFORT:
        payload["reasoning_effort"] = OPENAI_REASONING_EFFORT
    for _ in range(4):
        sent = {k: v for k, v in payload.items() if k not in _UNSUPPORTED}
        r = requests.post(f"{OPENAI_URL}/chat/completions", json=sent, timeout=300,
                          headers={"Authorization": f"Bearer {OPENAI_API_KEY}"})
        if r.status_code == 400:
            try:
                err = r.json().get("error", {})
            except ValueError:
                err = {}
            param = err.get("param")
            if param in ("temperature", "seed", "reasoning_effort") and param not in _UNSUPPORTED:
                _UNSUPPORTED.add(param)
                print(f"  [llm] {model} refuse « {param} » : paramètre retiré pour la suite ({err.get('message', '')[:120]})")
                continue
        if not r.ok:   # message d'erreur de l'API affiché (la réponse ne contient pas la clé)
            raise RuntimeError(f"OpenAI {r.status_code} : {r.text[:300]}")
        break
    data = r.json()
    content, calls, msg = from_openai_message(data["choices"][0]["message"])
    usage = data.get("usage", {})
    return {"content": content, "tool_calls": calls, "message": msg,
            "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0)}


def embed(texts, model=EMBED_MODEL):
    r = requests.post(f"{OLLAMA_URL}/api/embed", json={"model": model, "input": texts}, timeout=300)
    r.raise_for_status()
    return r.json()["embeddings"]
