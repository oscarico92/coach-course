"""Niveau 2 : agent outillé. Boucle écrite SANS framework (composant « fait main » exigé par le sujet).

- Boucle bornée : MAX_AGENT_STEPS appels au LLM et MAX_AGENT_TOKENS tokens au plus.
- Erreurs d'outils (arguments invalides, exception) renvoyées au modèle pour qu'il se corrige.
- Outils classés par effet (src/tools.EFFECTS) : un outil « write » n'est exécuté qu'après
  1) vérification des règles du club par du code (src/rules.py), 2) confirmation explicite de l'utilisateur.
- Routage (AGENT_ROUTER=1) : un premier appel court classe la question. Une question documentaire
  (plans, règles, définitions, sans calcul personnel ni calendrier) est traitée par la chaîne RAG du
  niveau 1 : recherche systématique, citations, abstention par seuil. Le reste passe par la boucle.
  Raison : laissé libre de choisir, le modèle 7B appelait rarement rechercher_corpus (0 % de sources citées).
- Repli (AGENT_FALLBACK=1) : si la boucle se termine sans aucun appel d'outil ni demande d'écriture, et que la
  réponse ne pose pas de question ou commence par « JE NE SAIS PAS », la question est repassée au RAG (« agent>doc »).
  Si le RAG s'abstient aussi, la réponse de l'agent est conservée.
"""
import json
import re
from datetime import date, timedelta

from config import AGENT_AUTO_PROPOSITION, AGENT_FALLBACK, AGENT_ROUTER, CALENDAR_DIR, MAX_AGENT_STEPS, MAX_AGENT_TOKENS
from src import rules, tools
from src.levels import level1_rag
from src.llm import chat

AVAILABLE = tools.ready()
USES_TOOLS = True
ABSTAIN = "JE NE SAIS PAS"
CITATION = re.compile(r"\[([^\[\]]+?\.md)(?:#[^\]]*)?\]")
WRITE_REQUEST = re.compile(r"\b(ajoute|ajouter|mets|mettre|prévois|planifie|programme)\b", re.I)
MINSEC = re.compile(r"(\d{1,2})\s*minutes?\s*(?:et\s*)?(\d{1,2})\s*secondes?", re.I)
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
- Allure ou VMA : utilise calcul_allures, ne calcule jamais toi-même. Un temps objectif se recopie tel
  qu'écrit dans temps_objectif (ex. « 1 h 45 », « 50 min »), avec distance_km (10, 21.0975 ou 42.195). Recopie les allures et les temps obtenus
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


def _text_tool_calls(content):
    """Appels d'outils écrits dans le texte au lieu du champ tool_calls (qwen2.5 via Ollama, parfois :
    « {"name": "ajouter_seances", "arguments": {...}} »). Seuls les outils connus sont retenus."""
    found, decoder, i = [], json.JSONDecoder(), 0
    while (i := content.find("{", i)) != -1:
        try:
            obj, end = decoder.raw_decode(content, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict) and obj.get("name") in tools.FUNCTIONS and isinstance(obj.get("arguments"), (dict, str)):
            found.append({"function": {"name": obj["name"], "arguments": obj["arguments"]}})
        i = end
    return found


def _describe(seances):
    return "\n".join(f"- {JOURS[date.fromisoformat(x['date']).weekday()]} {x['date']} : {x.get('titre', x['type'])} "
                     f"({x.get('km', 0):g} km)" for x in seances)


def _always_yes(name, args):
    return True


# Exemples volontairement absents de data/tests.jsonl, pour ne pas régler le routeur sur le jeu de test.
ROUTER_PROMPT = """Tu classes la demande d'un coureur adressée au coach d'un club.
Réponds par un seul mot : DOC, ECRITURE ou ACTION.
DOC : demande d'information générale ou sur les documents du club (plans, règles, allures données par un plan,
tests de VMA, définitions, conseils), sans calcul à partir de chiffres personnels et sans calendrier.
ECRITURE : demande de placer, d'ajouter ou de planifier une ou plusieurs séances dans le calendrier.
Prioritaire : si la demande contient un ajout au calendrier, réponds ECRITURE même si elle demande aussi un calcul.
ACTION : tout le reste. Calcul à partir de chiffres personnels (ma VMA, mon temps visé, ma distance au test),
lecture ou modification du calendrier, météo, demande vague ou incomplète, hors sujet ou médicale.

Exemples :
Combien de semaines dure le plan marathon du club ? -> DOC
Que dit le club sur l'échauffement avant un fractionné ? -> DOC
Quelle allure le plan 10 km donne-t-il pour les séances au seuil ? -> DOC
Qu'est-ce qu'une sortie longue ? -> DOC
J'ai couru 2 800 m au test de Cooper, quelle est ma VMA ? -> ACTION
Mets une sortie longue dimanche. -> ECRITURE
Inscris-moi un footing de 40 minutes samedi. -> ECRITURE
Bloque mes séances de la semaine 3 du plan 10 km. -> ECRITURE
Avec 16 de VMA, donne-moi mes allures et inscris un seuil jeudi. -> ECRITURE
Qu'est-ce que j'ai de prévu mardi ? -> ACTION
Fais-moi un plan. -> ACTION
Aide-moi pour dimanche. -> ACTION"""


