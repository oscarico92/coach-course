"""Reproduit le tableau de résultats.

    python eval.py                      # tous les niveaux disponibles, avec pass^3 (tableau du rapport)
    python eval.py --pass-k 0           # sans pass^3 (plus rapide)
    python eval.py --levels 0 1         # niveaux choisis
    python eval.py --judge              # ajoute le juge LLM pour l'exactitude (plus lent)
    python eval.py --limit 5            # test rapide
    python eval.py --calibrate-judge    # accord juge / annotations humaines
    python eval.py --rescore resultats_finaux/gpt-6-luna/results
                                        # recalcule les scores d'un run archivé, sans rappeler les modèles

Sorties : results/level{n}_raw.jsonl (réponses brutes), results/summary.json et results/summary.md (tableau).
"""
import argparse
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

from config import TESTS_PATH, RESULTS_DIR, DATA_DIR, LLM_MODEL
from src.tracing import Trace
from src.task_checks import check_task
from src.levels import get_level, is_available, LEVEL_NAMES

REFUSAL_MARKERS = ["je ne sais pas", "je ne peux pas", "je ne suis pas en mesure", "professionnel de sante",
                   "medecin", "hors de mon domaine", "course a pied uniquement", "ne fait pas partie"]


# Formats équivalents d'une même valeur (changement du 24/11/2026, voir data/TESTS.md) : une réponse juste
# ne doit pas échouer pour son format. « 4 min 58 s », « 4'58 » et « 1 minute et 45 secondes » -> « 4:58 » ;
# séparateur décimal « 13.3 » -> « 13,3 ». Appliqué à la réponse et aux mots attendus, pour tous les niveaux.
PACE_MIN_S = re.compile(r"(\d{1,2})\s*(?:minutes?|min|mn)\s*(?:et\s*)?(\d{1,2})\s*(?:secondes?|sec|s)\b")
PACE_QUOTE = re.compile(r"(\d{1,2})\s*['’]\s*(\d{2})(?!\d)")
DECIMAL_DOT = re.compile(r"(?<=\d)\.(?=\d)")


def norm(text):
    text = unicodedata.normalize("NFKD", (text or "").lower().replace(" ", " ").replace("\xa0", " "))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = PACE_MIN_S.sub(lambda m: f"{m[1]}:{int(m[2]):02d}", text)
    text = PACE_QUOTE.sub(lambda m: f"{m[1]}:{m[2]}", text)
    return DECIMAL_DOT.sub(",", text)


def load_tests(limit=None):
    with open(TESTS_PATH, encoding="utf-8") as f:
        tests = [json.loads(line) for line in f if line.strip()]
    return tests[:limit] if limit else tests


def tool_context(case, n):
    """Contexte reproductible pour les niveaux outillés : date simulée, météo simulée,
    calendrier de départ (fixtures du cas) et réponse simulée à la demande de confirmation."""
    from datetime import date
    from config import CALENDAR_DIR
    from src.tools import impl
    fx = case.get("fixtures", {})
    path = CALENDAR_DIR / f"eval_l{n}_{case['id']}.ics"
    if path.exists():
        path.unlink()
    impl.init_calendrier(path, fx.get("calendar", []))
    wants = case.get("confirm", True)
    return {"confirm": lambda name, args: wants,
            "context": {"today": case.get("ref_date", date.today().isoformat()),
                        "weather": fx.get("weather", {}), "calendar_path": path,
                        "weather_default": {"tmax_c": 15, "vent_kmh": 10, "orage": False}}}


def read_calendar(case, n):
    """État final du calendrier d'une tâche, relu dans le fichier .ics (pas dans la réponse du modèle)."""
    from config import CALENDAR_DIR
    from src.tools import impl
    path = CALENDAR_DIR / f"eval_l{n}_{case['id']}.ics"
    try:
        return impl.lire_calendrier({"date_debut": "2000-01-01", "date_fin": "2100-01-01"},
                                    {"calendar_path": path})["seances"]
    except Exception as e:
        print(f"    calendrier illisible pour {case['id']} : {e!r}")
        return []


