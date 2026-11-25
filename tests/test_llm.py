"""Tests du client OpenAI de src/llm.py, SANS réseau ni clé : requests.post est simulé.

    python tests/test_llm.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.llm as llm  # noqa: E402

ok = total = 0


def check(label, cond):
    global ok, total
    total += 1
    ok += bool(cond)
    print(("OK   " if cond else "ÉCHEC") + " " + label)


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.ok = status < 400
        self.text = json.dumps(body)

    def json(self):
        return self._body


def fake_post(replies):
    sent = []

    def post(url, json=None, timeout=None, headers=None):
        sent.append({"url": url, "json": json, "headers": headers})
        return replies.pop(0)
    post.sent = sent
    return post


# 1. conversion Ollama -> OpenAI : identifiants d'appel, arguments en chaîne, réponses d'outil associées
msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "meteo", "arguments": {"date": "2026-11-20"}}},
            {"id": "abc", "function": {"name": "lire_calendrier", "arguments": {"date_debut": "a", "date_fin": "b"}}}]},
        {"role": "tool", "tool_name": "meteo", "content": "{}"},
        {"role": "tool", "tool_name": "lire_calendrier", "content": "[]"},
        {"role": "user", "content": "relance"}]
o = llm.to_openai_messages(msgs)
calls = o[2]["tool_calls"]
check("appels : identifiant généré ou conservé, type function, arguments en chaîne JSON",
      calls[0]["id"] == "call_2_0" and calls[1]["id"] == "abc" and calls[0]["type"] == "function"
      and json.loads(calls[0]["function"]["arguments"]) == {"date": "2026-11-20"})
check("réponses d'outil associées dans l'ordre des appels", o[3]["tool_call_id"] == "call_2_0" and o[4]["tool_call_id"] == "abc"
      and "tool_name" not in o[3])
check("messages ordinaires inchangés", o[0] == {"role": "system", "content": "S"} and o[5]["content"] == "relance")

# 2. réponse OpenAI -> format Ollama (arguments décodés, identifiant gardé)
content, tc, msg = llm.from_openai_message({"role": "assistant", "content": None, "tool_calls": [
    {"id": "x1", "type": "function", "function": {"name": "meteo", "arguments": "{\"date\": \"2026-11-20\"}"}}]})
check("réponse : arguments décodés, contenu vide, identifiant conservé",
      content == "" and tc[0]["function"]["arguments"] == {"date": "2026-11-20"} and msg["tool_calls"][0]["id"] == "x1")
check("aller-retour : le message renvoyé se reconvertit avec le même identifiant",
      llm.to_openai_messages([msg])[0]["tool_calls"][0]["id"] == "x1")

# 3. appel complet : clé dans l'en-tête, paramètre refusé retiré puis requête relancée
llm.OPENAI_API_KEY, llm.PROVIDER = "cle-de-test", "openai"
llm._UNSUPPORTED.clear()
ok_body = {"choices": [{"message": {"role": "assistant", "content": "Bonjour"}}],
           "usage": {"prompt_tokens": 12, "completion_tokens": 3}}
post = fake_post([FakeResponse(400, {"error": {"param": "temperature", "message": "Unsupported value"}}),
                  FakeResponse(200, ok_body)])
llm.requests.post = post
res = llm.chat([{"role": "user", "content": "Q"}], model="gpt-6-luna", temperature=0.7, seed=1)
check("température refusée : retirée, requête relancée, réponse lue",
      res["content"] == "Bonjour" and len(post.sent) == 2 and "temperature" in post.sent[0]["json"]
      and "temperature" not in post.sent[1]["json"] and res["prompt_tokens"] == 12)
check("clé envoyée dans l'en-tête Authorization, pas dans le corps",
      post.sent[1]["headers"]["Authorization"] == "Bearer cle-de-test" and "cle-de-test" not in json.dumps(post.sent[1]["json"]))
post = fake_post([FakeResponse(200, ok_body)])
llm.requests.post = post
llm.chat([{"role": "user", "content": "Q"}], model="gpt-6-luna")
check("paramètre refusé une fois : plus envoyé ensuite", "temperature" not in post.sent[0]["json"])
post = fake_post([FakeResponse(401, {"error": {"message": "Incorrect API key"}})])
llm.requests.post = post
try:
    llm.chat([{"role": "user", "content": "Q"}], model="gpt-6-luna")
    check("erreur 401 : exception claire", False)
except RuntimeError as e:
    check("erreur 401 : exception claire", "401" in str(e))

# 4. raisonnement : « none » imposé avec des outils, réglage de .env sinon
llm.requests.post = post = fake_post([FakeResponse(200, ok_body), FakeResponse(200, ok_body), FakeResponse(200, ok_body)])
llm.chat([{"role": "user", "content": "Q"}], tools=[{"type": "function", "function": {"name": "meteo"}}], model="gpt-6-luna")
llm.OPENAI_REASONING_EFFORT = ""
llm.chat([{"role": "user", "content": "Q"}], model="gpt-6-luna")
llm.OPENAI_REASONING_EFFORT = "low"
llm.chat([{"role": "user", "content": "Q"}], model="gpt-6-luna")
check("avec outils : reasoning_effort « none » ; sans outils : absent par défaut, sinon valeur de .env",
      post.sent[0]["json"].get("reasoning_effort") == "none" and "reasoning_effort" not in post.sent[1]["json"]
      and post.sent[2]["json"].get("reasoning_effort") == "low")
llm.OPENAI_REASONING_EFFORT = ""

llm.OPENAI_API_KEY = ""
try:
    llm.chat([{"role": "user", "content": "Q"}])
    check("clé absente : message explicite", False)
except RuntimeError as e:
    check("clé absente : message explicite", ".env" in str(e))

print(f"\n{ok}/{total} tests réussis")
sys.exit(0 if ok == total else 1)
