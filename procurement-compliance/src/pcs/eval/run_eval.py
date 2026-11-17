"""消融實驗：比較「單一 LLM + 向量 RAG」與「A2A + MCP + LightRAG」。

2×2 設計（另可加 local/global 模式）：
                     向量檢索 (naive)         知識圖譜 (hybrid)
  單一 LLM           single-naive【基線】     single-hybrid
  A2A + MCP 多代理   a2a-naive                a2a-hybrid【完整系統】

指標
  * verdict_accuracy        判斷結論正確率
  * conflict_detection_rate 跨文件衝突檢出率：在 has_conflict 案例中，結論正確且引用條文涵蓋 expected_rules
  * rule_recall             引用條文對 expected_rules 的召回率（平均）
  * doc_recall              檢索證據涵蓋 required_docs 的比例（平均）
  * hallucination_rate      幻覺率 = 無依據引用數 / 總引用數；無依據 = 條文不存在於語料，或不在該系統檢索到的證據中
  * hallucinated_cases      至少出現一次無依據引用的案例比例

用法：python -m pcs.eval.run_eval [--systems single-naive,a2a-hybrid,...] [--top-k 5] [--repeats N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time
from pathlib import Path

from ..config import settings
from ..corpus import load_corpus
from ..system import build_coordinator
from .baseline import SingleAgentRAG

DEFAULT_SYSTEMS = ["single-naive", "single-hybrid", "a2a-naive", "a2a-hybrid"]


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def corpus_rules() -> set[str]:
    rules = set()
    for d in load_corpus(settings.corpus_dir):
        rules |= set(re.findall(r"【規則\s*([A-Z]-\d+)】", d.text))
    return rules


def score_case(case: dict, out: dict, valid_rules: set[str]) -> dict:
    cited = set(out.get("cited_rules", []))
    evid = set(out.get("evidence_rules", []))
    expected = set(case["expected_rules"])
    unsupported = sorted(r for r in cited if r not in valid_rules or r not in evid)
    correct = out["verdict"] == case["expected_verdict"]
    return {
        "id": case["id"],
        "expected": case["expected_verdict"],
        "verdict": out["verdict"],
        "correct": correct,
        "has_conflict": case["has_conflict"],
        "conflict_detected": correct and expected <= cited,
        "rule_recall": len(expected & cited) / len(expected),
        "doc_recall": len(set(case["required_docs"]) & set(out.get("evidence_docs", []))) / len(case["required_docs"]),
        "cited": sorted(cited),
        "unsupported": unsupported,
        "n_cited": len(cited),
    }


def aggregate(rows: list[dict]) -> dict:
    conf = [r for r in rows if r["has_conflict"]]
    n_cited = sum(r["n_cited"] for r in rows)
    return {
        "n": len(rows),
        "verdict_accuracy": sum(r["correct"] for r in rows) / len(rows),
        "conflict_detection_rate": sum(r["conflict_detected"] for r in conf) / len(conf) if conf else None,
        "rule_recall": sum(r["rule_recall"] for r in rows) / len(rows),
        "doc_recall": sum(r["doc_recall"] for r in rows) / len(rows),
        "hallucination_rate": sum(len(r["unsupported"]) for r in rows) / n_cited if n_cited else 0.0,
        "hallucinated_cases": sum(bool(r["unsupported"]) for r in rows) / len(rows),
        "avg_latency_s": sum(r["latency_s"] for r in rows) / len(rows),
    }


async def run_system(name: str, cases: list[dict], repeats: int, top_k: int) -> list[dict]:
    valid = corpus_rules()
    rows = []
    arch, mode = name.split("-", 1)
    if arch == "single":
        answer = SingleAgentRAG(mode, top_k).answer
    else:
        coord = build_coordinator("local")

        async def answer(q):
            return await coord.handle({"question": q, "mode": mode, "top_k": top_k})

    for _ in range(repeats):
        for case in cases:
            t0 = time.perf_counter()
            try:
                out = await answer(case["question"])
            except Exception as e:  # noqa: BLE001
                out = {"verdict": "ERROR", "cited_rules": [], "error": str(e)}
            row = score_case(case, out, valid)
            row["latency_s"] = time.perf_counter() - t0
            rows.append(row)
    return rows


def to_markdown(summary: dict[str, dict], details: dict[str, list[dict]], top_k: int) -> str:
    pct = lambda v: "—" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    lines = [
        f"# 消融實驗結果（KG 後端：{settings.kg_backend}，推理器：{settings.reasoner}，top_k={top_k}）\n",
        "| 系統 | 結論正確率 | 跨文件衝突檢出率 | 條文召回 | 文件召回 | 幻覺率 | 幻覺案例比例 | 平均延遲(s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, s in summary.items():
        lines.append(f"| {name} | {pct(s['verdict_accuracy'])} | {pct(s['conflict_detection_rate'])} | "
                     f"{pct(s['rule_recall'])} | {pct(s['doc_recall'])} | {pct(s['hallucination_rate'])} | "
                     f"{pct(s['hallucinated_cases'])} | {s['avg_latency_s']:.2f} |")
    lines.append("\n## 逐案結果\n")
    lines.append("| 案例 | 預期 | " + " | ".join(details) + " |")
    lines.append("|---|---|" + "---|" * len(details))
    ids = list(dict.fromkeys(r["id"] for r in next(iter(details.values()))))
    for cid in ids:
        cells = []
        for rows in details.values():
            r = next(x for x in rows if x["id"] == cid)
            cells.append(("✅ " if r["correct"] else "❌ ") + r["verdict"])
        exp = next(r for r in next(iter(details.values())) if r["id"] == cid)["expected"]
        lines.append(f"| {cid} | {exp} | " + " | ".join(cells) + " |")
    if settings.reasoner == "rule":
        lines.append("\n> 註：rule 推理器為確定性規則引擎，幻覺率恆為 0；此模式量測的是「檢索 + 任務拆解」的貢獻。"
                     "正式論文數據請以 `PCS_REASONER=llm`（本機 Ollama）重跑並設定 --repeats。")
    return "\n".join(lines) + "\n"


async def amain(systems: list[str], repeats: int, top_k: int) -> dict:
    cases = load_cases(settings.testset_path)
    details = {s: await run_system(s, cases, repeats, top_k) for s in systems}
    summary = {s: aggregate(rows) for s, rows in details.items()}
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{settings.kg_backend}-{settings.reasoner}"
    (settings.results_dir / f"eval_{tag}.json").write_text(
        json.dumps({"summary": summary, "details": details}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = to_markdown(summary, details, top_k)
    (settings.results_dir / f"eval_{tag}.md").write_text(md, encoding="utf-8")
    print(md)
    return summary


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default=",".join(DEFAULT_SYSTEMS),
                    help="逗號分隔：{single,a2a}-{naive,local,global,hybrid,mix}")
    ap.add_argument("--top-k", type=int, default=5, help="每次檢索取回的文字塊數（所有系統一致）")
    ap.add_argument("--repeats", type=int, default=1, help="LLM 模式建議 ≥3 以估計變異")
    args = ap.parse_args()
    asyncio.run(amain(args.systems.split(","), args.repeats, args.top_k))


if __name__ == "__main__":
    main()
