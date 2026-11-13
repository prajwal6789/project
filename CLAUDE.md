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
