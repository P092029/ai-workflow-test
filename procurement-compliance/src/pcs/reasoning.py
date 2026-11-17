"""確定性規則推理器（PCS_REASONER=rule）。

重點：推理器「只能使用檢索到的條文」。若檢索漏掉文件 B，推理器就不知道緊急修繕可豁免，
因此檢索品質（向量 RAG vs. 圖譜 hybrid）會直接反映在判斷正確率上——這正是消融實驗要量測的。
LLM 模式（PCS_REASONER=llm）則把同樣的上下文交給本機 LLM，可量測幻覺率。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .corpus import Quote

_WAN = r"新臺幣\s*([\d,]+)\s*萬元"


def _num(s: str) -> int:
    return int(s.replace(",", ""))


@dataclass
class RuleBook:
    """從檢索上下文中解析出的可執行條文參數；值為 None 代表上下文中沒有該條文。"""

    small_purchase_cap: int | None = None  # A-2
    tender_threshold: int | None = None  # A-3
    split_window_days: int | None = None  # A-4
    special_rule_allowed: bool = False  # A-5 + B-1：B 為 A 的特別規定
    emergency_cap: int | None = None  # B-3
    emergency_quote_days: int | None = None  # B-4
    post_report_days: int | None = None  # B-5
    seen: dict[str, str] = field(default_factory=dict)  # rule_id -> 條文

    @classmethod
    def from_contexts(cls, contexts: list[dict]) -> "RuleBook":
        rb = cls()
        text = "\n".join(c["text"] for c in contexts)
        for m in re.finditer(r"【規則\s*([A-Z]-\d+)】([^\n【]*)", text):
            rid, body = m.group(1), m.group(2)
            rb.seen[rid] = body.strip()
            if "未逾" in body and "小額採購" in body and (n := re.search(_WAN, body)):
                rb.small_purchase_cap = _num(n.group(1)) * 10_000
            elif "逾" in body and "應辦理公開招標" in body and (n := re.search(_WAN, body)):
                rb.tender_threshold = _num(n.group(1)) * 10_000
            elif "分批" in body and (n := re.search(r"(\d+)\s*日內", body)):
                rb.split_window_days = int(n.group(1))
            elif "緊急修繕" in body and "以下" in body and (n := re.search(_WAN, body)):
                rb.emergency_cap = _num(n.group(1)) * 10_000
            elif "報價日期" in body and (n := re.search(r"(\d+)\s*日內", body)):
                rb.emergency_quote_days = int(n.group(1))
            elif "事後報備" in body and (n := re.search(r"(\d+)\s*日內", body)):
                rb.post_report_days = int(n.group(1))
        # A-5 允許特別規定排除 A-3；B-1 宣告自己就是該特別規定 → 兩條都在才能串起來
        rb.special_rule_allowed = "A-5" in rb.seen and "B-1" in rb.seen
        return rb


@dataclass
class Finding:
    agent: str
    claim: str
    rules: list[str]
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"agent": self.agent, "claim": self.claim, "rules": self.rules, "data": self.data}


# ---------------- 財務代理：金額、合併計算、門檻 ----------------
def finance_assess(quotes: list[Quote], related: list[Quote], rb: RuleBook) -> dict:
    findings: list[Finding] = []
    total = sum(q.amount for q in quotes)
    grouped = list(quotes)
    if rb.split_window_days is not None:
        for q in quotes:
            for r in related:
                if r.quote_no in {g.quote_no for g in grouped}:
                    continue
                if r.vendor == q.vendor and abs((r.quote_date - q.quote_date).days) <= rb.split_window_days:
                    grouped.append(r)
        if len({g.vendor for g in grouped}) == 1 and len(grouped) > 1:
            total = sum(g.amount for g in grouped)
            findings.append(Finding("finance", f"同一廠商 {rb.split_window_days} 日內 {len(grouped)} 筆報價應合併計算，合計 {total:,} 元", ["A-4"],
                                    {"merged_quotes": [g.quote_no for g in grouped]}))
    elif len(quotes) > 1 and len({q.vendor for q in quotes}) == 1:
        # 沒檢索到 A-4，就只能看到個別金額
        total = max(q.amount for q in quotes)

    exceeds = None
    if rb.tender_threshold is not None:
        exceeds = total > rb.tender_threshold
        findings.append(Finding("finance", f"採購金額 {total:,} 元{'逾' if exceeds else '未逾'}公開招標門檻 {rb.tender_threshold:,} 元", ["A-3"]))
    elif rb.small_purchase_cap is not None:
        exceeds = total > rb.small_purchase_cap
        findings.append(Finding("finance", f"採購金額 {total:,} 元{'逾' if exceeds else '未逾'}小額採購上限 {rb.small_purchase_cap:,} 元", ["A-2"]))
    if exceeds is False and rb.small_purchase_cap is not None:
        findings.append(Finding("finance", "符合小額採購，得逕洽廠商", ["A-2"]))

    within_cap = None
    if rb.emergency_cap is not None and any(q.is_emergency for q in quotes):
        within_cap = total <= rb.emergency_cap
        findings.append(Finding("finance", f"金額{'未超過' if within_cap else '超過'}緊急修繕豁免上限 {rb.emergency_cap:,} 元", ["B-3"]))
    return {"total_amount": total, "exceeds_tender_threshold": exceeds,
            "within_emergency_cap": within_cap, "findings": [f.to_dict() for f in findings]}


# ---------------- 法務代理：緊急修繕資格、特別規定、報備義務 ----------------
def legal_assess(quotes: list[Quote], rb: RuleBook) -> dict:
    findings: list[Finding] = []
    emergency_ok = None
    if any(q.is_emergency for q in quotes):
        if rb.emergency_cap is None:
            findings.append(Finding("legal", "報價單標示緊急修繕，但未檢索到任何豁免招標之依據", []))
            emergency_ok = False
        else:
            emergency_ok = True
            for q in quotes:
                if rb.emergency_quote_days is not None and q.incident_date:
                    gap = (q.quote_date - q.incident_date).days
                    if gap > rb.emergency_quote_days:
                        emergency_ok = False
                        findings.append(Finding("legal", f"{q.quote_no} 報價日距事故 {gap} 日，逾 {rb.emergency_quote_days} 日，不視為緊急修繕", ["B-4"]))
                    else:
                        findings.append(Finding("legal", f"{q.quote_no} 報價日距事故 {gap} 日，符合 {rb.emergency_quote_days} 日內要求", ["B-4"]))
            if emergency_ok and not rb.special_rule_allowed:
                findings.append(Finding("legal", "未能確認緊急修繕要點具排除公開招標之效力（缺 A-5/B-1 連結）", []))
                emergency_ok = False
            elif emergency_ok:
                findings.append(Finding("legal", "緊急修繕要點為採購作業規定之特別規定，可排除 A-3", ["A-5", "B-1"]))
    obligations = []
    if emergency_ok and rb.post_report_days is not None:
        obligations.append(Finding("legal", f"須於修繕完成後 {rb.post_report_days} 日內向主計及政風單位事後報備", ["B-5"]).to_dict())
    return {"emergency_qualified": emergency_ok, "obligations": obligations,
            "findings": [f.to_dict() for f in findings]}


# ---------------- 協調者：彙整判斷 ----------------
def combine(finance: dict, legal: dict) -> dict:
    exceeds = finance.get("exceeds_tender_threshold")
    conflicts = []
    if exceeds is None:
        verdict = "UNKNOWN"
    elif not exceeds:
        verdict = "COMPLIANT"
    elif legal.get("emergency_qualified") and finance.get("within_emergency_cap"):
        verdict = "CONDITIONAL" if legal.get("obligations") else "COMPLIANT"
        conflicts.append("A-3 要求公開招標 vs. B-3 緊急修繕得免招標 → 依 A-5/B-1 特別規定優先，適用 B-3")
    else:
        verdict = "VIOLATION"
        if legal.get("emergency_qualified") is not None or finance.get("within_emergency_cap") is not None:
            conflicts.append("A-3 要求公開招標 vs. B-3 豁免主張 → 豁免要件不符，回歸 A-3")
    if any("A-4" in f["rules"] for f in finance.get("findings", [])):
        conflicts.append("個別報價看似小額採購 vs. A-4 合併計算 → 合計逾門檻")
    rules = sorted({r for part in (finance, legal) for f in part.get("findings", []) + part.get("obligations", []) for r in f["rules"]})
    return {"verdict": verdict, "cited_rules": rules, "conflicts": conflicts}
