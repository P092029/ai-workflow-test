"""財務代理：金額計算、分批合併、門檻與豁免上限比對。透過 MCP 呼叫 LightRAG。"""

from __future__ import annotations

import argparse
from typing import Callable

import uvicorn

from ..llm import chat_json, format_context
from ..mcp_client import KGClient
from ..reasoning import finance_assess
from .a2a import agent_card, create_a2a_app
from .common import evidence, gather, quote_numbers, related_quotes, use_llm

FINANCE_QUERIES = [
    "採購金額 門檻 公開招標 小額採購",
    "分批 合併計算 同一廠商 日內",
    "緊急修繕 採購金額 以下 上限",
]

LLM_SYSTEM = """你是財務代理，只能依【參考資料】計算，不得引用不存在的條文。
請輸出 JSON：{"total_amount": 整數, "exceeds_tender_threshold": true|false|null,
"within_emergency_cap": true|false|null,
"findings": [{"agent":"finance","claim":"...","rules":["A-3"],"data":{}}]}
注意：同一廠商、同一標的短期內多筆報價是否須合併計算，請依參考資料判斷。"""


async def handle(task: dict, kg: KGClient | None = None) -> dict:
    kg = kg or KGClient()
    quote_nos = task.get("quote_nos") or quote_numbers(task.get("question", ""))
    mode = task.get("mode", "hybrid")
    quotes, ctx, rb = await gather(kg, quote_nos, FINANCE_QUERIES, mode, task.get("top_k", 5))
    # 以廠商名稱再查一次圖譜，找出同廠商的其他報價（分批規避偵測）
    for vendor in {q.vendor for q in quotes}:
        for c in await kg.query(vendor, "local", task.get("top_k", 5)):
            if c["chunk_id"] not in {x["chunk_id"] for x in ctx}:
                ctx.append(c)
    if use_llm():
        out = await chat_json(LLM_SYSTEM, f"【問題】{task.get('question')}\n\n【參考資料】\n{format_context(ctx)}")
        out.setdefault("findings", [])
    else:
        out = finance_assess(quotes, related_quotes(ctx, {q.quote_no for q in quotes}), rb)
    out["evidence"] = evidence(ctx)
    out["mcp_calls"] = kg.calls
    return out


CARD = agent_card(
    "finance-agent", "財務代理：計算採購金額、偵測分批規避、比對招標門檻與豁免上限", "http://finance-agent:8202",
    [{"id": "finance-review", "name": "金額與門檻審查", "description": "輸入報價單號，回傳合計金額與門檻比對",
      "tags": ["procurement", "finance"], "examples": ["Q-2025-0904 是否須與其他報價合併計算？"]}],
)


def build_app(kg_factory: Callable[[], KGClient] = KGClient):
    """每個 A2A 任務建立新的 KGClient（獨立的 MCP 呼叫紀錄）。"""
    return create_a2a_app(CARD, lambda t: handle(t, kg_factory()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8202)
    uvicorn.run(build_app(), host="0.0.0.0", port=ap.parse_args().port)
