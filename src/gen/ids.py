"""Stable identifiers used by the generated entities."""

import re


def _numbered(prefix: str, number: int, width: int) -> str:
    if number < 1:
        raise ValueError("IDs are one-based")
    return f"{prefix}{number:0{width}d}"


def customer_id(number: int) -> str:
    return _numbered("CUS-", number, 6)


def product_id(number: int) -> str:
    return _numbered("PRD-", number, 5)


def order_id(number: int, year: int = 2026) -> str:
    return _numbered(f"ORD-{year}-", number, 6)


def order_line_id(number: int, year: int = 2026) -> str:
    return _numbered(f"ORL-{year}-", number, 7)


def event_id(number: int) -> str:
    return _numbered("EVT-", number, 7)


def support_case_id(number: int) -> str:
    return _numbered("CAS-", number, 6)


def consent_id(number: int) -> str:
    return _numbered("CON-", number, 6)


def segment_id(number: int, year: int = 2026) -> str:
    return _numbered(f"SEG-{year}-", number, 6)


def membership_id(segment_number: int, customer_number: int, year: int = 2026) -> str:
    return f"MEM-SEG-{year}-{segment_number:06d}-CUS-{customer_number:06d}"


def action_outcome_id(number: int, year: int = 2026) -> str:
    return _numbered(f"ACTN-{year}-", number, 6)


PATTERNS = {
    "customer": re.compile(r"^CUS-\d{6}$"),
    "product": re.compile(r"^PRD-\d{5}$"),
    "order": re.compile(r"^ORD-\d{4}-\d{6}$"),
    "order_line": re.compile(r"^ORL-\d{4}-\d{7}$"),
    "event": re.compile(r"^EVT-\d{7}$"),
    "support_case": re.compile(r"^CAS-\d{6}$"),
    "consent": re.compile(r"^CON-\d{6}$"),
    "segment": re.compile(r"^SEG-\d{4}-\d{6}$"),
    "membership": re.compile(r"^MEM-SEG-\d{4}-\d{6}-CUS-\d{6}$"),
    "action_outcome": re.compile(r"^ACTN-\d{4}-\d{6}$"),
}
