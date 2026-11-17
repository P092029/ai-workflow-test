"""命令列 Demo：python -m pcs.demo "報價單 Q-2025-0601 能否不經公開招標，直接向廠商採購？" """

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from .system import build_coordinator


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default="報價單 Q-2025-0601 能否不經公開招標，直接向廠商採購？")
    ap.add_argument("--deployment", choices=["local", "remote"], default="local")
    ap.add_argument("--mode", default="hybrid")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = asyncio.run(build_coordinator(args.deployment).handle({"question": args.question, "mode": args.mode}))
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"問題：{args.question}\n")
    print("A2A 任務流程：", " → ".join(f"{t['agent']}:{t['state']}" for t in out["a2a_trace"]))
    print(f"MCP 呼叫次數：{out['mcp_calls']}；引用文件：{', '.join(out['evidence_docs'])}\n")
    for f in out["findings"]:
        print(f"  [{f['agent']}] {f['claim']}  ({', '.join(f['rules']) or '無條文'})")
    print("\n衝突分析：")
    for c in out["conflicts"] or ["（無）"]:
        print(f"  - {c}")
    print(f"\n結論：{out['verdict']}；引用條文：{', '.join(out['cited_rules'])}")


if __name__ == "__main__":
    main()