# ------------------------------------------------------------------ exécution
def run_level(n, tests):
    module = get_level(n)
    rows = []
    for case in tests:
        trace = Trace(level=n, question=case["question"], case_id=case["id"])
        try:
            if getattr(module, "USES_TOOLS", False):
                out = module.answer(case["question"], trace, **tool_context(case, n))
            else:
                out = module.answer(case["question"], trace)
            err = None
        except Exception as e:  # un cas qui plante ne bloque pas l'évaluation
            out, err = {"answer": "", "sources": [], "abstained": False, "tool_calls": []}, repr(e)
        data = trace.close({**out, "error": err})
        row = {"case": case, "output": out, "error": err,
               "tokens": data["total_tokens"], "latency_s": data["duration_s"]}
        if getattr(module, "USES_TOOLS", False) and case["type"] == "task":
            row["final_calendar"] = read_calendar(case, n)
        rows.append(row)
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
            if "final_calendar" in r:   # niveaux outillés : état final vérifié par du code
                s["success"], s["checks"] = check_task(case, out, case.get("fixtures", {}).get("calendar", []),
                                                       r["final_calendar"])
            else:                       # niveaux sans outils : non applicable (« — » dans le tableau)
                s["success"] = None
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
    task_rows = [r for r in rows if r["case"]["type"] == "task"]
    top = lambda t: [s["top_score"] for s in by(t) if "top_score" in s]
    return {
        "niveau": f"{n} · {LEVEL_NAMES[n]} ({LLM_MODEL})",
        "recall@5": _rate([s.get("recall5") for s in docs]),
        "mrr": round(statistics.mean(s["rr"] for s in docs), 3) if docs and "rr" in docs[0] else None,
        "exactitude": _rate([s["correct"] for s in docs]),
        "sources_citees": _rate([s["source_ok"] for s in docs]),
        "abstention": _rate([s["abstained"] for s in absent]),
        "abstention_a_tort": _rate([s["false_abstention"] for s in docs]),
        "ambigus_ok": _rate([s["ok"] for s in amb]),
        # tâches utilisées pour régler le prompt / tâches jamais vues pendant le réglage (task-h*)
        "succes_taches": _rate([s["success"] for s, r in zip(tasks, task_rows) if not r["case"].get("held_out")]),
        "succes_taches_non_vues": _rate([s["success"] for s, r in zip(tasks, task_rows) if r["case"].get("held_out")]),
        "pass_k": None,
        "tokens_moy": round(statistics.mean(r["tokens"] for r in rows)),
        "latence_moy_s": round(statistics.mean(r["latency_s"] for r in rows), 2),
        "erreurs": sum(r["error"] is not None for r in rows),
        # aide au réglage du seuil d'abstention du RAG
        "score_max_moy_in_docs": round(statistics.mean(top("in_docs")), 3) if top("in_docs") else None,
        "score_max_moy_absent": round(statistics.mean(top("absent")), 3) if top("absent") else None,
    }


def routing_report(rows):
    """Niveau 3 (multi-agents) : vers quel agent chaque type de question est parti.
    doc = agent documentaire dès l'orchestrateur, agent = agent actions, agent>doc = agent actions sans outil
    puis repli vers l'agent documentaire.
    Attendu : in_docs et absent finissent au RAG, task et ambiguous dans la boucle. Les écarts sont listés par cas."""
    routed = [r for r in rows if r["output"].get("route")]
    if not routed:
        return None
    expected = {"in_docs": "doc", "absent": "doc", "task": "agent", "ambiguous": "agent"}
    counts, errors = {}, []
    for r in routed:
        t, got = r["case"]["type"], r["output"]["route"]
        c = counts.setdefault(t, {"doc": 0, "agent": 0, "agent>doc": 0})
        c[got] = c.get(got, 0) + 1
        final = "doc" if got.endswith("doc") else "agent"
        if final != expected.get(t, final):
            errors.append(f"{r['case']['id']}->{got}")
    return {"par_type": counts, "ecarts": errors}


def to_markdown(table):
    cols = [("niveau", "Niveau"), ("recall@5", "Recall@5"), ("mrr", "MRR"), ("exactitude", "Exactitude"),
            ("sources_citees", "Sources citées"), ("abstention", "Abstention"),
            ("abstention_a_tort", "Abst. à tort"), ("ambigus_ok", "Ambigus OK"),
            ("succes_taches", "Succès tâches"), ("succes_taches_non_vues", "Tâches non vues"), ("pass_k", "pass^k"), ("tokens_moy", "Tokens / req."), ("latence_moy_s", "Latence (s)")]
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


