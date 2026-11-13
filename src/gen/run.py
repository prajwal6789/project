"""End-to-end deterministic synthetic dataset generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from .config import load_yaml, resolve_scale
from .ids import *
from .master import generate_actions, generate_customers, generate_products, generate_segment_rules
from .rng import child_generators


AS_OF = date(2026, 10, 22)
START = date(2024, 10, 23)


def _ts(rng, start=START, end=AS_OF):
    return (start + timedelta(days=int(rng.integers(0, (end - start).days + 1)),
                             seconds=int(rng.integers(0, 86400)))).isoformat()


def _orders(customers, products, n, rng, internal=None):
    customer_ids = customers.customer_id.to_numpy()
    product_ids = products.product_id.to_numpy()
    ids = np.arange(1, n + 1)
    if internal is not None:
        rates = {"NEW": .55, "ACTIVE_CORE": 1.00, "BIG_SPENDER": 2.20, "DORMANT": .45, "CHURNED": .30, "HIGH_SERVICE": 1.35}
        weights = internal.archetype.map(rates).to_numpy() * rng.gamma(1.6, 1.0, len(internal))
        probabilities = weights / weights.sum()
        customer_for_order = rng.choice(customer_ids, n, p=probabilities)
    else:
        customer_for_order = rng.choice(customer_ids, n)
    signup_map = customers.set_index("customer_id").signup_date
    signup_dates = pd.to_datetime(pd.Series(customer_for_order).map(signup_map)).dt.date.to_numpy()
    age_days = np.array([(AS_OF - value).days for value in signup_dates])
    days_after_signup = np.array([rng.integers(0, max(1, value + 1)) for value in age_days])
    seconds = rng.integers(0, 86400, n)
    timestamps = [(start + timedelta(days=int(days), seconds=int(second))).isoformat() for start, days, second in zip(signup_dates, days_after_signup, seconds)]
    line_counts = rng.integers(1, 5, n)
    line_order_numbers = np.repeat(ids, line_counts)
    line_products = rng.choice(product_ids, len(line_order_numbers))
    line_qty = rng.integers(1, 3, len(line_order_numbers))
    line_price = np.round(rng.lognormal(np.log(60), .5, len(line_order_numbers)), 2)
    line_discount = np.round(line_price * line_qty * rng.uniform(0, .12, len(line_order_numbers)), 2)
    line_total = np.round(line_price * line_qty - line_discount, 2)
    order_lines = pd.DataFrame({"order_line_id": [order_line_id(i) for i in range(1, len(line_order_numbers) + 1)],
        "order_id": [order_id(int(i)) for i in line_order_numbers], "product_id": line_products,
        "quantity": line_qty, "unit_price": line_price, "discount": line_discount, "line_total": line_total,
        "line_type": "SALE", "original_order_line_id": None})
    totals = order_lines.assign(gross=order_lines.unit_price * order_lines.quantity).groupby("order_id").agg(gross=("gross", "sum"), discount=("discount", "sum")).reindex([order_id(int(i)) for i in ids]).fillna(0)
    orders = pd.DataFrame({"order_id": [order_id(int(i)) for i in ids], "customer_id": customer_for_order, "order_ts": timestamps,
        "order_type": "SALE", "status": "DELIVERED", "currency": "INR", "gross_amount": totals.gross.round(2).to_numpy(),
        "discount_amount": totals.discount.round(2).to_numpy(), "net_amount": (totals.gross - totals.discount).round(2).to_numpy(), "related_order_id": None})
    # Returns are represented as separate orders and lines, never negative quantities.
    return_n = max(1, round(n * .06))
    eligible_returns = orders.loc[pd.to_datetime(orders.order_ts).dt.date < AS_OF, "order_id"].to_numpy()
    source_order_ids = rng.choice(eligible_returns, return_n, replace=len(eligible_returns) < return_n)
    source_orders = orders.set_index("order_id").loc[source_order_ids].reset_index()
    lines_by_order = {order_id_value: group for order_id_value, group in order_lines.groupby("order_id", sort=False)}
    return_numbers = np.arange(n + 1, n + return_n + 1)
    return_ids = [order_id(int(i)) for i in return_numbers]
    return_line_rows = []
    return_totals = []
    for return_id_value, source_order_id in zip(return_ids, source_order_ids):
        source = lines_by_order[source_order_id]
        total = 0.0
        for line in source.itertuples(index=False):
            return_line_rows.append({"order_line_id": None, "order_id": return_id_value, "product_id": line.product_id,
                "quantity": line.quantity, "unit_price": line.unit_price, "discount": line.discount,
                "line_total": line.line_total, "line_type": "RETURN", "original_order_line_id": line.order_line_id})
            total += float(line.line_total)
        return_totals.append(round(total, 2))
    return_lines = pd.DataFrame(return_line_rows)
    return_lines["order_line_id"] = [order_line_id(len(order_lines) + i + 1) for i in range(len(return_lines))]
    original_dates = pd.to_datetime(source_orders.order_ts)
    return_dates = [min(value.to_pydatetime() + timedelta(days=int(rng.integers(1, 31))), datetime.combine(AS_OF, datetime.min.time())) for value in original_dates]
    return_orders = pd.DataFrame({"order_id": return_ids, "customer_id": source_orders.customer_id.to_numpy(),
        "order_ts": [value.isoformat() for value in return_dates], "order_type": "RETURN", "status": "RETURN_COMPLETED", "currency": "INR",
        "gross_amount": return_totals, "discount_amount": 0.0, "net_amount": return_totals,
        "related_order_id": source_orders.order_id.to_numpy()})
    order_lines = pd.concat([order_lines, return_lines], ignore_index=True)
    orders = pd.concat([orders, return_orders], ignore_index=True)
    return orders.sort_values("order_id").reset_index(drop=True), order_lines.sort_values("order_line_id").reset_index(drop=True)


def _consent(customers, rng):
    customer_ids = customers.customer_id.to_numpy()
    combinations = [(channel, purpose, probability) for purpose, channel_probs in {
        "MARKETING": (("EMAIL", .70), ("SMS", .40), ("PUSH", .55), ("PHONE", .20)),
        "SERVICE": (("EMAIL", .95), ("SMS", .95), ("PUSH", .95), ("PHONE", .95)),
    }.items() for channel, probability in channel_probs]
    count = len(customer_ids) * len(combinations)
    customer_values = np.repeat(customer_ids, len(combinations))
    channel_values = np.tile([item[0] for item in combinations], len(customer_ids))
    purpose_values = np.tile([item[1] for item in combinations], len(customer_ids))
    probabilities = np.tile([item[2] for item in combinations], len(customer_ids))
    granted = rng.random(count) < probabilities
    withdrawable = granted & (purpose_values == "MARKETING") & (rng.random(count) < .04)
    withdrawal_days = rng.integers(1, (AS_OF - START).days + 1, count)
    withdrawal_ts = (pd.Timestamp(START) + pd.to_timedelta(withdrawal_days, unit="D")).astype(str).to_numpy()
    ids = np.arange(1, count + 1)
    base_ids = [consent_id(int(i)) for i in ids]
    base_all = pd.DataFrame({"consent_id": base_ids, "customer_id": customer_values, "channel": channel_values, "purpose": purpose_values,
        "status": "GRANTED", "effective_from": START.isoformat(),
        "effective_to": np.where(withdrawable, withdrawal_ts, None), "source": "synthetic_seed"})
    base = base_all.loc[granted].reset_index(drop=True)
    withdrawn_initial = withdrawable[granted]
    base_ids = base.consent_id.tolist()
    events = pd.DataFrame({"consent_event_id": [f"CNE-{int(i):07d}" for i in range(1, len(base) + 1)], "consent_id": base_ids,
        "customer_id": base.customer_id, "event_type": "GRANTED", "event_ts": START.isoformat()})
    if withdrawn_initial.any():
        withdrawn_ids = np.arange(count + 1, count + 1 + int(withdrawn_initial.sum()))
        withdrawn_rows = base.loc[withdrawn_initial].copy()
        withdrawn_rows["consent_id"] = [consent_id(int(i)) for i in withdrawn_ids]
        withdrawn_rows["status"] = "WITHDRAWN"
        withdrawn_rows["effective_from"] = withdrawn_rows["effective_to"]
        withdrawn_rows["effective_to"] = None
        base = pd.concat([base, withdrawn_rows], ignore_index=True)
        events = pd.concat([events, pd.DataFrame({"consent_event_id": [f"CNE-{int(i):07d}" for i in withdrawn_ids],
            "consent_id": withdrawn_rows.consent_id.to_numpy(), "customer_id": withdrawn_rows.customer_id.to_numpy(),
            "event_type": "WITHDRAWN", "event_ts": withdrawn_rows.effective_from.to_numpy()})], ignore_index=True)
    return base, events


def _events(customers, orders, target, rng, outcomes=None, actions=None):
    cids = customers.customer_id.to_numpy()
    types = ("WEB_VISIT", "PRODUCT_VIEW", "CART_ADD", "APP_SESSION", "EMAIL_SENT", "EMAIL_OPEN", "EMAIL_CLICK")
    send_rows = pd.DataFrame()
    if outcomes is not None and actions is not None:
        channel_map = dict(zip(actions.action_code, actions.channel))
        sent = outcomes[outcomes.decision.eq("SENT")].copy()
        sent["channel"] = sent.action_code.map(channel_map)
        sent = sent[sent.channel.isin(["EMAIL", "SMS"])].copy()
        send_rows = pd.DataFrame({"customer_id": sent.customer_id, "action_id": sent.action_outcome_id,
            "product_id": None, "event_type": sent.channel.map({"EMAIL": "EMAIL_SENT", "SMS": "SMS_SENT"}),
            "channel": sent.channel, "event_ts": sent.sent_at, "parent_event_id": None})
    base_count = max(target - len(send_rows), len(cids))
    count = base_count
    event_days = rng.integers(0, (AS_OF - START).days + 1, count)
    event_seconds = rng.integers(0, 86400, count)
    event_timestamps = (pd.Timestamp(START) + pd.to_timedelta(event_days, unit="D") + pd.to_timedelta(event_seconds, unit="s")).astype(str)
    base = pd.DataFrame({"event_id": [event_id(i) for i in range(1, count + 1)],
        "customer_id": rng.choice(cids, count), "action_id": None, "product_id": None,
        "event_type": rng.choice(types, count, p=(.30,.25,.08,.15,.10,.08,.04)),
        "channel": rng.choice(("WEB", "APP", "EMAIL"), count),
        "event_ts": event_timestamps, "parent_event_id": None})
    if len(send_rows):
        send_rows.insert(0, "event_id", [event_id(count + i) for i in range(1, len(send_rows) + 1)])
        base = pd.concat([base, send_rows[base.columns]], ignore_index=True)
    return base


def _support(customers, orders, rng):
    count = max(1, round(len(customers) * .3))
    cids = customers.customer_id.to_numpy(); severities = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    rows = []
    for i in range(1, count + 1):
        opened = _ts(rng); opened_dt = datetime.fromisoformat(opened)
        resolved = (opened_dt + timedelta(hours=int(rng.integers(1, 72)))).isoformat()
        rows.append({"case_id": support_case_id(i), "customer_id": rng.choice(cids), "order_id": None,
                     "severity": rng.choice(severities, p=(.55,.30,.12,.03)), "status": "CLOSED",
                     "opened_at": opened, "resolved_at": resolved, "closed_at": resolved,
                     "handle_minutes": int(rng.integers(5, 180)), "cost_amount": 0.0, "csat": int(rng.integers(1, 6))})
    result = pd.DataFrame(rows)
    order_by_customer = orders.groupby("customer_id").order_id.apply(list).to_dict()
    result["order_id"] = [rng.choice(order_by_customer.get(customer_id, [None])) if rng.random() < .55 else None for customer_id in result.customer_id]
    rates = {"LOW": .5, "MEDIUM": .8, "HIGH": 1.4, "CRITICAL": 2.5}
    result["cost_amount"] = (result.handle_minutes * result.severity.map(rates)).round(2)
    return result


def _classify_lifecycle(frame, as_of):
    """Single lifecycle rule implementation used by as-of and monthly paths."""
    if "r_score" not in frame:
        frame["r_score"] = np.clip(np.ceil((1 - frame.recency_days.rank(pct=True, method="first")) * 5 + 1), 1, 5).astype(int)
        frame["f_score"] = np.clip(np.ceil(frame.frequency_12m.rank(pct=True, method="first") * 5), 1, 5).astype(int)
        frame["m_score"] = np.clip(np.ceil(frame.monetary_net_12m.rank(pct=True, method="first") * 5), 1, 5).astype(int)
    suppressed = frame.get("marketing_suppressed", pd.Series(False, index=frame.index))
    age = frame.signup_date.map(lambda value: (pd.Timestamp(as_of).date() - date.fromisoformat(str(value)[:10])).days)
    return np.select([
        suppressed,
        age.le(90) & frame.frequency_12m.le(1),
        frame.r_score.eq(5) & frame.f_score.eq(5) & frame.m_score.eq(5),
        frame.recency_days.between(120, 270) & frame.frequency_12m.ge(3),
        frame.r_score.ge(3) & frame.f_score.ge(3),
        frame.recency_days.gt(270) & frame.frequency_12m.eq(0)],
        ["CONSENT_SUPPRESSED", "NEW", "CHAMPIONS", "AT_RISK", "LOYAL", "DORMANT"], default="PROMISING")


def _memberships(customers, orders, segments, consent=None, support=None):
    sales = orders[orders.order_type.eq("SALE")]
    returns = orders[orders.order_type.eq("RETURN")].groupby("customer_id").net_amount.sum().rename("return_net")
    agg = sales.groupby("customer_id").agg(frequency_12m=("order_id", "count"), monetary_net_12m=("net_amount", "sum"), last=("order_ts", "max")).reset_index()
    agg = agg.merge(returns, on="customer_id", how="left"); agg["monetary_net_12m"] = agg.monetary_net_12m - agg.return_net.fillna(0)
    result = customers[["customer_id", "signup_date"]].merge(agg, on="customer_id", how="left")
    result[["frequency_12m", "monetary_net_12m"]] = result[["frequency_12m", "monetary_net_12m"]].fillna(0)
    result["recency_days"] = result["last"].map(lambda x: (AS_OF - pd.Timestamp(x).date()).days if pd.notna(x) else 999).astype(int)
    result["r_score"] = np.clip(np.ceil((1 - result.recency_days.rank(pct=True, method="first")) * 5 + 1), 1, 5).astype(int)
    result["f_score"] = np.clip(np.ceil(result.frequency_12m.rank(pct=True, method="first") * 5), 1, 5).astype(int)
    result["m_score"] = np.clip(np.ceil(result.monetary_net_12m.rank(pct=True, method="first") * 5), 1, 5).astype(int)
    if consent is not None:
        active_marketing = consent[(consent.purpose.eq("MARKETING")) & (consent.status.eq("GRANTED")) & consent.effective_to.isna()].groupby("customer_id").size()
        result["marketing_suppressed"] = ~result.customer_id.isin(active_marketing.index)
    else:
        result["marketing_suppressed"] = False
    result["segment_name"] = _classify_lifecycle(result, AS_OF)
    if support is not None:
        service_cost = support.groupby("customer_id").cost_amount.sum()
        result["service_cost_ratio"] = result.customer_id.map(service_cost).fillna(0) / result.monetary_net_12m.clip(lower=1)
    else:
        result["service_cost_ratio"] = 0.0
    sale_value = orders[orders.order_type.eq("SALE")].groupby("customer_id").gross_amount.sum()
    return_value = orders[orders.order_type.eq("RETURN")].groupby("customer_id").net_amount.sum()
    result["return_ratio"] = result.customer_id.map(return_value).fillna(0) / result.customer_id.map(sale_value).fillna(0).clip(lower=1)
    result["value_premium"] = result.monetary_net_12m.ge(result.monetary_net_12m.quantile(.90))
    rules_config = load_yaml("rules.yaml")
    overlay = rules_config["overlay_thresholds"]
    overlay_masks = [("HIGH_SERVICE_COST", result.service_cost_ratio.ge(overlay["high_service_cost_ratio"])), ("HIGH_RETURNER", result.return_ratio.ge(.30)), ("VALUE_TIER_PREMIUM", result.value_premium)]
    lookup = dict(zip(segments.segment_name, segments.segment_id))
    rows = []
    for position, row in enumerate(result.itertuples(index=False)):
        segment_names = [row.segment_name] + [name for name, mask in overlay_masks if bool(mask.iloc[position])]
        for name in segment_names:
            segment_number = int(lookup[name].split("-")[-1])
            evidence = f"frequency_12m={int(row.frequency_12m)}; recency_days={int(row.recency_days)}; monetary_net_12m={float(row.monetary_net_12m):.2f}; r_score={int(row.r_score)}; f_score={int(row.f_score)}; m_score={int(row.m_score)}"
            rows.append({"membership_id": membership_id(segment_number, int(row.customer_id.split('-')[-1])), "segment_id": lookup[name], "customer_id": row.customer_id,
                "recency_days": int(row.recency_days), "frequency_12m": int(row.frequency_12m), "monetary_net_12m": round(float(row.monetary_net_12m), 2),
                "r_score": int(row.r_score), "f_score": int(row.f_score), "m_score": int(row.m_score), "rule_matched": name, "evidence": evidence,
                "effective_from": AS_OF.isoformat(), "effective_to": None, "status": "ACTIVE"})
    memberships = pd.DataFrame(rows)
    events = pd.DataFrame({"membership_event_id": [f"SME-{i:06d}" for i in range(1, len(memberships)+1)],
        "membership_id": memberships.membership_id, "customer_id": memberships.customer_id, "segment_id": memberships.segment_id,
        "event_type": "ENTER", "event_ts": AS_OF.isoformat()})
    return memberships, events


def _monthly_snapshots(customers, orders, segments):
    month_ends = list(pd.date_range("2024-11-30", "2026-09-30", freq="ME")) + [pd.Timestamp(AS_OF)]
    lookup = dict(zip(segments.segment_name, segments.segment_id))
    frames = []
    for snapshot_date in month_ends:
        end = snapshot_date.date(); start = end - timedelta(days=365)
        order_dates = pd.to_datetime(orders.order_ts, format="mixed").dt.date
        sales = orders[(orders.order_type.eq("SALE")) & (order_dates <= end) & (order_dates >= start)]
        agg = sales.groupby("customer_id").agg(frequency_12m=("order_id", "count"), monetary_net_12m=("net_amount", "sum"), last=("order_ts", "max")).reset_index()
        frame = customers[["customer_id", "signup_date"]].merge(agg, on="customer_id", how="left")
        frame[["frequency_12m", "monetary_net_12m"]] = frame[["frequency_12m", "monetary_net_12m"]].fillna(0)
        frame["recency_days"] = frame["last"].map(lambda value: (end - pd.Timestamp(value).date()).days if pd.notna(value) else 999).astype(int)
        frame["rule_matched"] = _classify_lifecycle(frame, end)
        frame["segment_id"] = frame.rule_matched.map(lookup)
        frame["evidence"] = frame.apply(lambda row: f"frequency_12m={int(row.frequency_12m)}; recency_days={int(row.recency_days)}; monetary_net_12m={float(row.monetary_net_12m):.2f}", axis=1)
        frame = frame[["customer_id", "segment_id", "recency_days", "frequency_12m", "monetary_net_12m", "rule_matched", "evidence"]]
        frame.insert(0, "snapshot_id", [f"SNP-{snapshot_date:%Y%m}-{i:07d}" for i in range(1, len(frame) + 1)])
        frame["snapshot_date"] = snapshot_date.date().isoformat()
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _membership_history_events(snapshots, memberships):
    current_by_customer = memberships[memberships.rule_matched.isin(["NEW", "CHAMPIONS", "AT_RISK", "LOYAL", "DORMANT", "PROMISING", "CONSENT_SUPPRESSED"])].set_index("customer_id").membership_id.to_dict()
    rows = []
    for customer_id, group in snapshots.sort_values(["customer_id", "snapshot_date"]).groupby("customer_id", sort=False):
        previous = None
        for row in group.itertuples(index=False):
            if previous is None:
                rows.append({"membership_event_id": f"SME-{len(rows)+1:08d}", "membership_id": current_by_customer.get(customer_id, row.snapshot_id), "customer_id": customer_id, "segment_id": row.segment_id, "event_type": "ENTER", "event_ts": row.snapshot_date})
            elif previous != row.segment_id:
                rows.append({"membership_event_id": f"SME-{len(rows)+1:08d}", "membership_id": current_by_customer.get(customer_id, row.snapshot_id), "customer_id": customer_id, "segment_id": previous, "event_type": "EXIT", "event_ts": row.snapshot_date})
                rows.append({"membership_event_id": f"SME-{len(rows)+1:08d}", "membership_id": current_by_customer.get(customer_id, row.snapshot_id), "customer_id": customer_id, "segment_id": row.segment_id, "event_type": "ENTER", "event_ts": row.snapshot_date})
            previous = row.segment_id
    return pd.DataFrame(rows)


def _outcomes(memberships, actions, bridge, consent, orders, support, customers, rng):
    eligible = bridge.merge(memberships[["membership_id", "customer_id", "segment_id"]], on="segment_id")
    eligible = eligible.merge(actions[["action_code", "channel", "purpose"]], on="action_code")
    granted = consent[(consent.status == "GRANTED") & consent.effective_to.isna()][["customer_id", "channel", "purpose"]].drop_duplicates()
    eligible = eligible.merge(granted, on=["customer_id", "channel", "purpose"], how="left", indicator=True)
    eligible["has_consent"] = eligible["_merge"].eq("both")
    withdrawal_events = consent[consent.status.eq("WITHDRAWN")][["customer_id", "effective_from"]].rename(columns={"effective_from": "withdrawal"})
    closed_grants = consent[consent.status.eq("GRANTED") & consent.effective_to.notna()][["customer_id", "effective_to"]].rename(columns={"effective_to": "withdrawal"})
    withdrawn_before = pd.concat([withdrawal_events, closed_grants], ignore_index=True).assign(withdrawal=lambda x: pd.to_datetime(x.withdrawal)).groupby("customer_id").withdrawal.min()
    recommendation_time = pd.Timestamp(AS_OF) - pd.Timedelta(days=30)
    eligible["has_consent"] = eligible.has_consent & ~eligible.customer_id.map(withdrawn_before).fillna(pd.Timestamp.max).le(recommendation_time)
    eligible = eligible.drop_duplicates(["customer_id", "action_code"])
    if eligible.empty:
        return pd.DataFrame(columns=["action_outcome_id","customer_id","action_code","segment_id","membership_id","recommended_at","decision","suppression_reason","sent_at","outcome","outcome_at","attributed_order_id","attribution_window_days","control_group_flag"])
    customer_order = eligible.groupby("customer_id").cumcount()
    service_customers = set(support[support.severity.isin(["HIGH", "CRITICAL"])].customer_id) if support is not None else set()
    open_service = eligible.customer_id.isin(service_customers) & eligible.purpose.eq("MARKETING")
    frequency_cap = customer_order.ge(2) & eligible.purpose.eq("MARKETING")
    cooldown = customer_order.ge(3) & eligible.purpose.eq("MARKETING")
    control_group = eligible.has_consent & eligible.purpose.eq("MARKETING") & (rng.random(len(eligible)) < .10)
    reasons = np.select([~eligible.has_consent, cooldown, frequency_cap, open_service], ["NO_CONSENT", "COOLDOWN", "FREQUENCY_CAP", "OPEN_SERVICE_CASE"], default=None)
    eligible["control_group_flag"] = control_group.astype(int)
    eligible["decision"] = np.select([~eligible.has_consent, control_group, cooldown, frequency_cap, open_service], ["SUPPRESSED", "RECOMMENDED", "SUPPRESSED", "SUPPRESSED", "SUPPRESSED"], default="SENT")
    eligible["suppression_reason"] = reasons
    recommended = (pd.Timestamp(AS_OF) - pd.Timedelta(days=30)).isoformat()
    eligible["recommended_at"] = recommended; eligible["sent_at"] = np.where(eligible.decision.eq("SENT"), recommended, None)
    random_draw = rng.random(len(eligible))
    signup_map = customers.set_index("customer_id").signup_date
    conversion_allowed = pd.to_datetime(eligible.customer_id.map(signup_map)) <= pd.Timestamp(recommended)
    eligible["outcome"] = np.where(eligible.decision.eq("SENT") & conversion_allowed & (random_draw < .02), "CONVERTED", np.where(eligible.decision.eq("SENT") & (random_draw < .10), "OPENED", "NONE"))
    eligible["outcome_at"] = np.where(eligible.outcome.ne("NONE"), (pd.Timestamp(recommended) + pd.Timedelta(days=3)).isoformat(), None)
    eligible["attributed_order_id"] = None; eligible["attribution_window_days"] = 14
    eligible.insert(0, "action_outcome_id", [action_outcome_id(i) for i in range(1, len(eligible) + 1)])
    result = eligible[["action_outcome_id","customer_id","action_code","segment_id","membership_id","recommended_at","decision","suppression_reason","sent_at","outcome","outcome_at","attributed_order_id","attribution_window_days","control_group_flag"]]
    converted = result[result.outcome.eq("CONVERTED")].copy()
    if len(converted):
        start_order = int(len(orders) + 1)
        conversion_ids = [order_id(start_order + i) for i in range(len(converted))]
        conversion_orders = pd.DataFrame({"order_id": conversion_ids, "customer_id": converted.customer_id.to_numpy(),
            "order_ts": converted.outcome_at.to_numpy(), "order_type": "SALE", "status": "DELIVERED", "currency": "INR",
            "gross_amount": 60.0, "discount_amount": 0.0, "net_amount": 60.0, "related_order_id": None})
        conversion_lines = pd.DataFrame({"order_line_id": [order_line_id(len(orders) + len(orders) + i + 1) for i in range(len(converted))],
            "order_id": conversion_ids, "product_id": "PRD-00001", "quantity": 1, "unit_price": 60.0, "discount": 0.0,
            "line_total": 60.0, "line_type": "SALE", "original_order_line_id": None})
        result.loc[converted.index, "attributed_order_id"] = conversion_ids
    else:
        conversion_orders = pd.DataFrame(columns=orders.columns)
        conversion_lines = pd.DataFrame(columns=["order_line_id","order_id","product_id","quantity","unit_price","discount","line_total","line_type","original_order_line_id"])
    return result, conversion_orders, conversion_lines


def _inject_anomalies(tables, scale, rng):
    """Inject bounded labelled edge cases after clean generation."""
    n = len(tables["Customer"])
    factor = n / 50000
    counts = {"CONFLICTING_EXCLUSIVE_SEGMENTS": max(1, round(150 * factor)),
              "ACTION_VIOLATES_CONSENT": max(1, round(300 * factor)),
              "RETURN_NOT_NETTED": max(1, round(200 * factor)),
              "OUTCOME_WRONG_ACTION": max(1, round(250 * factor))}
    labels = []
    memberships = tables["SegmentMembership"]
    segments = tables["SegmentRule"]
    customers = tables["Customer"]
    lifecycle_ids = set(segments.loc[segments.exclusive_group.eq("LIFECYCLE"), "segment_id"])
    conflict_sources = memberships[memberships.segment_id.isin(lifecycle_ids)].drop_duplicates("customer_id").reset_index(drop=True)
    for k in range(min(counts["CONFLICTING_EXCLUSIVE_SEGMENTS"], len(conflict_sources))):
        source = conflict_sources.iloc[k].copy()
        customer_number = int(source.customer_id.split('-')[-1])
        alternate_segment = next(segment_number for segment_number in (7, 6, 5, 4, 3, 2, 1) if membership_id(segment_number, customer_number) not in set(memberships.membership_id))
        source["segment_id"] = segments.iloc[alternate_segment - 1].segment_id
        source["membership_id"] = membership_id(alternate_segment, customer_number)
        source["rule_matched"] = "PROMISING"
        memberships = pd.concat([memberships, pd.DataFrame([source])], ignore_index=True)
        labels.append({"ground_truth_id": f"GT-{len(labels)+1:06d}", "entity_type": "SegmentMembership", "entity_id": source.membership_id,
                       "customer_id": source.customer_id, "issue_type": "CONFLICTING_EXCLUSIVE_SEGMENTS", "expected_detection_rule": "one_active_lifecycle_segment", "expected_decision": "FLAG", "injected_field": "segment_id", "original_value": "", "injected_value": source.segment_id, "notes": "second active lifecycle membership"})
    outcomes = tables["ActionOutcome"]
    withdrawn = tables["Consent"][tables["Consent"].status.eq("GRANTED") & tables["Consent"].effective_to.notna()]
    membership_by_customer = tables["SegmentMembership"].drop_duplicates("customer_id").set_index("customer_id")
    for k in range(min(counts["ACTION_VIOLATES_CONSENT"], len(outcomes), len(withdrawn))):
        idx = outcomes.index[k]; con = withdrawn.iloc[k]
        outcomes.loc[idx, "customer_id"] = con.customer_id
        if con.customer_id in membership_by_customer.index:
            outcomes.loc[idx, "membership_id"] = membership_by_customer.loc[con.customer_id, "membership_id"]
            outcomes.loc[idx, "segment_id"] = membership_by_customer.loc[con.customer_id, "segment_id"]
        outcomes.loc[idx, "decision"] = "SENT"; outcomes.loc[idx, "suppression_reason"] = None; outcomes.loc[idx, "sent_at"] = con.effective_to; outcomes.loc[idx, "attributed_order_id"] = None; outcomes.loc[idx, "outcome"] = "NONE"; outcomes.loc[idx, "outcome_at"] = None
        labels.append({"ground_truth_id": f"GT-{len(labels)+1:06d}", "entity_type": "ActionOutcome", "entity_id": outcomes.loc[idx, "action_outcome_id"], "customer_id": con.customer_id, "issue_type": "ACTION_VIOLATES_CONSENT", "expected_detection_rule": "consent_violation", "expected_decision": "FLAG", "injected_field": "sent_at", "original_value": "", "injected_value": con.effective_to, "notes": "sent at withdrawal boundary"})
    for k in range(min(counts["RETURN_NOT_NETTED"], len(memberships))):
        idx = memberships.index[k]; old = memberships.loc[idx, "monetary_net_12m"]; memberships.loc[idx, "monetary_net_12m"] = float(old) + 1.0
        labels.append({"ground_truth_id": f"GT-{len(labels)+1:06d}", "entity_type": "SegmentMembership", "entity_id": memberships.loc[idx, "membership_id"], "customer_id": memberships.loc[idx, "customer_id"], "issue_type": "RETURN_NOT_NETTED", "expected_detection_rule": "metric_reconciliation", "expected_decision": "FLAG", "injected_field": "monetary_net_12m", "original_value": old, "injected_value": float(old)+1.0, "notes": "net metric altered"})
    orders = tables["OrderHeader"]
    for k in range(min(counts["OUTCOME_WRONG_ACTION"], len(outcomes), len(orders))):
        idx = outcomes.index[k]; wrong = orders.iloc[-(k+1)]
        outcomes.loc[idx, "attributed_order_id"] = wrong.order_id
        labels.append({"ground_truth_id": f"GT-{len(labels)+1:06d}", "entity_type": "ActionOutcome", "entity_id": outcomes.loc[idx, "action_outcome_id"], "customer_id": outcomes.loc[idx, "customer_id"], "issue_type": "OUTCOME_WRONG_ACTION", "expected_detection_rule": "attribution_window_and_customer_match", "expected_decision": "FLAG", "injected_field": "attributed_order_id", "original_value": "", "injected_value": wrong.order_id, "notes": "attribution points to an unrelated order"})
    tables["SegmentMembership"] = memberships; tables["ActionOutcome"] = outcomes
    return pd.DataFrame(labels)


def generate(scale: str, seed: int, out: Path, inject: bool = True):
    cfg = resolve_scale(scale, seed); rngs = child_generators(seed); out.mkdir(parents=True, exist_ok=True)
    products = generate_products(rngs["products"], 400); customers, internal = generate_customers(rngs["customers"], cfg["customers"])
    segments = generate_segment_rules(); actions, bridge = generate_actions()
    orders, lines = _orders(customers, products, cfg["orders"], rngs["orders"], internal)
    consent, consent_events = _consent(customers, rngs["consent"])
    support = _support(customers, orders, rngs["support"])
    memberships, _ = _memberships(customers, orders, segments, consent, support)
    snapshots = _monthly_snapshots(customers, orders, segments)
    membership_events = _membership_history_events(snapshots, memberships)
    status_rows = []
    for row in customers.itertuples(index=False):
        signup = pd.Timestamp(row.signup_date)
        states = [("NEW", signup)]
        if row.lifecycle_state == "ACTIVE":
            states.append(("ACTIVE", max(signup + pd.Timedelta(days=1), pd.Timestamp(AS_OF))))
        elif row.lifecycle_state == "DORMANT":
            active_at = max(signup + pd.Timedelta(days=1), pd.Timestamp(AS_OF) - pd.Timedelta(days=365))
            states.extend([("ACTIVE", active_at), ("DORMANT", max(active_at + pd.Timedelta(days=1), pd.Timestamp(AS_OF)))])
        elif row.lifecycle_state == "CHURNED":
            active_at = max(signup + pd.Timedelta(days=1), pd.Timestamp(AS_OF) - pd.Timedelta(days=540))
            dormant_at = max(active_at + pd.Timedelta(days=1), pd.Timestamp(AS_OF) - pd.Timedelta(days=180))
            states.extend([("ACTIVE", active_at), ("DORMANT", dormant_at), ("CHURNED", max(dormant_at + pd.Timedelta(days=1), pd.Timestamp(AS_OF)))])
        for state, event_date in states:
            old = status_rows[-1]["new_status"] if status_rows and status_rows[-1]["customer_id"] == row.customer_id else None
            status_rows.append({"status_event_id": f"CSE-{len(status_rows)+1:07d}", "customer_id": row.customer_id, "old_status": old, "new_status": state, "event_ts": event_date.isoformat()})
    status_events = pd.DataFrame(status_rows)
    outcomes, conversion_orders, conversion_lines = _outcomes(memberships, actions, bridge, consent, orders, support, customers, rngs["outcomes"])
    events = _events(customers, orders, cfg["events"], rngs["events"], outcomes, actions)
    if len(conversion_orders):
        conversion_lines["order_line_id"] = [order_line_id(len(lines) + i + 1) for i in range(len(conversion_lines))]
        signup_map = customers.set_index("customer_id").signup_date
        conversion_orders["order_ts"] = [max(pd.Timestamp(value), pd.Timestamp(signup_map[customer_id])).isoformat() for value, customer_id in zip(conversion_orders.order_ts, conversion_orders.customer_id)]
    orders = pd.concat([orders, conversion_orders], ignore_index=True)
    lines = pd.concat([lines, conversion_lines], ignore_index=True)
    if len(conversion_orders):
        net_by_customer = orders.groupby("customer_id").apply(lambda x: x.loc[x.order_type.eq("SALE"), "net_amount"].sum() - x.loc[x.order_type.eq("RETURN"), "net_amount"].sum(), include_groups=False)
        memberships["monetary_net_12m"] = memberships.customer_id.map(net_by_customer).fillna(memberships.monetary_net_12m).round(2)
        memberships["evidence"] = memberships.apply(lambda row: f"frequency_12m={int(row.frequency_12m)}; recency_days={int(row.recency_days)}; monetary_net_12m={float(row.monetary_net_12m):.2f}; r_score={int(row.r_score)}; f_score={int(row.f_score)}; m_score={int(row.m_score)}", axis=1)
    ground_truth = pd.DataFrame(columns=["ground_truth_id","entity_type","entity_id","customer_id","issue_type","expected_detection_rule","expected_decision","injected_field","original_value","injected_value","notes"])
    tables = {"Customer": customers, "Product": products, "SegmentRule": segments, "ActionCatalog": actions, "ActionEligibilityBridge": bridge,
              "OrderHeader": orders, "OrderLine": lines, "Consent": consent, "ConsentEvent": consent_events, "EngagementEvent": events,
              "SupportCase": support, "SegmentMembership": memberships, "SegmentMembershipSnapshot": snapshots, "SegmentMembershipEvent": membership_events, "CustomerStatusEvent": status_events,
              "ActionOutcome": outcomes}
    ground_truth = _inject_anomalies(tables, scale, rngs["anomalies"]) if inject else pd.DataFrame(columns=["ground_truth_id","entity_type","entity_id","customer_id","issue_type","expected_detection_rule","expected_decision","injected_field","original_value","injected_value","notes"])
    tables["ground_truth"] = ground_truth
    for name, frame in tables.items():
        frame.to_csv(out / f"{name}.csv", index=False, lineterminator="\n", float_format="%.2f")
        if len(frame) > 100_000:
            frame.to_json(out / f"{name}.ndjson", orient="records", lines=True)
    ground_truth.to_json(out / "ground_truth.json", orient="records", indent=2)
    def sql_value(value):
        if pd.isna(value): return "NULL"
        if isinstance(value, (int, float, np.integer, np.floating)): return str(value)
        return "'" + str(value).replace("'", "''") + "'"
    with (out / "seed.sql").open("w", encoding="utf-8", newline="\n") as seed_file:
        seed_file.write("-- Synthetic seed; generated deterministically.\nPRAGMA foreign_keys = ON;\n\n")
        for name, frame in tables.items():
            if name == "ground_truth" or frame.empty: continue
            columns = ", ".join(frame.columns)
            for row in frame.itertuples(index=False, name=None):
                seed_file.write(f"INSERT INTO {name} ({columns}) VALUES ({', '.join(sql_value(v) for v in row)});\n")
    shutil.copyfile(Path(__file__).resolve().parents[2] / "docs" / "schema.sql", out / "schema.sql")
    shutil.copyfile(Path(__file__).resolve().parents[2] / "README.md", out / "README.md")
    from src.validate.checks import validate
    validation = validate(out)
    manifest = {"generator_version": "0.1.0", "seed": seed, "scale": scale, "as_of_date": AS_OF.isoformat(), "external_data": False, "row_counts": {k: len(v) for k,v in tables.items()}, "files": {}, "validation_status": validation["status"]}
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "source_manifest.json": manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--scale", choices=("starter", "full"), default="starter"); parser.add_argument("--seed", type=int, default=20261022); parser.add_argument("--out", type=Path, required=True); parser.add_argument("--clean", action="store_true", help="omit labelled anomaly injection")
    args = parser.parse_args(); manifest = generate(args.scale, args.seed, args.out, inject=not args.clean); print(json.dumps(manifest["row_counts"], indent=2))


if __name__ == "__main__": main()
