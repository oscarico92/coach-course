"""Cas en échec d'un niveau, tous types confondus (dernier run de eval.py), pour l'analyse d'erreurs.

    python scripts/diag_cas.py 3                       # échecs du niveau 3 (results/level3_raw.jsonl)
    python scripts/diag_cas.py 2 --dossier resultats_finaux/gpt-6-luna/results
    python scripts/diag_cas.py 3 --cas amb-002 doc-011  # ces cas, réussis ou non

Pour chaque cas : type, ce qui a échoué, route (niveau 3), outils appelés, sources et début de la réponse.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import RESULTS_DIR, ROOT  # noqa: E402

args = sys.argv[1:]
if not args or not args[0].isdigit():
    sys.exit(__doc__)
level, folder, only = int(args[0]), RESULTS_DIR, None
if "--dossier" in args:
    folder = ROOT / args[args.index("--dossier") + 1]
if "--cas" in args:
    only = [a for a in args[args.index("--cas") + 1:] if not a.startswith("--")]

rows = [json.loads(l) for l in open(folder / f"level{level}_raw.jsonl", encoding="utf-8") if l.strip()]


def failure(r):
    """Ce qui a échoué, ou None si le cas est réussi."""
    case, s, out = r["case"], r.get("scores", {}), r["output"]
    if r.get("error"):
        return f"erreur : {r['error'][:120]}"
    t = case["type"]
    if t == "in_docs":
        why = [w for w, bad in (("abstention à tort", s.get("false_abstention")),
                                (f"mots attendus absents {case.get('must_contain')}", not s.get("keywords_ok")),
                                ("juge : incorrect", s.get("judge_ok") is False)) if bad]
        src = "" if s.get("source_ok") else f" ; source attendue non citée {case['expected_sources']}"
        return ("; ".join(why) + src) if why or src else None
    if t == "absent":
        return None if s.get("abstained") else "pas d'abstention"
    if t == "ambiguous":
        return None if s.get("ok") else f"attendu : {case['expected']} (question de précision « ? » ou refus)"
    if t == "task":
        if s.get("success") is None:   # niveaux sans outils : tâches non applicables (« — » dans le tableau)
            return None
        failed = [k for k, v in (s.get("checks") or {}).items() if not v]
        return None if s.get("success") else "vérifications en échec : " + (", ".join(failed) or "?")
    return None


shown = 0
for r in rows:
    case, out = r["case"], r["output"]
    why = failure(r)
    if only is not None:
        if case["id"] not in only:
            continue
    elif why is None:
        continue
    shown += 1
    tools = ", ".join(c["name"] for c in out.get("tool_calls", [])) or "aucun"
    print(f"{case['id']}  ({case['type']})  {'ÉCHEC : ' + why if why else 'réussi'}")
    print(f"    question : {case['question']}")
    if out.get("route"):
        print(f"    route : {out['route']}")
    print(f"    outils : {tools}  |  sources : {out.get('sources')}")
    print(f"    réponse : {' '.join((out.get('answer') or '').split())[:300]}")
    print()
print(f"{shown} cas affichés (niveau {level}, {folder.relative_to(ROOT) if folder.is_relative_to(ROOT) else folder})")
