import numpy as np
import pandas as pd

from src.gen.master import generate_actions, generate_customers, generate_products, generate_segment_rules
from src.gen.rng import child_generators
from src.gen.run import _consent, _memberships, _orders, _support


def test_orders_respect_signup_and_have_variable_customer_counts():
    rngs = child_generators(20261022)
    customers, internal = generate_customers(rngs["customers"], 500)
    products = generate_products(rngs["products"], 40)
    orders, _ = _orders(customers, products, 2000, rngs["orders"], internal)
    signup = dict(zip(customers.customer_id, pd.to_datetime(customers.signup_date)))
    assert all(pd.Timestamp(row.order_ts) >= signup[row.customer_id] for row in orders.itertuples())
    assert orders[orders.order_type.eq("SALE")].groupby("customer_id").size().nunique() > 1


def test_consent_has_service_and_append_only_withdrawals():
    rngs = child_generators(20261022)
    customers, _ = generate_customers(rngs["customers"], 500)
    consent, events = _consent(customers, rngs["consent"])
    assert {"MARKETING", "SERVICE"} <= set(consent.purpose)
    assert "PHONE" in set(consent.channel)
    assert consent.status.eq("WITHDRAWN").sum() > 0
    assert events.event_type.isin({"GRANTED", "WITHDRAWN"}).all()


def test_segments_and_support_are_rule_inputs():
    rngs = child_generators(20261022)
    customers, internal = generate_customers(rngs["customers"], 500)
    products = generate_products(rngs["products"], 40)
    orders, _ = _orders(customers, products, 2000, rngs["orders"], internal)
    consent, _ = _consent(customers, rngs["consent"])
    support = _support(customers, orders, rngs["support"])
    memberships, _ = _memberships(customers, orders, generate_segment_rules(), consent, support)
    actions, bridge = generate_actions()
    assert memberships.rule_matched.nunique() >= 3
    assert len(actions) == 14
    assert len(bridge) > 10
    assert support.order_id.notna().any()
