"""Reproduit le tableau de résultats : python eval.py [--levels 0 1 2 3] [--limit N]

Pour l'instant : exécution des niveaux disponibles, abstention, tokens et latence.
À compléter : exactitude (règles + juge LLM calibré), Recall@5/MRR, succès des tâches, pass^3.
"""
import argparse
import json
import statistics

from config import TESTS_PATH, RESULTS_DIR
from src.tracing import Trace
from src.levels import get_level, is_available, LEVEL_NAMES


def load_tests(limit=None):
    with open(TESTS_PATH, encoding="utf-8") as f:
        tests = [json.loads(line) for line in f if line.strip()]
    return tests[:limit] if limit else tests


def run_level(n, tests):
    module = get_level(n)
    rows = []
    for case in tests:
        trace = Trace(level=n, question=case["question"], case_id=case["id"])
        try:
            out = module.answer(case["question"], trace)
            err = None
        except Exception as e:                       # un cas qui plante ne bloque pas l'évaluation
            out, err = {"answer": "", "sources": [], "abstained": False, "tool_calls": []}, repr(e)
        data = trace.close({**out, "error": err})
        rows.append({"case": case, "output": out, "error": err,
                     "tokens": data["total_tokens"], "latency_s": data["duration_s"]})
        print(f"  [{n}] {case['id']:<10} {data['duration_s']:6.1f}s  {data['total_tokens']:>6} tok"
              + (f"  ERREUR {err}" if err else ""))
    return rows


def summarize(n, rows):
    absent = [r for r in rows if r["case"]["type"] == "absent"]
    return {
        "niveau": f"{n} · {LEVEL_NAMES[n]}",
        "abstention": (sum(r["output"]["abstained"] for r in absent) / len(absent)) if absent else None,
        "tokens_moy": statistics.mean(r["tokens"] for r in rows),
        "latence_moy_s": statistics.mean(r["latency_s"] for r in rows),
        "erreurs": sum(r["error"] is not None for r in rows),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--levels", type=int, nargs="+", default=[0, 1, 2, 3])
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    tests = load_tests(args.limit)
    table = []
    for n in args.levels:
        if not is_available(n):
            print(f"Niveau {n} ({LEVEL_NAMES[n]}) : pas encore disponible, ignoré.")
            continue
        print(f"Niveau {n} ({LEVEL_NAMES[n]}) sur {len(tests)} cas")
        rows = run_level(n, tests)
        with open(RESULTS_DIR / f"level{n}_raw.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        table.append(summarize(n, rows))

    with open(RESULTS_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=2)
    print("\nRésultats")
    for row in table:
        print(row)


if __name__ == "__main__":
    main()
