"""Implémentation des outils de l'agent (niveau 2). Contrat : src/tools/__init__.py."""
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from icalendar import Calendar, Event

ZONES = {"récupération (60 %)": 0.60, "EF (70 %)": 0.70, "marathon (77 %)": 0.77, "semi (82 %)": 0.82,
         "seuil (85 %)": 0.85, "10 km (90 %)": 0.90, "VMA 95 %": 0.95, "VMA (100 %)": 1.00}
RACE_PCT = {10: 0.90, 21.0975: 0.82, 42.195: 0.77}
PARIS = (48.8566, 2.3522)
PLANS = {"5km": "plan_5km_debutant.md", "10km": "plan_10km_50min.md",
         "semi": "plan_semi_1h45.md", "marathon": "plan_marathon_3h45.md"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _pace(kmh, km=1.0):
    m, s = divmod(round(km * 3600 / kmh), 60)
    return f"{m}:{s:02d}"


DUREE_HMS = re.compile(r"^\s*(\d{1,2}):(\d{2}):(\d{2})\s*$")
DUREE_H = re.compile(r"(\d{1,2})\s*(?:heures?|h)\s*(?:(\d{1,2})\s*(?:min(?:utes?)?)?)?", re.I)
DUREE_MIN = re.compile(r"(\d{1,3})\s*(?:min(?:utes?)?|mn)\b", re.I)


def duree_minutes(text):
    """Convertit un temps écrit par l'utilisateur en minutes : « 1 h 50 », « 1h50 », « 3 heures 45 »,
    « 50 min », « 50 minutes », « 1:50:00 ». Lève ValueError si le texte n'est pas reconnu."""
    t = str(text).strip()
    m = DUREE_HMS.match(t)
    if m:
        return int(m[1]) * 60 + int(m[2]) + int(m[3]) / 60
    m = DUREE_H.search(t)
    if m:
        return int(m[1]) * 60 + int(m[2] or 0)
    m = DUREE_MIN.search(t)
    if m:
        return int(m[1])
    raise ValueError(f"Temps objectif non reconnu : « {text} ». Recopier le temps tel qu'écrit, ex. « 1 h 50 » ou « 50 min ».")


def calcul_allures(args, ctx):
    if args.get("temps_objectif"):    # texte recopié de la question : la conversion est faite par le code
        args = {**args, "temps_objectif_min": duree_minutes(args["temps_objectif"])}
    vma = args.get("vma_kmh")
    cible = None
    if not vma and args.get("distance_test_m"):
        vma = args["distance_test_m"] / 100
    if args.get("temps_objectif_min") and args.get("distance_km"):
        dist = args["distance_km"]
        v = dist / (args["temps_objectif_min"] / 60)
        cible = _pace(v)
        pct = next((p for d, p in RACE_PCT.items() if abs(d - dist) < 0.5), None)
        if not vma and pct:
            vma = v / pct
    if not vma:
        if cible:
            return {"allure_cible": cible}
        raise ValueError("Il faut une VMA (vma_kmh), un test demi-Cooper (distance_test_m) "
                         "ou un temps objectif avec sa distance (temps_objectif + distance_km).")

    vma = round(float(vma), 1)
    if not 8 <= vma <= 25:
        raise ValueError(f"VMA de {vma} km/h peu plausible (attendu entre 8 et 25). "
                         "Pour un temps objectif, passer temps_objectif et distance_km.")
    out = {"vma_kmh": vma,
           "allures": {zone: _pace(vma * p) for zone, p in ZONES.items()},
           "400 m à 95 % VMA": _pace(vma * 0.95, 0.4),
           "1000 m à 90 % VMA": _pace(vma * 0.90)}
    if cible:
        out["allure_cible"] = cible
    return out


def meteo(args, ctx):
    d = args["date"]
    date.fromisoformat(d)
    if ctx.get("weather") is not None:
        default = ctx.get("weather_default", {"tmax_c": 15, "vent_kmh": 10, "orage": False})
        return {"date": d, **ctx["weather"].get(d, default)}

    lat, lon = ctx.get("location", PARIS)
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
        "latitude": lat, "longitude": lon, "timezone": "Europe/Paris", "start_date": d, "end_date": d,
        "daily": "temperature_2m_max,wind_speed_10m_max,weather_code"})
    r.raise_for_status()
    day = r.json()["daily"]
    return {"date": d, "tmax_c": day["temperature_2m_max"][0], "vent_kmh": day["wind_speed_10m_max"][0],
            "orage": day["weather_code"][0] in (95, 96, 99)}


