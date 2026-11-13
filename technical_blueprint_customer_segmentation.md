# Technical Blueprint: Explainable Customer Segmentation Dataset

Execution guide for Claude Code | Fixed seed 20261022 | As-of date 2026-10-22

## 1. Purpose and How to Use This Document

This document turns the task brief into (a) a set of design decisions that remove ambiguity, (b) a repository layout, (c) exact generation, rule and validation specs, and (d) a numbered sequence of prompts to paste into Claude Code. Work the prompts in order. Each prompt ends with an acceptance check; do not move on until it passes.

Deliverables: a parameterized Python generator, 11 entity tables (plus 3 supporting history tables), a separate ground_truth file, a validator, exports (CSV, NDJSON, SQL), README, data dictionary, source manifest, validation summary and a reproducibility report.

## 2. Key Design Decisions (Resolve Ambiguity Up Front)

| Topic | Decision |
|---|---|
| Language / libs | Python 3.11+, numpy, pandas, pytest. No network calls, no external data (so provenance is fully synthetic; source manifest states this). |
| Determinism | One root seed 20261022. Use numpy SeedSequence.spawn to give each module (customers, products, orders, events, support, consent, outcomes, anomalies) its own child generator, so changing one module does not shift others. No wall-clock time, no unordered set iteration, no Python hash(). Fixed as-of date 2026-10-22 replaces now(). |
| Scale | Config key scale with presets: starter = 2,000 customers / 8,000 orders / 40,000 events; full = 50,000 / 200,000 / 1,000,000. Ratios (1 : 4 : 20) are identical so the same code runs both. |
| History window | 2024-10-23 to 2026-10-22 (24 months). Customers may have signup dates before the window (tenure), but all orders and events fall inside it. |
| ID year token | The 2026 in ORD-2026-, SEG-2026-, ACTN-2026- is the fixed program year (the as-of year), not the row date. One global zero-padded counter per entity. IDs immutable and generated in sorted creation order. |
| ID mapping | CUS-000001 = Customer; ORD-2026-000001 = Order; SEG-2026-000001 = SegmentRule; MEM-SEG-2026-000003-CUS-000123 = SegmentMembership (one row per segment-customer pair); ACTN-2026-000001 = ActionOutcome (one recommendation instance). Other entities use: PRD-00001 (Product), ORL-2026-0000001 (OrderLine), EVT-0000001 (EngagementEvent), CAS-000001 (SupportCase), CON-000001 (Consent record), AC-xxx natural code (ActionCatalog). State these extras in the data dictionary. |
| Returns | Returns are separate Order rows with order_type = RETURN and related_order_id pointing to the original sale; lines carry line_type = RETURN and original_order_line_id. Net spend = SALE totals minus RETURN totals. Never stored as negative quantity. |
| History, not overwrites | Consent is append-only (new row per change, old row gets effective_to). Segment changes are logged in SegmentMembershipEvent (ENTER, EXIT). SegmentMembership is the current-state projection and holds the explainability evidence. Customer lifecycle changes are logged in CustomerStatusEvent. |
| Ground truth isolation | Input tables never contain issue_type, is_anomaly or label columns. All labels live in ground_truth.csv/json keyed by entity type + entity ID. The validator and any evaluation code must not import ground truth during detection; only the scoring script may read it. |

## 3. Repository Layout

```
project/
  CLAUDE.md                  # standing instructions for Claude Code (section 11)
  config/scale.yaml          # presets, seed, as_of_date, distribution params, thresholds
  config/rules.yaml          # RFM cutoffs, segment rules, action eligibility, suppression
  src/gen/
    ids.py  rng.py  config.py
    master.py                # Product, Customer, ActionCatalog, SegmentRule
    transactions.py          # Order, OrderLine, returns
    events.py                # EngagementEvent
    support.py               # SupportCase
    consent.py               # Consent + ConsentEvent history
    segmentation.py          # RFM + rule engine -> memberships + events
    actions.py               # eligibility, suppression, recommendations, outcomes
    anomalies.py             # labelled injection + ground_truth writer
    export.py                # CSV, NDJSON, SQL, manifest
  src/validate/checks.py     # all checks, one function per rule
  src/eval/score.py          # metrics + anomaly detection scoring vs ground truth
  docs/data_dictionary.md  docs/data_dictionary.csv  docs/schema.sql
  tests/                     # pytest for each module
  out/{starter,full}/        # generated data (gitignored except manifests)
  README.md  Makefile
```

