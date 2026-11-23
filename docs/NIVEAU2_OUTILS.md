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

## Suites de l'issue #4

- **Semaine de course** : quand la sortie longue du plan est « Course le dimanche », `semaine_plan` ne crée plus de sortie longue et renvoie la course à part (clé `course`). Les jours écrits dans le plan (« (jeudi) », « le mercredi ») sont respectés et l'endurance va sur un jour libre.
- **« 2 × 6 km »** est compté 12 km (plan marathon, séance C).
- **Relance** : si le modèle pose une question avant tout appel d'outil, c'est une demande de précision et on ne le relance plus. Après un appel d'outil, une question est une demande de confirmation (« Voulez-vous que j'ajoute… ? ») et la relance s'applique toujours. Une première version qui ne relançait jamais une réponse avec « ? » faisait retomber task-003 et task-005 (10/12).
- **Tests** : `tests/test_outils.py` (18 cas sur `calcul_allures` et `semaine_plan`) et 3 cas de relance dans `test_agent_loop.py` (11/11).

Mesure après ces changements : tâches 12/12, cas ambigus `amb-*` au niveau 2 : 5/5.

## Routage des questions documentaires (22/11/2026)

**Constat.** Sur les 25 questions `doc-*`, le niveau 2 obtenait 24 à 28 % d'exactitude, 0 % de sources citées
et 52 % d'abstentions à tort, contre 92 %, 92 % et 0 % au niveau 1. L'outil `rechercher_corpus` utilise pourtant
la même recherche que le niveau 1. La différence : au niveau 1 la recherche est toujours faite, au niveau 2 le
modèle doit décider de l'appeler, et avec 6 outils et un prompt centré sur le calendrier, `qwen2.5:7b` le faisait
rarement (réponse de mémoire ou « JE NE SAIS PAS » sans chercher).

**Correction.** Un premier appel court au modèle (`route`, température 0) classe la question :
- `DOC` (information sur les plans, règles, définitions, sans calcul personnel ni calendrier) : chaîne RAG du
  niveau 1 (recherche systématique, citations, abstention par seuil) ;
- `ACTION` (calcul à partir de chiffres personnels, calendrier, météo, demande vague, hors sujet ou médicale) :
  boucle de l'agent, inchangée. Une sortie illisible du routeur envoie aussi vers la boucle.

Les exemples du prompt de routage ne viennent pas de `data/tests.jsonl` ; deux exemples trop proches de cas de test
(`task-h03`, `amb-001`) ont été retirés pour ne pas biaiser la mesure des tâches non vues.

**Coût.** Un appel LLM de plus par question (quelques centaines de tokens).

**Mesurer.** `AGENT_ROUTER=0` rend le comportement d'avant. `eval.py` affiche le routage par type de question et les
cas mal routés (attendu : `in_docs` et `absent` vers le RAG, `task` et `ambiguous` vers la boucle) ; le détail
est aussi dans `results/summary.json` (clé `routage`) et dans `route` de `results/level2_raw.jsonl`.

```bash
AGENT_ROUTER=0 python eval.py --levels 2      # avant (sous Windows : set AGENT_ROUTER=0)
python eval.py --levels 2                     # après
```

**Risque à surveiller.** Une tâche de calcul envoyée par erreur au RAG (ex. « je vise 1 h 50 au semi, quelle
allure ? ») recevrait l'allure du plan 1 h 45 au lieu d'un calcul. Les écarts de routage sur les `task-*`
sont donc le premier chiffre à regarder après la mesure.

### Mesure du routage et repli vers le RAG (22/11/2026)

Premier run avec routage (`qwen2.5:7b`) : exactitude doc 28 % -> 56 %, sources citées 0 % -> 44 %, abstention à tort
52 % -> 24 %. Aucune tâche envoyée au RAG, mais 12 questions `doc-*` sur 25 restent dans la boucle : surtout des
questions à la première personne (« je peux… ? », « ma sortie longue… ») et des questions sur une séance précise d'un plan.

Les tâches passent toutes par la boucle, dont le code n'a pas changé, et pourtant : tâches vues 83 % -> 92 %, non vues
40 % -> 20 %. Ollama n'est donc pas déterministe à température 0 ; un écart d'une tâche n'est pas un effet mesuré.

Plutôt que de retoucher le prompt du routeur sur les cas qui échouent (ce serait régler le routeur sur le jeu de test),
un repli structurel : si la boucle se termine **sans aucun appel d'outil**, sans question de précision (« ? ») et sans
demande d'écriture, la question est repassée au RAG (route `agent>doc` dans les résultats). `AGENT_FALLBACK=0` le désactive.

