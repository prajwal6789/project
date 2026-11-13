"""Deterministic synthetic master-data generation."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .ids import customer_id, product_id, segment_id
from .config import load_yaml


ARCHETYPES = ("NEW", "ACTIVE_CORE", "BIG_SPENDER", "DORMANT", "CHURNED", "HIGH_SERVICE")
ARCHETYPE_PROBS = (0.12, 0.45, 0.08, 0.18, 0.10, 0.07)


def generate_products(rng: np.random.Generator, count: int = 400) -> pd.DataFrame:
    categories = {
        "APPAREL": ["TOPS", "BOTTOMS", "OUTERWEAR", "SHOES"],
        "BEAUTY": ["SKINCARE", "HAIRCARE", "COSMETICS"],
        "HOME": ["KITCHEN", "DECOR", "BEDDING"],
        "ELECTRONICS": ["AUDIO", "MOBILE", "ACCESSORIES"],
        "GROCERY": ["SNACKS", "BEVERAGES", "PANTRY"],
        "SPORTS": ["FITNESS", "OUTDOOR", "TEAM"] ,
        "BOOKS": ["FICTION", "NONFICTION", "CHILDREN"],
        "PETS": ["FOOD", "TOYS", "CARE"],
    }
    rows = []
    start = date(2023, 1, 1)
    keys = tuple(categories)
    for i in range(1, count + 1):
        l1 = keys[(i - 1) % len(keys)]
        l2 = categories[l1][(i - 1) % len(categories[l1])]
        price = round(float(rng.lognormal(np.log(60), 0.55)), 2)
        launch = start + timedelta(days=int(rng.integers(0, 1000)))
        rows.append({"product_id": product_id(i), "sku": f"SKU-{i:06d}", "category_l1": l1,
                     "category_l2": l2, "list_price": price, "unit_cost": round(price * 0.55, 2),
                     "launch_date": launch.isoformat(), "discontinued_date": None})
    return pd.DataFrame(rows)


def generate_segment_rules() -> pd.DataFrame:
    rules_config = load_yaml("rules.yaml")
    overlay = rules_config["overlay_thresholds"]
    rules = [
        ("CONSENT_SUPPRESSED", "LIFECYCLE", 1, "all marketing consents withdrawn or none granted"),
        ("NEW", "LIFECYCLE", 2, "signup within 90 days and frequency_12m <= 1"),
        ("CHAMPIONS", "LIFECYCLE", 3, "R = 5 and F = 5 and M = 5"),
        ("LOYAL", "LIFECYCLE", 4, "R >= 3 and F >= 3"),
        ("AT_RISK", "LIFECYCLE", 5, "recency 120..270 days and prior frequency >= 3"),
        ("DORMANT", "LIFECYCLE", 6, "recency > 270 days and frequency_12m = 0"),
        ("PROMISING", "LIFECYCLE", 7, "everything else active"),
        ("HIGH_SERVICE_COST", None, 8, f"service_cost_ratio >= {overlay['high_service_cost_ratio']} or {overlay['high_service_case_count_90d']}+ cases in 90 days"),
        ("HIGH_RETURNER", None, 9, "return value ratio >= 0.30"),
        ("VALUE_TIER_PREMIUM", None, 10, "top 10 percent monetary_net_12m"),
    ]
    return pd.DataFrame([{"segment_id": segment_id(i), "segment_name": name, "exclusive_group": group,
                          "priority": priority, "rule_expression": expr, "rule_version": "v1",
                          "effective_from": "2024-10-23", "effective_to": None}
                         for i, (name, group, priority, expr) in enumerate(rules, 1)])


def generate_actions() -> tuple[pd.DataFrame, pd.DataFrame]:
    actions = [
        ("WELCOME_SERIES", "EMAIL", "MARKETING", 14, "EMAIL", ("NEW",)),
        ("UPSELL_BUNDLE", "EMAIL", "MARKETING", 30, "EMAIL", ("CHAMPIONS",)),
        ("LOYALTY_REWARD", "PUSH", "MARKETING", 30, "PUSH", ("LOYAL",)),
        ("WINBACK_DISCOUNT", "EMAIL", "MARKETING", 21, "EMAIL", ("AT_RISK",)),
        ("REACTIVATION_SURVEY", "EMAIL", "MARKETING", 30, "EMAIL", ("DORMANT",)),
        ("SERVICE_OUTREACH", "PHONE", "SERVICE", 7, "PHONE", ("HIGH_SERVICE_COST",)),
        ("RETURN_POLICY_TIPS", "EMAIL", "MARKETING", 30, "EMAIL", ("HIGH_RETURNER",)),
        ("NO_ACTION_SUPPRESS", "EMAIL", "MARKETING", 0, "EMAIL", ("CONSENT_SUPPRESSED",)),
        ("CROSS_SELL_CATEGORY", "EMAIL", "MARKETING", 21, "EMAIL", ("PROMISING", "VALUE_TIER_PREMIUM")),
        ("PREMIUM_CONCIERGE", "PHONE", "SERVICE", 14, "PHONE", ("VALUE_TIER_PREMIUM",)),
        ("HIGH_VALUE_PREVIEW", "PUSH", "MARKETING", 30, "PUSH", ("VALUE_TIER_PREMIUM", "CHAMPIONS")),
        ("SERVICE_CASE_FOLLOWUP", "PHONE", "SERVICE", 14, "PHONE", ("HIGH_SERVICE_COST",)),
        ("RETURNER_EDUCATION", "SMS", "MARKETING", 21, "SMS", ("HIGH_RETURNER",)),
        ("LOYALTY_ANNIVERSARY", "EMAIL", "MARKETING", 45, "EMAIL", ("LOYAL", "CHAMPIONS")),
    ]
    catalog = pd.DataFrame([{"action_code": code, "channel": channel, "purpose": purpose,
                             "cooldown_days": cooldown, "unit_cost": 0.25, "requires_consent_channel": consent,
                             "active_flag": 1} for code, channel, purpose, cooldown, consent, _ in actions])
    segment_rows = generate_segment_rules().to_dict("records")
    bridges = pd.DataFrame([{"action_code": code, "segment_id": row["segment_id"],
                             "effective_from": "2024-10-23", "effective_to": None}
                            for code, _, _, _, _, allowed in actions
                            for row in segment_rows if row["segment_name"] in allowed])
    return catalog, bridges


def generate_customers(rng: np.random.Generator, count: int, as_of: date = date(2026, 10, 22)) -> tuple[pd.DataFrame, pd.DataFrame]:
    archetypes = rng.choice(ARCHETYPES, size=count, p=ARCHETYPE_PROBS)
    rows = []
    for i, archetype in enumerate(archetypes, 1):
        if archetype == "NEW":
            age_days = int(rng.integers(0, 90))
            lifecycle = "NEW"
        elif archetype in ("DORMANT", "CHURNED"):
            age_days = int(rng.integers(365, 900))
            lifecycle = archetype
        else:
            age_days = int(rng.integers(90, 900))
            lifecycle = "ACTIVE" if archetype != "CHURNED" else "CHURNED"
        signup = as_of - timedelta(days=age_days)
        rows.append({"customer_id": customer_id(i), "signup_date": signup.isoformat(), "country": "IN",
                     "region": ("NORTH", "SOUTH", "EAST", "WEST")[int(rng.integers(0, 4))],
                     "age_band": rng.choice(("18-24", "25-34", "35-44", "45-54", "55+")),
                     "acquisition_channel": rng.choice(("ORGANIC", "PAID_SEARCH", "SOCIAL", "REFERRAL")),
                     "preferred_channel": rng.choice(("EMAIL", "SMS", "PUSH")), "tier": rng.choice(("STANDARD", "PLUS", "PREMIUM"), p=(.65,.25,.10)),
                     "lifecycle_state": lifecycle, "synthetic_email_token": f"email_token_{i:06d}", "is_test_account": 0})
    customers = pd.DataFrame(rows)
    internal = customers[["customer_id"]].copy()
    internal["archetype"] = archetypes
    return customers, internal
