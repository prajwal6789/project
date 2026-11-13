"""Ground-truth-independent structural validator."""
from pathlib import Path
import json
import pandas as pd
from src.gen.ids import PATTERNS
from src.gen.config import load_yaml


def validate(folder: Path) -> dict:
    rules_config = load_yaml("rules.yaml")
    results = []
    tables = {}
    semantic = []
    findings = []
    id_patterns = {"Customer": "customer", "Product": "product", "OrderHeader": "order", "OrderLine": "order_line", "EngagementEvent": "event", "SupportCase": "support_case", "Consent": "consent", "SegmentRule": "segment", "SegmentMembership": "membership", "ActionOutcome": "action_outcome"}
    for path in sorted(folder.glob("*.csv")):
        if path.name == "ground_truth.csv": continue
        frame = pd.read_csv(path)
        tables[path.stem] = frame
        key = frame.columns[0] if len(frame.columns) else None
        if path.stem == "ActionEligibilityBridge" and {"action_code", "segment_id", "effective_from"} <= set(frame.columns):
            unique = not frame.duplicated(["action_code", "segment_id", "effective_from"]).any()
            key = "action_code+segment_id+effective_from"
        else:
            unique = bool(key is not None and frame[key].notna().all() and frame[key].is_unique)
        labels_absent = not bool(set(frame.columns) & {"issue_type", "ground_truth", "is_anomaly"})
        results.append({"table": path.stem, "rows": len(frame), "primary_key": key, "primary_key_unique": unique, "label_columns_absent": labels_absent})
        duplicate_rows = int(frame.duplicated().sum())
        semantic.append({"check": f"duplicate_rows:{path.stem}", "violations": duplicate_rows, "status": "PASS" if duplicate_rows == 0 else "FAIL"})
        if path.stem in id_patterns and key:
            invalid = int((~frame[key].fillna("").astype(str).map(lambda value: bool(PATTERNS[id_patterns[path.stem]].fullmatch(value)))).sum())
            semantic.append({"check": f"id_format:{path.stem}", "violations": invalid, "status": "PASS" if invalid == 0 else "FAIL"})
    def fk(child, field, parent, parent_field):
        if child not in tables or parent not in tables: return
        values = set(tables[parent][parent_field].dropna())
        bad = tables[child][field].dropna().map(lambda x: x not in values).sum()
        semantic.append({"check": f"fk:{child}.{field}", "violations": int(bad), "status": "PASS" if bad == 0 else "FAIL"})
    fk("OrderHeader", "customer_id", "Customer", "customer_id"); fk("OrderLine", "order_id", "OrderHeader", "order_id"); fk("OrderLine", "product_id", "Product", "product_id")
    fk("Consent", "customer_id", "Customer", "customer_id")
    fk("SupportCase", "customer_id", "Customer", "customer_id"); fk("SupportCase", "order_id", "OrderHeader", "order_id")
    fk("EngagementEvent", "customer_id", "Customer", "customer_id"); fk("EngagementEvent", "action_id", "ActionOutcome", "action_outcome_id"); fk("EngagementEvent", "product_id", "Product", "product_id")
    fk("SegmentMembership", "customer_id", "Customer", "customer_id"); fk("SegmentMembership", "segment_id", "SegmentRule", "segment_id")
    fk("SegmentMembershipSnapshot", "customer_id", "Customer", "customer_id"); fk("SegmentMembershipSnapshot", "segment_id", "SegmentRule", "segment_id")
    fk("ActionOutcome", "customer_id", "Customer", "customer_id"); fk("ActionOutcome", "action_code", "ActionCatalog", "action_code")
    if {"OrderHeader", "OrderLine"} <= tables.keys():
        line_totals = tables["OrderLine"].groupby("order_id").line_total.sum()
        order_totals = tables["OrderHeader"].set_index("order_id").net_amount
        diff = (order_totals - line_totals.reindex(order_totals.index).fillna(0)).abs()
        semantic.append({"check": "order_total_reconciliation", "violations": int((diff > .01).sum()), "status": "PASS" if (diff <= .01).all() else "FAIL"})
    if {"OrderHeader", "OrderLine"} <= tables.keys():
        sales = tables["OrderLine"][tables["OrderLine"].line_type.eq("SALE")].groupby("order_line_id").quantity.sum()
        returns = tables["OrderLine"][tables["OrderLine"].line_type.eq("RETURN")]
        bad_returns = int(sum(row.quantity > sales.get(row.original_order_line_id, 0) for row in returns.itertuples()))
        semantic.append({"check": "return_quantity_integrity", "violations": bad_returns, "status": "PASS" if bad_returns == 0 else "FAIL"})
        if "Customer" in tables:
            signup = tables["Customer"].set_index("customer_id").signup_date
            order_dates = pd.to_datetime(tables["OrderHeader"].order_ts, format="mixed")
            signup_dates = pd.to_datetime(tables["OrderHeader"].customer_id.map(signup), format="mixed")
            bad_signup = int((order_dates < signup_dates).sum())
            semantic.append({"check": "order_after_signup", "violations": bad_signup, "status": "PASS" if bad_signup == 0 else "FAIL"})
        order_lookup_dates = tables["OrderHeader"].set_index("order_id").order_ts
        bad_return_dates = int(sum(pd.Timestamp(row.order_ts) <= pd.Timestamp(order_lookup_dates.get(row.related_order_id)) for row in tables["OrderHeader"].query("order_type == 'RETURN'").itertuples() if row.related_order_id in order_lookup_dates))
        semantic.append({"check": "return_after_sale", "violations": bad_return_dates, "status": "PASS" if bad_return_dates == 0 else "FAIL"})
    if "Consent" in tables:
        consent = tables["Consent"]
        starts = pd.to_datetime(consent["effective_from"], errors="coerce", format="mixed")
        ends = pd.to_datetime(consent["effective_to"], errors="coerce", format="mixed")
        bad = int((ends.notna() & (ends < starts)).sum())
        semantic.append({"check": "consent_date_ordering", "violations": bad, "status": "PASS" if bad == 0 else "FAIL"})
    if "SupportCase" in tables:
        support = tables["SupportCase"]
        opened = pd.to_datetime(support["opened_at"], errors="coerce", format="mixed")
        resolved = pd.to_datetime(support["resolved_at"], errors="coerce", format="mixed")
        closed = pd.to_datetime(support["closed_at"], errors="coerce", format="mixed")
        bad = int(((resolved.notna() & (resolved < opened)) | (closed.notna() & (closed < opened)) | (closed.notna() & resolved.notna() & (closed < resolved))).sum())
        semantic.append({"check": "support_date_ordering", "violations": bad, "status": "PASS" if bad == 0 else "FAIL"})
    if {"ActionOutcome", "Consent"} <= tables.keys():
        withdrawn = tables["Consent"][tables["Consent"].status.eq("WITHDRAWN")][["customer_id", "effective_from"]].rename(columns={"effective_from": "withdrawal_at"})
        closed_grants = tables["Consent"][tables["Consent"].status.eq("GRANTED") & tables["Consent"].effective_to.notna()][["customer_id", "effective_to"]].rename(columns={"effective_to": "withdrawal_at"})
        withdrawn = pd.concat([withdrawn, closed_grants], ignore_index=True)
        sent = tables["ActionOutcome"][tables["ActionOutcome"].decision.eq("SENT")]
        if "ActionCatalog" in tables:
            sent = sent.merge(tables["ActionCatalog"][["action_code", "purpose"]], on="action_code", how="left")
            sent = sent[sent.purpose.eq("MARKETING")]
        violations = 0
        for row in sent.itertuples():
            end = withdrawn.loc[withdrawn.customer_id.eq(row.customer_id), "withdrawal_at"]
            if len(end) and any(pd.Timestamp(row.sent_at) >= pd.Timestamp(value) for value in end.dropna()):
                violations += 1; findings.append({"rule": "consent_violation", "entity_type": "ActionOutcome", "entity_id": row.action_outcome_id})
        semantic.append({"check": "marketing_consent_at_send", "violations": violations, "status": "PASS" if violations == 0 else "FAIL"})
    if {"SegmentMembership", "SegmentRule"} <= tables.keys():
        lifecycle = tables["SegmentRule"][tables["SegmentRule"].exclusive_group.eq("LIFECYCLE")][["segment_id"]]
        active = tables["SegmentMembership"].merge(lifecycle, on="segment_id")
        duplicate_groups = active.groupby("customer_id").size(); duplicate_customers = int((duplicate_groups > 1).sum())
        for customer_id in duplicate_groups[duplicate_groups > 1].index:
            findings.append({"rule": "one_active_lifecycle_segment", "entity_type": "SegmentMembership", "entity_id": active.loc[active.customer_id.eq(customer_id), "membership_id"].iloc[-1]})
        semantic.append({"check": "one_active_lifecycle_segment", "violations": duplicate_customers, "status": "PASS" if duplicate_customers == 0 else "FAIL"})
        if "Customer" in tables:
            signup = tables["Customer"].set_index("customer_id").signup_date
            active_consent = set(tables["Consent"].loc[(tables["Consent"].purpose == "MARKETING") & (tables["Consent"].status == "GRANTED") & tables["Consent"].effective_to.isna(), "customer_id"]) if "Consent" in tables else set()
            expected = []
            for row in active.itertuples(index=False):
                age = (pd.Timestamp("2026-10-22").date() - pd.Timestamp(signup[row.customer_id]).date()).days
                if row.customer_id not in active_consent: name = "CONSENT_SUPPRESSED"
                elif age <= 90 and row.frequency_12m <= 1: name = "NEW"
                elif row.r_score == 5 and row.f_score == 5 and row.m_score == 5: name = "CHAMPIONS"
                elif 120 <= row.recency_days <= 270 and row.frequency_12m >= 3: name = "AT_RISK"
                elif row.r_score >= 3 and row.f_score >= 3: name = "LOYAL"
                elif row.recency_days > 270 and row.frequency_12m == 0: name = "DORMANT"
                else: name = "PROMISING"
                expected.append(name != row.rule_matched)
            mismatch = int(sum(expected))
            semantic.append({"check": "segment_rule_rederivation", "violations": mismatch, "status": "PASS" if mismatch == 0 else "FAIL"})
    if {"SegmentMembership", "OrderHeader"} <= tables.keys():
        source = tables["OrderHeader"].groupby("customer_id").apply(lambda x: x.loc[x.order_type.eq("SALE"), "net_amount"].sum() - x.loc[x.order_type.eq("RETURN"), "net_amount"].sum(), include_groups=False)
        compared = tables["SegmentMembership"].merge(source.rename("expected_net"), left_on="customer_id", right_index=True, how="left")
        mismatch_mask = (compared.monetary_net_12m - compared.expected_net.fillna(0)).abs().gt(.01); mismatch = int(mismatch_mask.sum())
        findings.extend({"rule": "metric_reconciliation", "entity_type": "SegmentMembership", "entity_id": entity_id} for entity_id in compared.loc[mismatch_mask, "membership_id"])
        semantic.append({"check": "membership_net_spend_reconciliation", "violations": mismatch, "status": "PASS" if mismatch == 0 else "FAIL"})
    if {"ActionOutcome", "OrderHeader"} <= tables.keys():
        order_lookup = tables["OrderHeader"].set_index("order_id")
        bad = 0
        for row in tables["ActionOutcome"].dropna(subset=["attributed_order_id"]).itertuples():
            if row.attributed_order_id not in order_lookup.index:
                bad += 1; findings.append({"rule": "attribution_window_and_customer_match", "entity_type": "ActionOutcome", "entity_id": row.action_outcome_id}); continue
            linked = order_lookup.loc[row.attributed_order_id]
            if linked.customer_id != row.customer_id or pd.Timestamp(linked.order_ts) < pd.Timestamp(row.sent_at) or pd.Timestamp(linked.order_ts) > pd.Timestamp(row.sent_at) + pd.Timedelta(days=14):
                bad += 1; findings.append({"rule": "attribution_window_and_customer_match", "entity_type": "ActionOutcome", "entity_id": row.action_outcome_id})
        semantic.append({"check": "action_attribution_integrity", "violations": bad, "status": "PASS" if bad == 0 else "FAIL"})
    if {"ActionOutcome", "SegmentMembership"} <= tables.keys():
        membership_customer = tables["SegmentMembership"].set_index("membership_id").customer_id
        linked = tables["ActionOutcome"].dropna(subset=["membership_id"])
        mismatched = int(linked.customer_id.ne(linked.membership_id.map(membership_customer)).sum())
        semantic.append({"check": "outcome_membership_customer_match", "violations": mismatched, "status": "PASS" if mismatched == 0 else "FAIL"})
    if "ActionOutcome" in tables:
        sent_dates = pd.to_datetime(tables["ActionOutcome"].sent_at, errors="coerce", format="mixed")
        recommended_dates = pd.to_datetime(tables["ActionOutcome"].recommended_at, errors="coerce", format="mixed")
        bad_order = int((sent_dates.notna() & (sent_dates < recommended_dates)).sum())
        semantic.append({"check": "sent_after_recommended", "violations": bad_order, "status": "PASS" if bad_order == 0 else "FAIL"})
    enum_checks = {
        "Customer.tier": ("Customer", "tier", {"STANDARD", "PLUS", "PREMIUM"}),
        "OrderHeader.order_type": ("OrderHeader", "order_type", {"SALE", "RETURN"}),
        "Consent.status": ("Consent", "status", {"GRANTED", "WITHDRAWN"}),
        "ActionOutcome.decision": ("ActionOutcome", "decision", {"RECOMMENDED", "SUPPRESSED", "SENT"}),
    }
    for name, (table, column, allowed) in enum_checks.items():
        if table in tables:
            invalid = int((~tables[table][column].isin(allowed)).sum())
            semantic.append({"check": f"enum:{name}", "violations": invalid, "status": "PASS" if invalid == 0 else "FAIL"})
    if "CustomerStatusEvent" in tables:
        bad_transitions = 0
        for _, group in tables["CustomerStatusEvent"].sort_values("event_ts").groupby("customer_id"):
            previous = None
            for row in group.itertuples(index=False):
                if previous is not None and row.old_status != previous: bad_transitions += 1
                previous = row.new_status
        semantic.append({"check": "customer_status_transitions", "violations": bad_transitions, "status": "PASS" if bad_transitions == 0 else "FAIL"})
    if "OrderHeader" in tables and "Customer" in tables:
        sales = tables["OrderHeader"].query("order_type == 'SALE'")
        counts = sales.groupby("customer_id").size().reindex(tables["Customer"].customer_id, fill_value=0)
        as_of = pd.Timestamp("2026-10-22")
        recent = sales[pd.to_datetime(sales.order_ts, format="mixed").between(as_of - pd.Timedelta(days=365), as_of)]
        recent_counts = recent.groupby("customer_id").size().reindex(tables["Customer"].customer_id, fill_value=0)
        metrics = {"median_orders_per_customer": float(counts.median()), "p95_orders_per_customer": float(counts.quantile(.95)), "zero_order_share": float((counts == 0).mean()), "last12m_zero_order_share": float((recent_counts == 0).mean())}
        targets = rules_config["distribution_targets"]
        violations = int(not (targets["median_orders_per_customer"][0] <= metrics["median_orders_per_customer"] <= targets["median_orders_per_customer"][1])) + int(metrics["p95_orders_per_customer"] < targets["p95_orders_per_customer_min"]) + int(not (targets["last12m_zero_order_share"][0] <= metrics["last12m_zero_order_share"] <= targets["last12m_zero_order_share"][1]))
        customer_states = tables["Customer"].lifecycle_state.value_counts(normalize=True)
        lifecycle = tables["SegmentRule"].query("exclusive_group == 'LIFECYCLE'")["segment_id"]
        lifecycle_memberships = tables["SegmentMembership"].query("segment_id in @lifecycle")
        champion_share = float(lifecycle_memberships.rule_matched.eq("CHAMPIONS").mean())
        order_headers = tables["OrderHeader"]
        return_value_share = float(abs(order_headers.query("order_type == 'RETURN'").net_amount.sum()) / max(order_headers.query("order_type == 'SALE'").net_amount.sum(), 1))
        consent = tables.get("Consent", pd.DataFrame())
        marketing = consent[consent.purpose.eq("MARKETING")] if len(consent) else consent
        marketing_withdrawal = float(marketing.status.eq("WITHDRAWN").mean()) if len(marketing) else 0.0
        line_average = float(tables["OrderLine"].groupby("order_id").size().mean()) if "OrderLine" in tables else 0.0
        service_share = float(tables["SegmentMembership"].loc[tables["SegmentMembership"].segment_id.eq("SEG-2026-000008"), "customer_id"].nunique() / len(tables["Customer"]))
        metrics.update({"champions_lifecycle_share": champion_share, "lifecycle_dormant_share": float(customer_states.get("DORMANT", 0)), "lifecycle_new_share": float(customer_states.get("NEW", 0)), "return_value_share": return_value_share, "marketing_withdrawal_share": marketing_withdrawal, "order_lines_per_order": line_average, "zero_order_share": metrics["zero_order_share"], "high_service_cost_share": service_share})
        violations += int(not (targets["champions_lifecycle_share"][0] <= champion_share <= targets["champions_lifecycle_share"][1]))
        violations += int(not (targets["lifecycle_dormant_share"][0] <= metrics["lifecycle_dormant_share"] <= targets["lifecycle_dormant_share"][1]))
        violations += int(not (targets["lifecycle_new_share"][0] <= metrics["lifecycle_new_share"] <= targets["lifecycle_new_share"][1]))
        violations += int(not (targets["return_value_share"][0] <= return_value_share <= targets["return_value_share"][1]))
        violations += int(not (targets["marketing_withdrawal_share"][0] <= marketing_withdrawal <= targets["marketing_withdrawal_share"][1]))
        violations += int(not (targets["order_lines_per_order"][0] <= line_average <= targets["order_lines_per_order"][1]))
        violations += int(not (targets["zero_order_share"][0] <= metrics["zero_order_share"] <= targets["zero_order_share"][1]))
        violations += int(not (targets["high_service_cost_share"][0] <= service_share <= targets["high_service_cost_share"][1]))
        semantic.append({"check": "distribution_targets", "violations": violations, "status": "PASS" if violations == 0 else "FAIL", "metrics": metrics, "targets": targets})
    for check in semantic:
        if check["status"] != "FAIL":
            continue
        existing = sum(1 for finding in findings if finding.get("rule") == check["check"])
        for index in range(existing, int(check["violations"])):
            findings.append({"rule": check["check"], "entity_type": "Validation", "entity_id": f"{check['check']}-{index + 1:06d}"})
    passed = all(r["label_columns_absent"] and r["primary_key_unique"] for r in results) and all(r["status"] in ("PASS", "INFO") for r in semantic)
    report = {"status": "PASS" if passed else "FAIL", "checks": results, "semantic_checks": semantic, "findings": findings}
    (folder / "validation_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (folder / "validation_summary.md").write_text("# Validation summary\n\nStatus: **%s**\n\nGenerated tables contain no ground-truth label columns.\n" % report["status"], encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("folder", type=Path); args = p.parse_args(); print(json.dumps(validate(args.folder), indent=2))
