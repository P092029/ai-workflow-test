from pcs.corpus import parse_quote
from pcs.kg import get_backend
from pcs.reasoning import RuleBook


def test_quote_parsing():
    doc = get_backend().find_quote("Q-2025-0601")
    q = parse_quote(doc["text"])
    assert q.amount == 600_000 and q.is_emergency and (q.quote_date - q.incident_date).days == 2


def test_hybrid_links_documents_a_and_b():
    ctx = get_backend().query("60 萬緊急修繕是否需要公開招標？", "hybrid", 8)
    assert {"A", "B"} <= {c["doc_id"] for c in ctx}


def test_cross_reference_relation_b1_to_a5():
    rels = {r["entity"]: r["documents"] for r in get_backend().relations()}
    assert rels["A-5"] == ["A", "B"]


def test_rulebook_only_knows_retrieved_rules():
    kg = get_backend()
    rb_a = RuleBook.from_contexts([kg.get_document("A")])
    assert rb_a.tender_threshold == 500_000 and rb_a.emergency_cap is None
    rb_ab = RuleBook.from_contexts([kg.get_document("A"), kg.get_document("B")])
    assert rb_ab.emergency_cap == 1_000_000 and rb_ab.special_rule_allowed
