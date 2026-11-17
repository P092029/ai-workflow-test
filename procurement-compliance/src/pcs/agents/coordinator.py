"""Coordinator 代理：拆解任務 → 以 A2A 平行派發給法務/財務代理 → 輪詢狀態 → 彙整衝突與結論。"""

from __future__ import annotations

import argparse
import asyncio

import uvicorn

from ..config import settings
from ..reasoning import combine
from .a2a import A2AClient, agent_card, create_a2a_app
from .common import quote_numbers


class Coordinator:
    def __init__(self, legal: A2AClient | None = None, finance: A2AClient | None = None):
        self.legal = legal or A2AClient(settings.legal_url)
        self.finance = finance or A2AClient(settings.finance_url)

    async def handle(self, task: dict) -> dict:
        question = task["question"]
        sub = {"question": question, "quote_nos": quote_numbers(question), "mode": task.get("mode", "hybrid"),
               "top_k": task.get("top_k", 5)}
        trace: list[dict] = []

        def log(agent):
            return lambda t: trace.append({"agent": agent, "task_id": t["id"], "state": t["status"]["state"]})

        legal, finance = await asyncio.gather(
            self.legal.run(sub, on_status=log("legal")),
            self.finance.run(sub, on_status=log("finance")),
        )
        decision = combine(finance, legal)
        evidence_rules = sorted({r for part in (legal, finance) for e in part["evidence"] for r in e.get("rules", [])})
        return {
            **decision,
            "findings": legal.get("findings", []) + legal.get("obligations", []) + finance.get("findings", []),
            "total_amount": finance.get("total_amount"),
            "evidence_rules": evidence_rules,
            "evidence_docs": sorted({e["doc_id"] for part in (legal, finance) for e in part["evidence"] if "doc_id" in e}),
            "mcp_calls": len(legal.get("mcp_calls", [])) + len(finance.get("mcp_calls", [])),
            "a2a_trace": trace,
        }


CARD = agent_card(
    "coordinator", "採購合規協調者：派發法務/財務審查並彙整跨文件衝突", "http://coordinator:8200",
    [{"id": "compliance-check", "name": "採購合規檢核", "description": "輸入含報價單號的問題，回傳合規判斷",
      "tags": ["procurement", "compliance"], "examples": ["報價單 Q-2025-0601 能否不經公開招標，直接向廠商採購？"]}],
)


def build_app(coordinator: Coordinator | None = None):
    c = coordinator or Coordinator()
    return create_a2a_app(CARD, c.handle)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8200)
    uvicorn.run(build_app(), host="0.0.0.0", port=ap.parse_args().port)