Command contract: `python -m src.gen.run --scale full --seed 20261022 --out out/full` and the same with `--scale starter`.

## 4. Data Model

### 4.1 Entities, keys and relationships

| Entity | PK | Foreign keys | Notes |
|---|---|---|---|
| Customer | customer_id | none | Lifecycle state: NEW, ACTIVE, DORMANT, CHURNED, SUPPRESSED (current), history in CustomerStatusEvent |
| Product | product_id | none | Taxonomy: category_l1 / category_l2, SKU, list_price, unit_cost, launch_date, discontinued_date (optional) |
| Order | order_id | customer_id, related_order_id (nullable, self) | order_type SALE or RETURN; status lifecycle; totals derived from lines |
| OrderLine | order_line_id | order_id, product_id, original_order_line_id (nullable, self) | line_type SALE or RETURN |
| EngagementEvent | event_id | customer_id, action_id (nullable ACTN id for campaign-driven events), product_id (nullable) | event_type, channel, event_ts |
| SupportCase | case_id | customer_id, order_id (nullable) | severity, status lifecycle, handle_minutes, cost_amount derived |
| Consent | consent_id | customer_id | channel x purpose, status GRANTED or WITHDRAWN, effective_from, effective_to |
| SegmentRule | segment_id | none | exclusive_group, priority, rule expression, version, effective dates |
| SegmentMembership | membership_id | segment_id, customer_id | current state, evidence columns, effective_from/to |
| ActionCatalog | action_code | none | channel, purpose, eligible segments, cooldown, cost, active flag |
| ActionOutcome | action_outcome_id (ACTN-2026-...) | customer_id, action_code, segment_id, membership_id, attributed_order_id (nullable) | decision RECOMMENDED, SUPPRESSED, SENT, with outcome status |

Supporting tables: SegmentMembershipEvent (PK event id, FK membership_id), CustomerStatusEvent, ConsentEvent (optional mirror of changes), and ActionEligibilityBridge.

### 4.2 Cardinality

- Customer 1:N Order, SupportCase, EngagementEvent, Consent, SegmentMembership, ActionOutcome.
- Order 1:N OrderLine. Order (RETURN) N:1 Order (SALE) for related_order_id. OrderLine (RETURN) N:1 OrderLine (SALE).
- Product 1:N OrderLine.
- SegmentRule 1:N SegmentMembership. Customer N:M SegmentRule resolved by SegmentMembership (bridge, with effective dates).
- ActionCatalog N:M SegmentRule resolved by ActionEligibilityBridge (action_code, segment_id, effective dates).
- ActionCatalog 1:N ActionOutcome. ActionOutcome N:0..1 Order (attribution is optional).
- SupportCase N:0..1 Order (optional).

### 4.3 Key fields to include in the data dictionary

The data dictionary (docs/data_dictionary.md and .csv) must list for every field: name, type, required/optional, allowed values, unit, uniqueness, validation rule. Minimum fields:

- **Customer**: customer_id, signup_date, country, region, age_band, acquisition_channel, preferred_channel, tier (STANDARD, PLUS, PREMIUM), lifecycle_state, is_test_account. No raw PII; use synthetic hashed email token only.
- **Order**: order_id, customer_id, order_ts, order_type, status (PLACED, SHIPPED, DELIVERED, CANCELLED, RETURN_COMPLETED), currency (single currency, INR or USD, documented), gross_amount, discount_amount, net_amount, related_order_id.
- **OrderLine**: quantity (integer >= 1), unit_price, discount, line_total = quantity x unit_price - discount, line_type.
- **EngagementEvent**: event_type (EMAIL_SENT, EMAIL_OPEN, EMAIL_CLICK, SMS_SENT, WEB_VISIT, PRODUCT_VIEW, CART_ADD, APP_SESSION, UNSUBSCRIBE), channel (EMAIL, SMS, WEB, APP, PUSH), event_ts.
- **SupportCase**: severity (LOW, MEDIUM, HIGH, CRITICAL), status (OPEN, IN_PROGRESS, RESOLVED, CLOSED, REOPENED), opened_at <= resolved_at <= closed_at, handle_minutes, cost_amount = handle_minutes x agent_rate_by_severity, csat (1 to 5, optional).
- **Consent**: channel (EMAIL, SMS, PUSH, PHONE), purpose (MARKETING, SERVICE), status, effective_from, effective_to (null if current), source.
- **SegmentRule**: segment_id, segment_name, exclusive_group (LIFECYCLE or null), priority, rule_expression (human readable), rule_version, effective_from, effective_to.
- **SegmentMembership**: membership_id, recency_days, frequency_12m, monetary_net_12m, r_score, f_score, m_score, rule_matched, evidence text, effective_from, effective_to, status (ACTIVE, EXITED).
- **ActionCatalog**: action_code, channel, purpose, cooldown_days, unit_cost, requires_consent_channel, allowed_segments.
- **ActionOutcome**: recommended_at, decision (RECOMMENDED, SUPPRESSED, SENT), suppression_reason, sent_at, outcome (NONE, OPENED, CLICKED, CONVERTED, UNSUBSCRIBED), outcome_at, attributed_order_id, attribution_window_days, control_group_flag.

