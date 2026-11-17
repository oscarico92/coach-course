"""Test de la boucle de l'agent SANS Ollama : le LLM est simulé par un script d'appels d'outils.

    python tests/test_agent_loop.py

Si les vrais outils (src/tools/impl.py) ne sont pas encore implémentés, des versions minimales
sont utilisées. Une fois impl.py terminé, lancer avec --vrais-outils pour tester aussi l'implémentation.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import tools                       # noqa: E402
from src.levels import level2_agent as agent  # noqa: E402
from src.tracing import Trace               # noqa: E402

USE_REAL = "--vrais-outils" in sys.argv
CAL = {}


def fake_lire(args, ctx):
    s = [x for x in CAL.get(ctx["calendar_path"], []) if args["date_debut"] <= x["date"] <= args["date_fin"]]
    return {"seances": s, "km_total": sum(x["km"] for x in s)}


def fake_ajouter(args, ctx):
    CAL.setdefault(ctx["calendar_path"], []).extend(args["seances"])
    return {"ajoutees": len(args["seances"]), "dates": [x["date"] for x in args["seances"]]}


def fake_meteo(args, ctx):
    return (ctx.get("weather") or {}).get(args["date"], {"tmax_c": 15, "vent_kmh": 10, "orage": False})


if not USE_REAL:
    tools.FUNCTIONS.update(lire_calendrier=fake_lire, ajouter_seances=fake_ajouter, meteo=fake_meteo,
                           calcul_allures=lambda a, c: {"allures": {"10 km (90 %)": "4:27"}})


def scripted_chat(script):
    """Renvoie une fonction chat() qui joue une suite de réponses (appels d'outils puis texte)."""
    steps = iter(script)

    def chat(messages, tools=None, **kw):
        step = next(steps, "Terminé.")
        if isinstance(step, str):
            msg, calls = {"role": "assistant", "content": step}, []
        else:
            calls = [{"function": {"name": n, "arguments": a}} for n, a in step]
            msg = {"role": "assistant", "content": "", "tool_calls": calls}
        chat.seen.append(messages[-1])
        return {"content": msg["content"], "tool_calls": calls, "message": msg,
                "prompt_tokens": 50, "completion_tokens": 10, "latency_s": 0.0}
    chat.seen = []
    return chat


def run(script, confirm=True, calendar=None, weather=None):
    path = Path(tempfile.mkdtemp()) / "cal.ics"
    CAL[path] = list(calendar or [])
    agent.chat = scripted_chat(script)
    out = agent.answer("test", Trace(2, "test"), confirm=lambda n, a: confirm,
                       context={"today": "2026-11-12", "weather": weather or {}, "calendar_path": path})
    return out, CAL[path], agent.chat.seen


S = lambda d, t, km=8: {"date": d, "titre": t, "type": t, "km": km}
ok = 0


def check(label, cond):
    global ok
    print(("OK   " if cond else "ÉCHEC") + " " + label)
    ok += cond
    return cond


# 1. écriture confirmée
out, cal, _ = run([[("ajouter_seances", {"seances": [S("2026-11-17", "fractionne"), S("2026-11-19", "endurance")]})]])
check("écriture confirmée : 2 séances ajoutées", len(cal) == 2 and out["asked_confirmation"])
# 2. refus de l'utilisateur
out, cal, _ = run([[("ajouter_seances", {"seances": [S("2026-11-17", "endurance")]})]], confirm=False)
check("refus de confirmation : rien n'est écrit", cal == [] and out["asked_confirmation"])
# 3. règle R2 : intense le lendemain d'une séance intense existante
out, cal, seen = run([[("ajouter_seances", {"seances": [S("2026-11-18", "fractionne")]})]],
                     calendar=[{"date": "2026-11-17", "titre": "Fractionné", "intense": True, "km": 8}])
check("R2 : refus d'une séance intense consécutive", len(cal) == 1 and "R2" in str(seen))
# 4. règle R5 : séance intense par 31 °C
out, cal, _ = run([[("ajouter_seances", {"seances": [S("2026-11-19", "seuil")]})]],
                  weather={"2026-11-19": {"tmax_c": 31, "vent_kmh": 10, "orage": False}})
check("R5 : refus d'une séance intense par forte chaleur", cal == [])
# 5. règle R1 : 48 km après une semaine à 40 km
prev = [{"date": d, "titre": "Footing", "intense": False, "km": k}
        for d, k in [("2026-11-09", 10), ("2026-11-11", 8), ("2026-11-13", 8), ("2026-11-15", 14)]]
out, cal, _ = run([[("ajouter_seances", {"seances": [S(f"2026-11-{d}", "endurance", 12) for d in (16, 18, 20, 22)]})]],
                  calendar=prev)
check("R1 : refus de +20 % de volume", len(cal) == 4)
# 6. erreur d'outil renvoyée au modèle, puis correction
out, cal, seen = run([[("ajouter_seances", {"seances": [S("2026-11-17", "sprint")]})],
                      [("ajouter_seances", {"seances": [S("2026-11-17", "endurance")]})]])
check("erreur d'outil renvoyée au modèle puis corrigée", "invalide" in str(seen) and len(cal) == 1)
# 7. outil inconnu
out, cal, seen = run([[("supprimer_tout", {})]])
check("outil inconnu : erreur renvoyée, rien ne plante", "inconnu" in str(seen))
# 8. boucle bornée
out, _, _ = run([[("lire_calendrier", {"date_debut": "2026-11-16", "date_fin": "2026-11-22"})]] * 20)
check("boucle bornée par MAX_AGENT_STEPS", "étapes" in out["answer"])

print(f"\n{ok}/8 tests réussis")
sys.exit(0 if ok == 8 else 1)
