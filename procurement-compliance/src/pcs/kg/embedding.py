"""離線可用的字元 n-gram 雜湊向量（TF-IDF 加權），作為「傳統向量 RAG」基線的嵌入。

若設定 PCS_REASONER=llm 且 Ollama 可用，基線改用 Ollama 嵌入模型（見 vector_rag.py）。
"""

from __future__ import annotations

import hashlib
import math
import re

import numpy as np

DIM = 4096
_STRIP = re.compile(r"[\s#【】：:，。、（）()\-\*]+")


def _ngrams(text: str) -> list[str]:
    t = _STRIP.sub("", text)
    return [t[i : i + n] for n in (1, 2) for i in range(len(t) - n + 1)]


def _bucket(g: str) -> int:
    return int.from_bytes(hashlib.blake2b(g.encode(), digest_size=4).digest(), "little") % DIM


class HashingEmbedder:
    def __init__(self) -> None:
        self.idf = np.ones(DIM, dtype=np.float32)

    def fit(self, texts: list[str]) -> "HashingEmbedder":
        df = np.zeros(DIM, dtype=np.float32)
        for t in texts:
            for b in {_bucket(g) for g in _ngrams(t)}:
                df[b] += 1
        n = max(len(texts), 1)
        self.idf = np.log((1 + n) / (1 + df)).astype(np.float32) + 1.0
        return self

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            for g in _ngrams(t):
                out[i, _bucket(g)] += 1.0
            out[i] = np.log1p(out[i]) * self.idf
            norm = math.sqrt(float(out[i] @ out[i])) or 1.0
            out[i] /= norm
        return out
