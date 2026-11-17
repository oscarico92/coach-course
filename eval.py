"""Reproduit le tableau de résultats.

    python eval.py                      # tous les niveaux disponibles
    python eval.py --levels 0 1         # niveaux choisis
    python eval.py --judge              # ajoute le juge LLM pour l'exactitude (plus lent)
    python eval.py --limit 5            # test rapide
    python eval.py --calibrate-judge    # accord juge / annotations humaines

Sorties : results/level{n}_raw.jsonl (réponses brutes), results/summary.json et results/summary.md (tableau).
"""
import argparse
import json
import statistics
import unicodedata

from config import TESTS_PATH, RESULTS_DIR, DATA_DIR
from src.tracing import Trace
from src.levels import get_level, is_available, LEVEL_NAMES

REFUSAL_MARKERS = ["je ne sais pas", "je ne peux pas", "je ne suis pas en mesure", "professionnel de sante",
                   "medecin", "hors de mon domaine", "course a pied uniquement", "ne fait pas partie"]


def norm(text):
    text = unicodedata.normalize("NFKD", (text or "").lower().replace(" ", " ").replace("\xa0", " "))
    return "".join(c for c in text if not unicodedata.combining(c))


def load_tests(limit=None):
    with open(TESTS_PATH, encoding="utf-8") as f:
        tests = [json.loads(line) for line in f if line.strip()]
    return tests[:limit] if limit else tests


# ------------------------------------------------------------------ exécution
def run_level(n, tests):
    module = get_level(n)
    rows = []
    for case in tests:
        trace = Trace(level=n, question=case["question"], case_id=case["id"])
        try:
            out = module.answer(case["question"], trace)
            err = None
        except Exception as e:  # un cas qui plante ne bloque pas l'évaluation
            out, err = {"answer": "", "sources": [], "abstained": False, "tool_calls": []}, repr(e)
        data = trace.close({**out, "error": err})
        rows.append({"case": case, "output": out, "error": err,
                     "tokens": data["total_tokens"], "latency_s": data["duration_s"]})
        print(f"  [{n}] {case['id']:<10} {data['duration_s']:6.1f}s  {data['total_tokens']:>6} tok"
              + ("  (abstention)" if out.get("abstained") else "") + (f"  ERREUR {err}" if err else ""))
    return rows


# ------------------------------------------------------------------ notation par cas
def score_rows(rows, use_judge=False):
    if use_judge:
        from src.judge import judge
    for r in rows:
        case, out, s = r["case"], r["output"], {}
        ans = norm(out.get("answer", ""))
        if case["type"] == "in_docs":
            s["keywords_ok"] = all(norm(k) in ans for k in case.get("must_contain", []))
            s["false_abstention"] = bool(out.get("abstained"))
            s["source_ok"] = any(src in out.get("sources", []) for src in case["expected_sources"])
            retrieved = out.get("retrieved")
            if retrieved is not None:
                ranks = [i for i, src in enumerate(retrieved) if src in case["expected_sources"]]
                s["recall5"] = bool(ranks) and ranks[0] < 5
                s["rr"] = 1.0 / (ranks[0] + 1) if ranks else 0.0
            if use_judge and not out.get("abstained"):
                s["judge_ok"], r["judge_tokens"] = judge(case["question"], case["expected"], out.get("answer", ""))
            elif use_judge:
                s["judge_ok"] = False
            s["correct"] = s["keywords_ok"] and s.get("judge_ok", True) and not s["false_abstention"]
        elif case["type"] == "absent":
            s["abstained"] = bool(out.get("abstained"))
        elif case["type"] == "ambiguous":
            if case["expected"] == "clarification":
                s["ok"] = "?" in out.get("answer", "")
            else:  # refus
                s["ok"] = bool(out.get("abstained")) or any(m in ans for m in REFUSAL_MARKERS)
        elif case["type"] == "task":
            s["success"] = out.get("task_success")  # renseigné par les niveaux qui ont des outils
        if "top_score" in out:
            s["top_score"] = out["top_score"]
        r["scores"] = s
    return rows


