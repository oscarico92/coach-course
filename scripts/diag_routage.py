"""Diagnostic du niveau 2 : questions documentaires restées dans la boucle de l'agent.

    python scripts/diag_routage.py            # lit results/level2_raw.jsonl (dernier run de eval.py --levels 2)

Pour chaque cas in_docs dont la route est « agent » : outils appelés, exactitude, source citée,
présence d'un « ? » (qui empêche le repli vers le RAG) et début de la réponse.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import RESULTS_DIR  # noqa: E402

rows = [json.loads(l) for l in open(RESULTS_DIR / "level2_raw.jsonl", encoding="utf-8") if l.strip()]
stuck = [r for r in rows if r["case"]["type"] == "in_docs" and r["output"].get("route") == "agent"]
tools_used = Counter()

for r in stuck:
    out, s = r["output"], r.get("scores", {})
    calls = [c["name"] + (" (erreur)" if c.get("error") else "") for c in out.get("tool_calls", [])]
    tools_used.update(c["name"] for c in out.get("tool_calls", []))
    answer = " ".join(out.get("answer", "").split())
    print(f"{r['case']['id']}  exact={'oui' if s.get('correct') else 'non'}  "
          f"source={'oui' if s.get('source_ok') else 'non'}  ?={'oui' if '?' in answer else 'non'}")
    print(f"    outils : {', '.join(calls) or 'aucun'}")
    print(f"    sources renvoyées : {out.get('sources')}")
    print(f"    réponse : {answer[:220]}")

print(f"\n{len(stuck)} questions documentaires restées dans la boucle")
print("Outils appelés (tous cas confondus) : " + ", ".join(f"{n} x{k}" for n, k in tools_used.most_common()))
