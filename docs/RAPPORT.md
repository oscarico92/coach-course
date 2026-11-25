# Coach Course : un assistant de course à pied qui se mesure

Projet IA générative 2026 · parcours Texte · [À COMPLÉTER : noms] · dépôt : [À COMPLÉTER : lien GitHub]

> Brouillon. Les passages marqués [À COMPLÉTER] attendent une information. Chiffres tirés de
> `resultats_finaux/` (runs des 24 et 25/11/2026) et de `docs/RESULTATS.md`.

## 1. Cas d'usage

Assistant du club fictif « Foulées ECE ». Il répond aux questions sur les plans d'entraînement (5 km, 10 km,
semi-marathon, marathon), les allures, les tests de VMA et les règles du club, et il planifie des séances dans le
calendrier de l'utilisateur (fichier .ics). **Action à valider** : ajouter des séances au calendrier.

- **Corpus** : 8 documents rédigés pour le projet (licence CC BY 4.0), aux valeurs volontairement précises (plans,
  zones, règles R1 à R7) qu'un LLM seul ne peut pas deviner, et 7 articles Wikipédia ; 150 passages indexés.
- **Jeu de test** (`data/tests.jsonl`, 52 cas) : 25 questions dont la réponse est dans les documents, 5 sans réponse,
  5 ambiguës ou hors sujet, 17 tâches en plusieurs étapes (12 servant au réglage, 5 « non vues » écrites après).
  L'état final des tâches est vérifié par du code (calendrier relu dans le .ics, allures dans la réponse).
- **Modèles** : qwen2.5:7b (ouvert, local, RTX 5060 8 Go) et gpt-6-luna (API fournie), sur le même code.
  Embeddings bge-m3 en local dans les deux cas.

## 2. Architecture

```
                  question
                     |
   +-----------------+-----------------+-----------------------------+
   |                 |                 |                             |
Niveau 0         Niveau 1          Niveau 2 : agent seul          Niveau 3 : multi-agents
LLM + prompt     RAG               boucle bornée (10 étapes,      orchestrateur : classe
                 découpage         20 000 tokens), écrite sans      DOC / ECRITURE / ACTION
                 bge-m3 + BM25     framework                      + question OUI/NON écriture
                 fusion RRF        6 outils (schémas JSON) :              | rapport JSON
                 top 5             - lecture : rechercher_corpus,   +------+-------+
                 seuil 0,45          semaine_plan, calcul_allures,  |              |
                 citations           meteo, lire_calendrier       agent          agent
                 abstention        - écriture : ajouter_seances   documentaire   actions
                                     -> règles R1 R2 R5 R6 (code)  (niveau 1)    (niveau 2)
                                     -> version conforme (code)       |              |
                                     -> confirmation utilisateur      +-- rapport JSON --+
                                     -> fichier .ics               repli : agent actions sans
                                                                   outil -> agent documentaire
```

Composants écrits sans framework : client LLM (HTTP direct, Ollama et OpenAI), boucle de l'agent, validation des
actions (règles du club, confirmation), évaluation (`eval.py`, contrôles des tâches, pass^3). Chaque exécution est
tracée en JSONL (étapes, outils, arguments, tokens, durée) et affichée dans l'interface Streamlit.

## 3. Choix justifiés par des mesures

**RAG (niveau 1).** Découpage par section (titres Markdown et Wikipédia), sections longues en fenêtres de 1 200
caractères avec 200 de recouvrement, titre du document et de la section ajoutés au texte indexé pour que
« semaine 6 du plan 10 km » retrouve le bon tableau. bge-m3 (multilingue, local) et recherche hybride dense + BM25
fusionnée par RRF : **Recall@5 = 100 %, MRR = 0,89**. Abstention en deux temps (seuil sur le score dense, puis
consigne au modèle) : 100 % d'abstention sur les questions sans réponse, 0 % d'abstention à tort. Limite : aucune
alternative (dense seul, autre découpage) n'a été mesurée.

**Agent (niveau 2) : le modèle choisit, le code calcule.** Chaque ajout répond à un échec observé dans les traces :