def _new_calendar():
    cal = Calendar()
    cal.add("prodid", "-//Foulees ECE//Coach Course//FR")
    cal.add("version", "2.0")
    return cal


def _event(s):
    from src.tools import INTENSE_TYPES
    d = date.fromisoformat(str(s["date"]))
    intense = s.get("intense", s.get("type") in INTENSE_TYPES)
    km = float(s.get("km") or 0)
    ev = Event()
    ev.add("uid", f"{uuid.uuid4()}@coach-course")
    ev.add("dtstamp", datetime.now())
    ev.add("dtstart", d)
    ev.add("dtend", d + timedelta(days=1))
    ev.add("summary", s.get("titre", ""))
    ev.add("description", f"{s.get('type') or 'séance'} · {km:g} km")
    ev.add("x-coach-type", s.get("type") or "")
    ev.add("x-coach-km", str(km))
    ev.add("x-coach-intense", "1" if intense else "0")
    return ev


def _save(path, seances, append=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if append and path.exists():
        cal = Calendar.from_ical(path.read_bytes())
    else:
        cal = _new_calendar()
    for s in seances:
        cal.add_component(_event(s))
    path.write_bytes(cal.to_ical())


def lire_calendrier(args, ctx):
    debut, fin = date.fromisoformat(args["date_debut"]), date.fromisoformat(args["date_fin"])
    path = Path(ctx["calendar_path"])
    if not path.exists():
        return {"seances": [], "km_total": 0.0}

    seances = []
    for ev in Calendar.from_ical(path.read_bytes()).walk("VEVENT"):
        d = ev.get("dtstart").dt
        if isinstance(d, datetime):
            d = d.date()
        if not debut <= d <= fin:
            continue
        seances.append({"date": d.isoformat(), "titre": str(ev.get("summary", "")),
                        "type": str(ev.get("x-coach-type", "")) or None,
                        "km": float(str(ev.get("x-coach-km", 0))),
                        "intense": str(ev.get("x-coach-intense", "0")) == "1"})
    seances.sort(key=lambda s: s["date"])
    return {"seances": seances, "km_total": round(sum(s["km"] for s in seances), 1)}


def ajouter_seances(args, ctx):
    today = ctx.get("today")
    if isinstance(today, str):
        today = date.fromisoformat(today)
    passees = [s["date"] for s in args["seances"] if today and date.fromisoformat(str(s["date"])) < today]
    if passees:
        raise ValueError(f"Date(s) déjà passée(s) : {', '.join(passees)}. Aujourd'hui : {today}.")

    deja = {(s["date"], s["titre"].strip().lower())
            for s in lire_calendrier({"date_debut": "2000-01-01", "date_fin": "2100-01-01"}, ctx)["seances"]}
    seances = [s for s in args["seances"] if (str(s["date"]), s.get("titre", "").strip().lower()) not in deja]
    _save(ctx["calendar_path"], seances)
    out = {"ajoutees": len(seances), "dates": [str(s["date"]) for s in seances]}
    if len(seances) < len(args["seances"]):
        out["deja_presentes"] = len(args["seances"]) - len(seances)
    return out


def init_calendrier(path, seances):
    _save(path, seances, append=False)


def _plan_row(fichier, semaine):
    from config import CORPUS_DIR
    header = None
    for line in (CORPUS_DIR / fichier).read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().replace("**", "") for c in line.strip().strip("|").split("|")]
        if cells[0] == "Semaine":
            header = cells
        elif header and cells[0] == str(semaine):
            return cells
    raise ValueError(f"Semaine {semaine} absente de {fichier}.")


def _minutes(text):
    m = re.search(r"(\d+)\s*h\s*(\d+)?", text)
    if m:
        return int(m[1]) * 60 + int(m[2] or 0)
    m = re.search(r"(\d+)\s*min", text)
    return int(m[1]) if m else 60


def _type(text):
    t = text.lower()
    for key, typ in [("allure marathon", "allure_marathon"), ("allure semi", "allure_semi"),
                     ("allure 10 km", "allure_10km"), ("seuil", "seuil"), ("vma", "fractionne")]:
        if key in t:
            return typ
    return "endurance"


