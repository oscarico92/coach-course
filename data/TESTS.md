# Jeu de test (`tests.jsonl`)

47 cas, figés le 08/11/2026, à ne plus modifier une fois les premières mesures faites
(sinon, dater le changement et relancer tous les niveaux).

| Type | Nb | Minimum du sujet | Ce que l'on vérifie |
|---|---|---|---|
| `in_docs` | 25 | 20 | réponse correcte (`must_contain` puis juge LLM), source citée parmi `expected_sources` |
| `absent` | 5 | 5 | abstention |
| `task` | 12 | 10 | état final vérifié par du code (`check`), pass^3 sur 3 essais |
| `ambiguous` | 5 | 5 | `clarification` (question de précision) ou `refus` |

## Champs

- `must_contain` : éléments qui doivent apparaître dans la réponse (premier filtre automatique, avant le juge LLM).
- `ref_date` : date « d'aujourd'hui » simulée pour les tâches (2026-11-12, un jeudi) ; « la semaine prochaine » = 16-22 novembre.
- `fixtures.calendar` : séances déjà présentes dans le calendrier avant la tâche.
- `fixtures.weather` : météo simulée, utilisée à la place d'Open-Meteo pendant l'évaluation, pour que les tests soient reproductibles.
- `confirm` : réponse simulée de l'utilisateur quand l'agent demande confirmation avant d'écrire (`false` : il refuse).

## Vérifications des tâches (`check`)

| Clé | Signification |
|---|---|
| `answer_paces` + `tolerance_s` | allures attendues (min:s) dans la réponse, à ± `tolerance_s` secondes |
| `answer_contains` | valeurs qui doivent apparaître dans la réponse |
| `ics_new_events` / `ics_new_events_min` | nombre d'événements ajoutés au calendrier |
| `ics_dates` | dates exactes des événements ajoutés |
| `ics_no_intense_on` / `ics_no_event_on` | dates où aucune séance intense / aucune séance ne doit être ajoutée |
| `no_consecutive_intense` | règle R2 respectée sur la semaine |
| `no_consecutive_days`, `min_rest_days` | règles du plan 5 km et R6 |
| `ics_week_km_max` | règle R1 : volume de la semaine plafonné (40 km la semaine précédente, donc 44 km au plus) |
| `asked_confirmation` | l'agent a demandé une confirmation avant l'écriture |

## Valeurs calculées (vérifiées)

- VMA 15 km/h : EF 70 % = 5:43, seuil 85 % = 4:42, 10 km 90 % = 4:27 min/km.
- Demi-Cooper 1 450 m : VMA 14,5 km/h ; 400 m à 95 % = 104,5 s, soit 1:45.
- Tâche 8 : semaine précédente = 10 + 8 + 8 + 14 = 40 km, donc 44 km maximum (R1).
- Tâche 10 : 9 + 8 + 9 + 6 = 32 km, 2 séances intenses.
- Marathon 3 h 45 : 225 min / 42,195 km = 5:20 min/km. Semi 1 h 45 : 4:58 min/km.

## Ce que le jeu de test ne couvre pas

Les questions de culture générale sur la course (où le niveau 0 est déjà bon) sont volontairement peu nombreuses :
le jeu de test mesure ce que le RAG et l'agent apportent. À mentionner dans le rapport.
