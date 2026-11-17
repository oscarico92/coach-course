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
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def system_prompt(today):
    return f"""Tu es le coach de course à pied du club « Foulées ECE ». Aujourd'hui : {JOURS[today.weekday()]} {today.isoformat()}.
Tu disposes d'outils. Règles :
- Pour toute information sur les plans et règles du club, utilise rechercher_corpus et cite le fichier entre crochets, ex. [plan_10km_50min.md].
- Pour tout calcul d'allure ou de VMA, utilise calcul_allures : ne calcule jamais toi-même.
- Avant d'ajouter des séances, consulte lire_calendrier et meteo pour les jours concernés.
- ajouter_seances modifie le calendrier : l'utilisateur confirmera ; si l'outil refuse (règle du club), propose une alternative conforme.
- Si une information indispensable manque (quel plan, quel jour), pose une question au lieu de deviner.
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
    final = None

    for step in range(MAX_AGENT_STEPS):
        if trace.total_tokens > MAX_AGENT_TOKENS:
            trace.log("stop", reason=f"budget de {MAX_AGENT_TOKENS} tokens dépassé")
            break
        res = chat(messages, tools=tools.SCHEMAS)
        trace.log_llm(res, note=f"étape {step + 1}")
        messages.append(res["message"])
        if not res["tool_calls"]:
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
            calls.append({"name": name, "args": args, "error": error})
            trace.log_tool(name, args, result, error)
            messages.append({"role": "tool", "tool_name": name,
                             "content": json.dumps({"erreur": error} if error else result, ensure_ascii=False)})
    else:
        trace.log("stop", reason=f"limite de {MAX_AGENT_STEPS} étapes atteinte")

    if final is None:
        final = f"Je n'ai pas pu terminer la demande en {MAX_AGENT_STEPS} étapes."
    cited = [s for s in dict.fromkeys(CITATION.findall(final)) if s in sources_seen]
    return {"answer": final, "sources": cited, "abstained": final.upper().startswith(ABSTAIN),
            "tool_calls": calls, "written": written, "asked_confirmation": asked_confirmation,
            "task_success": None}  # calculé par eval.py à partir de l'état final


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


def _guarded_write(name, args, ctx, confirm):
    seances = args.get("seances")
    if not seances:
        return {}, "Argument 'seances' manquant ou vide."
    for s in seances:
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
                "consigne": "Rien n'a été écrit. Propose à l'utilisateur une alternative conforme."}, None

    # 2) Confirmation explicite de l'utilisateur avant toute écriture
    if not confirm(name, args):
        return {"confirmation_demandee": True, "ajoutees": 0,
                "message": "L'utilisateur a refusé : rien n'a été écrit. Ne réessaie pas sans nouvelle demande."}, None
    result = tools.FUNCTIONS[name](args, ctx)
    return {**result, "confirmation_demandee": True}, None
