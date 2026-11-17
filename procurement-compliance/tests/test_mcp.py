import asyncio

from pcs.mcp_client import KGClient


def test_mcp_tools_via_protocol():
    async def run():
        kg = KGClient()
        chunks = await kg.query("緊急修繕 特別規定", "hybrid", 5)
        quote = await kg.find_quote("Q-2025-0803")
        return kg, chunks, quote

    kg, chunks, quote = asyncio.run(run())
    assert any(c["doc_id"] == "B" for c in chunks)
    assert quote["doc_id"] == "E"
    assert [c["tool"] for c in kg.calls] == ["kg_query", "kg_find_quote"]
