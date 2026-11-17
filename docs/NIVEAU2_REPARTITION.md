# Niveau 2 : répartition du travail

## Déjà fait (Oscar)

| Fichier | Contenu |
|---|---|
| `src/tools/__init__.py` | **Contrat** : schémas JSON des 5 outils vus par le LLM, classement par effet (lecture / écriture) |
| `src/levels/level2_agent.py` | Boucle de l'agent sans framework : bornée (étapes et tokens), erreurs d'outils renvoyées au modèle, confirmation avant écriture |
| `src/rules.py` | Règles du club R1, R2, R5, R6 vérifiées par du code avant toute écriture |
| `tests/test_agent_loop.py` | 8 tests de la boucle avec un LLM simulé (sans Ollama) |
| `eval.py` | Contexte reproductible pour les tâches : date, météo et calendrier simulés, confirmation simulée |

## À faire (binôme) : `src/tools/impl.py`

Remplacer chaque `raise NotImplementedError` et retirer le décorateur `@todo`. Le contrat exact
(arguments et retours) est dans la docstring de chaque fonction.

| Fonction | Effet | Notes |
|---|---|---|
| `calcul_allures` | lecture | zones de `guide_allures.md` ; allure = 60 / vitesse ; demi-Cooper : VMA = distance / 100 |
| `meteo` | lecture | en évaluation, AUCUN appel réseau (`ctx["weather"]`, sinon `ctx["weather_default"]`) ; sinon Open-Meteo |
| `lire_calendrier` | lecture | bibliothèque `icalendar` ; calendrier absent = liste vide |
| `ajouter_seances` | **écriture** | n'est appelée qu'après règles et confirmation ; stocker type et km pour la relecture |
| `init_calendrier` | (évaluation) | crée le calendrier de départ d'une tâche |

`rechercher_corpus` est déjà implémenté (réutilise le niveau 1).

## Vérifier

```bash
python tests/test_agent_loop.py                 # boucle avec outils simulés : 8/8
python tests/test_agent_loop.py --vrais-outils  # même chose avec vos implémentations
python eval.py --levels 2 --limit 5             # le niveau 2 devient disponible quand plus aucun outil n'est @todo
```

## Reste à faire ensuite (Oscar)

Dans `eval.py` : vérification de l'état final des tâches (champ `check` de `tests.jsonl`) et pass^3.
