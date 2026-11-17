"""Contrat des outils de l'agent (niveau 2).

Ce fichier fixe ce que le LLM voit (schémas JSON) et comment chaque outil est classé par effet.
Les implémentations sont dans src/tools/impl.py.

Signature commune : fonction(args: dict, ctx: dict) -> dict (sérialisable en JSON).
`ctx` contient :
    today          : datetime.date, « aujourd'hui » (simulé pendant l'évaluation)
    weather        : dict date ISO -> {"tmax_c", "vent_kmh", "orage"} ou None (alors appel réel à Open-Meteo)
    calendar_path  : pathlib.Path du fichier .ics de l'utilisateur
En cas d'erreur, lever une exception avec un message clair : la boucle de l'agent le renvoie au modèle.
"""
from src.tools import impl

# Types de séance reconnus. Les types « intenses » (zones Z4 à Z6) sont soumis aux règles R2 et R5.
SESSION_TYPES = ["recuperation", "endurance", "sortie_longue", "allure_marathon",
                 "allure_semi", "allure_10km", "seuil", "fractionne"]
INTENSE_TYPES = {"allure_semi", "allure_10km", "seuil", "fractionne"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

SCHEMAS = [
    {"type": "function", "function": {
        "name": "calcul_allures",
        "description": "Calcule les allures d'entraînement (min/km) par zone du club à partir d'une VMA, "
                       "ou d'un temps objectif sur une distance. Toujours utiliser cet outil pour un calcul d'allure.",
        "parameters": {"type": "object", "properties": {
            "vma_kmh": {"type": "number", "description": "VMA en km/h"},
            "temps_objectif_min": {"type": "number", "description": "temps visé en minutes"},
            "distance_km": {"type": "number", "description": "distance de la course visée en km (5, 10, 21.0975, 42.195)"},
            "distance_test_m": {"type": "number", "description": "distance parcourue au test demi-Cooper (6 min), en mètres"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "meteo",
        "description": "Prévisions météo d'un jour : température maximale, vent, risque d'orage.",
        "parameters": {"type": "object", "properties": {
            "date": {"type": "string", "description": "date au format AAAA-MM-JJ"}},
            "required": ["date"]}}},
    {"type": "function", "function": {
        "name": "lire_calendrier",
        "description": "Liste les séances déjà prévues dans le calendrier de l'utilisateur entre deux dates incluses.",
        "parameters": {"type": "object", "properties": {
            "date_debut": {"type": "string", "description": "AAAA-MM-JJ"},
            "date_fin": {"type": "string", "description": "AAAA-MM-JJ"}},
            "required": ["date_debut", "date_fin"]}}},
    {"type": "function", "function": {
        "name": "rechercher_corpus",
        "description": "Cherche dans les documents du club (plans 5 km, 10 km, semi, marathon, allures, règles). "
                       "Renvoie des extraits avec leur fichier source, à citer entre crochets.",
        "parameters": {"type": "object", "properties": {
            "requete": {"type": "string"}}, "required": ["requete"]}}},
    {"type": "function", "function": {
        "name": "semaine_plan",
        "description": "Séances d'une semaine d'un plan du club, placées la semaine prochaine, avec jour, titre, "
                       "type et km, plus l'allure cible du plan : à passer telles quelles (ou filtrées) à ajouter_seances.",
        "parameters": {"type": "object", "properties": {
            "plan": {"type": "string", "enum": ["5km", "10km", "semi", "marathon"]},
            "semaine": {"type": "integer", "description": "numéro de semaine du plan (1 = première)"}},
            "required": ["plan", "semaine"]}}},
    {"type": "function", "function": {
        "name": "ajouter_seances",
        "description": "AJOUTE des séances au calendrier de l'utilisateur. Action qui modifie ses données : "
                       "l'utilisateur devra confirmer, et les règles du club sont vérifiées avant l'écriture.",
        "parameters": {"type": "object", "properties": {
            "seances": {"type": "array", "items": {"type": "object", "properties": {
                "jour": {"type": "string", "enum": JOURS,
                         "description": "jour de la semaine prochaine ; à préférer à date"},
                "date": {"type": "string", "description": "AAAA-MM-JJ, seulement hors semaine prochaine"},
                "titre": {"type": "string", "description": "ex. « Fractionné 8 × 400 m à 95 % VMA »"},
                "type": {"type": "string", "enum": SESSION_TYPES},
                "km": {"type": "number", "description": "distance estimée en km"},
                "duree_min": {"type": "number"}},
                "required": ["titre", "type", "km"]}}},
            "required": ["seances"]}}},
]

# Classement des outils par effet : seuls les outils « write » demandent une confirmation.
EFFECTS = {"calcul_allures": "read", "meteo": "read", "lire_calendrier": "read",
           "rechercher_corpus": "read", "semaine_plan": "read", "ajouter_seances": "write"}

FUNCTIONS = {name: getattr(impl, name) for name in EFFECTS}


def ready():
    """Vrai quand tous les outils sont implémentés (plus aucun n'est marqué @todo)."""
    return not any(getattr(f, "todo", False) for f in FUNCTIONS.values())
