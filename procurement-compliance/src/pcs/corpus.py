"""文件載入、切塊與報價單欄位解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

RULE_RE = re.compile(r"【規則\s*([A-Z]-\d+)】")
RULE_REF_RE = re.compile(r"(?<![A-Za-z0-9-])([A-Z]-\d{1,2})(?![0-9-])")
QUOTE_NO_RE = re.compile(r"Q-\d{4}-\d{4}")


@dataclass
class Document:
    doc_id: str  # 檔名前綴字母，例如 "A"
    title: str
    path: Path
    text: str

    @property
    def is_quote(self) -> bool:
        return "報價單號" in self.text


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    text: str
    rule_id: str | None = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "rule_id": self.rule_id,
            "text": self.text,
        }


def load_corpus(corpus_dir: Path) -> list[Document]:
    docs = []
    for path in sorted(Path(corpus_dir).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        first = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
        docs.append(Document(doc_id=path.stem.split("_", 1)[0], title=first, path=path, text=text))
    return docs


def chunk_document(doc: Document) -> list[Chunk]:
    """規章依【規則】條文切塊；報價單整份為一塊。"""
    if doc.is_quote:
        return [Chunk(f"{doc.doc_id}#0", doc.doc_id, doc.title, doc.text.strip())]
    chunks = []
    for i, para in enumerate(p.strip() for p in doc.text.split("\n\n")):
        if not para or para.startswith("#"):
            continue
        m = RULE_RE.search(para)
        chunks.append(
            Chunk(f"{doc.doc_id}#{i}", doc.doc_id, doc.title, para, rule_id=m.group(1) if m else None)
        )
    return chunks


@dataclass
class Quote:
    quote_no: str
    vendor: str
    subject: str
    is_emergency: bool
    amount: int
    quote_date: date
    incident_date: date | None
    doc_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "quote_no": self.quote_no,
            "vendor": self.vendor,
            "subject": self.subject,
            "is_emergency": self.is_emergency,
            "amount": self.amount,
            "quote_date": self.quote_date.isoformat(),
            "incident_date": self.incident_date.isoformat() if self.incident_date else None,
            "doc_id": self.doc_id,
        }


def _field(text: str, name: str) -> str | None:
    m = re.search(rf"{name}[：:]\s*(.+)", text)
    return m.group(1).strip() if m else None


def parse_quote(text: str, doc_id: str | None = None) -> Quote | None:
    no = _field(text, "報價單號")
    amount_s = _field(text, "報價金額")
    qdate = _field(text, "報價日期")
    if not (no and amount_s and qdate):
        return None
    amount = int(re.sub(r"[^\d]", "", amount_s.split("元")[0]))
    inc = _field(text, "事故日期")
    return Quote(
        quote_no=no,
        vendor=_field(text, "廠商") or "",
        subject=_field(text, "標的") or "",
        is_emergency=(_field(text, "是否緊急修繕") or "").startswith("是"),
        amount=amount,
        quote_date=date.fromisoformat(qdate),
        incident_date=date.fromisoformat(inc) if inc else None,
        doc_id=doc_id,
    )
