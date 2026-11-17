"""Niveau 2 : agent outillé. Boucle écrite SANS framework (composant « fait main » exigé par le sujet).

- Boucle bornée : MAX_AGENT_STEPS appels au LLM et MAX_AGENT_TOKENS tokens au plus.
- Erreurs d'outils (arguments invalides, exception) renvoyées au modèle pour qu'il se corrige.
- Outils classés par effet (src/tools.EFFECTS) : un outil « write » n'est exécuté qu'après
  1) vérification des règles du club par du code (src/rules.py), 2) confirmation explicite de l'utilisateur.
"""
import json
import re
from datetime import date, timedelta

from config import CALENDAR_DIR, MAX_AGENT_STEPS, MAX_AGENT_TOKENS
from src import rules, tools
from src.llm import chat

AVAILABLE = tools.ready()
USES_TOOLS = True
ABSTAIN = "JE NE SAIS PAS"
CITATION = re.compile(r"\[([^\[\]]+?\.md)(?:#[^\]]*)?\]")
WRITE_REQUEST = re.compile(r"\b(ajoute|ajouter|mets|mettre|prévois|planifie|programme)\b", re.I)
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _calendar(today):
    lines = []
    for i in range(1, 15):
        d = today + timedelta(days=i)
        lines.append(f"{JOURS[d.weekday()]} {d.isoformat()}")
    monday = today + timedelta(days=7 - today.weekday())
    return "\n".join(lines), monday


def system_prompt(today):
    days, monday = _calendar(today)
    return f"""Tu es le coach de course à pied du club « Foulées ECE ». Aujourd'hui : {JOURS[today.weekday()]} {today.isoformat()}.
« La semaine prochaine » va du lundi {monday.isoformat()} au dimanche {(monday + timedelta(days=6)).isoformat()}.
« Mardi prochain », « jeudi prochain »... désignent le jour de la semaine prochaine.
Jours à venir :
{days}

Règles :
- Plans et règles du club : utilise rechercher_corpus et cite le fichier entre crochets, ex. [plan_10km_50min.md].
- Allure ou VMA : utilise calcul_allures, ne calcule jamais toi-même. Un temps objectif se passe en minutes
  (1 h 45 = 105, 3 h 45 = 225) avec distance_km (10, 21.0975 ou 42.195). Recopie les allures et les temps obtenus
  exactement au format m:ss, par exemple « 4:27 min/km » ou « 1:45 » (jamais « 1 minute et 45 secondes »).
- Lecture du calendrier : lire_calendrier. Pour compter des séances intenses, utilise le champ "intense".
- Semaine d'un plan ou séance d'un plan (séance qualité, sortie longue... des plans 5km, 10km, semi, marathon) :
  appelle semaine_plan, qui renvoie les séances de la semaine prochaine. Passe-les à ajouter_seances, en gardant seulement celles demandées et en changeant
  le champ "jour" si l'utilisateur impose d'autres jours.
- Pour un jour de la semaine prochaine (« mardi prochain »), renseigne "jour" (ex. "mardi") et pas "date" :
  le système calcule la date. Séance isolée (hors plan) : appelle ajouter_seances directement. Types :
  endurance fondamentale = "endurance", sortie longue = "sortie_longue", fractionné ou VMA = "fractionne",
  seuil = "seuil", allure 10 km = "allure_10km". Environ 6 min/km en endurance pour estimer les km.
- Ne demande jamais de confirmation dans ta réponse : le système la demande lui-même à l'utilisateur,
  et il vérifie aussi les règles du club et la météo.
- Si ajouter_seances refuse une séance (règle du club, météo), rappelle-le aussitôt avec une version conforme :
  autre jour, endurance au lieu d'une séance intense, ou moins de km. Si un outil renvoie une erreur, corrige les arguments.
- Ne pose une question que si la demande est vraiment impossible à interpréter. Un plan, une semaine ou un jour cités suffisent.
- Si la réponse n'est ni dans les documents ni accessible par un outil, commence par « {ABSTAIN} ».
- Pas d'avis médical. Réponds en français, de façon concise."""