def route(question, trace):
    """Renvoie "doc", "ecriture" ou "agent". En cas de réponse illisible, "agent" (comportement d'avant le routage)."""
    res = chat([{"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": question}], temperature=0)
    trace.log_llm(res, note="routage")
    word = res["content"].upper()
    if re.search(r"\bÉ?ECRITURE\b", word.replace("É", "E")):
        choice = "ecriture"
    elif re.search(r"\bDOC\b", word) and "ACTION" not in word:
        choice = "doc"
    else:
        choice = "agent"
    trace.log("routage", choix=choice, sortie_modele=res["content"].strip()[:40])
    return choice


WRITE_PROMPT = """Réponds uniquement par OUI ou NON.
La demande de l'utilisateur demande-t-elle d'ajouter, de placer ou de planifier des séances dans son calendrier,
même si elle demande aussi autre chose (calcul d'allure, explication) ?"""


def write_intent(question, trace):
    """Question binaire posée quand le routeur a répondu ACTION : le routeur à 3 classes classait
    « calcule mon allure et ajoute… » en ACTION malgré la consigne de priorité."""
    res = chat([{"role": "system", "content": WRITE_PROMPT},
                {"role": "user", "content": question}], temperature=0)
    trace.log_llm(res, note="intention d'écriture")
    yes = bool(re.search(r"\bOUI\b", res["content"].upper()))
    trace.log("intention d'écriture", ecriture=yes, sortie_modele=res["content"].strip()[:40])
    return yes


def _answer_doc(question, trace):
    out = level1_rag.answer(question, trace)
    # retrieved / retrieved_ids ne sont pas renvoyés : Recall@5 et MRR restent ceux du niveau 1,
    # et ils ne seraient calculés ici que sur une partie des questions (celles routées vers le RAG)
    out.pop("retrieved", None)
    out.pop("retrieved_ids", None)
    return {**out, "tool_calls": [], "written": [], "asked_confirmation": False,
            "pending_write": None, "task_success": None, "route": "doc", "intention_ecriture": False}


