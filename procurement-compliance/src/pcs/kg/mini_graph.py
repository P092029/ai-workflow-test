"""MiniGraphRAG：模仿 LightRAG 檢索模式（naive / local / global / hybrid）的輕量知識圖譜。

用途：
  * 在沒有 GPU / Ollama 的環境下驗證整條 A2A + MCP 管線；
  * 作為消融實驗中「圖譜檢索」的可重現對照。

圖譜結構：節點 = 文字塊 + 實體；邊 = 文字塊提及實體。
實體來源：領域詞彙表、條文編號（含交叉引用，如 B-1 提及 A-5）、報價單號、廠商名稱。
  * local  ：以查詢中出現的實體，取回直接提及它們的文字塊（低階、精確）
  * global ：由種子實體沿「文字塊–實體–文字塊」擴張一跳，取回跨文件關聯（高階、關係）
  * hybrid ：local ∪ global（LightRAG 預設建議模式）
  * naive  ：純向量相似度
"""

from __future__ import annotations

import math
from collections import defaultdict

from ..corpus import QUOTE_NO_RE, RULE_REF_RE, Chunk, Document, chunk_document, parse_quote
from .embedding import HashingEmbedder

LEXICON = [
    "公開招標", "小額採購", "限制性採購", "緊急修繕", "特別規定", "分批", "合併計算",
    "事後報備", "事故", "天災", "報價日期", "採購金額", "工程", "財物", "勞務",
    "出差", "住宿費", "交通費",
]

MODES = ("naive", "local", "global", "hybrid", "mix")


class MiniGraphRAG:
    def __init__(self, docs: list[Document]):
        self.docs = {d.doc_id: d for d in docs}
        self.chunks: list[Chunk] = [c for d in docs for c in chunk_document(d)]
        self.chunk_entities: dict[str, set[str]] = {}
        self.entity_chunks: dict[str, set[str]] = defaultdict(set)
        self.by_id = {c.chunk_id: c for c in self.chunks}
        for c in self.chunks:
            if q := parse_quote(c.text):
                ents = self._quote_entities(c.text, q)
            else:
                ents = self._extract_entities(c.text)
            if c.rule_id:
                ents.add(c.rule_id)
            self.chunk_entities[c.chunk_id] = ents
            for e in ents:
                self.entity_chunks[e].add(c.chunk_id)
        n = len(self.chunks)
        self.idf = {e: math.log(1 + n / len(cs)) for e, cs in self.entity_chunks.items()}
        self.embedder = HashingEmbedder().fit([c.text for c in self.chunks])
        self.matrix = self.embedder.embed([c.text for c in self.chunks])

    # ---------- 建圖 ----------
    @staticmethod
    def _extract_entities(text: str) -> set[str]:
        ents = {w for w in LEXICON if w in text}
        ents |= set(RULE_REF_RE.findall(text))
        ents |= set(QUOTE_NO_RE.findall(text))
        return ents

    def _quote_entities(self, text: str, q) -> set[str]:
        """報價單只從「欄位值」抽實體，避免欄位名稱（如「是否緊急修繕：否」）造成假關聯。"""
        values = " ".join(
            line.split("：", 1)[1] for line in text.splitlines()
            if "：" in line and any(k in line for k in ("標的", "事故說明", "採購類別"))
        )
        ents = {w for w in LEXICON if w in values} | {q.quote_no, q.vendor, "採購金額"}
        if q.is_emergency:
            ents |= {"緊急修繕", "事故", "報價日期"}
        return ents

    def stats(self) -> dict:
        edges = sum(len(v) for v in self.chunk_entities.values())
        return {"documents": len(self.docs), "chunks": len(self.chunks),
                "entities": len(self.entity_chunks), "edges": edges}

    def relations(self) -> list[dict]:
        """跨文件關係：兩個不同文件的文字塊共享的實體（供視覺化 / 論文圖表）。"""
        rels = []
        for e, cids in self.entity_chunks.items():
            docs = sorted({self.by_id[c].doc_id for c in cids})
            if len(docs) > 1:
                rels.append({"entity": e, "documents": docs})
        return sorted(rels, key=lambda r: (-len(r["documents"]), r["entity"]))

    # ---------- 檢索 ----------
    def _seed_entities(self, query: str) -> set[str]:
        seeds = self._extract_entities(query)
        seeds |= {e for e in self.entity_chunks if len(e) >= 2 and e in query}
        return seeds

    def _rank(self, scores: dict[str, float], top_k: int) -> list[tuple[str, float]]:
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]

    def _naive(self, query: str, top_k: int) -> list[tuple[str, float]]:
        q = self.embedder.embed([query])[0]
        sims = self.matrix @ q
        return [(self.chunks[i].chunk_id, float(sims[i])) for i in sims.argsort()[::-1][:top_k]]

    def _local(self, seeds: set[str], top_k: int) -> list[tuple[str, float]]:
        scores: dict[str, float] = defaultdict(float)
        for e in seeds:
            for cid in self.entity_chunks.get(e, ()):
                scores[cid] += self.idf[e]
        return self._rank(scores, top_k)

    def _global(self, seeds: set[str], top_k: int) -> list[tuple[str, float]]:
        # 種子實體 → 文字塊 → 其上的實體（擴張）→ 其他文字塊
        hop1 = {cid for e in seeds for cid in self.entity_chunks.get(e, ())}
        expanded = {e for cid in hop1 for e in self.chunk_entities[cid]} - seeds
        scores: dict[str, float] = defaultdict(float)
        for e in expanded:
            for cid in self.entity_chunks[e]:
                scores[cid] += self.idf[e] * 0.5
        for e in seeds:
            for cid in self.entity_chunks.get(e, ()):
                scores[cid] += self.idf[e]
        return self._rank(scores, top_k)

    def query(self, query: str, mode: str = "hybrid", top_k: int = 8) -> list[dict]:
        if mode not in MODES:
            raise ValueError(f"mode 必須為 {MODES}")
        seeds = self._seed_entities(query)
        if mode == "naive":
            ranked = self._naive(query, top_k)
        elif mode == "local":
            ranked = self._local(seeds, top_k)
        elif mode == "global":
            ranked = self._global(seeds, top_k)
        else:
            merged: dict[str, float] = {}
            parts = [self._local(seeds, top_k), self._global(seeds, top_k)]
            if mode == "mix":
                parts.append(self._naive(query, top_k))
            for part in parts:
                for cid, s in part:
                    merged[cid] = max(merged.get(cid, 0.0), s)
            ranked = self._rank(merged, top_k * 2)
        out = []
        for cid, score in ranked:
            d = self.by_id[cid].to_dict()
            d["score"] = round(score, 4)
            d["entities"] = sorted(self.chunk_entities[cid])
            out.append(d)
        return out

    def get_document(self, doc_id: str) -> dict | None:
        d = self.docs.get(doc_id)
        return {"doc_id": d.doc_id, "title": d.title, "text": d.text} if d else None

    def find_quote(self, quote_no: str) -> dict | None:
        for d in self.docs.values():
            if quote_no in d.text and d.is_quote:
                return self.get_document(d.doc_id)
        return None