def _always_yes(name, args):
    return True


def answer(question, trace, confirm=None, context=None):
    """confirm(nom_outil, arguments) -> bool : demande à l'utilisateur (interface) ou réponse simulée (évaluation).
    context : {"today", "weather", "calendar_path"} ; valeurs par défaut pour un usage interactif."""
    ctx = {"today": date.today(), "weather": None, "calendar_path": CALENDAR_DIR / "utilisateur.ics", **(context or {})}
    if isinstance(ctx["today"], str):
        ctx["today"] = date.fromisoformat(ctx["today"])
    confirm = confirm or _always_yes

    messages = [{"role": "system", "content": system_prompt(ctx["today"])},
                {"role": "user", "content": question}]
    calls, written, asked_confirmation, sources_seen = [], [], False, set()
    final, pending = None, None
    wants_write = bool(WRITE_REQUEST.search(question))
    nudges = 0
    paces = []

    for step in range(MAX_AGENT_STEPS):
        if trace.total_tokens > MAX_AGENT_TOKENS:
            trace.log("stop", reason=f"budget de {MAX_AGENT_TOKENS} tokens dépassé")
            break
        res = chat(messages, tools=tools.SCHEMAS)
        trace.log_llm(res, note=f"étape {step + 1}")
        messages.append(res["message"])
        if not res["tool_calls"]:
            if wants_write and not asked_confirmation and nudges < 2:
                nudges += 1
                tried = any(c["name"] == "ajouter_seances" for c in calls)
                messages.append({"role": "user", "content":
                                 "Les séances ont été refusées : rappelle ajouter_seances avec une version conforme "
                                 "(autre jour, endurance au lieu d'intense, moins de km)." if tried else
                                 "Tu n'as pas encore appelé ajouter_seances. Appelle-le maintenant avec les séances demandées."})
                continue
            final = res["content"].strip()
            break

        for tc in res["tool_calls"]:
            name = tc.get("function", {}).get("name", "")
            args = tc.get("function", {}).get("arguments", {}) or {}
            if isinstance(args, str):                      # certains modèles renvoient une chaîne JSON
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result, error = _run_tool(name, args, ctx, confirm)
            if name == "ajouter_seances":
                asked_confirmation = asked_confirmation or bool(result.get("confirmation_demandee"))
                if result.get("ajoutees"):
                    written += args.get("seances", [])
            if name == "rechercher_corpus" and not error:
                sources_seen |= {e["source"] for e in result.get("extraits", [])}
            if name == "semaine_plan" and not error:
                sources_seen.add(result["plan"])
            if result.get("allure_cible"):
                paces.append(result["allure_cible"])
            calls.append({"name": name, "args": args, "error": error})
            trace.log_tool(name, args, result, error)
            if result.get("en_attente_confirmation"):
                pending = {"name": name, "args": args}
            messages.append({"role": "tool", "tool_name": name,
                             "content": json.dumps({"erreur": error} if error else result, ensure_ascii=False)})
        if pending:
            final = "Je propose d'ajouter ces séances à ton calendrier. Tu confirmes ?"
            break
    else:
        trace.log("stop", reason=f"limite de {MAX_AGENT_STEPS} étapes atteinte")

    if final is None:
        final = f"Je n'ai pas pu terminer la demande en {MAX_AGENT_STEPS} étapes."
    for p in dict.fromkeys(paces):
        if p not in final:
            final += f"\n\nAllure cible : {p} min/km."
    cited = [s for s in dict.fromkeys(CITATION.findall(final)) if s in sources_seen]
    return {"answer": final, "sources": cited, "abstained": final.upper().startswith(ABSTAIN),
            "tool_calls": calls, "written": written, "asked_confirmation": asked_confirmation,
            "pending_write": pending, "task_success": None}  # calculé par eval.py à partir de l'état final


