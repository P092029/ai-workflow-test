import asyncio

import httpx
import pytest

from pcs.agents.a2a import A2AClient, create_a2a_app, agent_card


def _client(handler):
    app = create_a2a_app(agent_card("t", "test", "http://t", []), handler)
    return A2AClient("http://t", transport=httpx.ASGITransport(app=app), timeout=5)


def test_task_lifecycle_and_polling():
    async def handler(data):
        await asyncio.sleep(0.3)
        return {"echo": data["x"]}

    async def run():
        c = _client(handler)
        card = await c.get_card()
        states = []
        result = await c.run({"x": 1}, poll_interval=0.05, on_status=lambda t: states.append(t["status"]["state"]))
        return card, states, result

    card, states, result = asyncio.run(run())
    assert card["name"] == "t"
    assert result == {"echo": 1}
    assert states[0] == "working" and states[-1] == "completed"


def test_failed_task_raises():
    async def handler(data):
        raise ValueError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(_client(handler).run({}, poll_interval=0.05))