## 5. Generation Pipeline (Strict Order)

1. **Config and RNG** - load config, spawn child generators.
2. **Master data** - Product (about 400 SKUs across 8 categories, 3 to 6 subcategories each), ActionCatalog (about 14 actions), SegmentRule (about 10 segments), Customer (50,000).
3. **Customer behavior archetypes (hidden driver, not exported)** - assign each customer an archetype that drives behavior: NEW (12%), ACTIVE_CORE (45%), BIG_SPENDER (8%), DORMANT (18%), CHURNED (10%), HIGH_SERVICE (7%). Archetype is internal only and never written to input tables. It controls order rate, engagement rate and support rate so correlations are realistic.
4. **Orders and lines** - draw order counts from a negative binomial or lognormal-driven Poisson per archetype (mean about 4 orders per customer, heavy tail), spread timestamps with weekly and holiday seasonality, ensure order_ts >= signup_date. 1 to 6 lines per order (mean about 2.5). Product choice uses a Zipf-like popularity. About 6% of customers' orders get a return order, 30-day max gap, returned quantity <= remaining sold quantity. Compute Order totals from lines only.
5. **Consent** - initial state per customer (about 70% email marketing granted, 40% SMS, 55% push), append-only history; about 4% withdraw during the window (new row with WITHDRAWN, old row closed). Withdrawal date is a real timestamp that later steps must respect.
6. **Engagement events** - about 1M. Event counts per customer follow lognormal x archetype multiplier. EMAIL_SENT and SMS_SENT only when an active marketing consent covers that moment; opens and clicks are children of sends (open prob 0.22, click-given-open 0.18, modifiable per segment). Browsing events precede some orders (session within 7 days before order for about 40% of orders), so engagement and purchase correlate.
7. **Support cases** - about 0.3 per customer, HIGH_SERVICE archetype about 2.5x rate, severity mix 55/30/12/3, lifecycle timestamps consistent, cost derived. Cases can reference an order, which must belong to the same customer.
8. **Segmentation** - section 6, run at monthly snapshots to build history events, then keep the as-of state as SegmentMembership.
9. **Actions** - section 7: recommend, apply eligibility and suppression, simulate sends, generate outcomes from the documented response model, attribute orders.
10. **Anomaly injection** - section 8. Done last, on copies of valid rows, each logged to ground truth.
11. **Validation, export, reproducibility** - sections 9 and 10.

### Distribution targets (check in validation summary)

- Orders per customer: median 2 to 3, p95 above 12, about 15 to 20% with zero orders in the last 12 months.
- Order value: lognormal, median near 60 currency units, p99 at least 10x median.
- Return rate by order about 6% (by value 5 to 8%); higher in apparel-type categories than consumables.
- New customers (signup within 90 days of as-of) about 12%; dormant (no order or event in 180 days) 15 to 20%.
- Consent withdrawal 3 to 5%; high-service-cost accounts (top decile of cost per net spend) about 7 to 10%.

## 6. Segmentation Logic (Explainable by Construction)

All thresholds live in config/rules.yaml and each membership row stores the evidence used.

**Metrics (computed from source rows at the snapshot date, 12-month lookback):**

- recency_days = snapshot - last SALE order date.
- frequency_12m = count of SALE orders.
- monetary_net_12m = sum of SALE net_amount minus sum of RETURN net_amount.
- R, F, M scores 1 to 5 via fixed quantile cutoffs computed once on the as-of snapshot and written to config output (so scoring is reproducible and boundaries are documented). Boundary rule: value equal to a cutoff goes to the higher score.
- service_cost_ratio = 12-month support cost / max(monetary_net_12m, 1).

