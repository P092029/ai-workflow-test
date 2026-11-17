from __future__ import annotations

from functools import lru_cache

from ..config import settings
from ..corpus import load_corpus
from .mini_graph import MODES, MiniGraphRAG

__all__ = ["MODES", "MiniGraphRAG", "get_backend"]


@lru_cache(maxsize=1)
def get_backend():
    docs = load_corpus(settings.corpus_dir)
    if settings.kg_backend == "lightrag":
        from .lightrag_backend import LightRAGBackend

        return LightRAGBackend(docs)
    return MiniGraphRAG(docs)