À vérifier après mesure : les refus `amb-004` et `amb-005` peuvent partir en repli ; ils restent corrects si le RAG
s'abstient ou oriente vers un professionnel de santé.

### Diagnostic des questions restées dans la boucle (`scripts/diag_routage.py`)

Run avec repli : exactitude doc 60 %, sources 48 %, un seul cas rattrapé. Sur les 11 questions `doc-*` restées dans la boucle :

- 5 sans outil, réponse « Je ne sais pas… ? » (doc-003, 004, 012, 019, 024) : le « ? » bloquait le repli. Corrigé :
  une réponse sans outil qui commence par « JE NE SAIS PAS » est repassée au RAG, même avec une question.
- 6 avec un outil mal choisi ou mal utilisé, non corrigés (limites du modèle 7B, à citer dans le rapport) :
  `meteo` pour une question de règle (doc-018, doc-025, qui annonce même ajouter une séance alors qu'on ne lui a rien
  demandé) ; `calcul_allures` avec 90 min au lieu de 105 pour 1 h 45 (doc-011, 4:16 au lieu de 4:58) ; bonne réponse
  sans citation après `semaine_plan` ou `calcul_allures` (doc-010, doc-023) ; « 13.3 » au lieu de « 13,3 » (doc-015,
  contrôle par mots-clés sensible au séparateur décimal, non modifié pour ne pas changer la métrique après coup).

### Repli sur abstention : mesure et ajustement

Run suivant : exactitude doc 76 %, sources 68 %, abstention à tort 0 %, mais ambigus 100 % -> 80 % : amb-001
(« C'est quoi la meilleure ? ») partait en repli, le RAG s'abstenait sans poser de question. Ajustement : le repli ne
remplace la réponse de l'agent que si le RAG apporte une réponse ; sinon la réponse de l'agent est conservée.
Règle trouvée en analysant l'échec d'amb-001 (à mentionner), mais indépendante de la formulation des questions.

## Diagnostic des tâches et corrections (23/11/2026)

Run de référence (routage + repli) : tâches vues 92 %, **non vues 20 %**. `scripts/diag_taches.py` :

| Tâche | Cause | Correction |
|---|---|---|
| task-h01 « Cale-moi la semaine 2 » | non reconnue comme écriture par `WRITE_REQUEST` : pas de relance, séances listées mais pas ajoutées | intention d'écriture donnée par le routeur (classe `ECRITURE`), le regex ne sert plus que sans routage |
| task-h05 « au programme » | prise pour une écriture : relance vers `ajouter_seances`, réponse (35 km) perdue | idem |
| task-h03 « 1 h 50 » | `temps_objectif_min: 100` au lieu de 110 (même erreur que doc-011 : 90 au lieu de 105) | `calcul_allures` reçoit `temps_objectif` en texte recopié (« 1 h 50 ») et le code convertit (`duree_minutes`) |
| task-007 | allure juste mais écrite « 1 minute et 45 secondes » | réécrite en « 1:45 » par le code |
| task-h02 | séance refusée (météo), le modèle répond « Séance ajoutée » sans rien écrire | non corrigeable par le code ; la réponse rappelle désormais qu'aucune séance n'a été enregistrée |

Principe, comme pour les dates : le modèle recopie, le code calcule.

**Biais de mesure.** Ces corrections viennent de l'analyse de task-h01, h02, h03 et h05 : ces tâches ne sont plus
« non vues ». Les exemples du routeur n'utilisent ni « cale » ni « programme », mais il faut de nouvelles tâches
non vues (`task-h06` et suivantes, écrites sans regarder le code) pour mesurer honnêtement la généralisation.

**À surveiller.** Le prompt du routeur a changé (3 classes) : le routage des questions `doc-*` peut bouger.

**Mesure (23/11/2026).** Questions doc : exactitude 92 % (égale au niveau 1), sources 80 %, ambigus 100 %.
Tâches non vues 20 % -> 60 % (h03, h05), mais tâches vues 92 % -> 83 % : task-002 et task-012 (« calcule… **et
ajoute**… ») n'étaient plus relancées, le routeur les classant sans doute en ACTION à cause du calcul (le regex
les attrapait par « ajoute »). Correction : ECRITURE prioritaire quand la demande contient un ajout, même avec un
calcul. `diag_taches.py` affiche désormais l'intention d'écriture retenue.
