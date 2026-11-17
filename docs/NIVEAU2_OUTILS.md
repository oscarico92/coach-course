# Niveau 2 : outils et réglage de l'agent

Suite de `NIVEAU2_REPARTITION.md` : implémentation des outils, puis corrections de l'agent après les premières mesures.

## Résultat

Tâches du niveau 2 (`data/tests.jsonl`, type `task`), `qwen2.5:7b`, température 0 :

| Version | Tâches réussies |
|---|---|
| Outils seuls, prompt d'origine | 5 / 12 |
| + nouveau prompt (jours à venir, agir sans demander) | 9 / 12 |
| + `semaine_plan`, relance, dates calculées par le code | 10 / 12 |
| + consignes de refus par règle, format m:ss | **12 / 12** |

Tests sans Ollama : `test_agent_loop.py` 8/8 (avec et sans `--vrais-outils`), `test_task_checks.py` 24/24.

## Outils (`src/tools/impl.py`)

| Outil | Ce qu'il fait |
|---|---|
| `calcul_allures` | VMA à partir de `vma_kmh`, du demi-Cooper (`distance_test_m / 100`) ou d'un temps objectif (VMA = vitesse / 0,90 pour un 10 km, / 0,82 semi, / 0,77 marathon). Renvoie les allures par zone, l'allure cible, les temps au 400 m à 95 % et au 1000 m à 90 %. Refuse une VMA hors de 8 à 25 km/h. |
| `meteo` | En évaluation : `ctx["weather"]`, sinon `weather_default`, aucun appel réseau. Sinon Open-Meteo (Paris), orage = codes 95, 96, 99. |
| `lire_calendrier` | Lit le .ics avec `icalendar`. Type, km et intensité sont relus depuis `X-COACH-TYPE`, `X-COACH-KM`, `X-COACH-INTENSE`. Fichier absent = liste vide. |
| `ajouter_seances` | Un VEVENT journée entière par séance. Refuse les dates passées, ignore une séance déjà présente (même date, même titre). |
| `init_calendrier` | Recrée le calendrier de départ d'une tâche. |
| `semaine_plan` (nouveau) | Lit le tableau du plan dans `data/corpus/` et renvoie les séances de la semaine demandée, placées la semaine prochaine, avec jour, titre, type, km et l'allure cible du plan. |

Arrondi des allures : à la seconde la plus proche. Le semi en 1 h 45 donne 4:59 (le corpus écrit 4:58, valeur tronquée), dans la tolérance de 5 s.

## Problèmes observés et corrections

**Le modèle demandait au lieu d'agir.** L'ancien prompt disait de poser une question si une information manquait et de consulter calendrier et météo avant d'écrire. Le modèle posait une question (« quelle date ? ») ou épuisait ses 6 étapes. Le prompt dit maintenant d'appeler `ajouter_seances` directement : les règles et la météo sont vérifiées par le code, et la confirmation est demandée par le système.

**Mauvaises dates.** Même avec la liste des jours dans le prompt, le modèle écrivait « mercredi 15 » ou prenait un vendredi comme lundi. Le modèle passe désormais `"jour": "mardi"` et `_guarded_write` calcule la date de la semaine prochaine. `date` reste possible pour une autre semaine.

**Contenu des plans mélangé.** La recherche RAG renvoyait des extraits de plusieurs plans (fractionné du plan 10 km dans le plan 5 km débutant). `semaine_plan` lit directement le bon tableau.

**Annonce sans action.** « Je vais ajouter les séances… » puis fin de la boucle. Si la question demande un ajout (ajoute, mets, prévois…) et qu'aucune écriture n'est arrivée jusqu'à la confirmation, la boucle relance le modèle, deux fois au plus.

**Refus mal corrigés.** Avec du vent samedi, le modèle retentait samedi avec moins de km. Le refus contient maintenant une consigne propre à la règle violée (vent : changer de jour ; chaleur : endurance ou autre jour ; R2 : deux jours d'écart ; R1 : réduire les km ; R6 : retirer une séance).

**Allures absentes ou en toutes lettres.** L'allure cible renvoyée par un outil est ajoutée en fin de réponse si le modèle l'a oubliée, et le prompt impose le format m:ss.

**Budget d'étapes.** `MAX_AGENT_STEPS` passe de 6 à 10 : plan, allures, écriture, refus et correction ne tenaient pas en 6.

## Fichiers modifiés

- `src/tools/impl.py` : les outils
- `src/tools/__init__.py` : schéma de `semaine_plan`, champ `jour` dans `ajouter_seances` (`date` n'est plus obligatoire)
- `src/levels/level2_agent.py` : prompt, calcul des dates, relance, consignes de refus, allure cible
- `config.py`, `.env.example` : `MAX_AGENT_STEPS=10`
- `tests/test_agent_loop.py` : avec `--vrais-outils`, le test relit le vrai fichier .ics au lieu du calendrier simulé

## Limites restantes

- Les 12 tâches passent, mais le contenu n'est pas toujours celui du plan : pour une séance isolée, le modèle n'appelle pas toujours `semaine_plan` (task-012 : un fractionné au lieu de la séance de seuil du plan).
- La réponse texte peut citer une mauvaise date alors que le calendrier est juste (task-006 : « dimanche 19 », séance bien enregistrée le 22).
- « Prévois-moi 48 km » : le modèle pose une question au lieu de proposer 44 km. La tâche passe car rien n'est écrit.
- Pas encore mesuré : questions documentaires (`doc-*`) avec le nouveau prompt, et stabilité sur plusieurs essais (`python eval.py --levels 2 --pass-k 3`).

## Reproduire

```bash
ollama pull qwen2.5:7b
ollama pull bge-m3
python tests/test_agent_loop.py --vrais-outils
python tests/test_task_checks.py
python eval.py --levels 2
```
