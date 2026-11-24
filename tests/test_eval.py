"""Tests de la notation de eval.py (formats équivalents, --rescore), sans modèle.

    python tests/test_eval.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import eval as ev  # noqa: E402

ok = total = 0


def check(label, cond):
    global ok, total
    total += 1
    ok += bool(cond)
    print(("OK   " if cond else "ÉCHEC") + " " + label)


n = ev.norm
check("« 4 min 58 s » vaut « 4:58 »", n("4:58") in n("L'allure est de **4 min 58 s** par km"))
check("« 1 minute et 45 secondes » vaut « 1:45 »", n("1:45") in n("400 m en 1 minute et 45 secondes"))
check("« 4'58 » vaut « 4:58 »", n("4:58") in n("4'58 au km"))
check("« 13.3 » vaut « 13,3 »", n("13,3") in n("VMA 13.3 km/h"))
check("pas de faux format : « 50 min 10 km », dates, « 4 min 58 » sans « s » inchangés",
      n("sortie de 50 min 10 km") == "sortie de 50 min 10 km" and n("2026-11-20") == "2026-11-20"
      and n("4 min 58 par km") == "4 min 58 par km")

# --rescore : un run archivé est renoté sans modèle, pass^k repris de son summary.json
case = next(c for c in ev.load_tests() if c["id"] == "doc-011")
row = {"case": case, "error": None, "tokens": 100, "latency_s": 1.0,
       "output": {"answer": "L'allure cible est de **4 min 58 s** par kilomètre. [plan_semi_1h45.md]",
                  "sources": ["plan_semi_1h45.md"], "abstained": False, "tool_calls": []},
       "scores": {"correct": False}}
folder = Path(tempfile.mkdtemp())
(folder / "level3_raw.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
json.dump([{"niveau": "3 · Multi-agents (gpt-6-luna)", "pass_k": 1.0}], open(folder / "summary.json", "w", encoding="utf-8"))
ev.rescore(folder, [3])
res = json.load(open(folder / "summary_rescore.json", encoding="utf-8"))[0]
check("--rescore : doc-011 devient exact, nom du modèle et pass^k repris",
      res["exactitude"] == 1.0 and res["niveau"].endswith("(gpt-6-luna)") and res["pass_k"] == 1.0)

print(f"\n{ok}/{total} tests réussis")
sys.exit(0 if ok == total else 1)
