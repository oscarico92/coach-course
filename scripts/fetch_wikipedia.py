"""Télécharge des articles de Wikipédia (fr) en texte brut et fige leur révision.

    python scripts/fetch_wikipedia.py

Licence des articles : CC BY-SA 4.0 (attribution : contributeurs de Wikipédia).
"""
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import CORPUS_DIR  # noqa: E402

ARTICLES = [
    "Vitesse maximale aérobie",
    "VO2 max",
    "Fartlek",
    "Marathon (athlétisme)",
    "Semi-marathon",
    "Course à pied",
    "Échauffement",
    "Surentraînement",
]

API = "https://fr.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "coach-course-student-project/0.1 (projet ECE)"}
OUT = CORPUS_DIR / "wikipedia"


def fetch(title):
    params = {"action": "query", "titles": title, "prop": "extracts|revisions", "explaintext": 1,
              "rvprop": "ids", "redirects": 1, "format": "json"}
    r = requests.get(API, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    page = next(iter(r.json()["query"]["pages"].values()))
    if "missing" in page:
        return None
    return page["title"], page["revisions"][0]["revid"], page.get("extract", "")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for title in ARTICLES:
        res = fetch(title)
        if res is None:
            print(f"  introuvable : {title}")
            continue
        real_title, revid, text = res
        fname = real_title.replace(" ", "_").replace("/", "-") + ".md"
        header = (f"# {real_title}\n\nSource : Wikipédia (fr), révision {revid}, "
                  f"licence CC BY-SA 4.0, récupéré le {date.today():%d/%m/%Y}\n\n")
        (OUT / fname).write_text(header + text, encoding="utf-8")
        rows.append(f"| wikipedia/{fname} | {real_title} | {revid} | {date.today():%d/%m/%Y} |")
        print(f"  ok : {real_title} ({len(text)} caractères)")

    sources = CORPUS_DIR / "SOURCES.md"
    with open(sources, "a", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    print(f"{len(rows)} articles enregistrés dans {OUT}, SOURCES.md mis à jour.")


if __name__ == "__main__":
    main()
