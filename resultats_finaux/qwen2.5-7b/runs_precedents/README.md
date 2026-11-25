# Runs précédents de qwen2.5:7b

- `25-11_sans_application_proposition/` : premier run final, lancé par erreur avec `AGENT_AUTO_PROPOSITION=0`
  (version conforme calculée après un refus, mais jamais appliquée par le système). Seule différence avec le run
  final : tâches vues 75 % au lieu de 92 %, pass^3 59 % au lieu de 76 % (niveaux 2 et 3). Sert de mesure de l'apport
  de cette option ; les niveaux 0 et 1 et les questions des niveaux 2 et 3 ne sont pas concernés.

Run final : `../results/summary.md`.
