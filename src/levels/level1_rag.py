"""Niveau 1 : RAG (semaine 2).

À implémenter :
- découpage du corpus (data/corpus) en passages, avec métadonnées (fichier, section) ;
- index dense (src.llm.embed, bge-m3) + BM25 (rank_bm25), fusion des scores (ex. RRF) ;
- prompt qui impose de citer les sources [doc#section] et de s'abstenir sous un seuil de score ;
- renvoyer aussi les identifiants récupérés (pour Recall@k et MRR dans eval.py).
"""

AVAILABLE = False


def retrieve(question, k=5):
    raise NotImplementedError


def answer(question, trace):
    raise NotImplementedError("Niveau 1 (RAG) pas encore implémenté")
