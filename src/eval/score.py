"""Lightweight evaluation metrics for generated outputs."""
from pathlib import Path
import json
import pandas as pd


def score(folder: Path) -> dict:
    outcomes = pd.read_csv(folder / "ActionOutcome.csv")
    memberships = pd.read_csv(folder / "SegmentMembership.csv")
    truth = pd.read_csv(folder / "ground_truth.csv")
    validation = json.loads((folder / "validation_summary.json").read_text(encoding="utf-8")) if (folder / "validation_summary.json").exists() else {}
    findings = pd.DataFrame(validation.get("findings", []))
    detection_scores = {}
    for issue, group in truth.groupby("issue_type") if len(truth) else []:
        expected = set(group.entity_id.astype(str))
        rule = str(group.expected_detection_rule.iloc[0])
        detected = set(findings.loc[findings.rule.eq(rule), "entity_id"].astype(str)) if len(findings) else set()
        tp = len(expected & detected); precision = tp / len(detected) if detected else 0.0; recall = tp / len(expected) if expected else 1.0
        detection_scores[issue] = {"precision": precision, "recall": recall, "expected": len(expected), "detected": len(detected)}
    result = {
        "segment_membership_count": int(len(memberships)),
        "action_outcome_count": int(len(outcomes)),
        "suppression_rate": float(outcomes.decision.eq("SUPPRESSED").mean()) if len(outcomes) else 0.0,
        "sent_rate": float(outcomes.decision.eq("SENT").mean()) if len(outcomes) else 0.0,
        "conversion_rate": float(outcomes.outcome.eq("CONVERTED").mean()) if len(outcomes) else 0.0,
        "ground_truth_rows": int(len(truth)),
        "detection_scores": detection_scores,
    }
    (folder / "evaluation_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("folder", type=Path); args = p.parse_args(); print(json.dumps(score(args.folder), indent=2))
