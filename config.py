import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
TESTS_PATH = DATA_DIR / "tests.jsonl"
TRACES_DIR = ROOT / "traces"
RESULTS_DIR = ROOT / "results"
CALENDAR_DIR = ROOT / "calendar"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "6"))

for d in (TRACES_DIR, RESULTS_DIR, CALENDAR_DIR):
    d.mkdir(exist_ok=True)
