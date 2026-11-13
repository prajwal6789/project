import numpy as np

from src.gen.rng import MODULES, child_generators


def test_rng_is_deterministic_and_module_scoped():
    first = child_generators(20261022)
    second = child_generators(20261022)
    assert tuple(first) == MODULES
    for name in MODULES:
        assert np.array_equal(first[name].integers(0, 2**31, 16), second[name].integers(0, 2**31, 16))


def test_different_seed_changes_streams():
    first = child_generators(20261022)
    second = child_generators(20261023)
    assert any(first[name].integers(0, 2**31) != second[name].integers(0, 2**31) for name in MODULES)
