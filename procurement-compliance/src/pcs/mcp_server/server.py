"""LightRAG 知識圖譜查詢的 MCP Server。

工具：
  * kg_query(query, mode, top_k)  — 依 LightRAG 模式（naive/local/global/hybrid/mix）檢索
  * kg_get_document(doc_id)        — 取得原始文件全文
  * kg_find_quote(quote_no)        — 以報價單號找報價單
  * kg_stats()                     — 圖譜統計與跨文件關係

啟動：python -m pcs.mcp_server.server --transport streamable-http --port 8100
      （Claude Desktop / 其他 MCP Client 可用 --transport stdio）
"""

from __future__ import annotations

import argparse
import inspect
import json

from mcp.server.mcpserver import MCPServer

from ..kg import MODES, get_backend


def build_server(backend=None) -> MCPServer:
    kg = backend or get_backend()
    server = MCPServer(
        name="lightrag-kg",
        instructions="採購法規知識圖譜。先用 kg_query(mode='hybrid') 找相關條文，再用 kg_find_quote 取報價單。",
    )

    @server.tool()
    async def kg_query(query: str, mode: str = "hybrid", top_k: int = 8) -> str:
        """在採購法規知識圖譜中檢索與 query 相關的條文/文件片段。mode: naive|local|global|hybrid|mix。"""
        if mode not in MODES:
            raise ValueError(f"mode 必須為 {MODES}")
        res = kg.aquery(query, mode, top_k) if hasattr(kg, "aquery") else kg.query(query, mode, top_k)
        if inspect.isawaitable(res):
            res = await res
        return json.dumps(res, ensure_ascii=False)

    @server.tool()
    def kg_get_document(doc_id: str) -> str:
        """取得指定文件（例如 'A'）全文。"""
        return json.dumps(kg.get_document(doc_id), ensure_ascii=False)

    @server.tool()
    def kg_find_quote(quote_no: str) -> str:
        """以報價單號（例如 'Q-2025-0601'）取得報價單全文。"""
        return json.dumps(kg.find_quote(quote_no), ensure_ascii=False)

    @server.tool()
    def kg_stats() -> str:
        """回傳知識圖譜統計與跨文件關係。"""
        return json.dumps({"stats": kg.stats(), "cross_document_relations": kg.relations()}, ensure_ascii=False)

    return server


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", default="streamable-http", choices=["stdio", "sse", "streamable-http"])
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8100)
    args = ap.parse_args()
    server = build_server()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run(args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
