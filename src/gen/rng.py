"""Deterministic independent RNG streams for generator modules."""

from collections.abc import Mapping

import numpy as np


MODULES = (
    "customers", "products", "orders", "events", "support", "consent",
    "outcomes", "anomalies",
)


def child_generators(seed: int) -> dict[str, np.random.Generator]:
    """Return stable child streams; adding draws to one stream won't shift others."""
    sequence = np.random.SeedSequence(seed)
    children = sequence.spawn(len(MODULES))
    return {name: np.random.default_rng(child) for name, child in zip(MODULES, children)}


def same_streams(first: Mapping[str, np.random.Generator], second: Mapping[str, np.random.Generator]) -> bool:
    """Small helper for tests and diagnostics."""
    return all(np.array_equal(a.integers(0, 2**31, 8), b.integers(0, 2**31, 8)) for a, b in zip(first.values(), second.values()))
