"""Copie les résultats du dernier run (results/) et les traces (traces/) dans resultats_finaux/<nom>/,
un dossier versionné : la consigne demande les résultats bruts par niveau et les traces dans le dépôt.

    python scripts/archiver_resultats.py gpt-6-luna
    python scripts/archiver_resultats.py qwen2.5-7b
    python scripts/archiver_resultats.py qwen2.5-7b --remplacer   # écrase une archive existante de ce nom

Vider traces/ AVANT le run (les traces s'ajoutent d'un run à l'autre), puis archiver juste APRÈS :
    Remove-Item traces\\*.jsonl      (PowerShell)
    python eval.py
    python scripts/archiver_resultats.py <nom>
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import RESULTS_DIR, ROOT, TRACES_DIR  # noqa: E402

args = [a for a in sys.argv[1:] if a != "--remplacer"]
if len(args) != 1:
    sys.exit(__doc__)
dest = ROOT / "resultats_finaux" / args[0]
if dest.exists():
    if "--remplacer" not in sys.argv:
        sys.exit(f"{dest} existe déjà : choisir un autre nom, ou ajouter --remplacer pour l'écraser.")
    for sub in ("results", "traces"):   # runs_precedents/ et autres ajouts manuels sont gardés
        shutil.rmtree(dest / sub, ignore_errors=True)

files = [(p, dest / "results" / p.name) for p in sorted(RESULTS_DIR.glob("*")) if p.is_file()]
files += [(p, dest / "traces" / p.name) for p in sorted(TRACES_DIR.glob("*.jsonl"))]
if not files:
    sys.exit("Rien à archiver : results/ et traces/ sont vides.")
for src, dst in files:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}  ({src.stat().st_size / 1024:.0f} Ko)")
print(f"\n{len(files)} fichiers copiés dans {dest.relative_to(ROOT)}. À versionner :")
print(f"    git add {dest.relative_to(ROOT).as_posix()}")
