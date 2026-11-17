# Sources du corpus

Corpus figé le 06/11/2026. Toute modification doit être datée ici, et les cas de test concernés vérifiés.

## Documents originaux (rédigés pour le projet)

Club fictif « Foulées ECE ». Licence CC BY 4.0. Aucune donnée personnelle.
Les valeurs (plans, zones, règles) sont volontairement précises : le niveau 0 (LLM seul) ne peut pas les connaître,
ce qui permet de mesurer l'apport du RAG.

| Fichier | Contenu |
|---|---|
| plan_5km_debutant.md | Plan 8 semaines, 3 séances, course/marche |
| plan_10km_50min.md | Plan 8 semaines, 4 séances, allure 5:00 min/km |
| plan_semi_1h45.md | Plan 10 semaines, volumes 35 à 51 km |
| plan_marathon_3h45.md | Plan 12 semaines, volumes 40 à 64 km, allure 5:20 min/km (ajouté le 08/11/2026) |
| guide_allures.md | Zones Z1 à Z6 en % de VMA, conversions |
| tests_vma.md | Demi-Cooper, VAMEVAL |
| regles_progression.md | Règles R1 à R7, vérifiées par l'agent |
| glossaire.md | Définitions |

## Documents publics (Wikipédia, CC BY-SA 4.0)

Téléchargés avec `python scripts/fetch_wikipedia.py` (dossier `wikipedia/`). Le script complète ce tableau
avec la date et l'identifiant de révision de chaque article, ce qui fige la version utilisée.

| Fichier | Article | Révision | Date |
|---|---|---|---|
| wikipedia/Vitesse_maximale_aérobie.md | Vitesse maximale aérobie | 241086437 | 17/11/2026 |
| wikipedia/Fartlek.md | Fartlek | 230721134 | 17/11/2026 |
| wikipedia/Marathon_(sport).md | Marathon (sport) | 241222347 | 17/11/2026 |
| wikipedia/Semi-marathon.md | Semi-marathon | 240590354 | 17/11/2026 |
| wikipedia/Course_à_pied.md | Course à pied | 240754956 | 17/11/2026 |
| wikipedia/Échauffement.md | Échauffement | 211280679 | 17/11/2026 |
| wikipedia/Surentraînement.md | Surentraînement | 241181934 | 17/11/2026 |
