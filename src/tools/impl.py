"""Implémentation des outils. À FAIRE (binôme) : remplacer chaque `raise NotImplementedError`
et retirer le décorateur @todo. Le contrat (arguments, retours) est décrit dans chaque docstring
et dans src/tools/__init__.py. Le test `python tests/test_agent_loop.py` doit continuer de passer.
"""


def todo(f):
    f.todo = True
    return f


@todo
def calcul_allures(args, ctx):
    """Allures par zone du club (guide_allures.md), au format "m:ss" min/km.

    Entrées possibles (au moins une) :
      - vma_kmh
      - temps_objectif_min + distance_km  -> renvoie aussi "allure_cible" ; VMA estimée si distance 10 km : v / 0,90
      - distance_test_m (demi-Cooper)     -> VMA = distance / 100
    Retour : {"vma_kmh": 15.0, "allures": {"EF (70 %)": "5:43", "seuil (85 %)": "4:42", "10 km (90 %)": "4:27",
              "VMA (100 %)": "4:00", ...}, "allure_cible": "5:00" (si objectif)}
    Erreur si aucune entrée exploitable.
    """
    raise NotImplementedError


@todo
def meteo(args, ctx):
    """Météo du jour args["date"].
    Mode évaluation (ctx["weather"] n'est pas None) : renvoyer ctx["weather"][date] si présente,
    sinon ctx["weather_default"] ; AUCUN appel réseau, pour que les tests soient reproductibles.
    Mode interactif (ctx["weather"] is None) : appel Open-Meteo (Paris par défaut). Retour : {"date", "tmax_c", "vent_kmh", "orage": bool}.
    """
    raise NotImplementedError


@todo
def lire_calendrier(args, ctx):
    """Séances du fichier ctx["calendar_path"] (.ics, bibliothèque icalendar) entre date_debut et date_fin incluses.
    Retour : {"seances": [{"date", "titre", "type", "km", "intense": bool}, ...], "km_total": float}
    Un calendrier inexistant = liste vide (pas une erreur).
    """
    raise NotImplementedError


@todo
def ajouter_seances(args, ctx):
    """Écrit args["seances"] dans ctx["calendar_path"] (un VEVENT par séance, journée entière).
    Stocker type et km dans l'événement (ex. DESCRIPTION ou X-propriétés) pour que lire_calendrier les relise.
    N'est appelée QU'APRÈS confirmation de l'utilisateur et vérification des règles (boucle de l'agent).
    Retour : {"ajoutees": n, "dates": [...]}
    """
    raise NotImplementedError


@todo
def init_calendrier(path, seances):
    """Crée un calendrier .ics à `path` contenant `seances` (format de tests.jsonl : date, titre, intense, km).
    Utilisée par l'évaluation pour partir d'un état connu avant chaque tâche."""
    raise NotImplementedError


def rechercher_corpus(args, ctx):
    """Réutilise la recherche hybride du niveau 1 (déjà implémentée)."""
    from src.levels.level1_rag import retrieve
    hits, top = retrieve(args["requete"])
    return {"score_max": round(top, 3),
            "extraits": [{"source": h["source"], "section": h["section"], "texte": h["text"]} for h in hits]}
