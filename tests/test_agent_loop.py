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
from src.levels import level1_rag, level3_ext as multi  # noqa: E402
import re  # noqa: E402

REAL_WRITE = agent.write_intent
# intention d'écriture simulée pour les tests de la boucle seule (le vrai write_intent interroge le modèle)
WRITE_RE = re.compile(r"\b(ajoute|mets|cale|prévois|programme-moi)\b", re.I)
# RAG du niveau 1 simulé (agent documentaire du niveau 3), pour ne jamais appeler Ollama
level1_rag.answer = lambda q, tr: {"answer": "Réponse [plan_10km_50min.md]", "sources": ["plan_10km_50min.md"],
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
    # niveau 2 seul ; l'orchestrateur du niveau 3 est testé à part (tests 12 et suivants)
    agent.write_intent = lambda q, tr: bool(WRITE_RE.search(q))
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
# (sans application automatique de la proposition, pour tester la relance)
agent.AGENT_AUTO_PROPOSITION = False
out, cal, seen = run([[("ajouter_seances", {"seances": [S("2026-11-19", "seuil")]})],
                      "Il fera 31 °C. Voulez-vous de l'endurance à la place ?",
                      [("ajouter_seances", {"seances": [S("2026-11-19", "endurance")]})]],
                     weather={"2026-11-19": {"tmax_c": 31, "vent_kmh": 10, "orage": False}},
                     question="Mets une séance de seuil jeudi prochain.")
check("question après un refus : relance puis version conforme ajoutée", len(cal) == 1 and cal[0]["type"] == "endurance")
agent.AGENT_AUTO_PROPOSITION = True


# 12 à 14. niveau 3 : l'orchestrateur confie une question documentaire à l'agent documentaire (RAG), le reste à l'agent actions


def routed(router_reply, question="Quelle est la séance de la semaine 3 ?", loop=("Réponse de la boucle ?",),
           write_reply="NON"):
    # la question binaire d'écriture n'est posée que si le routeur n'a répondu ni DOC ni ECRITURE
    extra = [] if router_reply in ("DOC", "ECRITURE") else [write_reply]
    agent.chat = multi.chat = scripted_chat([router_reply, *extra, *loop])   # un seul script pour les deux modules
    agent.write_intent = REAL_WRITE
    path = Path(tempfile.mkdtemp()) / "cal.ics"
    out = multi.answer(question, Trace(3, question), confirm=lambda n, a: True,
                       context={"today": "2026-11-12", "weather": {}, "calendar_path": path})
    return out, agent.chat.seen


out, seen = routed("DOC")
check("orchestrateur DOC : agent documentaire, sources gardées, pas de Recall/MRR, rapports JSON", out["route"] == "doc"
      and [r["agent"] for r in out["rapports"]] == ["documentaire", "documentaire"]
      and out["sources"] == ["plan_10km_50min.md"] and "retrieved" not in out and len(seen) == 1)
out, seen = routed("ACTION")
check("routage ACTION : la boucle de l'agent répond", out["route"] == "agent" and out["answer"] == "Réponse de la boucle ?")
out, seen = routed("Je ne sais pas trop")
check("routage illisible : boucle de l'agent par défaut", out["route"] == "agent")


# 15 à 22. repli vers l'agent documentaire quand l'agent actions n'a appelé aucun outil
out, seen = routed("ACTION", loop=["JE NE SAIS PAS."])
check("repli : aucun outil, réponse sans question -> RAG", out["route"] == "agent>doc"
      and out["sources"] == ["plan_10km_50min.md"] and "retrieved" not in out)
out, seen = routed("ACTION", loop=["Quel plan suis-tu ?"])
check("pas de repli : question de précision gardée", out["route"] == "agent" and out["answer"].endswith("?"))
out, seen = routed("ACTION", loop=["Je ne sais pas. Quel plan suis-tu ?"])
check("repli : abstention sans outil, même suivie d'une question -> RAG", out["route"] == "agent>doc")
RAG_OK = level1_rag.answer
level1_rag.answer = lambda q, tr: {**RAG_OK(q, tr), "answer": "JE NE SAIS PAS : rien.", "sources": [], "abstained": True}
out, seen = routed("ACTION", loop=["Je ne sais pas. Tu parles de quoi ?"])
check("repli annulé : le RAG s'abstient aussi, la question de l'agent est gardée",
      out["route"] == "agent" and out["answer"] == "Je ne sais pas. Tu parles de quoi ?")
level1_rag.answer = RAG_OK
out, seen = routed("ACTION", loop=[[("calcul_allures", {"vma_kmh": 15})], "Allures calculées."])
check("pas de repli : un outil a été appelé ; rapport de l'agent actions", out["route"] == "agent"
      and out["rapports"][1]["outils_appeles"] == 1)
out, seen = routed("ECRITURE", question="Cale-moi un footing jeudi.", loop=["Fait.", "Fait.", "Fait."])
check("ECRITURE (sans verbe du regex) : relance, pas de repli", out["route"] == "agent" and out["intention_ecriture"]
      and "pas encore appelé" in str(seen))
out, seen = routed("ACTION", question="Combien de km j'ai au programme ?",
                   loop=[[("lire_calendrier", {"date_debut": "2026-11-16", "date_fin": "2026-11-22"})], "Tu as 35 km."])
check("« au programme » classé ACTION : pas de relance d'écriture", not out["intention_ecriture"]
      and "pas encore appelé" not in str(seen))

out, seen = routed("ACTION", question="Calcule mon allure et cale un seuil jeudi.", write_reply="OUI",
                   loop=["Fait.", "Fait.", "Fait."])
check("ACTION + OUI à la question d'écriture : relance", out["intention_ecriture"] and "pas encore appelé" in str(seen))

# niveau 2 seul : ni orchestrateur ni repli
out, cal, seen = run(["JE NE SAIS PAS."], question="Quelle est la séance de la semaine 3 ?")
check("niveau 2 seul : réponse de l'agent gardée, pas de repli", out["answer"] == "JE NE SAIS PAS." and "route" not in out)

# 23 et 24. format des allures et écriture annoncée mais refusée
out, cal, _ = run([[("calcul_allures", {"distance_test_m": 1450})], "Ton 400 m : 1 minute et 45 secondes."],
                  question="Allure ?")
check("« 1 minute et 45 secondes » réécrit en 1:45", "1:45" in out["answer"] and "secondes" not in out["answer"])
out, cal, _ = run([[("ajouter_seances", {"seances": [S("2026-11-19", "seuil")]})], "Séance ajoutée samedi."],
                  weather={"2026-11-19": {"tmax_c": 31, "vent_kmh": 10, "orage": False}}, question="Un seuil jeudi ?")
check("refus non corrigé : la réponse rappelle que rien n'est écrit", cal == [] and "aucune séance n'a été enregistrée" in out["answer"])


# 25 à 31. proposition d'une version conforme par le code après un refus (_propose)
from datetime import date as _date  # noqa: E402
TODAY = _date(2026, 11, 12)
W = lambda **days: (lambda d: days.get(d.replace("-", "_"), {"tmax_c": 15, "vent_kmh": 10, "orage": False}))
P = lambda d, t, km=8, jour=None: {"date": d, "titre": t, "type": t, "km": km, **({"jour": jour} if jour else {})}
hot = {"tmax_c": 31, "vent_kmh": 10, "orage": False}

p = agent._propose([P("2026-11-19", "seuil", jour="jeudi")], [], W(**{"2026_11_19": hot}), TODAY)
check("chaleur : seuil déplacé au jour le plus proche (vendredi), jour recalculé",
      p and p[0]["date"] == "2026-11-20" and p[0]["jour"] == "vendredi" and p[0]["type"] == "seuil")
p = agent._propose([P("2026-11-21", "sortie_longue", 14)], [],
                   W(**{"2026_11_21": {"tmax_c": 12, "vent_kmh": 60, "orage": False}}), TODAY)
check("vent : sortie longue déplacée au dimanche", p and p[0]["date"] == "2026-11-22")
p = agent._propose([P("2026-11-20", "fractionne")], [],
                   W(**{"2026_11_20": {"tmax_c": 14, "vent_kmh": 20, "orage": True}}), TODAY)
check("orage : fractionné déplacé hors du vendredi", p and p[0]["date"] != "2026-11-20")
prev = [{"date": d, "titre": "Footing", "intense": False, "km": k}
        for d, k in [("2026-11-09", 10), ("2026-11-11", 8), ("2026-11-13", 8), ("2026-11-15", 14)]]
p = agent._propose([P(f"2026-11-{d}", "endurance", 12) for d in (16, 18, 20, 22)], prev, W(), TODAY)
check("R1 : 48 km ramenés à 44 km au plus", p and sum(x["km"] for x in p) <= 44 and sum(x["km"] for x in p) >= 43)
p = agent._propose([P("2026-11-18", "fractionne")], [{"date": "2026-11-17", "titre": "VMA", "intense": True, "km": 8}],
                   W(), TODAY)
check("R2 : fractionné écarté d'au moins deux jours de l'autre séance intense",
      p and abs(_date.fromisoformat(p[0]["date"]) - _date(2026, 11, 17)).days >= 2)
between = [{"date": "2026-11-17", "titre": "VMA", "intense": True, "km": 8},
           {"date": "2026-11-19", "titre": "Allure 10 km", "intense": True, "km": 9},
           {"date": "2026-11-22", "titre": "Sortie longue", "intense": False, "km": 9}]
p = agent._propose([P("2026-11-18", "fractionne")], between, W(), TODAY)
check("R2 entre deux intenses : meilleur candidat retenu (samedi), pas le premier qui améliore (vendredi)",
      p and p[0]["date"] == "2026-11-21")
full = [{"date": f"2026-11-{d}", "titre": "Footing", "intense": False, "km": 5} for d in range(16, 22)]
check("R6 sans solution : pas de proposition", agent._propose([P("2026-11-22", "endurance", 5)], full, W(), TODAY) is None)
out, cal, seen = run([[("ajouter_seances", {"seances": [{"jour": "jeudi", "titre": "Seuil", "type": "seuil", "km": 8}]})]],
                     weather={"2026-11-19": hot}, question="Mets un seuil jeudi.")
check("refus : la proposition calculée est renvoyée au modèle", "proposition" in str(seen) and "2026-11-20" in str(seen))


# 32 à 36. appel d'outil écrit en texte, proposition appliquée par le système
call = '{"name": "ajouter_seances", "arguments": {"seances": [{"date": "2026-11-17", "titre": "endurance", "type": "endurance", "km": 8}]}}'
out, cal, seen = run(["ursal " + call], question="Ajoute un footing mardi.")
check("appel d'outil écrit en texte : exécuté", len(cal) == 1 and cal[0]["date"] == "2026-11-17")
seuil = [[("ajouter_seances", {"seances": [{"jour": "jeudi", "titre": "Seuil", "type": "seuil", "km": 8}]})],
         "Voici la proposition : ```json [{\"jour\": \"vendredi\"}] ```"]
out, cal, seen = run(seuil, weather={"2026-11-19": hot}, question="Mets un seuil jeudi prochain.")
check("proposition recopiée en texte : appliquée par le système, réponse rédigée par le code",
      len(cal) == 1 and cal[0]["date"] == "2026-11-20" and cal[0]["type"] == "seuil"
      and "vendredi 2026-11-20" in out["answer"] and "json" not in out["answer"] and len(seen) == 2)
out, cal, seen = run(seuil, weather={"2026-11-19": hot}, question="Mets un seuil jeudi prochain.", confirm=None)
check("interface : la proposition attend la confirmation", cal == [] and out["pending_write"]
      and out["pending_write"]["args"]["seances"][0]["date"] == "2026-11-20" and out["answer"].endswith("Tu confirmes ?"))
out, cal, seen = run(seuil, weather={"2026-11-19": hot}, question="Mets un seuil jeudi prochain.", confirm=False)
check("confirmation refusée : rien n'est écrit", cal == [] and "rien n'a été écrit" in out["answer"])
agent.AGENT_AUTO_PROPOSITION = False
out, cal, seen = run(seuil + ["Proposition.", "Proposition."], weather={"2026-11-19": hot}, question="Mets un seuil jeudi prochain.")
check("AGENT_AUTO_PROPOSITION=0 : rien n'est appliqué par le système", cal == [])
agent.AGENT_AUTO_PROPOSITION = True

print(f"\n{ok}/38 tests réussis")
sys.exit(0 if ok == 38 else 1)