def _rate(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def summarize(n, rows):
    by = lambda t: [r["scores"] for r in rows if r["case"]["type"] == t]
    docs, absent, amb, tasks = by("in_docs"), by("absent"), by("ambiguous"), by("task")
    top = lambda t: [s["top_score"] for s in by(t) if "top_score" in s]
    return {
        "niveau": f"{n} · {LEVEL_NAMES[n]}",
        "recall@5": _rate([s.get("recall5") for s in docs]),
        "mrr": round(statistics.mean(s["rr"] for s in docs), 3) if docs and "rr" in docs[0] else None,
        "exactitude": _rate([s["correct"] for s in docs]),
        "sources_citees": _rate([s["source_ok"] for s in docs]),
        "abstention": _rate([s["abstained"] for s in absent]),
        "abstention_a_tort": _rate([s["false_abstention"] for s in docs]),
        "ambigus_ok": _rate([s["ok"] for s in amb]),
        "succes_taches": _rate([s["success"] for s in tasks]),
        "tokens_moy": round(statistics.mean(r["tokens"] for r in rows)),
        "latence_moy_s": round(statistics.mean(r["latency_s"] for r in rows), 2),
        "erreurs": sum(r["error"] is not None for r in rows),
        # aide au réglage du seuil d'abstention du RAG
        "score_max_moy_in_docs": round(statistics.mean(top("in_docs")), 3) if top("in_docs") else None,
        "score_max_moy_absent": round(statistics.mean(top("absent")), 3) if top("absent") else None,
    }


def to_markdown(table):
    cols = [("niveau", "Niveau"), ("recall@5", "Recall@5"), ("mrr", "MRR"), ("exactitude", "Exactitude"),
            ("sources_citees", "Sources citées"), ("abstention", "Abstention"),
            ("abstention_a_tort", "Abst. à tort"), ("ambigus_ok", "Ambigus OK"),
            ("succes_taches", "Succès tâches"), ("tokens_moy", "Tokens / req."), ("latence_moy_s", "Latence (s)")]
    fmt = lambda v: "—" if v is None else (f"{v:.0%}" if isinstance(v, float) and v <= 1 else str(v))
    lines = ["| " + " | ".join(h for _, h in cols) + " |", "|" + "---|" * len(cols)]
    for row in table:
        lines.append("| " + " | ".join(fmt(row[k]) if k not in ("niveau", "mrr", "latence_moy_s")
                                         else str(row[k] if row[k] is not None else "—") for k, _ in cols) + " |")
    return "\n".join(lines)


# ------------------------------------------------------------------ calibration du juge
def calibrate_judge():
    """Compare le juge à des annotations humaines : data/judge_annotations.jsonl
    (une ligne par cas : {"question", "expected", "answer", "human_correct": true/false})."""
    from src.judge import judge
    path = DATA_DIR / "judge_annotations.jsonl"
    if not path.exists():
        print(f"Créer d'abord {path} (20 réponses annotées à la main).")
        return
    items = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    todo = [i["id"] for i in items if i.get("human_correct") is None]
    if todo:
        print(f"{len(todo)} cas pas encore annotés (human_correct = true/false) : {', '.join(todo)}")
        return
    tp = fp = fn = tn = 0
    for i in items:
        j = judge(i["question"], i["expected"], i["answer"])[0]
        h = i["human_correct"]
        tp += j and h; fp += j and not h; fn += (not j) and h; tn += (not j) and not h
        if j != h:
            print(f"  désaccord {i['id']} : juge={j}, humain={h}")
    n = len(items)
    print(f"Accord juge / humain : {tp + tn}/{n} ({(tp + tn) / n:.0%})")
    print(f"Juge trop sévère (rejette une réponse juste) : {fn} | trop indulgent (accepte une réponse fausse) : {fp}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--levels", type=int, nargs="+", default=[0, 1, 2, 3])
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--judge", action="store_true", help="exactitude vérifiée aussi par le juge LLM")
    p.add_argument("--calibrate-judge", action="store_true")
    args = p.parse_args()
    if args.calibrate_judge:
        return calibrate_judge()

    tests = load_tests(args.limit)
    table = []
    for n in args.levels:
        if not is_available(n):
            print(f"Niveau {n} ({LEVEL_NAMES[n]}) : pas encore disponible, ignoré.")
            continue
        print(f"Niveau {n} ({LEVEL_NAMES[n]}) sur {len(tests)} cas")
        rows = score_rows(run_level(n, tests), use_judge=args.judge)
        with open(RESULTS_DIR / f"level{n}_raw.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        table.append(summarize(n, rows))

    with open(RESULTS_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, indent=2)
    md = to_markdown(table)
    (RESULTS_DIR / "summary.md").write_text(md + "\n", encoding="utf-8")
    print("\n" + md)
    for row in table:
        if row["score_max_moy_in_docs"] is not None:
            print(f"\n{row['niveau']} : score dense max moyen, questions avec réponse = {row['score_max_moy_in_docs']}, "
                  f"sans réponse = {row['score_max_moy_absent']} (aide pour régler RAG_MIN_SCORE)")


if __name__ == "__main__":
    main()