def pass_k(n, tasks, k, temperature):
    """pass^k : part des tâches réussies lors des k essais (graines 1..k, température > 0)."""
    import src.llm as llm
    if not tasks:
        return None
    ok = {c["id"]: True for c in tasks}
    saved = (llm.TEMPERATURE, llm.SEED)
    try:
        for run in range(1, k + 1):
            llm.TEMPERATURE, llm.SEED = temperature, run
            print(f"  pass^{k} : essai {run}/{k}")
            for r in score_rows(run_level(n, tasks)):
                ok[r["case"]["id"]] &= bool(r["scores"]["success"])
    finally:
        llm.TEMPERATURE, llm.SEED = saved
    print(f"  pass^{k} par tâche : " + ", ".join(f"{i}={'ok' if v else 'échec'}" for i, v in ok.items()))
    return round(sum(ok.values()) / len(ok), 3)


def rescore(folder, levels, use_judge=False):
    """Recalcule le tableau d'un run archivé à partir de ses réponses brutes (aucun appel aux modèles, sauf
    --judge). Le pass^k n'est pas recalculable (essais non enregistrés) : il est repris du summary.json du dossier.
    Écrit summary_rescore.json et summary_rescore.md dans le dossier."""
    old = {}
    if (folder / "summary.json").exists():
        old = {row["niveau"].split(" · ")[0]: row for row in json.load(open(folder / "summary.json", encoding="utf-8"))}
    table = []
    for n in levels:
        path = folder / f"level{n}_raw.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        rows = score_rows(rows, use_judge=use_judge)
        summary = summarize(n, rows)
        prev = old.get(str(n), {})
        summary["niveau"] = prev.get("niveau", summary["niveau"])   # nom du modèle du run d'origine
        summary["pass_k"] = prev.get("pass_k")
        table.append(summary)
    if not table:
        sys.exit(f"Aucun levelN_raw.jsonl dans {folder}")
    json.dump(table, open(folder / "summary_rescore.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    md = to_markdown(table)
    (folder / "summary_rescore.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    print(f"\nÉcrit : {folder / 'summary_rescore.md'}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--levels", type=int, nargs="+", default=[0, 1, 2, 3])
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--judge", action="store_true", help="exactitude vérifiée aussi par le juge LLM")
    p.add_argument("--calibrate-judge", action="store_true")
    p.add_argument("--pass-k", type=int, default=3,
                   help="relance les tâches k fois (graines différentes) : une tâche compte si les k essais réussissent ; "
                        "0 pour ne pas le faire (3 par défaut, colonne pass^3 du tableau attendu)")
    p.add_argument("--rescore", metavar="DOSSIER",
                   help="recalcule les scores à partir des levelN_raw.jsonl d'un dossier (pass^k repris de son summary.json)")
    p.add_argument("--pass-temp", type=float, default=0.7,
                   help="température des essais pass^k (à 0, les essais seraient quasi identiques)")
    args = p.parse_args()
    if args.calibrate_judge:
        return calibrate_judge()
    if args.rescore:
        return rescore(Path(args.rescore), args.levels, args.judge)

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
        summary = summarize(n, rows)
        routing = routing_report(rows)
        if routing:
            summary["routage"] = routing
            print("  Routage : " + ", ".join(f"{t} {c['doc']} doc / {c['agent']} agent / {c['agent>doc']} repli"
                                              for t, c in routing["par_type"].items()))
            print("  Écarts au routage attendu : " + (", ".join(routing["ecarts"]) or "aucun"))
        if args.pass_k and getattr(get_level(n), "USES_TOOLS", False) and summary["erreurs"]:
            print(f"  pass^{args.pass_k} ignoré : {summary['erreurs']} erreur(s) au run principal, à corriger d'abord")
        elif args.pass_k and getattr(get_level(n), "USES_TOOLS", False):
            summary["pass_k"] = pass_k(n, [c for c in tests if c["type"] == "task"], args.pass_k, args.pass_temp)
        table.append(summary)

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
