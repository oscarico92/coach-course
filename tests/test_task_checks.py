"""Vérifie que les vérifications de tâches (src/task_checks.py) acceptent une bonne exécution
et rejettent une mauvaise, pour chacune des 12 tâches de tests.jsonl. Sans Ollama.

    python tests/test_task_checks.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.task_checks import check_task  # noqa: E402

T = {c["id"]: c for c in map(json.loads, open(ROOT / "data/tests.jsonl", encoding="utf-8")) if c["type"] == "task"}
S = lambda d, titre, typ, km=8: {"date": d, "titre": titre, "type": typ, "km": km, "intense": typ in
                                 {"allure_semi", "allure_10km", "seuil", "fractionne"}}

# (bonne exécution, mauvaise exécution) : (réponse, séances ajoutées, confirmation demandée)
SCENARIOS = {
    "task-001": (("EF 5:43, seuil 4:42, allure 10 km 4:27 min/km", [], False),
                 ("EF 6:10, seuil 4:42, allure 10 km 4:27", [], False)),
    "task-002": (("Allure cible 5:00 min/km.", [S("2026-11-17", "Fractionné", "fractionne"), S("2026-11-19", "EF", "endurance"),
                                               S("2026-11-22", "Sortie longue", "sortie_longue")], True),
                 ("Allure cible 5:00.", [S("2026-11-17", "Fractionné", "fractionne"), S("2026-11-18", "Seuil", "seuil"),
                                         S("2026-11-22", "Sortie longue", "sortie_longue")], True)),
    "task-003": (("D'accord, je n'ajoute rien.", [], True),
                 ("C'est ajouté !", [S("2026-11-17", "Fractionné", "fractionne")], False)),
    "task-004": (("Mercredi est trop proche du fractionné de mardi, je propose jeudi.", [S("2026-11-19", "8 × 400 m", "fractionne")], True),
                 ("Ajouté mercredi.", [S("2026-11-18", "8 × 400 m", "fractionne")], True)),
    "task-005": (("31 °C jeudi : je mets de l'endurance fondamentale.", [S("2026-11-19", "Footing", "endurance")], True),
                 ("Seuil ajouté jeudi.", [S("2026-11-19", "Seuil", "seuil")], True)),
    "task-006": (("Vent à 60 km/h samedi : je décale à dimanche.", [S("2026-11-22", "Sortie longue 1 h 10", "sortie_longue", 12)], True),
                 ("Ajoutée samedi.", [S("2026-11-21", "Sortie longue 1 h 10", "sortie_longue", 12)], True)),
    "task-007": (("VMA 14,5 km/h, 400 m à 95 % en 1:45.", [], False),
                 ("VMA 14 km/h, 400 m en 1:50.", [], False)),
    "task-008": (("48 km dépasse +10 % : je prévois 44 km.", [S(f"2026-11-{d}", f"Footing {d}", "endurance", 11) for d in (16, 18, 20, 22)], True),
                 ("48 km prévus.", [S(f"2026-11-{d}", f"Footing {d}", "endurance", 12) for d in (16, 18, 20, 22)], True)),
    "task-009": (("Semaine 1 ajoutée.", [S(d, f"Course/marche {d}", "endurance", 4) for d in ("2026-11-17", "2026-11-19", "2026-11-22")], True),
                 ("Semaine 1 ajoutée.", [S(d, f"Course/marche {d}", "endurance", 4) for d in ("2026-11-17", "2026-11-18", "2026-11-22")], True)),
    "task-010": (("32 km prévus, dont 2 séances intenses.", [], False),
                 ("30 km prévus, 1 séance intense.", [], False)),
    "task-011": (("Allure marathon 5:20 min/km.", [S("2026-11-17", "Seuil 3 × 10 min", "seuil", 10), S("2026-11-18", "EF", "endurance"),
                                                   S("2026-11-20", "6 km allure marathon", "allure_marathon", 10),
                                                   S("2026-11-22", "Sortie longue", "sortie_longue", 14)], True),
                 ("Allure marathon 5:30.", [S("2026-11-17", "Seuil", "seuil", 10), S("2026-11-18", "Fractionné", "fractionne"),
                                            S("2026-11-20", "AM", "allure_marathon", 10), S("2026-11-22", "SL", "sortie_longue", 14)], True)),
    "task-012": (("Allure semi 4:58 min/km.", [S("2026-11-17", "2 × 15 min seuil", "seuil", 10)], True),
                 ("Allure semi 5:10.", [S("2026-11-18", "2 × 15 min seuil", "seuil", 10)], True)),
    # tâches non vues pendant le réglage du prompt (task-h*)
    "task-h01": (("Semaine 2 du plan semi ajoutée.", [S("2026-11-17", "10 × 400 m", "fractionne", 10), S("2026-11-18", "EF", "endurance"),
                                                      S("2026-11-20", "EF 2", "endurance"), S("2026-11-22", "Sortie longue", "sortie_longue", 12)], True),
                 ("Semaine 2 ajoutée.", [S("2026-11-17", "10 × 400 m", "fractionne", 10), S("2026-11-18", "Seuil", "seuil", 10),
                                         S("2026-11-20", "EF", "endurance"), S("2026-11-22", "SL", "sortie_longue", 20)], True)),
    "task-h02": (("Orage vendredi : je le place samedi.", [S("2026-11-21", "Fractionné", "fractionne")], True),
                 ("Ajouté vendredi.", [S("2026-11-20", "Fractionné", "fractionne")], True)),
    "task-h03": (("Il faut tenir 5:13 min/km.", [], False), ("Il faut tenir 5:30 min/km.", [], False)),
    "task-h04": (("Seuil à 5:26 min/km.", [], False), ("Seuil à 4:50 min/km.", [], False)),
    "task-h05": (("3 séances pour 35 km au total.", [], False), ("3 séances pour 32 km.", [], False)),
}

errors = 0
for tid, case in T.items():
    initial = case.get("fixtures", {}).get("calendar", [])
    for label, (ans, added, conf), want in (("bonne", SCENARIOS[tid][0], True), ("mauvaise", SCENARIOS[tid][1], False)):
        got, detail = check_task(case, {"answer": ans, "asked_confirmation": conf}, initial, initial + added)
        status = "OK   " if got == want else "ÉCHEC"
        errors += got != want
        failed = [k for k, v in detail.items() if not v]
        print(f"{status} {tid} exécution {label:<8} -> {'réussie' if got else 'échouée'}"
              + (f"  (vérifs en échec : {', '.join(failed)})" if failed else ""))
print(f"\n{2 * len(T) - errors}/{2 * len(T)} vérifications conformes")
sys.exit(1 if errors else 0)
