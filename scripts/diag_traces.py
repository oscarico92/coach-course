"""Détail des derniers essais d'un cas, relus dans traces/level2.jsonl (utile après un pass^k,
dont les essais ne sont pas enregistrés dans results/).

    python scripts/diag_traces.py task-006 task-010 task-h05        # 4 derniers essais de chaque cas
    python scripts/diag_traces.py task-006 --n 2

Pour chaque essai : décision du routeur, intention d'écriture, outils appelés (refus éventuels),
séances écrites et début de la réponse.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import TRACES_DIR  # noqa: E402

args = sys.argv[1:]
n = 4
if "--n" in args:
    i = args.index("--n")
    n = int(args[i + 1])
    args = args[:i] + args[i + 2:]
if not args:
    sys.exit(__doc__)

runs = {}
with open(TRACES_DIR / "level2.jsonl", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            t = json.loads(line)
            if t.get("case_id") in args:
                runs.setdefault(t["case_id"], []).append(t)

for case_id in args:
    trials = runs.get(case_id, [])[-n:]
    if not trials:
        print(f"{case_id} : aucune trace")
        continue
    print(f"{case_id} : {trials[0]['question']}")
    for k, t in enumerate(trials, 1):
        steps = t["steps"]
        route = next((s.get("choix") for s in steps if s["type"] == "routage"), "-")
        intent = next((s.get("ecriture") for s in steps if s["type"] == "intention d'écriture"), "-")
        repli = any(s["type"] == "repli" for s in steps)
        tools = []
        for s in steps:
            if s["type"] == "tool":
                label = s["name"]
                res = s.get("result") or {}
                if s.get("error"):
                    label += " (erreur)"
                elif res.get("refuse"):
                    label += " (refus : " + "; ".join(v.split(" :")[0] for v in res.get("violations", [])) + ")"
                tools.append(label)
        out = t.get("output") or {}
        print(f"  essai {k} ({t['started_at']}) routeur={route} écriture={intent}" + (" repli" if repli else ""))
        print(f"    outils : {', '.join(tools) or 'aucun'}")
        print(f"    séances écrites : {len(out.get('written') or [])}  "
              f"réponse : {' '.join((out.get('answer') or '').split())[:160]}")
    print()
