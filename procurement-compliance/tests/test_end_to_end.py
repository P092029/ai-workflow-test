import asyncio
import json

import pytest

from pcs.config import settings
from pcs.eval.baseline import SingleAgentRAG
from pcs.system import build_coordinator

CASES = [json.loads(l) for l in settings.testset_path.read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_full_system_answers_test_bank(case):
    out = asyncio.run(build_coordinator().handle({"question": case["question"], "mode": "hybrid"}))
    assert out["verdict"] == case["expected_verdict"]
    assert set(case["expected_rules"]) <= set(out["cited_rules"])
    assert set(out["cited_rules"]) <= set(out["evidence_rules"])  # 不引用未檢索到的條文
    if case["has_conflict"]:
        assert out["conflicts"]


def test_core_case_t01_baseline_misses_exemption():
    """核心案例：單一代理一次檢索無法同時拿到 A、B 的關鍵條文。"""
    out = asyncio.run(SingleAgentRAG("naive", 5).answer(CASES[0]["question"]))
    assert out["verdict"] != "CONDITIONAL"
