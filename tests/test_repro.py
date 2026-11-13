import json
from pathlib import Path

from src.eval.repro import write_report


def test_repro_report_contains_file_rows_and_seed_difference(tmp_path: Path):
    for name, seed, digest in (("a", 1, "a"), ("b", 1, "a"), ("different", 2, "b")):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "Customer.csv").write_text("x\n1\n", encoding="utf-8")
        (folder / "seed.sql").write_text("seed" + digest, encoding="utf-8")
        (folder / "source_manifest.json").write_text(json.dumps({"seed": seed, "scale": "starter", "generator_version": "v", "row_counts": {"Customer": 1}, "files": {"Customer.csv": "same", "seed.sql": digest}}), encoding="utf-8")
    report = tmp_path / "report.md"
    write_report(tmp_path / "a", tmp_path / "b", tmp_path / "different", report)
    text = report.read_text(encoding="utf-8")
    assert "Customer.csv" in text and "seed.sql" in text
    assert "Overall: **PASS**" in text and "Different-seed starter checksums differ: **PASS**" in text
