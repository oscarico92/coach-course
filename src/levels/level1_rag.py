"""Niveau 1 : RAG.

- Découpage du corpus par section (titres Markdown « ## » ou Wikipédia « == »), sections longues
  redécoupées en fenêtres avec recouvrement.
- Recherche hybride : dense (embeddings bge-m3, similarité cosinus) + BM25, fusionnées par RRF.
- Abstention en deux temps : seuil sur le meilleur score dense (sans appeler le LLM),
  puis consigne dans le prompt si les extraits ne contiennent pas la réponse.
- Chaque affirmation doit citer sa source [fichier.md] ; les citations sont extraites de la réponse.
"""
import hashlib
import json
import re
import unicodedata

import numpy as np
from rank_bm25 import BM25Okapi

from config import CORPUS_DIR, DATA_DIR, EMBED_MODEL, RAG_TOP_K, RAG_MIN_SCORE
from src.llm import chat, embed

AVAILABLE = True

INDEX_DIR = DATA_DIR / "index"
EXCLUDED = {"README.md", "SOURCES.md"}
MAX_CHARS = 1200      # au-delà, une section est redécoupée
OVERLAP = 200
RRF_K = 60
ABSTAIN = "JE NE SAIS PAS"

SYSTEM_PROMPT = f"""Tu es le coach de course à pied du club « Foulées ECE ».
Règles strictes :
- Réponds UNIQUEMENT à partir des extraits fournis, jamais de tes connaissances générales.
- Après chaque affirmation, cite sa source entre crochets avec le nom exact du fichier, par exemple [plan_10km_50min.md].
- Si les extraits ne contiennent pas la réponse, commence ta réponse par « {ABSTAIN} » et n'invente rien.
- Si la question est trop vague pour y répondre, pose une question de précision au lieu de répondre.
- Tu ne donnes pas d'avis médical : en cas de douleur, oriente vers un professionnel de santé.
- Réponds en français, de façon concise et précise (chiffres, semaines, allures)."""


# ---------------------------------------------------------------- découpage
HEADING = re.compile(r"^(#{1,3})\s+(.*)$|^(={2,4})\s*(.*?)\s*={2,4}\s*$")


def _sections(text):
    """Découpe un document en (titre de section, contenu)."""
    title, current, out = "", [], []
    for line in text.splitlines():
        m = HEADING.match(line.strip())
        if m:
            if "".join(current).strip():
                out.append((title, "\n".join(current).strip()))
            title, current = (m.group(2) or m.group(4)).strip(), []
        else:
            current.append(line)
    if "".join(current).strip():
        out.append((title, "\n".join(current).strip()))
    return out


def _windows(text):
    if len(text) <= MAX_CHARS:
        return [text]
    parts, start = [], 0
    while start < len(text):
        parts.append(text[start:start + MAX_CHARS])
        start += MAX_CHARS - OVERLAP
    return parts


def build_chunks():
    chunks = []
    for path in sorted(CORPUS_DIR.rglob("*.md")):
        if path.name in EXCLUDED:
            continue
        rel = path.relative_to(CORPUS_DIR).as_posix()
        text = path.read_text(encoding="utf-8")
        # les lignes d'en-tête (licence, provenance) ne sont pas indexées : elles créeraient des passages vides de sens
        text = "\n".join(l for l in text.splitlines()
                         if not l.startswith(("Club fictif", "Source : Wikipédia")))
        doc_title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("# ")), rel)
        for s_idx, (section, body) in enumerate(_sections(text)):
            for w_idx, piece in enumerate(_windows(body)):
                chunks.append({
                    "id": f"{rel}#{s_idx}.{w_idx}",
                    "source": rel,
                    "section": section,
                    # le titre du document et de la section sont ajoutés au texte indexé :
                    # « semaine 6 du plan 10 km » doit retrouver la bonne table
                    "text": f"{doc_title} — {section}\n{piece}" if section else f"{doc_title}\n{piece}",
                })
    return chunks


# ---------------------------------------------------------------- index
def _tokenize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?", text)


class Index:
    def __init__(self):
        self.chunks = build_chunks()
        key = hashlib.sha1((EMBED_MODEL + json.dumps(self.chunks, ensure_ascii=False)).encode()).hexdigest()[:12]
        INDEX_DIR.mkdir(exist_ok=True)
        cache = INDEX_DIR / f"emb_{key}.npy"
        if cache.exists():
            emb = np.load(cache)
        else:
            vectors = []
            for i in range(0, len(self.chunks), 32):
                vectors += embed([c["text"] for c in self.chunks[i:i + 32]])
            emb = np.array(vectors, dtype=np.float32)
            np.save(cache, emb)
        self.emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        self.bm25 = BM25Okapi([_tokenize(c["text"]) for c in self.chunks])

    def search(self, question, k=RAG_TOP_K, pool=20):
        q = np.array(embed([question])[0], dtype=np.float32)
        q /= np.linalg.norm(q)
        dense = self.emb @ q
        sparse = self.bm25.get_scores(_tokenize(question))
        dense_rank = np.argsort(-dense)[:pool]
        sparse_rank = np.argsort(-sparse)[:pool]
        fused = {}
        for ranking in (dense_rank, sparse_rank):
            for r, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
        best = sorted(fused, key=fused.get, reverse=True)[:k]
        hits = [{**self.chunks[i], "rrf": round(fused[i], 4), "dense": round(float(dense[i]), 4)} for i in best]
        return hits, float(dense.max())


_INDEX = None


def get_index():
    global _INDEX
    if _INDEX is None:
        _INDEX = Index()
    return _INDEX


def retrieve(question, k=RAG_TOP_K):
    return get_index().search(question, k)


# ---------------------------------------------------------------- réponse
CITATION = re.compile(r"\[([^\[\]]+?\.md)(?:#[^\]]*)?\]")


def answer(question, trace):
    hits, top_score = retrieve(question)
    retrieved = [h["source"] for h in hits]
    trace.log("retrieval", top_score=round(top_score, 4),
              hits=[{"id": h["id"], "rrf": h["rrf"], "dense": h["dense"]} for h in hits])
    base = {"tool_calls": [], "retrieved": retrieved, "retrieved_ids": [h["id"] for h in hits],
            "top_score": top_score}

    # Abstention 1 : aucun passage assez proche, on ne sollicite même pas le LLM
    if top_score < RAG_MIN_SCORE:
        trace.log("abstention", reason=f"score max {top_score:.3f} < seuil {RAG_MIN_SCORE}")
        return {**base, "answer": f"{ABSTAIN} : je ne trouve pas cette information dans les documents du club.",
                "sources": [], "abstained": True}

    context = "\n\n".join(f"[{h['source']}] ({h['section']})\n{h['text']}" for h in hits)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extraits des documents du club :\n\n{context}\n\nQuestion : {question}"}]
    res = chat(messages)
    trace.log_llm(res, note="réponse RAG")
    text = res["content"].strip()

    # Abstention 2 : le LLM juge que les extraits ne contiennent pas la réponse
    abstained = text.upper().startswith(ABSTAIN)
    cited = [s for s in dict.fromkeys(CITATION.findall(text)) if s in retrieved]
    return {**base, "answer": text, "sources": cited, "abstained": abstained}