**Exclusive LIFECYCLE group (exactly one ACTIVE membership per customer, priority order top to bottom):**

| Priority | Segment | Rule |
|---|---|---|
| 1 | CONSENT_SUPPRESSED | all marketing consents WITHDRAWN or none granted |
| 2 | NEW | signup within 90 days and frequency_12m <= 1 |
| 3 | CHAMPIONS | R >= 4, F >= 4, M >= 4 |
| 4 | LOYAL | R >= 3, F >= 3 |
| 5 | AT_RISK | recency 120 to 270 days and prior frequency >= 3 |
| 6 | DORMANT | recency > 270 days and frequency_12m = 0 |
| 7 | PROMISING | everything else active |

**Non-exclusive overlays:** HIGH_SERVICE_COST (service_cost_ratio >= 0.15 or 3+ cases in 90 days), HIGH_RETURNER (return value ratio >= 0.30), VALUE_TIER_PREMIUM (top 10% monetary_net_12m).

Each month-end snapshot recomputes the lifecycle segment. A change closes the old membership via SegmentMembershipEvent EXIT and opens ENTER with effective dates; nothing is deleted. Add a test that the engine reproduces every stored lifecycle membership from source data (this is the acceptance criterion: segment membership follows rules).

## 7. Actions, Eligibility, Suppression and Outcomes

**Catalog examples (about 14):** WELCOME_SERIES (NEW, email), UPSELL_BUNDLE (CHAMPIONS, email), LOYALTY_REWARD (LOYAL, push), WINBACK_DISCOUNT (AT_RISK, email or SMS), REACTIVATION_SURVEY (DORMANT, email), SERVICE_OUTREACH (HIGH_SERVICE_COST, phone, SERVICE purpose), RETURN_POLICY_TIPS (HIGH_RETURNER, email), NO_ACTION_SUPPRESS (CONSENT_SUPPRESSED).

**Eligibility (all must be true):**

1. Customer's ACTIVE lifecycle segment is in the action's allowed segments (via bridge table).
2. Active consent exists for the action's channel and purpose at recommended_at.
3. Action active on that date; customer is not is_test_account.

**Suppression rules (each logged with a reason code, producing the main exception path):**

- NO_CONSENT: consent absent or withdrawn at recommend time.
- FREQUENCY_CAP: more than 2 marketing contacts in 7 days or 6 in 30 days.
- COOLDOWN: same action sent within cooldown_days.
- OPEN_SERVICE_CASE: HIGH or CRITICAL case not CLOSED, or CSAT <= 2 within 14 days.
- RECENT_RETURN_DISPUTE: marketing action in the 7 days after a return for HIGH_RETURNER (optional rule).

Suppressed recommendations are still written to ActionOutcome with decision = SUPPRESSED and no sent_at, so suppression volume is measurable.

**Outcome simulation (derived, not independent random):** for each SENT action, response probability p = logistic(b0 + b_action + b_segment + b_recency x recency + b_engagement x opens_90d - b_service x open_case), with coefficients stored in config/rules.yaml. Draw OPEN, CLICK, CONVERT as nested events from p using the module's RNG. A CONVERTED outcome creates (or links to) a real SALE order inside the attribution window (14 days from sent_at) whose order_ts follows outcome_at. Reserve 10% of eligible customers per action as a control group (control_group_flag = true, no send) with a lower baseline conversion, enabling uplift calculation.

Attribution rule: an order is attributed to the most recent SENT action for that customer within 14 days before the order, same customer only. Store attributed_order_id and the rule name used.

## 8. Labelled Edge Cases and Ground Truth

Inject anomalies after the clean baseline, by copying or modifying a bounded set of rows, and record each in ground_truth.csv. Counts are config parameters (defaults for full scale shown):

| issue_type | How to inject | Default count |
|---|---|---|
| CONFLICTING_EXCLUSIVE_SEGMENTS | add a second ACTIVE LIFECYCLE membership (valid IDs) for a customer | 150 |
| ACTION_VIOLATES_CONSENT | a SENT ActionOutcome after the customer's consent WITHDRAWN effective_from (also emit the matching EMAIL_SENT event) | 300 |
| RETURN_NOT_NETTED | a membership whose monetary_net_12m equals gross sales, ignoring returns | 200 |
| OUTCOME_WRONG_ACTION | an outcome whose attributed_order_id is tied to a different action or outside the 14-day window or other customer's order | 250 |

