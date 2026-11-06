from importlib import import_module

LEVELS = {
    0: "src.levels.level0",
    1: "src.levels.level1_rag",
    2: "src.levels.level2_agent",
    3: "src.levels.level3_ext",
}

LEVEL_NAMES = {0: "LLM seul", 1: "RAG", 2: "Agent", 3: "Extension"}


def get_level(n):
    """Renvoie le module du niveau n (il expose answer(question, trace) -> dict)."""
    return import_module(LEVELS[n])


def is_available(n):
    return getattr(get_level(n), "AVAILABLE", True)
