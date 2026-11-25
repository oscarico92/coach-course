"""Diagnostic des tâches du niveau 2 (dernier run de eval.py --levels 2).

    python scripts/diag_taches.py           # tâches en échec
    python scripts/diag_taches.py --toutes  # toutes les tâches

Pour chaque tâche : vue ou non vue, vérifications en échec, outils appelés (arguments abrégés),
séances écrites et début de la réponse.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import RESULTS_DIR  # noqa: E402

ALL = "--toutes" in sys.argv
rows = [json.loads(l) for l in open(RESULTS_DIR / "level2_raw.jsonl", encoding="utf-8") if l.strip()]
tasks = [r for r in rows if r["case"]["type"] == "task"]


def short(args):
    if "seances" in args:
        return "[" + "; ".join(f"{s.get('jour') or s.get('date')} {s.get('type')} {s.get('km')} km"
                               for s in args["seances"]) + "]"
    return json.dumps(args, ensure_ascii=False)[:120]


for r in tasks:
    s, out, case = r.get("scores", {}), r["output"], r["case"]
    if s.get("success") and not ALL:
        continue
    failed = [k for k, v in (s.get("checks") or {}).items() if not v]
    print(f"{case['id']}  {'NON VUE' if case.get('held_out') else 'vue'}  "
          f"{'réussie' if s.get('success') else 'ÉCHEC'}  route={out.get('route')}  "
          f"intention d'écriture={out.get('intention_ecriture')}")
    print(f"    question : {case['question']}")
    print(f"    vérifications en échec : {', '.join(failed) or 'aucune'}")
    for c in out.get("tool_calls", []):
        print(f"    outil : {c['name']} {short(c.get('args') or {})}" + (f"  ERREUR {c['error']}" if c.get("error") else ""))
    if not out.get("tool_calls"):
        print("    outil : aucun")
    print(f"    confirmation demandée : {out.get('asked_confirmation')}  séances écrites : {short({'seances': out.get('written') or []})}")
    print(f"    réponse : {' '.join(out.get('answer', '').split())[:220]}")

ok = sum(bool(r.get("scores", {}).get("success")) for r in tasks)
print(f"\n{ok}/{len(tasks)} tâches réussies")