Also add boundary cases (not anomalies, label type BOUNDARY_VALID): customers exactly at 90 days signup, R/F/M cutoffs, return on day 30, consent withdrawn the same day as a send but after it.

ground_truth.csv columns: ground_truth_id, entity_type, entity_id, customer_id, issue_type, expected_detection_rule, expected_decision (for example FLAG, SUPPRESS, VALID), injected_field, original_value, injected_value, notes. Also include a ground truth section for expected decisions (for example, which customers must be suppressed by which rule). Keep it outside any feature file; the export step must assert no ground truth column names appear in any input table.

## 9. Validation (src/validate/checks.py)

Each check returns pass/fail, count, and sample offending IDs. Run it twice: against the clean baseline (all must pass) and against the final dataset (only labelled anomalies may fail, and the failures must match ground truth exactly).

- Primary key uniqueness and ID format regex for every table (zero-padded, correct prefixes).
- Foreign key integrity for every relationship in section 4.1.
- Allowed enum values per field.
- Date ordering: order_ts >= signup_date, return after original order, case timestamps ascending, consent effective_from < effective_to, outcome_at >= sent_at.
- Arithmetic: line_total, Order totals equal sum of lines, case cost, monetary_net_12m equals recomputed value.
- Return integrity: returned quantity <= sold quantity per original line.
- Lifecycle: one ACTIVE LIFECYCLE membership per customer; legal status transitions; no events after effective_to.
- Consent: no SENT action or marketing send inside a WITHDRAWN window (baseline).
- Duplicates: no duplicate natural keys (customer + order_ts + lines) or duplicate events.
- Segment rule re-derivation matches stored memberships.
- Distribution checks against section 5 targets.

Write results to validation_summary.json and .md.

## 10. Exports, Metrics and Reproducibility

**Exports (per scale):** CSV for every table (UTF-8, LF line endings, sorted by PK, fixed column order, fixed float formatting), NDJSON for the large tables, schema.sql (PostgreSQL and SQLite compatible DDL with PK/FK constraints) and seed.sql (full INSERTs for starter; for full, batched INSERTs or a COPY script), data_dictionary.md/csv, source_manifest.json (generator version, seed, scale, parameters, file list, row counts, SHA-256 per file, statement that no external data is used), README.md.

**Evaluation metrics (src/eval/score.py):** segment rule conformance rate; metric reconciliation difference (should be 0 on the baseline); suppression rate by reason; consent violation count (0 baseline); response and conversion rate by action and segment; uplift versus control group; precision and recall of the validator against ground truth by issue_type; share of recommendations with complete audit trail (segment, rule version, evidence, consent state).

**Reproducibility:** `make repro` generates the dataset twice into separate folders with the same seed, then compares row counts and SHA-256 checksums and writes reproducibility_report.md. Any mismatch is a failure. Also run starter with a different seed to prove the seed changes the data.

## 11. Claude Code Execution Plan

### 11.1 Setup

Create the project folder, run `claude` in it, enable plan mode for Prompt 1, and create CLAUDE.md as below. Commit after each prompt.

**CLAUDE.md content:**

```
Project: synthetic customer segmentation dataset (seed 20261022, as-of 2026-10-22).
Rules:
- Fully deterministic. Use numpy SeedSequence children per module. No datetime.now, no random module, no set iteration ordering.
- Same code for starter and full via --scale. Never hardcode 50000/200000/1000000 outside config.
- Generate parents before children. Every derived value (totals, scores, statuses) is computed from source rows.
- Never overwrite history; state changes are new rows/events.
- Ground truth is only in ground_truth.csv/json; never add label columns to input tables.
- IDs follow the nomenclature in docs; counters zero-padded and immutable.
- Run pytest and python -m src.validate.checks before saying a step is done.
- Use vectorized numpy/pandas; full run must finish in under 15 minutes.
```

### 11.2 Prompts to paste (in order)

**Prompt 1 - Scaffold and spec.** Read this blueprint. Create the repository layout from section 3, config/scale.yaml (starter and full presets, seed, as_of_date, history window) and config/rules.yaml (segment cutoffs, suppression thresholds, action coefficients). Write ids.py (formatters and regex for every ID type) and rng.py (SeedSequence child generators per module). Add unit tests for ID formats and for RNG determinism. Acceptance: pytest passes.

