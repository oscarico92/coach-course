"""Trace de chaque exécution, enregistrée en JSONL pour l'analyse d'erreurs."""
import json
import time
import uuid
from datetime import datetime

from config import TRACES_DIR


class Trace:
    def __init__(self, level, question, case_id=None):
        self.data = {
            "run_id": uuid.uuid4().hex[:8],
            "case_id": case_id,
            "level": level,
            "question": question,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "steps": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
        self._t0 = time.perf_counter()

    def log_llm(self, res, note=""):
        self.data["prompt_tokens"] += res["prompt_tokens"]
        self.data["completion_tokens"] += res["completion_tokens"]
        self.data["steps"].append({
            "type": "llm", "note": note,
            "tokens": res["prompt_tokens"] + res["completion_tokens"],
            "latency_s": round(res["latency_s"], 3),
            "tool_calls": res["tool_calls"],
        })

    def log_tool(self, name, args, result, error=None):
        self.data["steps"].append({"type": "tool", "name": name, "args": args,
                                   "result": result, "error": error})

    def log(self, kind, **info):
        self.data["steps"].append({"type": kind, **info})

    @property
    def total_tokens(self):
        return self.data["prompt_tokens"] + self.data["completion_tokens"]

    def close(self, output):
        self.data["duration_s"] = round(time.perf_counter() - self._t0, 3)
        self.data["total_tokens"] = self.total_tokens
        self.data["output"] = output
        path = TRACES_DIR / f"level{self.data['level']}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.data, ensure_ascii=False, default=str) + "\n")
        return self.data
