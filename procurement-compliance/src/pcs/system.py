"""組裝整個多代理系統。

* local ：三個代理以 FastAPI app 在同進程運行，A2A 走 httpx.ASGITransport（仍是完整 HTTP + JSON-RPC 流程），
          MCP 走 in-memory transport（未設定 PCS_MCP_URL 時）。適合測試、評估與無 Docker 的 Demo。
* remote：連線至 Docker Compose 中的獨立服務（PCS_LEGAL_URL / PCS_FINANCE_URL；代理自行連 PCS_MCP_URL）。
"""

from __future__ import annotations

import httpx

from .agents import finance, legal
from .agents.a2a import A2AClient
from .agents.coordinator import Coordinator
from .config import settings
from .mcp_client import KGClient


def build_coordinator(deployment: str = "local") -> Coordinator:
    if deployment == "remote":
        return Coordinator(A2AClient(settings.legal_url), A2AClient(settings.finance_url))
    target = KGClient().target  # 兩個代理共用同一個 MCP Server（in-memory 或 HTTP URL）

    def factory() -> KGClient:
        return KGClient(target)

    return Coordinator(
        A2AClient("http://legal-agent", transport=httpx.ASGITransport(app=legal.build_app(factory))),
        A2AClient("http://finance-agent", transport=httpx.ASGITransport(app=finance.build_app(factory))),
    )
