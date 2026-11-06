"""Niveau 2 : agent outillé (semaine 2-3). Boucle écrite SANS framework.

Outils prévus (schémas JSON passés à src.llm.chat(tools=...)) :
- calcul_allures      (lecture)  : VMA ou temps objectif -> allures par type de séance
- meteo               (lecture)  : Open-Meteo, prévisions par jour
- lire_calendrier     (lecture)  : séances déjà prévues dans calendar/*.ics
- ajouter_seances     (ÉCRITURE) : n'écrit qu'après confirmation explicite de l'utilisateur
- rechercher_corpus   (lecture)  : réutilise le retrieve() du niveau 1

Boucle bornée par MAX_AGENT_STEPS ; toute erreur d'outil est renvoyée au modèle
dans un message role="tool" ; règles métier vérifiées par du code avant écriture
(ex. pas deux séances intenses consécutives, +10 % de volume max par semaine).
"""

AVAILABLE = False


def answer(question, trace, confirm=None):
    raise NotImplementedError("Niveau 2 (agent) pas encore implémenté")
