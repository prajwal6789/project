from pathlib import Path

from src.eval.score import score
from src.gen.run import generate
from src.validate.checks import validate
import src.validate.checks as checks_module


def test_clean_baseline_passes_validator(tmp_path: Path):
    output = tmp_path / "clean"
    generate("starter", 20261022, output, inject=False)
    report = validate(output)
    assert report["status"] == "PASS"
    assert all(check["status"] == "PASS" for check in report["semantic_checks"])
    names = {check["check"] for check in report["semantic_checks"]}
    required = {
        "id_format:Customer", "duplicate_rows:Customer", "fk:Consent.customer_id",
        "fk:SupportCase.customer_id", "fk:SupportCase.order_id", "fk:EngagementEvent.customer_id",
        "consent_date_ordering", "support_date_ordering", "segment_rule_rederivation",
        "customer_status_transitions", "distribution_targets",
    }
    assert required <= names


def test_injected_anomalies_score_against_ground_truth(tmp_path: Path):
    output = tmp_path / "final"
    generate("starter", 20261022, output, inject=True)
    validate(output)
    scores = score(output)["detection_scores"]
    assert scores
    assert all(metrics["precision"] == 1.0 and metrics["recall"] == 1.0 for metrics in scores.values())


def test_distribution_threshold_is_enforced(tmp_path: Path, monkeypatch):
    output = tmp_path / "clean"
    generate("starter", 20261022, output, inject=False)
    original = checks_module.load_yaml
    def altered(name):
        config = original(name)
        if name == "rules.yaml":
            config["distribution_targets"]["champions_lifecycle_share"] = [0.99, 1.0]
        return config
    monkeypatch.setattr(checks_module, "load_yaml", altered)
    report = validate(output)
    distribution = next(item for item in report["semantic_checks"] if item["check"] == "distribution_targets")
    assert distribution["status"] == "FAIL" and distribution["violations"] > 0


def test_anomaly_counts_ids_and_label_isolation(tmp_path: Path):
    output = tmp_path / "final"
    generate("starter", 20261022, output, inject=True)
    truth = __import__("pandas").read_csv(output / "ground_truth.csv")
    assert truth.issue_type.value_counts().to_dict() == {"ACTION_VIOLATES_CONSENT": 12, "CONFLICTING_EXCLUSIVE_SEGMENTS": 6, "OUTCOME_WRONG_ACTION": 10, "RETURN_NOT_NETTED": 8}
    for row in truth.itertuples():
        assert any(row.entity_id in set(__import__("pandas").read_csv(path).iloc[:, 0].astype(str)) for path in output.glob("*.csv") if path.name != "ground_truth.csv")
    assert all("issue_type" not in __import__("pandas").read_csv(path).columns for path in output.glob("*.csv") if path.name != "ground_truth.csv")