def _jour(text, defaut):
    m = re.search(r"\b(" + "|".join(JOURS) + r")\b", text.lower())
    return m[1] if m else defaut


def _km(text, defaut):
    m = re.search(r"(\d+)\s*×\s*(\d+)\s*km", text)
    if m:
        return int(m[1]) * int(m[2])
    m = re.search(r"(\d+)\s*km", text)
    return int(m[1]) if m else defaut


def _libres(fixes, candidats, n):
    pris = {f[0] for f in fixes}
    return [j for j in candidats if j not in pris][:n]


def semaine_plan(args, ctx):
    plan = args.get("plan")
    if plan not in PLANS:
        raise ValueError(f"Plan inconnu : {plan}. Plans possibles : {', '.join(PLANS)}.")
    fichier = PLANS[plan]
    semaine = int(args["semaine"])
    v = _plan_row(fichier, semaine)
    course = plan != "5km" and v[-1].lower().startswith("course")

    if plan == "5km":
        seances = [(j, f"Course/marche : {v[1]}", "endurance", 4) for j in ("mardi", "jeudi", "dimanche")]
    elif plan == "10km":
        fixes = [(_jour(v[1], "mardi"), f"Fractionné : {v[1]}", _type(v[1]), 8),
                 (_jour(v[2], "samedi"), f"Allure 10 km : {v[2]}", _type(v[2]), 9)]
        if not course:
            fixes.append(("dimanche", f"Sortie longue {v[3]}", "sortie_longue", round(_minutes(v[3]) / 6)))
        seances = fixes + [(j, "Endurance fondamentale 45 min", "endurance", 8)
                           for j in _libres(fixes, ["jeudi", "mercredi", "vendredi"], 1)]
    else:
        vol = int(re.match(r"\d+", v[1])[0])
        if plan == "semi":
            fixes = [(_jour(v[2], "mardi"), f"Séance qualité : {v[2]}", _type(v[2]), 10)]
            if 4 <= semaine <= 8:
                fixes.append(("samedi", "Footing de récupération 35 min", "recuperation", 6))
            libres = _libres(fixes, ["mercredi", "vendredi", "jeudi"], 2)
        else:
            fixes = [(_jour(v[2], "mardi"), f"Séance A : {v[2]}", _type(v[2]), 10),
                     (_jour(v[3], "vendredi"), f"Allure marathon : {v[3]}", "allure_marathon", _km(v[3], 8) + 4)]
            libres = _libres(fixes, ["mercredi", "jeudi", "samedi"], 1)
        if not course:
            fixes.append(("dimanche", f"Sortie longue {v[-1]}", "sortie_longue", round(_minutes(v[-1]) / 6)))
        reste = max(vol - sum(f[3] for f in fixes), 0)
        seances = fixes + [(j, "Endurance fondamentale", "endurance", max(round(reste / len(libres)), 5)) for j in libres]

    today = ctx.get("today") or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    lundi = today + timedelta(days=7 - today.weekday())
    out = [{"date": (lundi + timedelta(days=JOURS.index(j))).isoformat(), "jour": j, "titre": t, "type": typ, "km": km}
           for j, t, typ, km in seances]
    out.sort(key=lambda s: s["date"])
    res = {"plan": fichier, "semaine": semaine, "seances": out}
    if course:
        j = _jour(v[-1], "dimanche")
        res["course"] = {"jour": j, "date": (lundi + timedelta(days=JOURS.index(j))).isoformat(),
                         "note": "Semaine de course : pas de sortie longue, la course a lieu ce jour-là. "
                                 "Ne pas l'ajouter comme séance."}
    from config import CORPUS_DIR
    m = re.search(r"Allure cible en course : (\d:\d\d)", (CORPUS_DIR / fichier).read_text(encoding="utf-8"))
    if m:
        res["allure_cible"] = m[1]
    return res


def rechercher_corpus(args, ctx):
    """Réutilise la recherche hybride du niveau 1 (déjà implémentée)."""
    from src.levels.level1_rag import retrieve
    hits, top = retrieve(args["requete"])
    return {"score_max": round(top, 3),
            "extraits": [{"source": h["source"], "section": h["section"], "texte": h["text"]} for h in hits]}
