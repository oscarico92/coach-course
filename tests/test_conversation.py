"""Tests des questions de suivi (src/conversation.py) et des prévisions de l'interface, sans modèle ni réseau.

    python tests/test_conversation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.conversation as conv  # noqa: E402
from src.tools import impl  # noqa: E402
from src.tracing import Trace  # noqa: E402

ok = total = 0


def check(label, cond):
    global ok, total
    total += 1
    ok += bool(cond)
    print(("OK   " if cond else "ÉCHEC") + " " + label)


def fake_chat(reply):
    def chat(messages, tools=None, **kw):
        chat.seen = messages
        return {"content": reply, "tool_calls": [], "message": {"role": "assistant", "content": reply},
                "prompt_tokens": 40, "completion_tokens": 12, "latency_s": 0.0}
    chat.seen = None
    return chat


hist = [{"question": "Quelle est la séance de fractionné de la semaine 6 du plan 10 km ?",
         "answer": "5 × 1000 m à 90 % VMA, récup 2 min [plan_10km_50min.md]"}]

conv.chat = fake_chat("ne doit pas servir")
check("sans historique : question inchangée, aucun appel au modèle",
      conv.standalone_question("Et la semaine 2 ?", []) == "Et la semaine 2 ?" and conv.chat.seen is None)

conv.chat = fake_chat("« Quelle est la séance de fractionné de la semaine 2 du plan 10 km ? »")
tr = Trace(3, "Et pour la semaine 2 ?")
q = conv.standalone_question("Et pour la semaine 2 ?", hist, tr)
check("question de suivi réécrite, guillemets retirés",
      q == "Quelle est la séance de fractionné de la semaine 2 du plan 10 km ?")
check("historique transmis au modèle, réécriture tracée (tokens et étape)",
      "semaine 6 du plan 10 km" in conv.chat.seen[1]["content"] and tr.total_tokens == 52
      and any(s["type"] == "reformulation" for s in tr.data["steps"]))

conv.chat = fake_chat("")
check("sortie vide : question d'origine", conv.standalone_question("Et pour la semaine 2 ?", hist) == "Et pour la semaine 2 ?")
conv.chat = fake_chat("x" * 500)
check("sortie aberrante (trop longue) : question d'origine", conv.standalone_question("Et après ?", hist) == "Et après ?")

long_hist = [{"question": f"q{i}", "answer": "r" * 1000} for i in range(6)]
text = conv._history_text(long_hist)
check("historique limité aux 3 derniers échanges, réponses tronquées",
      "q2" not in text and "q3" in text and "q5" in text and len(text) < 3 * 480)


class FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"daily": {"time": ["2026-11-26", "2026-11-27"], "temperature_2m_max": [9.5, 31.0],
                          "wind_speed_10m_max": [12.0, 55.0], "weather_code": [3, 95]}}


impl.requests.get = lambda url, **kw: (setattr(FakeResp, "params", kw["params"]), FakeResp())[1]
f = impl.previsions("2026-11-26", 2)
check("prévisions : une requête pour la période, orage détecté",
      FakeResp.params["end_date"] == "2026-11-27" and f[1]["orage"] and not f[0]["orage"] and f[1]["vent_kmh"] == 55.0)

print(f"\n{ok}/{total} tests réussis")
sys.exit(0 if ok == total else 1)