def answer(question, trace, confirm=None, context=None):
    """confirm(nom_outil, arguments) -> bool : demande à l'utilisateur (interface) ou réponse simulée (évaluation).
    context : {"today", "weather", "calendar_path"} ; valeurs par défaut pour un usage interactif."""
    ctx = {"today": date.today(), "weather": None, "calendar_path": CALENDAR_DIR / "utilisateur.ics", **(context or {})}
    if isinstance(ctx["today"], str):
        ctx["today"] = date.fromisoformat(ctx["today"])
    confirm = confirm or _always_yes

    choice = route(question, trace) if AGENT_ROUTER else None
    if choice == "doc":
        return _answer_doc(question, trace)

    messages = [{"role": "system", "content": system_prompt(ctx["today"])},
                {"role": "user", "content": question}]
    calls, written, asked_confirmation, sources_seen = [], [], False, set()
    final, pending = None, None
    # intention d'écriture : donnée par le routeur ; le regex ne sert que sans routage (comportement d'origine,
    # qui prenait « au programme » pour une écriture et ne reconnaissait pas « cale-moi »)
    if AGENT_ROUTER:
        wants_write = choice == "ecriture" or write_intent(question, trace)
    else:
        wants_write = bool(WRITE_REQUEST.search(question))
    nudges = 0
    paces = []
    proposal, refusal = None, None   # dernière version conforme calculée par le code après un refus

    for step in range(MAX_AGENT_STEPS):
        if trace.total_tokens > MAX_AGENT_TOKENS:
            trace.log("stop", reason=f"budget de {MAX_AGENT_TOKENS} tokens dépassé")
            break
        res = chat(messages, tools=tools.SCHEMAS)
        trace.log_llm(res, note=f"étape {step + 1}")
        if not res["tool_calls"] and (in_text := _text_tool_calls(res["content"])):
            trace.log("appel d'outil lu dans le texte", outils=[c["function"]["name"] for c in in_text])
            res = {**res, "tool_calls": in_text,
                   "message": {"role": "assistant", "content": "", "tool_calls": in_text}}
        messages.append(res["message"])
        if not res["tool_calls"]:
            # question posée avant tout appel d'outil = demande de précision : on la laisse passer.
            # Après un appel d'outil, une question est une demande de confirmation, que le système gère lui-même.
            asks_user = "?" in res["content"] and not calls
            if wants_write and AGENT_AUTO_PROPOSITION and proposal and not written and not pending:
                final = res["content"].strip()   # le système appliquera la proposition après la boucle
                break
            if wants_write and not asked_confirmation and not asks_user and nudges < 2:
                nudges += 1
                tried = any(c["name"] == "ajouter_seances" for c in calls)
                messages.append({"role": "user", "content":
                                 "Les séances ont été refusées : rappelle ajouter_seances avec la liste « proposition » "
                                 "renvoyée par l'outil (version conforme calculée par le système), sans la modifier." if tried else
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
                if result.get("proposition"):
                    proposal, refusal = result["proposition"], result["violations"]
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

    # Proposition appliquée par le système : le modèle a reçu une version conforme après un refus mais n'a pas
    # rappelé ajouter_seances (il la recopiait dans sa réponse). Elle passe par les règles et la confirmation
    # comme tout appel ; la réponse est rédigée par le code, avec les dates réelles.
    if AGENT_AUTO_PROPOSITION and wants_write and proposal and not written and not pending:
        args = {"seances": [dict(x) for x in proposal]}
        result, error = _run_tool("ajouter_seances", args, ctx, confirm)
        calls.append({"name": "ajouter_seances", "args": args, "error": error, "par_le_systeme": True})
        trace.log_tool("ajouter_seances", args, result, error)
        trace.log("proposition appliquée par le système", reponse_modele=(final or "")[:200])
        asked_confirmation = asked_confirmation or bool(result.get("confirmation_demandee"))
        motif = " ".join(v.split(",")[0].rstrip(".") + "." for v in refusal)
        if result.get("en_attente_confirmation"):
            pending = {"name": "ajouter_seances", "args": args}
            final = (f"Ta demande ne respecte pas les règles du club ({motif}) Je propose à la place :\n"
                     f"{_describe(args['seances'])}\n\nTu confirmes ?")
        elif result.get("ajoutees"):
            written += args["seances"]
            final = (f"Ta demande ne respecte pas les règles du club ({motif}) Version conforme enregistrée :\n"
                     f"{_describe(args['seances'])}")
        elif not error and result.get("confirmation_demandee"):
            final = f"Ta demande ne respecte pas les règles du club ({motif}) Tu as refusé la version proposée : rien n'a été écrit."

    # Repli vers le RAG : la boucle n'a appelé aucun outil et la demande n'est pas une écriture, et soit
    # la réponse ne pose pas de question de précision (réponse de mémoire), soit elle commence par une
    # abstention (« Je ne sais pas… pouvez-vous préciser ? » : abstention sans avoir cherché, pas une précision).
    abstained_blind = final is not None and final.upper().startswith(ABSTAIN)
    if (AGENT_FALLBACK and AGENT_ROUTER and final is not None and not calls and not wants_write
            and ("?" not in final or abstained_blind)):
        trace.log("repli", reason="aucun outil appelé : question repassée au RAG", reponse_agent=final[:200])
        doc = _answer_doc(question, trace)
        if not doc["abstained"]:
            return {**doc, "route": "agent>doc"}
        # le RAG ne trouve rien non plus : on garde la réponse de l'agent (question de précision, refus…)
        trace.log("repli annulé", reason="le RAG s'abstient aussi : réponse de l'agent conservée")

    if final is None:
        final = f"Je n'ai pas pu terminer la demande en {MAX_AGENT_STEPS} étapes."
    final = MINSEC.sub(lambda m: f"{m[1]}:{int(m[2]):02d}", final)   # « 1 minute et 45 secondes » -> « 1:45 »
    # le modèle peut annoncer « Séance ajoutée » alors que l'outil a refusé : l'état réel est rappelé par le code
    if any(c["name"] == "ajouter_seances" for c in calls) and not written and not pending:
        final += "\n\nNote : aucune séance n'a été enregistrée dans ton calendrier."
    for p in dict.fromkeys(paces):
        if p not in final:
            final += f"\n\nAllure cible : {p} min/km."
    cited = [s for s in dict.fromkeys(CITATION.findall(final)) if s in sources_seen]
    return {"answer": final, "sources": cited, "abstained": final.upper().startswith(ABSTAIN),
            "tool_calls": calls, "written": written, "asked_confirmation": asked_confirmation,
            "pending_write": pending, "task_success": None,  # calculé par eval.py à partir de l'état final
            "route": "agent", "intention_ecriture": wants_write}


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


def _propose(seances, existing, get_weather, today):
    """Cherche par du code une version des séances qui respecte les règles, pour que le modèle n'ait
    qu'à la recopier après un refus (il raisonnait mal sur la correction, surtout à température > 0).

    Pour chaque séance, dans l'ordre : déplacement vers le jour le plus proche de la même semaine
    (après plutôt qu'avant à distance égale, jamais dans le passé ni sur un jour déjà occupé), puis
    endurance le même jour si elle est intense, puis endurance déplacée. Une modification n'est gardée
    que si elle réduit le nombre de violations. Ensuite, R1 : km réduits au prorata.
    Renvoie la liste conforme, ou None si aucune n'est trouvée (R6 par exemple)."""
    def violations(p):
        return rules.check(p, existing, {x["date"]: get_weather(x["date"]) for x in p})

    def at(x, d):
        y = {**x, "date": d.isoformat()}
        y.pop("jour", None)
        return y

    def easy(x):
        return {**x, "type": "endurance", "titre": "Endurance fondamentale"}

    prop = [dict(x) for x in seances]
    base = len(violations(prop))
    for i, x in enumerate(prop):
        if base == 0:
            break
        d0 = date.fromisoformat(x["date"])
        monday = d0 - timedelta(days=d0.weekday())
        taken = {str(e["date"]) for e in existing} | {y["date"] for j, y in enumerate(prop) if j != i}
        days = sorted((monday + timedelta(days=k) for k in range(7)),
                      key=lambda d: (abs((d - d0).days), d < d0))
        moves = [at(x, d) for d in days if d != d0 and d > today and d.isoformat() not in taken]
        candidates = moves
        if x.get("type") in tools.INTENSE_TYPES:
            candidates = moves + [easy(x)] + [easy(m) for m in moves]
        for c in candidates:
            trial = prop[:i] + [c] + prop[i + 1:]
            n = len(violations(trial))
            if n < base:
                prop, base = trial, n
                break

    if any(v.startswith("R1") for v in violations(prop)):
        for w in {date.fromisoformat(x["date"]) - timedelta(days=date.fromisoformat(x["date"]).weekday()) for x in prop}:
            prev = sum(e.get("km", 0) for e in existing
                       if w - timedelta(days=7) <= date.fromisoformat(str(e["date"])) < w)
            already = sum(e.get("km", 0) for e in existing if w <= date.fromisoformat(str(e["date"])) < w + timedelta(days=7))
            new = [x for x in prop if w <= date.fromisoformat(x["date"]) < w + timedelta(days=7)]
            total = sum(x.get("km", 0) for x in new)
            room = prev * (1 + rules.MAX_VOLUME_INCREASE) - already
            if prev > 0 and total > room > 0:
                for x in new:   # arrondi à 0,5 km inférieur pour ne pas dépasser le plafond
                    x["km"] = int(x.get("km", 0) * room / total * 2) / 2

    if violations(prop):
        return None
    next_monday = today + timedelta(days=7 - today.weekday())
    for x in prop:   # « jour » rempli pour la semaine prochaine, sinon _guarded_write recalculerait l'ancienne date
        d = date.fromisoformat(x["date"])
        if next_monday <= d < next_monday + timedelta(days=7):
            x["jour"] = tools.JOURS[d.weekday()]
    return prop


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
    cache = {}

    def get_weather(d):
        if d not in cache:
            try:
                cache[d] = tools.FUNCTIONS["meteo"]({"date": d}, ctx)
            except Exception:
                cache[d] = {}  # météo indisponible : R5 non vérifiable, on ne bloque pas (à signaler dans le rapport)
        return cache[d]

    weather = {d: get_weather(d) for d in dict.fromkeys(s["date"] for s in seances)}
    violations = rules.check(seances, existing, weather)
    if violations:
        refus = {"refuse": True, "violations": violations}
        proposition = _propose(seances, existing, get_weather, ctx["today"])
        if proposition:
            return {**refus, "proposition": proposition,
                    "consigne": "Rien n'a été écrit. Version conforme calculée par le système : rappelle "
                                "ajouter_seances avec exactement la liste « proposition », sans la modifier, "
                                "puis explique le changement à l'utilisateur."}, None
        return {**refus, "consigne": "Rien n'a été écrit. Rappelle ajouter_seances en corrigeant ainsi : "
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
