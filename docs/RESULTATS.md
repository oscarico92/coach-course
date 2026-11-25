# Résultats : architecture ou taille du modèle ?

Synthèse des mesures du 22 au 24/11/2026 sur le jeu de test `data/tests.jsonl` (52 cas : 25 `in_docs`, 5 `absent`,
5 `ambiguous`, 17 `task` dont 5 « non vues » `task-h*`). Le détail de chaque correction et de chaque diagnostic est
dans `NIVEAU2_OUTILS.md`.

Chiffres relevés sur les sorties de `python eval.py` (tableau final de chaque run). « n/a » : métrique non applicable.

> **Restructuration du 24/11 (après lecture de la consigne).** Le niveau 3 doit être une extension de la liste 2.4,
> mesurée contre le niveau 2. Le routeur et le repli ont donc quitté le niveau 2 pour devenir l'extension
> **multi-agents** (`src/levels/level3_ext.py`) : un orchestrateur confie la demande à un agent documentaire (chaîne
> RAG) ou à un agent actions (boucle à outils du niveau 2), avec des rapports JSON. Le niveau 2 redevient l'agent
> seul, avec la question OUI/NON d'intention d'écriture et la proposition appliquée par le système.
> Les options `AGENT_ROUTER` et `AGENT_FALLBACK` n'existent plus.
>
> Correspondance avec les mesures ci-dessous : la configuration C est le niveau 3 actuel. La configuration D est
> proche du niveau 2 actuel, sans être identique (D utilisait le regex d'origine pour l'intention d'écriture et
> n'appliquait pas la proposition). Le tableau final des niveaux 0 à 3 a été mesuré avec `python eval.py`,
> pour chaque modèle : c'est fait, voir la section 0.

## 0. Tableau final : niveaux 0 à 3 (runs du 24 et 25/11/2026)

Une seule commande, `python eval.py`, pour chaque modèle ; métrique du 24/11 (formats équivalents, voir
`data/TESTS.md`). Résultats bruts et traces : `resultats_finaux/<modèle>/`.

**qwen2.5:7b** (local, Ollama, RTX 5060 8 Go) : `resultats_finaux/qwen2.5-7b/results/summary.md`

| Niveau | Recall@5 | MRR | Exactitude | Sources citées | Abstention | Abst. à tort | Ambigus OK | Tâches vues | Tâches non vues\* | pass^3 | Tokens / req. | Latence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 · LLM seul | n/a | n/a | 8 % | 0 % | 100 % | 44 % | 80 % | n/a | n/a | n/a | 312 | 15,0 s |
| 1 · RAG | 100 % | 0,89 | 100 % | 96 % | 100 % | 0 % | 60 % | n/a | n/a | n/a | 1 178 | 18,7 s |
| 2 · Agent | n/a | n/a | 20 % | 0 % | 80 % | 60 % | 100 % | 92 % | 100 % | 76 % | 3 772 | 23,6 s |
| 3 · Multi-agents | n/a | n/a | 92 % | 80 % | 100 % | 0 % | 100 % | 92 % | 100 % | 76 % | 3 673 | 23,3 s |

**gpt-6-luna** (API OpenAI, `OPENAI_REASONING_EFFORT=none`) : `resultats_finaux/gpt-6-luna/results/summary_rescore.md`
(run du 24/11 recalculé avec la métrique du 24/11 par `python eval.py --rescore`, sans nouvel appel au modèle)

| Niveau | Recall@5 | MRR | Exactitude | Sources citées | Abstention | Abst. à tort | Ambigus OK | Tâches vues | Tâches non vues\* | pass^3 | Tokens / req. | Latence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 · LLM seul | n/a | n/a | 16 % | 0 % | 80 % | 28 % | 60 % | n/a | n/a | n/a | 245 | 1,7 s |
| 1 · RAG | 100 % | 0,89 | 96 % | 100 % | 100 % | 0 % | 80 % | n/a | n/a | n/a | 1 024 | 3,4 s |
| 2 · Agent | n/a | n/a | 100 % | 100 % | 100 % | 0 % | 60 % | 100 % | 100 % | 100 % | 5 155 | 5,8 s |
| 3 · Multi-agents | n/a | n/a | 96 % | 100 % | 100 % | 0 % | 60 % | 100 % | 100 % | 100 % | 4 106 | 5,5 s |

\* Tâches « non vues » contaminées : elles ont servi à corriger le niveau 2 (section 7).

### Extension (niveau 3) mesurée contre l'agent seul (niveau 2)

| | qwen2.5:7b | gpt-6-luna |
|---|---|---|
| Exactitude doc | 20 % → 92 % (**+72 points**) | 100 % → 96 % (−4 points, 1 cas) |
| Sources citées | 0 % → 80 % | 100 % → 100 % |
| Abstention / à tort | 80 % / 60 % → 100 % / 0 % | 100 % / 0 % → 100 % / 0 % |
| Ambigus OK | 100 % → 100 % | 60 % → 60 % |
| pass^3 | 76 % → 76 % | 100 % → 100 % |
| Tokens / requête | 3 772 → 3 673 (−3 %) | 5 155 → 4 106 (**−20 %**) |
| Latence | 23,6 s → 23,3 s | 5,8 s → 5,5 s |

**Lecture.** L'extension corrige le défaut mesuré au niveau 2 avec le petit modèle : seul, qwen2.5:7b n'utilise
presque pas ses documents (20 %, aucune source citée, 60 % d'abstentions à tort) ; l'orchestrateur, en confiant ces
questions à l'agent documentaire, le ramène à 92 %. Avec gpt-6-luna, qui sait déjà chercher seul, elle n'apporte rien
en qualité (un cas perdu) et sert surtout à réduire le coût (−20 % de tokens). Elle ne change pas les tâches : elles
passent par le même agent actions, et leur plafond est celui du modèle (pass^3 76 % contre 100 %).

**Proposition appliquée par le système (qwen2.5:7b).** Un premier run final avait tourné avec
`AGENT_AUTO_PROPOSITION=0` par erreur : tâches vues 75 %, pass^3 59 % aux niveaux 2 et 3. Relancé avec l'option
active (seule différence), tâches vues 92 % et pass^3 76 % : task-005 et task-h02 réussissent sur les 3 essais.
Avec gpt-6-luna, l'option ne se déclenche jamais (il rappelle l'outil de lui-même).

**Autres constats.** Le RAG (niveau 1) ne dépend presque pas du modèle (100 % et 96 %) : la recherche fait le
travail. Le modèle seul (niveau 0) ne connaît pas les documents du club (8 % et 16 %). La latence de qwen dépend de
la charge de la machine (niveau 0 : 5,1 s au premier run, 15,0 s ici, code identique) : à comparer à l'intérieur
d'un même run.

## 1. Question posée

Le niveau 2 (agent outillé) avec `qwen2.5:7b` faisait beaucoup moins bien que le niveau 1 (RAG) sur les questions
documentaires, et ses tâches réussies ne tenaient pas sur plusieurs essais. Deux leviers possibles :

- **l'architecture** : ce que le code fait autour du modèle (routage, contrôles, calculs) ;
- **le modèle** : un modèle plus fort, ici `gpt-6-luna` (API OpenAI, imposé par l'enseignant).

Méthode : un seul levier à la fois, même code, même jeu de test, et pass^3 (3 essais, température 0,7 ; une tâche
compte si les 3 essais réussissent) pour mesurer la fiabilité et pas un run chanceux.

## 2. Configurations mesurées

| Configuration | Modèle | Ajouts du niveau 2 | Réglages `.env` / terminal |
|---|---|---|---|
| A. qwen, départ | qwen2.5:7b (Ollama, RTX 5060 8 Go) | aucun | code d'origine, avant ces travaux (commit 6ca86e3) |
| B. qwen, final mesuré | qwen2.5:7b | routeur, repli, question OUI/NON, proposition calculée | défauts, sauf proposition non appliquée par le système (étape 9 ci-dessous) |
| C. gpt-6-luna, avec ajouts | gpt-6-luna (API) | tous | `LLM_PROVIDER=openai`, `OPENAI_REASONING_EFFORT=none` |
| D. gpt-6-luna, sans ajouts | gpt-6-luna | routeur, repli et application de la proposition désactivés | C + `AGENT_ROUTER=0`, `AGENT_FALLBACK=0`, `AGENT_AUTO_PROPOSITION=0` |

Les embeddings (`bge-m3`, Ollama) et donc la recherche du RAG sont identiques dans toutes les configurations.

## 3. Tableau principal (niveau 2 · Agent)

| | A. qwen départ | B. qwen final | C. gpt-6-luna avec ajouts | D. gpt-6-luna sans ajouts |
|---|---|---|---|---|
| Exactitude doc | 28 % | 92 % | **96 %** | 96 % |
| Sources citées | 0 % | 80 % | **100 %** | 100 % |
| Abstention (questions sans réponse) | 100 % | 100 % | 100 % | 100 % |
| Abstention à tort | 52 % | 0 % | 0 % | 0 % |
| Ambigus OK | 100 % | 100 % | 80 % | 80 % |
| Tâches vues (1 run) | 83 % | 92 % | 100 % | 100 % |
| Tâches non vues (1 run) | 40 % | 80 %\* | 100 %\* | 80 %\* |
| **pass^3** | **41 %** (7/17) | **65 %** (11/17) | **100 %** (17/17) | **94 %** (16/17) |
| Tokens / requête | 4 001 | 4 039 | 3 916 | 5 382 |
| Latence moyenne | 7,5 s | 19,0 s | 5,8 s | 5,8 s |

\* Contaminé : les corrections de l'architecture ont été faites en analysant les échecs de `task-h01` à `task-h05`
(voir section 7).

## 4. Niveaux 0 et 1

| Exactitude doc | qwen2.5:7b | gpt-6-luna |
|---|---|---|
| 0 · LLM seul | 0 % | 16 %, 16 %, 24 % (3 runs) |
| 1 · RAG | 92 % | 92 %, 88 %, 88 % (3 runs) |
| 2 · Agent (config. B / C) | 92 % | 96 % |

| Autres métriques, gpt-6-luna (run sans raisonnement) | 0 · LLM seul | 1 · RAG |
|---|---|---|
| Sources citées | 0 % | 100 % |
| Abstention à tort | 28 % | 0 % |
| Ambigus OK | 80 % | 80 % |
| Recall@5 / MRR | n/a | 100 % / 0,89 |
| Tokens / requête | 241 | 1 026 |
| Latence | 1,6 s | 3,5 s |

Les deux premiers runs gpt-6-luna des niveaux 0 et 1 ont tourné avec le raisonnement par défaut du modèle, le
troisième sans (`OPENAI_REASONING_EFFORT=none`). Avec qwen, le niveau 1 citait ses sources dans 92 % des cas et
réussissait 60 % des cas ambigus.

## 5. Évolution de l'architecture avec qwen2.5:7b

Une ligne par changement, mesurée sur un run (température 0), sauf la colonne pass^3.

| Étape | Exactitude doc | Sources | Abst. à tort | Ambigus | Tâches vues / non vues | pass^3 | Latence |
|---|---|---|---|---|---|---|---|
| 1. Départ | 28 % | 0 % | 52 % | 100 % | 83 % / 40 % | 41 % | 7,5 s |
| 2. Routeur DOC / ACTION (questions documentaires vers le RAG) | 56 % | 44 % | 24 % | 100 % | 92 % / 20 % | | 11,6 s |
| 3. Repli vers le RAG si aucun outil appelé | 60 % | 48 % | 20 % | 100 % | 92 % / 20 % | | 12,3 s |
| 4. Repli aussi sur une abstention sans outil | 76 % | 68 % | 0 % | 80 % | 92 % / 20 % | | 13,6 s |
| 5. Repli annulé si le RAG s'abstient aussi | 84 % | 72 % | 0 % | 100 % | 92 % / 20 % | | 13,6 s |
| 6. Routeur à 3 classes (ÉCRITURE), temps objectif converti par le code, format m:ss | 92 % | 80 % | 0 % | 100 % | 83 % / 60 % | | 14,0 s |
| 7. ÉCRITURE prioritaire sur un calcul | 92 % | 80 % | 0 % | 100 % | 83 % / 80 % | | 13,8 s |
| 8. Question OUI/NON pour l'intention d'écriture | 92 % | 80 % | 0 % | 100 % | 92 % / 80 % | 59 % | 14,5 s |
| 9. Version conforme calculée par le code après un refus | 92 % | 80 % | 0 % | 100 % | 92 % / 80 % | 65 % | 19,0 s |
| 10. Proposition appliquée par le système, appels d'outils écrits en texte | non mesuré avec qwen | | | | | | |

Remarques :

- Les tâches passent toutes par la boucle de l'agent dès l'étape 2. Entre les étapes 2 et 5, leur code n'a pas changé :
  les écarts d'une tâche (83 % / 92 %, 40 % / 20 %) montrent qu'Ollama n'est pas déterministe à température 0.
- L'étape 4 a dégradé les cas ambigus (amb-001 envoyé au RAG, qui s'abstient sans poser de question), corrigé à
  l'étape 5. L'étape 6 a dégradé deux tâches vues (task-002, task-012), corrigé aux étapes 7 et 8.

## 6. Conclusions

1. **Plus le modèle est faible, plus l'architecture compte.** Avec qwen2.5:7b, les ajouts font passer l'exactitude
   documentaire de 28 % à 92 % et le pass^3 de 41 % à 65 %. Avec gpt-6-luna, ils ne changent pas l'exactitude (96 %
   dans les deux cas) et le pass^3 ne varie que d'une tâche (94 % → 100 %).
