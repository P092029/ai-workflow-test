"""Ollama 本機 LLM 介面（PCS_REASONER=llm 時使用）。"""

from __future__ import annotations

import json
import re

import httpx

from .config import settings

VERDICTS = ("COMPLIANT", "CONDITIONAL", "VIOLATION", "UNKNOWN")


def ollama_available() -> bool:
    try:
        return httpx.get(f"{settings.ollama_host}/api/tags", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


async def chat_json(system: str, user: str, *, model: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{settings.ollama_host}/api/chat", json={
            "model": model or settings.llm_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": "json", "stream": False, "options": {"temperature": 0},
        })
        r.raise_for_status()
        content = r.json()["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0)) if m else {"raw": content}


def format_context(contexts: list[dict]) -> str:
    return "\n\n".join(f"[來源 {c['doc_id']} | {c.get('doc_title','')}]\n{c['text']}" for c in contexts)


JUDGE_SYSTEM = """你是機關採購稽核人員。只能依據使用者提供的【參考資料】判斷，不得引用參考資料以外的條文。
請輸出 JSON：{"verdict": "COMPLIANT|CONDITIONAL|VIOLATION|UNKNOWN",
"cited_rules": ["A-3", ...], "conflicts": ["條文衝突說明"...], "reasoning": "簡短推理"}
COMPLIANT=可直接不經招標採購；CONDITIONAL=可免招標但須履行附帶義務；VIOLATION=必須公開招標；UNKNOWN=資料不足。"""


def normalize(ans: dict) -> dict:
    v = str(ans.get("verdict", "UNKNOWN")).upper()
    rules = ans.get("cited_rules") or []
    return {"verdict": v if v in VERDICTS else "UNKNOWN",
            "cited_rules": sorted({str(r).strip() for r in rules if r}),
            "conflicts": ans.get("conflicts") or [], "reasoning": ans.get("reasoning", "")}
