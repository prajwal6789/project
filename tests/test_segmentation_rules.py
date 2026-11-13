import pandas as pd
import pytest

from src.gen.run import AS_OF, _classify_lifecycle


def _row(name, **changes):
    row = {"customer_id": name, "signup_date": "2024-10-23", "frequency_12m": 4, "recency_days": 60, "r_score": 3, "f_score": 3, "m_score": 3, "marketing_suppressed": False}
    row.update(changes)
    return row


@pytest.mark.parametrize("name, changes, expected", [
    ("suppressed", {"marketing_suppressed": True}, "CONSENT_SUPPRESSED"),
    ("new", {"signup_date": "2026-07-24", "frequency_12m": 1}, "NEW"),
    ("champions", {"r_score": 5, "f_score": 5, "m_score": 5}, "CHAMPIONS"),
    ("loyal", {"r_score": 4, "f_score": 3, "m_score": 2}, "LOYAL"),
    ("at-risk-120", {"recency_days": 120, "frequency_12m": 3, "r_score": 2}, "AT_RISK"),
    ("at-risk-270", {"recency_days": 270, "frequency_12m": 3, "r_score": 2}, "AT_RISK"),
    ("dormant", {"recency_days": 271, "frequency_12m": 0, "r_score": 1}, "DORMANT"),
    ("promising", {"recency_days": 100, "frequency_12m": 2, "r_score": 2, "f_score": 2}, "PROMISING"),
])
def test_each_lifecycle_rule_and_boundaries(name, changes, expected):
    assert _classify_lifecycle(pd.DataFrame([_row(name, **changes)]), AS_OF)[0] == expected


def test_priority_resolves_new_before_champions():
    assert _classify_lifecycle(pd.DataFrame([_row("overlap", signup_date="2026-07-24", frequency_12m=1, r_score=5, f_score=5, m_score=5)]), AS_OF)[0] == "NEW"


def test_memberships_have_one_active_lifecycle_membership_per_customer():
    from src.gen.master import generate_segment_rules, generate_customers, generate_products
    from src.gen.rng import child_generators
    from src.gen.run import _consent, _memberships, _orders
    customers, internal = generate_customers(child_generators(44)["customers"], 40)
    orders, _ = _orders(customers, generate_products(child_generators(44)["products"], 10), 80, child_generators(44)["orders"], internal)
    consent, _ = _consent(customers, child_generators(44)["consent"])
    memberships, _ = _memberships(customers, orders, generate_segment_rules(), consent)
    lifecycle = memberships[memberships.segment_id.str[-6:].astype(int).between(1, 7)]
    assert lifecycle.groupby("customer_id").size().max() == 1
