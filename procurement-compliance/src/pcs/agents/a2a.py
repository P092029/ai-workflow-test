"""精簡版 A2A（Agent2Agent）協定實作：Agent Card + JSON-RPC 2.0 任務派發與狀態輪詢。

對應 A2A 規格的子集：
  * GET  /.well-known/agent-card.json（亦提供舊路徑 agent.json）— 代理能力描述
  * POST /  method=message/send  — 建立任務；configuration.blocking=false 時立即回傳 submitted
  * POST /  method=tasks/get     — 輪詢任務狀態（submitted → working → completed / failed）
  * POST /  method=tasks/cancel  — 取消任務
任務生命週期與 Artifact（parts.kind="data"）格式與官方規格一致，可再替換為官方 a2a-sdk。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

Handler = Callable[[dict], Awaitable[dict]]
TERMINAL = {"completed", "failed", "canceled", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def agent_card(name: str, description: str, url: str, skills: list[dict]) -> dict:
    return {
        "protocolVersion": "0.3.0",
        "name": name,
        "description": description,
        "url": url,
        "version": "0.1.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": skills,
    }


def create_a2a_app(card: dict, handler: Handler) -> FastAPI:
    app = FastAPI(title=card["name"])
    tasks: dict[str, dict] = {}
    runners: dict[str, asyncio.Task] = {}

    @app.get("/.well-known/agent-card.json")
    @app.get("/.well-known/agent.json")
    async def get_card():
        return card

    @app.get("/healthz")
    async def health():
        return {"ok": True, "tasks": len(tasks)}

    async def _run(task: dict, payload: dict) -> None:
        task["status"] = {"state": "working", "timestamp": _now()}
        try:
            result = await handler(payload)
            task["artifacts"] = [{"artifactId": str(uuid.uuid4()), "name": "result",
                                  "parts": [{"kind": "data", "data": result}]}]
            task["status"] = {"state": "completed", "timestamp": _now()}
        except asyncio.CancelledError:
            task["status"] = {"state": "canceled", "timestamp": _now()}
        except Exception as e:  # noqa: BLE001 — 錯誤回報給呼叫端
            task["status"] = {"state": "failed", "timestamp": _now(),
                              "message": {"role": "agent", "kind": "message", "messageId": str(uuid.uuid4()),
                                          "parts": [{"kind": "text", "text": f"{type(e).__name__}: {e}"}]}}

    def _err(rid, code, msg):
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}})

    @app.post("/")
    async def rpc(request: Request):
        body = await request.json()
        rid, method, params = body.get("id"), body.get("method"), body.get("params") or {}
        if method == "message/send":
            msg = params.get("message") or {}
            payload: dict[str, Any] = {}
            for part in msg.get("parts", []):
                if part.get("kind") == "data":
                    payload.update(part.get("data") or {})
                elif part.get("kind") == "text":
                    payload.setdefault("text", part.get("text"))
            task = {"id": str(uuid.uuid4()), "contextId": msg.get("contextId") or str(uuid.uuid4()),
                    "kind": "task", "status": {"state": "submitted", "timestamp": _now()},
                    "history": [msg], "artifacts": []}
            tasks[task["id"]] = task
            runner = asyncio.create_task(_run(task, payload))
            runners[task["id"]] = runner
            if (params.get("configuration") or {}).get("blocking", False):
                await runner
            return {"jsonrpc": "2.0", "id": rid, "result": task}
        if method == "tasks/get":
            task = tasks.get(params.get("id"))
            return _err(rid, -32001, "Task not found") if task is None else {"jsonrpc": "2.0", "id": rid, "result": task}
        if method == "tasks/cancel":
            task = tasks.get(params.get("id"))
            if task is None:
                return _err(rid, -32001, "Task not found")
            if task["status"]["state"] in TERMINAL:
                return _err(rid, -32002, "Task cannot be canceled")
            runners[task["id"]].cancel()
            return {"jsonrpc": "2.0", "id": rid, "result": task}
        return _err(rid, -32601, f"Method not found: {method}")

    return app


class A2AClient:
    """派發任務並輪詢狀態。transport 可注入 httpx.ASGITransport 以進程內測試。"""

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 600):
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, transport=self.transport, timeout=self.timeout)

    async def _rpc(self, method: str, params: dict) -> dict:
        async with self._client() as c:
            r = await c.post("/", json={"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params})
            r.raise_for_status()
            body = r.json()
        if "error" in body:
            raise RuntimeError(f"A2A {method} 錯誤：{body['error']}")
        return body["result"]

    async def get_card(self) -> dict:
        async with self._client() as c:
            r = await c.get("/.well-known/agent-card.json")
            r.raise_for_status()
            return r.json()

    async def send(self, data: dict) -> dict:
        msg = {"role": "user", "kind": "message", "messageId": str(uuid.uuid4()),
               "parts": [{"kind": "data", "data": data}]}
        return await self._rpc("message/send", {"message": msg, "configuration": {"blocking": False}})

    async def get_task(self, task_id: str) -> dict:
        return await self._rpc("tasks/get", {"id": task_id})

    async def run(self, data: dict, poll_interval: float = 0.2, on_status: Callable[[dict], None] | None = None) -> dict:
        """send + 輪詢直到終止狀態，回傳第一個 data artifact。"""
        task = await self.send(data)
        deadline = time.monotonic() + self.timeout
        last = None
        while task["status"]["state"] not in TERMINAL:
            if time.monotonic() > deadline:
                raise TimeoutError(f"A2A 任務 {task['id']} 逾時")
            await asyncio.sleep(poll_interval)
            task = await self.get_task(task["id"])
            if on_status and task["status"]["state"] != last:
                on_status(task)
                last = task["status"]["state"]
        if task["status"]["state"] != "completed":
            raise RuntimeError(f"A2A 任務失敗：{task['status']}")
        return task["artifacts"][0]["parts"][0]["data"]
