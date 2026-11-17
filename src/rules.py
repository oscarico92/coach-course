"""Règles métier du club (regles_progression.md), vérifiées par du code avant toute écriture.

Le LLM propose des séances ; ce module décide si elles respectent les règles. Il ne fait confiance
ni au modèle ni à la façon dont la demande est formulée.
"""
from datetime import date, timedelta

from src.tools import INTENSE_TYPES

MAX_INTENSE_PER_WEEK = 3      # R2 (2 pour 5 km / 10 km : plafond retenu = le plus permissif des plans)
MAX_VOLUME_INCREASE = 0.10    # R1
HOT_C, WIND_KMH = 28, 50      # R5


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def _intense(s):
    return s.get("intense", s.get("type") in INTENSE_TYPES)


def _week_start(d):
    return d - timedelta(days=d.weekday())


def check(new, existing, weather=None):
    """new, existing : listes de séances {"date", "type" ou "intense", "km"}.
    weather : dict date ISO -> {"tmax_c", "vent_kmh", "orage"} pour les dates concernées.
    Renvoie la liste des violations (vide = écriture autorisée)."""
    violations = []
    weather = weather or {}
    all_s = existing + new

    # R2 : pas deux séances intenses deux jours consécutifs, plafond par semaine
    intense_days = sorted({_d(s["date"]) for s in all_s if _intense(s)})
    new_intense = {_d(s["date"]) for s in new if _intense(s)}
    for a, b in zip(intense_days, intense_days[1:]):
        if (b - a).days == 1 and (a in new_intense or b in new_intense):
            violations.append(f"R2 : séances intenses deux jours consécutifs ({a} et {b}).")
    weeks = {_week_start(_d(s["date"])) for s in new}
    for w in weeks:
        n = sum(1 for d in intense_days if _week_start(d) == w)
        if n > MAX_INTENSE_PER_WEEK:
            violations.append(f"R2 : {n} séances intenses la semaine du {w} (maximum {MAX_INTENSE_PER_WEEK}).")

    # R1 : volume hebdomadaire au plus +10 % par rapport à la semaine précédente
    for w in weeks:
        vol = sum(s.get("km", 0) for s in all_s if _week_start(_d(s["date"])) == w)
        prev = sum(s.get("km", 0) for s in existing if _week_start(_d(s["date"])) == w - timedelta(days=7))
        if prev > 0 and vol > prev * (1 + MAX_VOLUME_INCREASE) + 1e-9:
            violations.append(f"R1 : {vol:g} km la semaine du {w}, au-delà de +10 % "
                              f"par rapport aux {prev:g} km de la semaine précédente (maximum {prev * 1.1:g} km).")

    # R6 : au moins un jour de repos par semaine
    for w in weeks:
        days = {_d(s["date"]) for s in all_s if _week_start(_d(s["date"])) == w}
        if len(days) >= 7:
            violations.append(f"R6 : aucun jour de repos la semaine du {w}.")

    # R5 : météo
    for s in new:
        m = weather.get(str(s["date"]))
        if not m:
            continue
        if m.get("orage") or m.get("vent_kmh", 0) > WIND_KMH:
            violations.append(f"R5 : vent fort ou orage le {s['date']}, séance à reporter.")
        elif _intense(s) and m.get("tmax_c", 0) > HOT_C:
            violations.append(f"R5 : {m['tmax_c']} °C le {s['date']}, séance intense interdite "
                              f"(endurance fondamentale ou autre jour).")
    return violations