| Échec observé (qwen2.5:7b) | Correction par le code | Effet mesuré |
|---|---|---|
| dates fausses (« mercredi 15 »), un vendredi pris pour un lundi | le modèle donne le jour, le code calcule la date (avec `semaine_plan` et la relance) | tâches 9/12 → 10/12 |
| « 1 h 50 » converti en 100 min | le modèle recopie « 1 h 50 », le code convertit | task-h03 réussie |
| après un refus des règles, correction recopiée en texte au lieu d'être exécutée | le code calcule une version conforme (autre jour, endurance, km réduits) et l'applique si le modèle ne le fait pas, avec confirmation | pass^3 qwen 59 % → 76 % (niveaux 2 et 3, seule l'option change) |
| « au programme » pris pour une écriture, « cale-moi » non reconnu (regex) | intention d'écriture demandée au modèle (classe ECRITURE, puis OUI/NON) | task-h01, task-h05 réussies (run unique) |

Le même bug de regex fait échouer task-h05 avec gpt-6-luna (pass^3 94 % au lieu de 100 %) : un défaut du code
autour du modèle pénalise aussi un modèle fort.

**Extension (niveau 3) : multi-agents.** Choisie d'après le défaut principal du niveau 2 : seul face à 6 outils,
qwen2.5:7b appelle rarement `rechercher_corpus` (exactitude documentaire 20 %, aucune source citée, 60 %
d'abstentions à tort, alors que le RAG seul atteint 100 %). L'orchestrateur confie ces questions à l'agent
documentaire.

**Évaluation.** Exactitude par mots-clés (`must_contain`), formats équivalents acceptés depuis le 24/11
(« 4 min 58 s » = « 4:58 », « 13.3 » = « 13,3 »), runs archivés recalculés sans rappeler les modèles. Juge LLM
calibré sur 20 cas annotés à la main : **accord 18/20 (90 %)**, 2 réponses justes rejetées, 0 réponse fausse
acceptée (juge [À COMPLÉTER : modèle utilisé pour la calibration]). Il est donc prudent mais un peu sévère : le tableau
repose sur les mots-clés, et le juge sert de contrôle (`--judge`), où il ne peut que rendre la notation plus stricte.

## 4. Résultats : niveaux 0 à 3

| Niveau | Modèle | Exactitude | Sources citées | Abstention | Abst. à tort | Ambigus | Tâches vues / non vues\* | pass^3 | Tokens / req. | Latence |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 · LLM seul | qwen2.5:7b | 8 % | 0 % | 100 % | 44 % | 80 % | n/a | n/a | 312 | 15,0 s |
| | gpt-6-luna | 16 % | 0 % | 80 % | 28 % | 60 % | n/a | n/a | 245 | 1,7 s |
| 1 · RAG | qwen2.5:7b | 100 % | 96 % | 100 % | 0 % | 60 % | n/a | n/a | 1 178 | 18,7 s |
| | gpt-6-luna | 96 % | 100 % | 100 % | 0 % | 80 % | n/a | n/a | 1 024 | 3,4 s |
| 2 · Agent | qwen2.5:7b | 20 % | 0 % | 80 % | 60 % | 100 % | 92 % / 100 % | 76 % | 3 772 | 23,6 s |
| | gpt-6-luna | 100 % | 100 % | 100 % | 0 % | 60 % | 100 % / 100 % | 100 % | 5 155 | 5,8 s |
| 3 · Multi-agents | qwen2.5:7b | 92 % | 80 % | 100 % | 0 % | 100 % | 92 % / 100 % | 76 % | 3 673 | 23,3 s |
| | gpt-6-luna | 96 % | 100 % | 100 % | 0 % | 60 % | 100 % / 100 % | 100 % | 4 106 | 5,5 s |

Recall@5 = 100 % et MRR = 0,89 pour les deux modèles (même recherche). \* Tâches « non vues » contaminées (section
6).

**Lecture.**
- **Le RAG fait l'essentiel sur les questions documentaires** (8 à 16 % → 96 à 100 %), quel que soit le modèle.
- **L'agent seul dépend du modèle** : qwen2.5:7b n'exploite pas ses documents (20 %), gpt-6-luna si (100 %).
- **L'extension corrige ce défaut pour le petit modèle** : +72 points d'exactitude, abstentions à tort de 60 % à 0 %.
  Avec gpt-6-luna, elle n'apporte rien en qualité (un cas perdu) et **réduit les tokens de 20 %**. Elle ne change
  pas les tâches, qui passent par le même agent actions.
- **Plus le modèle est faible, plus l'architecture compte** ; avec un modèle fort, elle sert surtout le coût.

## 5. Analyse de cinq échecs

**1. L'agent qui ne cherche pas (qwen2.5:7b, niveau 2, doc-013).** « À quel pourcentage de VMA correspond
l'endurance fondamentale au club ? » → « Je ne sais pas. Pourriez-vous me donner plus d'informations… », sans
appeler `rechercher_corpus`. 15 des 25 questions documentaires finissent ainsi. Cause : choix d'outil d'un petit
modèle face à 6 outils et à un prompt centré sur le calendrier. Correction : niveau 3 (92 %).

**2. La correction recopiée au lieu d'être exécutée (qwen2.5:7b, task-005).** « Mets une séance de seuil jeudi
prochain », avec 31 °C prévus jeudi. La règle R5 refuse, le code propose vendredi ; qwen répond « Je rappelle l'ajout
de la séance de seuil sur vendredi 2026-11-20… » sans rappeler l'outil : rien n'est écrit. Sur task-h02, avant la
proposition calculée, il annonçait même « Séance ajoutée… samedi 2026-11-18 » (un mercredi) sans rien écrire. Correction :
application de la proposition par le système, toujours soumise à la confirmation. Mesure, même code avec l'option
désactivée puis activée : task-005 et task-h02 réussissent sur les 3 essais, pass^3 de qwen 59 % → 76 % (niveaux 2
et 3). Avec gpt-6-luna, l'option ne sert jamais : il rappelle l'outil de lui-même.

**3. L'outil cru contre l'utilisateur (gpt-6-luna, niveau 3, doc-018).** « Il fera 30 °C demain, je peux faire ma
séance de seuil ? » → l'agent appelle `meteo` (15 °C dans l'évaluation) et répond « Tu peux donc faire ta séance de
seuil », sans citer la règle (pas de séance intense au-delà de 28 °C). La question portait sur une règle,
l'hypothèse de l'utilisateur a été remplacée par la donnée d'un outil. Non corrigé ; piste : consigne « une hypothèse
donnée par l'utilisateur prime sur les outils ».

**4. Agir sur une demande vague (gpt-6-luna, niveaux 2 et 3, amb-002).** « Ajoute une séance. » → l'agent ajoute
5 km d'endurance le mercredi suivant au lieu de demander laquelle. Le prompt avait été réglé pour que qwen agisse
(« ne pose une question que si la demande est impossible à interpréter ») ; un modèle plus fort applique la consigne
trop bien (ambigus : 100 % avec qwen, 60 % avec gpt-6-luna au niveau 2). Le garde-fou tient : dans l'interface,
aucune écriture sans clic « Confirmer ».

**5. Les échecs de la mesure (doc-011, amb-003).** doc-011 répondait juste, « 4 min 58 s par kilomètre », mais le
contrôle attendait « 4:58 » : la métrique jugeait un format. Corrigé le 24/11 (formats équivalents, changement daté
dans `data/TESTS.md`, runs recalculés). amb-003, « Prépare-moi pour ma course » : l'agent demande bien la distance et
la date, mais sans « ? », seul signe reconnu d'une demande de précision. Faux négatif laissé tel quel pour ne pas
rendre le critère flou.

## 6. Limites et coût

**Coût.** Un agent consomme 3 à 5 fois les tokens du RAG (3 700 à 5 200 contre 1 000 à 1 200 par requête) ; le
pass^3 relance 3 fois les 17 tâches. qwen2.5:7b est gratuit mais lent en local (15 à 24 s par requête, latence
dépendante de la charge de la machine : 5,1 s puis 15,0 s au niveau 0 pour le même code) ; gpt-6-luna répond en 2 à
6 s mais il est facturé. Le niveau 3 économise 20 % des tokens avec gpt-6-luna.

**Limites.**
- Tâches « non vues » contaminées : task-h01 à h05 ont servi à corriger le niveau 2. De nouvelles tâches seraient
  nécessaires pour mesurer la généralisation. [À COMPLÉTER si de nouvelles tâches sont ajoutées.]
- Un run par configuration pour les questions et un pass^3 par niveau (17 tâches : une tâche vaut 6 points). Pour
  qwen, les tâches en échec changent d'un run à l'autre (task-009, 011, 012 et h05 au dernier).
- Deux corrections de la métrique ont été faites après avoir vu des résultats ; elles sont datées et appliquées à
  tous les niveaux et aux deux modèles.
- gpt-6-luna tourne sans raisonnement (`reasoning_effort: none`, imposé avec des outils sur l'API utilisée).
- Le découpage et la recherche n'ont pas été comparés à des alternatives.
- Dans l'interface, les questions de suivi sont réécrites en question autonome avant d'être passées au niveau :
  fonction non mesurée, le jeu de test ne contenant que des questions isolées.
