"""Questions de suivi dans l'interface (hors évaluation).

Les niveaux 0 à 3 traitent une question isolée : c'est ce que mesure eval.py. Pour qu'un utilisateur puisse
enchaîner (« et pour la semaine 2 ? »), l'interface réécrit d'abord la question en question autonome à partir
des derniers échanges (« Quelle est la séance de fractionné de la semaine 2 du plan 10 km ? »), puis la passe au
niveau choisi, sans rien changer à celui-ci. Technique standard du RAG conversationnel (réécriture de requête).

Non mesuré par le jeu de test, qui ne contient que des questions isolées.
"""
from src.llm import chat

MAX_TURNS = 3          # échanges précédents transmis
MAX_ANSWER_CHARS = 400  # réponses tronquées : le sujet suffit, pas le détail

PROMPT = """Tu reformules la dernière question d'un coureur pour qu'elle soit compréhensible SEULE, sans l'historique.
- Remplace les références implicites (« et pour la semaine 2 ? », « mets-la samedi », « la même chose en 1 h 50 »)
  par ce qu'elles désignent dans la conversation (plan, semaine, séance, allure, jour…).
- Garde le sens, la langue et les chiffres de la question ; n'ajoute aucune information absente de la conversation.
- Si la question est déjà compréhensible seule, recopie-la telle quelle.
Réponds uniquement par la question reformulée, sans guillemets ni commentaire."""


def _history_text(history):
    lines = []
    for turn in history[-MAX_TURNS:]:
        answer = " ".join((turn.get("answer") or "").split())
        if len(answer) > MAX_ANSWER_CHARS:
            answer = answer[:MAX_ANSWER_CHARS] + "…"
        lines.append(f"Coureur : {turn['question']}\nCoach : {answer}")
    return "\n\n".join(lines)


def standalone_question(question, history, trace=None):
    """Renvoie la question à passer au niveau. Sans historique : la question telle quelle, sans appel au modèle.
    Sortie du modèle vide ou aberrante (plus de 3 fois la longueur de la question + 200 caractères) : question
    d'origine, pour ne jamais envoyer au niveau autre chose qu'une question."""
    if not history:
        return question
    res = chat([{"role": "system", "content": PROMPT},
                {"role": "user", "content": f"Conversation :\n{_history_text(history)}\n\nDernière question : {question}"}],
               temperature=0)
    if trace is not None:
        trace.log_llm(res, note="reformulation de la question de suivi")
    rewritten = res["content"].strip().strip("«»\"' ").strip()
    if not rewritten or len(rewritten) > 3 * len(question) + 200:
        rewritten = question
    if trace is not None:
        trace.log("reformulation", question=question, question_autonome=rewritten)
    return rewritten