**Prompt 2 - Schema and data dictionary.** Write docs/schema.sql with PK, FK, CHECK constraints for all 11 entities plus SegmentMembershipEvent, CustomerStatusEvent and ActionEligibilityBridge. Generate docs/data_dictionary.md and .csv with, for each field, type, required/optional, allowed values, unit, uniqueness and validation rule. Include cardinality table and lifecycle state diagrams in text. Acceptance: schema loads into SQLite without error; every column in the DDL is in the dictionary.

**Prompt 3 - Master data.** Implement master.py: Product taxonomy, ActionCatalog, SegmentRule (versioned, effective dated), ActionEligibilityBridge and Customer with hidden archetypes (kept in an internal dataframe, not exported). Include new, dormant, churned, high-service archetypes in the target proportions. Acceptance: PK uniqueness, archetype proportions within 1 percentage point of target.

**Prompt 4 - Orders, lines and returns.** Implement transactions.py following section 5 step 4. Totals must be computed from lines. Include returns referencing original lines with quantity limits. Acceptance: arithmetic reconciliation and return integrity tests pass; distribution summary printed against targets.

**Prompt 5 - Consent, events and support.** Implement consent.py (append-only history with withdrawals), events.py (about 1M at full scale, sends only under valid consent, opens and clicks as children of sends, browsing before orders) and support.py (lifecycle timestamps, derived cost). Acceptance: no marketing send in a withdrawn window; all FKs valid; event count within 2% of target.

**Prompt 6 - Segmentation engine.** Implement segmentation.py per section 6 with monthly snapshots, SegmentMembershipEvent history and current SegmentMembership with evidence fields. Write a standalone re-derivation test that recomputes memberships from source tables. Acceptance: 100% conformance, exactly one ACTIVE lifecycle segment per customer on the baseline.

**Prompt 7 - Actions and outcomes.** Implement actions.py per section 7: eligibility, suppression reasons, frequency caps, control group, response model with logistic coefficients from rules.yaml, conversions that create linked orders, attribution within 14 days. Acceptance: zero consent violations on baseline, suppression reasons all present, uplift positive for at least the main actions.

**Prompt 8 - Anomaly injection and ground truth.** Implement anomalies.py per section 8, writing ground_truth.csv and ground_truth.json plus boundary cases. Acceptance: counts match config, every injected ID exists, and a test asserts that no input table has columns named issue_type, ground_truth or is_anomaly.

**Prompt 9 - Validator and scoring.** Implement checks.py (section 9) and score.py (section 10 metrics). The validator must detect all four anomaly types without reading ground truth; score.py compares findings against ground truth and reports precision and recall per issue_type. Acceptance: baseline fully clean; final dataset failures equal injected anomalies (precision and recall at least 0.99).

**Prompt 10 - Export, manifest, reproducibility.** Implement export.py (CSV, NDJSON, SQL, manifest with SHA-256) and the Makefile targets `starter`, `full`, `validate`, `repro`. Run repro for starter and full. Acceptance: reproducibility_report.md shows identical row counts and checksums across two runs.

**Prompt 11 - Documentation.** Write README.md covering the exact generator command, seed, parameters, folder structure, ID conventions, how anomalies and ground truth are separated, validation summary, known limits, and lawful provenance (fully synthetic, no external data, no personal information). Produce a final validation_summary.md. Acceptance: a fresh clone can run `make starter` and `make validate` from the README alone.

### 11.3 Tips for working with Claude Code

- Start with the starter scale and only run full after all tests pass.
- If a prompt is large, ask Claude Code to implement it in two commits (code, then tests).
- If any validation fails, tell Claude Code to fix the generator rule, never patch output files.
- Ask it to profile runtime and memory at full scale; use chunked writes for events if memory is high.

## 12. Final Acceptance Checklist

- [ ] 50,000 customers, 200,000 orders, about 1,000,000 events at full scale; starter uses same code.
- [ ] All IDs follow the nomenclature; all PK and FK checks pass.
- [ ] Derived values reconcile to source rows (totals, net spend, scores, costs).
- [ ] Segment membership re-derives from rules; evidence stored for explainability.
- [ ] Consent and frequency constraints enforced; suppression reasons logged.
- [ ] Outcomes derive from the documented response model; attribution rule documented; control group present.
- [ ] Four required anomaly types injected, labelled and separated in ground_truth files.
- [ ] Validator catches all injected anomalies; baseline is clean.
- [ ] Two same-seed runs match on counts and checksums.
- [ ] README, data dictionary, schema, source manifest, validation summary delivered.
