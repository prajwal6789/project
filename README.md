# Explainable Customer Segmentation Dataset

Deterministic synthetic customer-segmentation data generator based on the technical blueprint. It uses seed `20261022`, fixed as-of date `2026-10-22`, and no external data or personal information.

## Run

```powershell
py -m src.gen.run --scale starter --seed 20261022 --out out/starter
py -m src.validate.checks out/starter
py -m pytest -q
```

Use the Make targets for the complete delivery workflow:

```powershell
make starter
make clean
make full
make repro
```

`make full` creates the 50,000-customer / 1,000,000-event release. `make repro` runs two full-scale clean builds with the same seed plus a starter build with a different seed, then writes the file-by-file comparison to `out/reproducibility_report.md`. No wall-clock timestamp is written to generated data or the report.

Generated CSV files, large-table NDJSON, `seed.sql`, `schema.sql`, `source_manifest.json`, and detailed validation summaries are written to the selected output folder at both scales. Ground truth is stored separately in `ground_truth.csv` and `ground_truth.json`; input tables do not contain `issue_type`, `ground_truth`, or `is_anomaly` columns.

## Validation

`validation_summary.json` contains the structural checks, semantic checks, measured metrics, configured targets, violation counts, and detailed findings. `evaluation_summary.json` contains anomaly detection precision and recall by issue type.

The validator checks primary keys, duplicate rows, ID formats, foreign keys, enums, order arithmetic, return quantities and dates, signup ordering, consent and support dates, consent-at-send, lifecycle exclusivity, segment rule re-derivation, membership spend reconciliation, attribution, outcome/customer consistency, recommendation/send ordering, status transitions, and distribution targets.

Distribution targets are configured in `config/rules.yaml`: CHAMPIONS 5–15% of lifecycle memberships; DORMANT 15–20%; NEW 10–15%; return value 5–8%; marketing withdrawals 3–5%; order lines/order 1.8–3.2; all-time zero-order customers 15–20%; HIGH_SERVICE_COST 7–10%; median orders/customer 2–5; p95 orders/customer at least 10.

## IDs and ground truth

Customers use `CUS-######`, orders use `ORD-YYYY-######`, events use `EVT-#######`, order lines use `ORL-#######`, actions use catalog codes in `ActionCatalog`, and memberships use `MEM-<segment-number>-<customer-number>`. The labelled anomaly file is separate from all input tables and is used only by `src/eval/score.py` for evaluation.

Generate a clean baseline without injected anomalies with `--clean`; use this for baseline validation before comparing the labelled final dataset.

```powershell
py -m src.gen.run --scale starter --seed 20261022 --out out/clean --clean
py -m src.validate.checks out/clean
```
