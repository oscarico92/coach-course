"""Vérification par du code de l'état final des tâches (champ `check` de tests.jsonl).

Une tâche est réussie si TOUTES ses vérifications passent. On compare le calendrier final
(relu dans le fichier .ics) au calendrier de départ (fixtures du cas) : les séances « nouvelles »
sont celles que l'agent a réellement écrites.
"""
import re
from datetime import date, timedelta

from src.tools import INTENSE_TYPES

PACE = re.compile(r"(\d{1,2})\s*(?::|'|’|min\s*)\s*(\d{2})")


def _sec(mmss):
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)


def _paces_in(text):
    return [int(m) * 60 + int(s) for m, s in PACE.findall(text or "")]


def _norm(text):
    return (text or "").lower().replace(" ", " ").replace("\xa0", " ")


def _key(s):
    return (str(s["date"]), (s.get("titre") or "").strip().lower())


def _intense(s):
    return s.get("intense", s.get("type") in INTENSE_TYPES)


def _monday(d):
    d = date.fromisoformat(str(d))
    return d - timedelta(days=d.weekday())


def check_task(case, out, initial, final):
    """Renvoie (succès: bool, détail: dict nom_de_vérification -> bool)."""
    c, ans = case.get("check", {}), out.get("answer", "")
    initial_keys = {_key(s) for s in initial}
    new = [s for s in final if _key(s) not in initial_keys]
    new_dates = [str(s["date"]) for s in new]
    res = {}

    tol = c.get("tolerance_s", 5)
    for name, expected in c.get("answer_paces", {}).items():
        res[f"allure {name} = {expected}"] = any(abs(p - _sec(expected)) <= tol for p in _paces_in(ans))
    for v in c.get("answer_contains", []):
        # nombre entier ou décimal : recherché comme nombre isolé (« 2 » ne doit pas matcher « 2026 »)
        variants = {_norm(v), _norm(v).replace(",", ".")}
        res[f"réponse contient {v}"] = any(re.search(rf"(?<![\d,.]){re.escape(x)}(?![\d,.]\d)", _norm(ans))
                                           for x in variants)
    if "ics_new_events" in c:
        res[f"{c['ics_new_events']} séance(s) ajoutée(s)"] = len(new) == c["ics_new_events"]
    if "ics_new_events_min" in c:
        res[f"au moins {c['ics_new_events_min']} séance(s) ajoutée(s)"] = len(new) >= c["ics_new_events_min"]
    if "ics_dates" in c:
        res["dates exactes"] = sorted(new_dates) == sorted(c["ics_dates"])
    for d in c.get("ics_no_intense_on", []):
        res[f"pas de séance intense le {d}"] = not any(str(s["date"]) == d and _intense(s) for s in new)
    for d in c.get("ics_no_event_on", []):
        res[f"pas de séance le {d}"] = d not in new_dates
    if c.get("no_consecutive_intense"):
        days = sorted({date.fromisoformat(str(s["date"])) for s in final if _intense(s)})
        res["pas d'intenses consécutives (R2)"] = all((b - a).days > 1 for a, b in zip(days, days[1:]))
    if c.get("no_consecutive_days"):
        days = sorted({date.fromisoformat(d) for d in new_dates})
        res["pas deux jours consécutifs"] = all((b - a).days > 1 for a, b in zip(days, days[1:]))
    if "min_rest_days" in c:
        week = _monday(c.get("week", new_dates[0] if new_dates else case.get("ref_date")))
        used = {str(s["date"]) for s in final if _monday(s["date"]) == week}
        res[f"au moins {c['min_rest_days']} jours de repos (R6)"] = 7 - len(used) >= c["min_rest_days"]
    if "ics_week_km_max" in c:
        week = _monday(c["week"])
        km = sum(float(s.get("km") or 0) for s in final if _monday(s["date"]) == week)
        res[f"volume ≤ {c['ics_week_km_max']} km (R1)"] = km <= c["ics_week_km_max"] + 1e-9
    if c.get("asked_confirmation"):
        res["confirmation demandée"] = bool(out.get("asked_confirmation"))
    return (all(res.values()) if res else False), res
