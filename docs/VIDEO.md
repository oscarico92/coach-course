# Brief de la vidéo de démonstration (3 à 5 min)

La consigne demande, pour le parcours Texte : **un cas réussi, une abstention, une tâche en plusieurs étapes avec
sa trace, une action validée.** Ce déroulé les couvre en environ 4 min 30, et montre en plus ce que le projet mesure
(apport de chaque niveau, rôle du modèle, coût).

## Préparation (avant d'enregistrer)

- [ ] Ollama lancé (`ollama list` : `bge-m3` doit apparaître ; il sert à la recherche même avec gpt-6-luna).
- [ ] `.env` : `OPENAI_API_KEY` renseignée. Dans l'interface, choisir **gpt-6-luna** (réponses en 5 s au lieu de
      25 s avec qwen).
- [ ] Calendrier vide : renommer `calendar/utilisateur.ics` s'il existe (par exemple en `utilisateur_avant_video.ics`),
      pour que la démo parte d'un calendrier vierge.
- [ ] `streamlit run app.py`, navigateur en plein écran, zoom 110 % pour la lisibilité.
- [ ] **Faire une répétition complète** : les réponses du modèle varient d'une fois à l'autre, et la météo est réelle
      (si elle déclenche la règle R5 pendant la démo, c'est un bonus : le montrer).
- [ ] Enregistrement : OBS, ou Xbox Game Bar sous Windows (`Win + G`), en 1080p, micro testé.
- [ ] Cliquer sur « Nouvelle conversation » avant de commencer.

## Déroulé

| Temps | Scène | À l'écran | À dire (idée) |
|---|---|---|---|
| 0:00 à 0:20 | **Introduction** | Page d'accueil : conversation, calendrier, météo | « Coach Course, l'assistant du club fictif Foulées ECE : il répond sur les plans d'entraînement du club et planifie les séances dans un calendrier. Quatre niveaux, chacun mesuré sur le même jeu de 52 cas. » |
| 0:20 à 1:10 | **Cas réussi, et ce que chaque niveau apporte** | Niveau **0**, question 1 ; puis niveau **3**, même question | « Seul, le modèle ne connaît pas les plans du club : il invente ou s'abstient. Avec la recherche dans les documents, il répond juste et cite sa source. » Montrer la ligne 📚 Sources et la ligne de coût (tokens, durée). |
| 1:10 à 1:30 | **Question de suivi** | Niveau 3, question 2 | Montrer « Question comprise : … » : « la question de suivi est réécrite en question autonome avant d'être traitée. » |
| 1:30 à 1:55 | **Abstention** | Niveau 3, question 3 | « L'information n'est pas dans les documents : l'assistant le dit au lieu d'inventer. » |
| 1:55 à 3:10 | **Tâche en plusieurs étapes, avec sa trace** | Niveau 3, question 4, puis ouvrir « 🔍 Trace de l'exécution » | Dérouler la trace : rapport JSON de l'orchestrateur (agent actions, écriture demandée), `calcul_allures` (allure cible 5:00 min/km), `semaine_plan` (séances du plan), `ajouter_seances` en attente. « Les dates sont calculées par le code, les règles du club vérifiées par le code avant toute écriture. » |
| 3:10 à 3:40 | **Action validée** | Tableau « confirmation requise », clic **✅ Confirmer** | « Rien n'est écrit sans mon accord. » Les séances apparaissent dans « Mon calendrier » à droite ; cliquer sur **Exporter le calendrier (.ics)**. |
| 3:40 à 4:10 | **Une règle du club qui refuse** | Niveau 3, question 5 | « Mercredi tombe entre deux séances intenses : la règle R2 refuse, le code calcule une version conforme et me la propose. » Confirmer ou refuser. |
| 4:10 à 4:40 | **Résultats et conclusion** | Tableau de `docs/RESULTATS.md` (section 0) ou du rapport | « Le RAG fait passer l'exactitude de 8 à 100 %. Avec le petit modèle qwen, l'agent seul n'exploite pas ses documents (20 %) ; l'extension multi-agents corrige ce défaut (92 %). Avec gpt-6-luna, elle sert surtout à réduire le coût (−20 % de tokens). Un agent consomme 3 à 5 fois plus de tokens que le RAG. » |

## Questions à taper

1. `Quelle est la séance de fractionné de la semaine 6 du plan 10 km ?`
2. `Et pour la semaine 2 ?`
3. `Combien de membres compte le club Foulées ECE ?`
4. `Je vise 10 km en 50 minutes. Calcule mon allure cible et ajoute les séances A, B et D de la semaine 1 du plan 10 km la semaine prochaine (mardi, jeudi, dimanche).`
5. `Ajoute un fractionné mercredi prochain.` (après la scène 4 : mardi et jeudi portent déjà des séances intenses)

## Option, si le temps le permet (30 s)

Comparer les modèles sur l'agent seul : niveau **2**, modèle **qwen2.5:7b**, question
`À quel pourcentage de VMA correspond l'endurance fondamentale au club ?` → qwen répond souvent « Je ne sais pas »
sans chercher ; même question au niveau **3** → réponse juste et sourcée. Couper l'attente (environ 25 s) au montage.

## Ce que couvre la vidéo

| Exigence de la consigne | Scène |
|---|---|
| Un cas réussi | 0:20, cas réussi avec source citée |
| Une abstention | 1:30 |
| Une tâche en plusieurs étapes avec sa trace | 1:55 |
| Une action validée | 3:10 (confirmation, calendrier mis à jour, export .ics) |
| En plus : niveaux comparés, coût, règles vérifiées par le code | 0:20, 3:40, 4:10 |

## Pièges à éviter

- Ne jamais montrer le fichier `.env` ni la clé à l'écran.
- Si une réponse rate pendant l'enregistrement, ne pas la cacher : la montrer brièvement et dire pourquoi (c'est
  ce que la consigne valorise), puis cliquer sur « 🔄 Régénérer » ou recommencer la scène.
- Rester sous 5 minutes : couper les attentes au montage plutôt que d'accélérer la parole.