2. **Les échecs restants de qwen viennent du modèle.** Avec le même code, gpt-6-luna réussit les 17 tâches sur les
   3 essais, y compris celles que les diagnostics attribuaient aux limites du 7B : enchaîner trois outils
   (task-002), se repérer dans les dates, rappeler l'outil après un refus au lieu de recopier la correction en texte
   (task-005, task-h02), appeler l'outil qu'il annonce (task-010, task-h05).
3. **Le RAG dépend peu du modèle** (92 % contre 88 à 92 %) : la recherche fait l'essentiel du travail. L'agent en
   dépend beaucoup (pass^3 65 % contre 100 %).
4. **Le modèle seul ne suffit pas**, quelle que soit sa taille : 0 à 24 % au niveau 0, faute de connaître les
   documents du club.
5. **Avec un modèle fort, le routeur sert surtout le coût** : sans lui, chaque question documentaire passe par la
   boucle de l'agent, et la consommation moyenne monte de 3 916 à 5 382 tokens par requête (+37 %), à latence égale.
6. **Un bug de code piège aussi le modèle fort.** Dans la configuration D, l'intention d'écriture revient au regex
   d'origine, qui prend « au programme » pour une demande d'écriture : `task-h05` est la seule tâche en échec. Cause
   cohérente avec le bug connu, à confirmer avec `python scripts/diag_traces.py task-h05`.