def _run_tool(name, args, ctx, confirm):
    """Exécute un outil ; renvoie (résultat, erreur). Ne lève jamais d'exception."""
    if name not in tools.FUNCTIONS:
        return {}, f"Outil inconnu : {name}. Outils disponibles : {', '.join(tools.FUNCTIONS)}."
    try:
        if tools.EFFECTS[name] == "write":
            return _guarded_write(name, args, ctx, confirm)
        return tools.FUNCTIONS[name](args, ctx), None
    except Exception as e:  # erreur renvoyée au modèle, pas d'arrêt de la boucle
        return {}, f"{type(e).__name__} : {e}"


def _fix(violation):
    if violation.startswith("R5 : vent"):
        return "Vent ou orage : garde la séance mais change de jour (le lendemain par exemple)."
    if violation.startswith("R5"):
        return "Chaleur : remplace la séance intense par de l'endurance, ou change de jour."
    if violation.startswith("R2"):
        return "Trop de séances intenses rapprochées : place-la au moins deux jours après une autre séance intense."
    if violation.startswith("R1"):
        return "Volume trop élevé : réduis les km pour respecter le maximum indiqué."
    if violation.startswith("R6"):
        return "Pas de jour de repos : retire une séance de la semaine."
    return "Propose une version conforme."


def _guarded_write(name, args, ctx, confirm):
    seances = args.get("seances")
    if not seances:
        return {}, "Argument 'seances' manquant ou vide."
    next_monday = ctx["today"] + timedelta(days=7 - ctx["today"].weekday())
    for s in seances:
        if s.get("jour") in tools.JOURS:
            s["date"] = (next_monday + timedelta(days=tools.JOURS.index(s["jour"]))).isoformat()
        if not s.get("date"):
            return {}, "Chaque séance doit avoir un jour (semaine prochaine) ou une date AAAA-MM-JJ."
        if s.get("type") not in tools.SESSION_TYPES:
            return {}, f"Type de séance invalide : {s.get('type')}. Types possibles : {tools.SESSION_TYPES}."
        date.fromisoformat(s["date"])  # lève une erreur claire si la date est mal formée

    # 1) Règles métier vérifiées par du code, sur l'état réel du calendrier et la météo
    dates = sorted(date.fromisoformat(s["date"]) for s in seances)
    start, end = dates[0] - timedelta(days=dates[0].weekday() + 7), dates[-1] + timedelta(days=6)
    existing = tools.FUNCTIONS["lire_calendrier"]({"date_debut": start.isoformat(), "date_fin": end.isoformat()},
                                                  ctx)["seances"]
    weather = {}
    for d in dict.fromkeys(s["date"] for s in seances):
        try:
            weather[d] = tools.FUNCTIONS["meteo"]({"date": d}, ctx)
        except Exception:
            pass  # météo indisponible : R5 non vérifiable, on ne bloque pas (à signaler dans le rapport)
    violations = rules.check(seances, existing, weather)
    if violations:
        return {"refuse": True, "violations": violations,
                "consigne": "Rien n'a été écrit. Rappelle ajouter_seances en corrigeant ainsi : "
                             + " ".join(dict.fromkeys(_fix(v) for v in violations))}, None

    # 2) Confirmation explicite de l'utilisateur avant toute écriture
    decision = confirm(name, args)
    if decision is None:   # interface : la décision sera prise par l'utilisateur après l'affichage
        return {"en_attente_confirmation": True, "confirmation_demandee": True, "ajoutees": 0}, None
    if not decision:
        return {"confirmation_demandee": True, "ajoutees": 0,
                "message": "L'utilisateur a refusé : rien n'a été écrit. Ne réessaie pas sans nouvelle demande."}, None
    result = tools.FUNCTIONS[name](args, ctx)
    return {**result, "confirmation_demandee": True}, None


def execute_confirmed(args, trace, context=None):
    """Écriture après un clic « Confirmer » dans l'interface : les règles sont revérifiées
    (le calendrier a pu changer entre la proposition et la confirmation)."""
    ctx = {"today": date.today(), "weather": None, "calendar_path": CALENDAR_DIR / "utilisateur.ics", **(context or {})}
    result, error = _run_tool("ajouter_seances", args, ctx, lambda n, a: True)
    trace.log_tool("ajouter_seances", args, result, error)
    trace.log("confirmation", decision="confirmée par l'utilisateur")
    return result, error
