"""建庫：python -m pcs.kg.build   （PCS_KG_BACKEND=lightrag 時以 Ollama 抽取實體/關係寫入 rag_storage/）

並驗證 hybrid 模式能否將文件 A 與 B 串連（第 3–5 週里程碑）。
"""

from __future__ import annotations

import asyncio
import json

from ..config import settings
from . import get_backend

PROBE = "60 萬緊急修繕是否需要公開招標？緊急修繕要點與採購作業規定的關係為何？"


async def amain() -> None:
    kg = get_backend()
    if settings.kg_backend == "lightrag":
        await kg.build()
        ctx = (await kg.aquery(PROBE, "hybrid", 10))[0]["text"]
        linked = all(k in ctx for k in ("公開招標", "緊急修繕")) and ("A-5" in ctx or "特別規定" in ctx)
    else:
        ctx_chunks = kg.query(PROBE, "hybrid", 8)
        docs = {c["doc_id"] for c in ctx_chunks}
        linked = {"A", "B"} <= docs
        print(json.dumps(kg.stats(), ensure_ascii=False))
        print("跨文件關係（前 10）：")
        for r in kg.relations()[:10]:
            print(f"  {r['entity']}: {'、'.join(r['documents'])}")
    print(f"\nhybrid 模式串連文件 A 與 B：{'✅ 通過' if linked else '❌ 未通過'}")


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
