"""單一代理 RAG：一個 LLM、一次檢索、一次判斷（無任務拆解、無多代理）。

* mode="naive"  → 基線「單一 LLM + 傳統向量 RAG」
* mode="hybrid" → 消融組「單一 LLM + LightRAG」（隔離知識圖譜的貢獻）

流程：問題 → 檢索 top-k 文字塊 → 一次性判斷。
  * rule 模式：同一套規則推理器，但只能看到 top-k 向量檢索結果（隔離「檢索 + 拆解」的效果）
  * llm  模式：把 top-k 內容與問題交給單一 LLM 一次回答（可量測幻覺）
"""

from __future__ import annotations

import re

from ..config import settings
from ..corpus import QUOTE_NO_RE, parse_quote
from ..kg import MiniGraphRAG, get_backend
from ..llm import JUDGE_SYSTEM, chat_json, format_context, normalize
from ..reasoning import RuleBook, combine, finance_assess, legal_assess


class SingleAgentRAG:
    def __init__(self, mode: str = "naive", top_k: int = 5, kg=None):
        self.mode, self.top_k = mode, top_k
        backend = kg or get_backend()
        if mode == "naive" and not isinstance(backend, MiniGraphRAG):
            # 傳統向量 RAG 基線不依賴 LightRAG 建庫
            backend = MiniGraphRAG(list(backend.docs.values()))
        self.kg = backend

    async def _retrieve(self, question: str) -> list[dict]:
        if hasattr(self.kg, "aquery"):
            return await self.kg.aquery(question, self.mode, self.top_k)
        return self.kg.query(question, self.mode, self.top_k)

    async def answer(self, question: str) -> dict:
        ctx = await self._retrieve(question)
        if settings.reasoner == "llm":
            out = normalize(await chat_json(JUDGE_SYSTEM, f"【問題】{question}\n\n【參考資料】\n{format_context(ctx)}"))
        else:
            rb = RuleBook.from_contexts(ctx)
            wanted = set(QUOTE_NO_RE.findall(question))
            quotes = [q for c in ctx if (q := parse_quote(c["text"], c["doc_id"])) and q.quote_no in wanted]
            others = [q for c in ctx if (q := parse_quote(c["text"], c["doc_id"])) and q.quote_no not in wanted]
            out = combine(finance_assess(quotes, others, rb), legal_assess(quotes, rb)) if quotes else {
                "verdict": "UNKNOWN", "cited_rules": [], "conflicts": []}
        out["evidence_rules"] = sorted({r for c in ctx for r in re.findall(r"【規則\s*([A-Z]-\d+)】", c["text"])})
        out["evidence_docs"] = sorted({c["doc_id"] for c in ctx})
        return out
