"""Tests de calcul_allures et semaine_plan, sans Ollama.

    python tests/test_outils.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.impl import calcul_allures, duree_minutes, semaine_plan  # noqa: E402

CTX = {"today": "2026-11-12"}
ok = total = 0


def check(label, cond):
    global ok, total
    total += 1
    ok += bool(cond)
    print(("OK   " if cond else "ÉCHEC") + " " + label)


def plan(p, semaine):
    r = semaine_plan({"plan": p, "semaine": semaine}, CTX)
    return r, {s["jour"]: s for s in r["seances"]}


# calcul_allures
a = calcul_allures({"vma_kmh": 15}, CTX)["allures"]
check("VMA 15 : EF 5:43, seuil 4:42, 10 km 4:27",
      (a["EF (70 %)"], a["seuil (85 %)"], a["10 km (90 %)"]) == ("5:43", "4:42", "4:27"))
r = calcul_allures({"distance_test_m": 1450}, CTX)
check("demi-Cooper 1450 m : VMA 14,5 et 400 m à 95 % en 1:45", r["vma_kmh"] == 14.5 and r["400 m à 95 % VMA"] == "1:45")
check("marathon en 3 h 45 : allure cible 5:20",
      calcul_allures({"temps_objectif_min": 225, "distance_km": 42.195}, CTX)["allure_cible"] == "5:20")
check("10 km en 50 min : VMA estimée 13,3", calcul_allures({"temps_objectif_min": 50, "distance_km": 10}, CTX)["vma_kmh"] == 13.3)
# temps objectif recopié par le modèle, converti par le code
check("durées : 1 h 50, 1h45, 3 heures 45, 50 min, 1:50:00, 2 h",
      [duree_minutes(x) for x in ("1 h 50", "1h45", "3 heures 45", "50 min", "1:50:00", "2 h")] == [110, 105, 225, 50, 110, 120])
check("semi en « 1 h 50 » : allure cible 5:13",
      calcul_allures({"temps_objectif": "1 h 50", "distance_km": 21.0975}, CTX)["allure_cible"] == "5:13")
for args in ({}, {"vma_kmh": 36}, {"temps_objectif": "rapide", "distance_km": 10}):
    try:
        calcul_allures(args, CTX)
        check(f"erreur attendue pour {args}", False)
    except ValueError:
        check(f"erreur attendue pour {args}", True)

# semaine_plan : semaine normale
r, j = plan("marathon", 1)
check("marathon S1 : mardi, mercredi, vendredi, dimanche", list(j) == ["mardi", "mercredi", "vendredi", "dimanche"])
check("marathon S1 : dates de la semaine du 16 novembre",
      [s["date"] for s in r["seances"]] == ["2026-11-17", "2026-11-18", "2026-11-20", "2026-11-22"])
check("marathon S1 : volume 40 km et allure cible 5:20",
      sum(s["km"] for s in r["seances"]) == 40 and r["allure_cible"] == "5:20")
r, j = plan("5km", 1)
check("5 km S1 : 3 séances d'endurance non consécutives",
      list(j) == ["mardi", "jeudi", "dimanche"] and all(s["type"] == "endurance" for s in r["seances"]))
check("marathon S6 : 2 × 6 km à allure marathon comptés 12 km (+ 4)", plan("marathon", 6)[1]["vendredi"]["km"] == 16)

# semaine_plan : semaine de course
for p, semaine in [("10km", 8), ("semi", 10), ("marathon", 12)]:
    r, j = plan(p, semaine)
    check(f"{p} S{semaine} : pas de sortie longue, course le dimanche",
          "dimanche" not in j and r.get("course", {}).get("date") == "2026-11-22"
          and not any(s["type"] == "sortie_longue" for s in r["seances"]))
r, j = plan("10km", 8)
check("10 km S8 : jours du plan respectés (mardi, jeudi), endurance un autre jour",
      j["mardi"]["type"] == "fractionne" and j["jeudi"]["type"] == "allure_10km" and "mercredi" in j)
check("semi S10 : séance qualité le mercredi", plan("semi", 10)[1]["mercredi"]["type"] == "allure_semi")
check("marathon S12 : allure marathon le jeudi", plan("marathon", 12)[1]["jeudi"]["type"] == "allure_marathon")
check("semi S1 : pas de clé course", "course" not in plan("semi", 1)[0])

print(f"\n{ok}/{total} tests réussis")
sys.exit(0 if ok == total else 1)
