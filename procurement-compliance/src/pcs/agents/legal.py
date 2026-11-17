"""法務代理：判斷緊急修繕資格、特別規定效力與附帶義務。透過 MCP 呼叫 LightRAG。"""

from __future__ import annotations

import argparse
from typing import Callable

import uvicorn

from ..llm import chat_json, format_context
from ..mcp_client import KGClient
from ..reasoning import legal_assess
from .a2a import agent_card, create_a2a_app
from .common import evidence, gather, quote_numbers, use_llm

LEGAL_QUERIES = [
    "緊急修繕 豁免 公開招標 限制性採購 金額上限",
    "特別規定 排除 公開招標",
    "緊急修繕 報價日期 事故 日內 事後報備",
]

LLM_SYSTEM = """你是法務代理，只能依【參考資料】判斷，不得引用不存在的條文。
請輸出 JSON：{"emergency_qualified": true|false|null,
"obligations": [{"agent":"legal","claim":"...","rules":["B-5"],"data":{}}],
"findings": [{"agent":"legal","claim":"...","rules":["B-4"],"data":{}}]}
emergency_qualified：報價單是否符合可豁免公開招標的緊急修繕（含時限、特別規定效力）；非緊急案件填 null。"""


async def handle(task: dict, kg: KGClient | None = None) -> dict:
    kg = kg or KGClient()
    quote_nos = task.get("quote_nos") or quote_numbers(task.get("question", ""))
    quotes, ctx, rb = await gather(kg, quote_nos, LEGAL_QUERIES, task.get("mode", "hybrid"), task.get("top_k", 5))
    if use_llm():
        out = await chat_json(LLM_SYSTEM, f"【問題】{task.get('question')}\n\n【參考資料】\n{format_context(ctx)}")
        out.setdefault("findings", []); out.setdefault("obligations", [])
    else:
        out = legal_assess(quotes, rb)
    out["evidence"] = evidence(ctx)
    out["mcp_calls"] = kg.calls
    return out


CARD = agent_card(
    "legal-agent", "法務代理：解釋採購法規、判斷緊急修繕豁免要件與特別規定效力", "http://legal-agent:8201",
    [{"id": "legal-review", "name": "法規適用審查", "description": "輸入報價單號，回傳豁免資格與附帶義務",
      "tags": ["procurement", "legal"], "examples": ["Q-2025-0601 可否免公開招標？"]}],
)


def build_app(kg_factory: Callable[[], KGClient] = KGClient):
    """每個 A2A 任務建立新的 KGClient（獨立的 MCP 呼叫紀錄）。"""
    return create_a2a_app(CARD, lambda t: handle(t, kg_factory()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8201)
    uvicorn.run(build_app(), host="0.0.0.0", port=ap.parse_args().port)
