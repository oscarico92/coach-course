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
REAL_ROUTE = agent.route
# RAG du niveau 1 simulé (routage et repli), pour ne jamais appeler Ollama
agent.level1_rag.answer = lambda q, tr: {"answer": "Réponse [plan_10km_50min.md]", "sources": ["plan_10km_50min.md"],
                                         "abstained": False, "tool_calls": [], "retrieved": ["plan_10km_50min.md"],
                                         "retrieved_ids": ["x"], "top_score": 0.7}
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


def run(script, confirm=True, calendar=None, weather=None, question="test"):
    path = Path(tempfile.mkdtemp()) / "cal.ics"
    CAL[path] = list(calendar or [])
    if USE_REAL:
        tools.impl.init_calendrier(path, CAL[path])
    agent.chat = scripted_chat(script)
    # le routage est testé à part (tests 12 et suivants) ; ici, intention d'écriture simulée par le regex d'origine
    agent.route = lambda q, tr: "ecriture" if agent.WRITE_REQUEST.search(q) else "agent"
    out = agent.answer(question, Trace(2, question), confirm=lambda n, a: confirm,
                       context={"today": "2026-11-12", "weather": weather or {}, "calendar_path": path})
    if USE_REAL:
        CAL[path] = tools.FUNCTIONS["lire_calendrier"]({"date_debut": "2000-01-01", "date_fin": "2100-01-01"},
                                                       {"calendar_path": path})["seances"]
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
# 9. demande floue : le modèle pose une question, pas de relance
out, cal, seen = run(["Quel type de séance et quel jour ?"], question="Ajoute une séance.")
check("demande floue : la question du modèle n'est pas relancée", out["answer"].endswith("?") and len(seen) == 1)
# 10. annonce sans appel d'outil : relance, puis écriture
out, cal, seen = run(["Je vais ajouter la séance.",
                      [("ajouter_seances", {"seances": [S("2026-11-19", "endurance")]})]],
                     question="Ajoute un footing jeudi prochain.")
check("annonce sans écriture : relance puis séance ajoutée", len(cal) == 1 and "pas encore appelé" in str(seen))
# 11. question après un refus (« Voulez-vous de l'endurance ? ») : relance quand même
out, cal, seen = run([[("ajouter_seances", {"seances": [S("2026-11-19", "seuil")]})],
                      "Il fera 31 °C. Voulez-vous de l'endurance à la place ?",
                      [("ajouter_seances", {"seances": [S("2026-11-19", "endurance")]})]],
                     weather={"2026-11-19": {"tmax_c": 31, "vent_kmh": 10, "orage": False}},
                     question="Mets une séance de seuil jeudi prochain.")
check("question après un refus : relance puis version conforme ajoutée", len(cal) == 1 and cal[0]["type"] == "endurance")


# 12 à 14. routage : une question documentaire part vers le RAG du niveau 1, le reste vers la boucle


def routed(router_reply, question="Quelle est la séance de la semaine 3 ?", loop=("Réponse de la boucle ?",)):
    agent.chat = scripted_chat([router_reply, *loop])
    agent.route = REAL_ROUTE
    path = Path(tempfile.mkdtemp()) / "cal.ics"
    out = agent.answer(question, Trace(2, question), confirm=lambda n, a: True,
                       context={"today": "2026-11-12", "weather": {}, "calendar_path": path})
    return out, agent.chat.seen


out, seen = routed("DOC")
check("routage DOC : réponse du RAG, sources gardées, pas de Recall/MRR", out["route"] == "doc"
      and out["sources"] == ["plan_10km_50min.md"] and "retrieved" not in out and len(seen) == 1)
out, seen = routed("ACTION")
check("routage ACTION : la boucle de l'agent répond", out["route"] == "agent" and out["answer"] == "Réponse de la boucle ?")
out, seen = routed("Je ne sais pas trop")
check("routage illisible : boucle de l'agent par défaut", out["route"] == "agent")


# 15 à 21. repli vers le RAG quand la boucle n'a appelé aucun outil
out, seen = routed("ACTION", loop=["JE NE SAIS PAS."])
check("repli : aucun outil, réponse sans question -> RAG", out["route"] == "agent>doc"
      and out["sources"] == ["plan_10km_50min.md"] and "retrieved" not in out)
out, seen = routed("ACTION", loop=["Quel plan suis-tu ?"])
check("pas de repli : question de précision gardée", out["route"] == "agent" and out["answer"].endswith("?"))
out, seen = routed("ACTION", loop=["Je ne sais pas. Quel plan suis-tu ?"])
check("repli : abstention sans outil, même suivie d'une question -> RAG", out["route"] == "agent>doc")
RAG_OK = agent.level1_rag.answer
agent.level1_rag.answer = lambda q, tr: {**RAG_OK(q, tr), "answer": "JE NE SAIS PAS : rien.", "sources": [], "abstained": True}
out, seen = routed("ACTION", loop=["Je ne sais pas. Tu parles de quoi ?"])
check("repli annulé : le RAG s'abstient aussi, la question de l'agent est gardée",
      out["route"] == "agent" and out["answer"] == "Je ne sais pas. Tu parles de quoi ?")
agent.level1_rag.answer = RAG_OK
out, seen = routed("ACTION", loop=[[("calcul_allures", {"vma_kmh": 15})], "Allures calculées."])
check("pas de repli : un outil a été appelé", out["route"] == "agent")
out, seen = routed("ECRITURE", question="Cale-moi un footing jeudi.", loop=["Fait.", "Fait.", "Fait."])
check("ECRITURE (sans verbe du regex) : relance, pas de repli", out["route"] == "agent" and out["intention_ecriture"]
      and "pas encore appelé" in str(seen))
out, seen = routed("ACTION", question="Combien de km j'ai au programme ?",
                   loop=[[("lire_calendrier", {"date_debut": "2026-11-16", "date_fin": "2026-11-22"})], "Tu as 35 km."])
check("« au programme » classé ACTION : pas de relance d'écriture", not out["intention_ecriture"]
      and "pas encore appelé" not in str(seen))

# 22 et 23. format des allures et écriture annoncée mais refusée
out, cal, _ = run([[("calcul_allures", {"distance_test_m": 1450})], "Ton 400 m : 1 minute et 45 secondes."],
                  question="Allure ?")
check("« 1 minute et 45 secondes » réécrit en 1:45", "1:45" in out["answer"] and "secondes" not in out["answer"])
out, cal, _ = run([[("ajouter_seances", {"seances": [S("2026-11-19", "seuil")]})], "Séance ajoutée samedi."],
                  weather={"2026-11-19": {"tmax_c": 31, "vent_kmh": 10, "orage": False}}, question="Un seuil jeudi ?")
check("refus non corrigé : la réponse rappelle que rien n'est écrit", cal == [] and "aucune séance n'a été enregistrée" in out["answer"])

print(f"\n{ok}/23 tests réussis")
sys.exit(0 if ok == 23 else 1)
