import pytest

from src.gen.ids import PATTERNS, action_outcome_id, customer_id, membership_id, order_id, order_line_id, product_id


@pytest.mark.parametrize("kind,value", [
    ("customer", customer_id(1)),
    ("product", product_id(1)),
    ("order", order_id(1)),
    ("order_line", order_line_id(1)),
    ("action_outcome", action_outcome_id(1)),
    ("membership", membership_id(3, 123)),
])
def test_id_formats(kind, value):
    assert PATTERNS[kind].fullmatch(value)


def test_ids_are_one_based():
    with pytest.raises(ValueError):
        customer_id(0)
