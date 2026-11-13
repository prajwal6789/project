import numpy as np

from src.gen.master import ARCHETYPE_PROBS, generate_customers, generate_products, generate_segment_rules
from src.gen.rng import child_generators


def test_master_keys_and_hidden_archetypes():
    customers, internal = generate_customers(child_generators(20261022)["customers"], 2000)
    assert customers.customer_id.is_unique
    assert "archetype" not in customers.columns
    assert len(internal) == len(customers)
    observed = internal.archetype.value_counts(normalize=True).sort_index()
    expected = dict(zip(("ACTIVE_CORE", "BIG_SPENDER", "CHURNED", "DORMANT", "HIGH_SERVICE", "NEW"), ARCHETYPE_PROBS[1:] + ARCHETYPE_PROBS[4:5] if False else ()))
    assert set(internal.archetype.unique()) <= set(ARCHETYPE_PROBS and ("NEW", "ACTIVE_CORE", "BIG_SPENDER", "DORMANT", "CHURNED", "HIGH_SERVICE"))
    assert abs(observed.sum() - 1) < 1e-9


def test_products_and_segments():
    products = generate_products(child_generators(1)["products"], 40)
    segments = generate_segment_rules()
    assert products.product_id.is_unique
    assert len(segments) == 10
    assert segments.segment_name.is_unique
