"""代理端的 MCP 客戶端：所有知識查詢一律經由 MCP 協定呼叫 LightRAG MCP Server。

* 設定 PCS_MCP_URL → 透過 Streamable HTTP 連到獨立的 MCP Server（Docker 部署）
* 未設定 → 以記憶體內傳輸（in-memory transport）連到同進程的 MCP Server（測試/單機 Demo）
"""

from __future__ import annotations

import json
from typing import Any

from mcp import Client

from .config import settings


class KGClient:
    def __init__(self, target: Any | None = None):
        if target is None:
            if settings.mcp_url:
                target = settings.mcp_url
            else:
                from .mcp_server.server import build_server

                target = build_server()
        self.target = target
        self.calls: list[dict] = []  # 供評估與 Demo 顯示的呼叫紀錄

    async def _call(self, tool: str, **arguments) -> Any:
        async with Client(self.target, raise_exceptions=True) as client:
            res = await client.call_tool(tool, arguments)
        if getattr(res, "isError", False) or getattr(res, "is_error", False):
            raise RuntimeError(f"MCP 工具 {tool} 失敗：{res}")
        text = res.content[0].text
        self.calls.append({"tool": tool, "arguments": arguments})
        return json.loads(text)

    async def query(self, query: str, mode: str = "hybrid", top_k: int = 8) -> list[dict]:
        return await self._call("kg_query", query=query, mode=mode, top_k=top_k)

    async def get_document(self, doc_id: str) -> dict | None:
        return await self._call("kg_get_document", doc_id=doc_id)

    async def find_quote(self, quote_no: str) -> dict | None:
        return await self._call("kg_find_quote", quote_no=quote_no)