7. **Coût de fonctionnement.** qwen tourne en local et gratuitement, mais lentement (14 à 19 s par requête sur une
   RTX 5060 8 Go avec l'architecture complète). gpt-6-luna répond en 5,8 s mais il est facturé à l'usage.

Principe retenu pour le niveau 2 : **le modèle comprend la demande et choisit, le code calcule et vérifie** (dates,
conversion des temps, règles du club, version conforme après un refus).

## 7. Limites

- **Tâches non vues contaminées.** `task-h01` à `task-h05` ont été diagnostiquées puis corrigées : elles ne mesurent
  plus la généralisation. Il faut de nouvelles tâches (`task-h06` et suivantes), écrites sans regarder le code.
- **Un run par configuration** pour les questions documentaires et les cas ambigus. Avec qwen, un écart d'un cas
  entre deux runs identiques a été observé ; avec gpt-6-luna, le RAG varie de 88 % à 92 % sur trois runs.
- **Un seul pass^3 par configuration** : sur 17 tâches, une tâche vaut 6 points.
  Pour qwen2.5:7b, les tâches en échec changent d'un pass^3 à l'autre (task-009, 011, 012 et h05 au dernier run).
- **Ablation partielle (configuration D).** Elle ne retire que le routeur, le repli et l'application automatique de
  la proposition. Les améliorations des outils restent actives : conversion des temps par le code, proposition
  renvoyée dans le refus, lecture des appels d'outils écrits en texte, réécriture « 1 minute et 45 secondes ».
- **Étape 10 non mesurée avec qwen** : l'application de la proposition par le système et la lecture des appels
  d'outils écrits en texte n'ont été mesurées qu'avec gpt-6-luna.
- **Température.** Les runs gpt-6-luna sans raisonnement ont accepté la température (0, puis 0,7 pour le pass^3),
  comme qwen. Avec le raisonnement par défaut, gpt-6-luna n'accepte que la température 1.
- **Cas ambigus en échec avec gpt-6-luna** : amb-002 (ajoute une séance sans demander laquelle) et amb-003 (demande
  bien une précision, mais sans « ? » : faux négatif de la métrique).
- **Choix de conception discutable** : avec `AGENT_AUTO_PROPOSITION=1`, la correction d'un refus est faite par le
  code et non plus par le modèle (avec confirmation de l'utilisateur).

**Juge LLM** : accord avec les 20 annotations humaines 18/20 (90 %), 2 réponses justes rejetées, 0 réponse fausse
acceptée (`python eval.py --calibrate-judge`).

## 8. Reproduire

```bash
python eval.py --levels 0 1 2 --pass-k 3                  # configuration selon .env
python scripts/diag_routage.py                            # questions doc restées dans l'agent
python scripts/diag_taches.py                             # tâches en échec, dernier run
python scripts/diag_traces.py task-005 task-h02           # détail des essais d'un pass^k
```

Sous PowerShell, une configuration se règle pour le terminal en cours, par exemple pour D :

```powershell
$env:AGENT_ROUTER = "0"; $env:AGENT_FALLBACK = "0"; $env:AGENT_AUTO_PROPOSITION = "0"
```

Les variables du terminal passent avant celles de `.env`. `results/summary.md` et `results/level2_raw.jsonl` sont
écrasés à chaque run : les copier entre deux configurations.

## 9. Mesures finales (faites les 24 et 25/11, tableau en section 0)

| Run | Réglages | Commande |
|---|---|---|
| qwen2.5:7b | `LLM_PROVIDER=ollama`, `LLM_MODEL=qwen2.5:7b` | `python eval.py` |
| gpt-6-luna | `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-6-luna`, `OPENAI_REASONING_EFFORT=none` | `python eval.py` |

`python eval.py` lance les niveaux 0 à 3 et le pass^3 des niveaux 2 et 3. Avant chaque run, vider `traces/` ; après,
copier `results/` et `traces/` dans un dossier propre au modèle, à versionner (la consigne demande les résultats bruts
par niveau et les traces dans le dépôt).

## 10. Correction après les runs finaux (26/11/2026)

En préparant la vidéo : `_propose` gardait le premier déplacement qui réduisait le nombre de violations, et pouvait
s'arrêter sur une version encore refusée (fractionné un mercredi entre deux séances intenses : vendredi retenu, une
violation, au lieu de samedi, conforme). Il retient désormais le meilleur candidat. **Aucun résultat mesuré ne
change** : dans les traces archivées, tous les refus suivis d'une proposition n'avaient qu'une violation (le premier
candidat qui améliore est alors le meilleur) ; le seul refus à plusieurs violations (task-009 avec qwen, semaine de
7 séances, règle R6) reste sans solution par déplacement.
