"""Niveau 3 : extension « multi-agents » (consigne 2.4) : un orchestrateur et deux agents spécialisés,
liés par des rapports JSON. Mesure attendue : qualité et tokens face à l'agent seul du niveau 2.

Défaut mesuré au niveau 2 qui motive l'extension : laissé seul face à 6 outils, qwen2.5:7b appelait rarement
rechercher_corpus (questions documentaires : 28 % d'exactitude, 0 % de sources citées, contre 92 % au RAG).

- Orchestrateur : classe la demande (DOC, ECRITURE ou ACTION) puis, pour ACTION, pose la question OUI/NON
  d'intention d'écriture. Il produit un rapport JSON {"agent", "classe", "ecriture"} qui choisit l'agent.
- Agent documentaire : la chaîne RAG du niveau 1 (recherche systématique, citations, abstention par seuil).
- Agent actions : la boucle à outils du niveau 2, à qui l'orchestrateur transmet l'intention d'écriture.
- Chaque agent renvoie un rapport JSON. Si le rapport de l'agent actions montre qu'il n'a appelé aucun outil
  sans poser de question de précision (ou en s'abstenant), l'orchestrateur repasse la demande à l'agent
  documentaire ; si celui-ci s'abstient aussi, la réponse de l'agent actions est gardée.

Les rapports sont écrits dans la trace (étapes « rapport ») et renvoyés dans la sortie (clé « rapports »).
"""
import re

from src.levels import level1_rag, level2_agent
from src.llm import chat

AVAILABLE = level2_agent.AVAILABLE
USES_TOOLS = True
ABSTAIN = level2_agent.ABSTAIN
execute_confirmed = level2_agent.execute_confirmed   # écriture après clic « Confirmer » dans l'interface

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


def classify(question, trace):
    """Renvoie "DOC", "ECRITURE" ou "ACTION". Sortie illisible : ACTION (l'agent actions sait tout faire)."""
    res = chat([{"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": question}], temperature=0)
    trace.log_llm(res, note="orchestrateur : classe")
    word = res["content"].upper().replace("É", "E")
    if re.search(r"\bECRITURE\b", word):
        return "ECRITURE"
    if re.search(r"\bDOC\b", word) and "ACTION" not in word:
        return "DOC"
    return "ACTION"


def orchestrate(question, trace):
    """Rapport JSON de l'orchestrateur : quel agent, et avec quelle intention d'écriture."""
    classe = classify(question, trace)
    if classe == "DOC":
        report = {"agent": "documentaire", "classe": classe, "ecriture": False}
    else:
        ecriture = classe == "ECRITURE" or level2_agent.write_intent(question, trace)
        report = {"agent": "actions", "classe": classe, "ecriture": ecriture}
    trace.log("rapport", de="orchestrateur", **report)
    return report


def doc_agent(question, trace):
    """Agent documentaire : chaîne RAG du niveau 1, sortie au format commun et rapport JSON."""
    out = level1_rag.answer(question, trace)
    # retrieved / retrieved_ids retirés : Recall@5 et MRR sont mesurés au niveau 1, sur toutes les questions,
    # et ne seraient calculés ici que sur celles confiées à l'agent documentaire
    out.pop("retrieved", None)
    out.pop("retrieved_ids", None)
    report = {"agent": "documentaire", "abstention": out["abstained"], "sources": out["sources"]}
    trace.log("rapport", de="agent documentaire", **report)
    return {**out, "tool_calls": [], "written": [], "asked_confirmation": False, "pending_write": None,
            "task_success": None, "intention_ecriture": False}, report


def actions_report(out):
    answer = out["answer"]
    return {"agent": "actions", "outils_appeles": len(out["tool_calls"]),
            "question_precision": "?" in answer and not out["abstained"], "abstention": out["abstained"],
            "ecriture_demandee": out["intention_ecriture"], "seances_ecrites": len(out["written"]),
            "confirmation_en_attente": bool(out["pending_write"])}


def answer(question, trace, confirm=None, context=None):
    reports = [orchestrate(question, trace)]
    if reports[0]["agent"] == "documentaire":
        out, report = doc_agent(question, trace)
        return {**out, "route": "doc", "rapports": reports + [report]}

    out = level2_agent.run_agent(question, trace, confirm, context, wants_write=reports[0]["ecriture"])
    report = actions_report(out)
    trace.log("rapport", de="agent actions", **report)
    reports.append(report)

    # Repli vers l'agent documentaire : l'agent actions n'a utilisé aucun outil pour une demande qui n'est pas
    # une écriture, et n'a pas posé de question de précision (réponse de mémoire) ou s'est abstenu sans chercher.
    if (not report["ecriture_demandee"] and report["outils_appeles"] == 0
            and (not report["question_precision"] or report["abstention"])):
        trace.log("repli", reason="agent actions sans outil : demande confiée à l'agent documentaire")
        doc, doc_report = doc_agent(question, trace)
        reports.append(doc_report)
        if not doc["abstained"]:
            return {**doc, "route": "agent>doc", "rapports": reports}
        # l'agent documentaire ne trouve rien : la réponse de l'agent actions (précision, refus…) est gardée
        trace.log("repli annulé", reason="l'agent documentaire s'abstient aussi")
    return {**out, "route": "agent", "rapports": reports}
