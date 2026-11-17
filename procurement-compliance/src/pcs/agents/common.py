"""專責代理共用：經 MCP 取回報價單與條文，並依 PCS_REASONER 選擇規則或 LLM 推理。"""

from __future__ import annotations

import re

from ..config import settings
from ..corpus import QUOTE_NO_RE, parse_quote
from ..mcp_client import KGClient
from ..reasoning import RuleBook


def quote_numbers(text: str) -> list[str]:
    return list(dict.fromkeys(QUOTE_NO_RE.findall(text)))


async def gather(kg: KGClient, quote_nos: list[str], queries: list[str], mode: str = "hybrid", top_k: int = 8):
    quotes, quote_docs = [], []
    for no in quote_nos:
        doc = await kg.find_quote(no)
        if doc and (q := parse_quote(doc["text"], doc["doc_id"])):
            quotes.append(q)
            quote_docs.append({"chunk_id": f"{doc['doc_id']}#0", "doc_id": doc["doc_id"],
                               "doc_title": doc["title"], "text": doc["text"], "rule_id": None})
    contexts: dict[str, dict] = {c["chunk_id"]: c for c in quote_docs}
    for q in queries:
        for c in await kg.query(q, mode, top_k):
            contexts.setdefault(c["chunk_id"], c)
    ctx = list(contexts.values())
    return quotes, ctx, RuleBook.from_contexts(ctx)


def related_quotes(contexts: list[dict], exclude: set[str]):
    out = []
    for c in contexts:
        q = parse_quote(c["text"], c["doc_id"])
        if q and q.quote_no not in exclude:
            out.append(q)
    return out


def evidence(contexts: list[dict]) -> list[dict]:
    rules = set()
    for c in contexts:
        rules |= set(re.findall(r"【規則\s*([A-Z]-\d+)】", c["text"]))
    return [{"chunk_id": c["chunk_id"], "doc_id": c["doc_id"]} for c in contexts] + [{"rules": sorted(rules)}]


def use_llm() -> bool:
    return settings.reasoner == "llm"
