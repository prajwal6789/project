"""Build a deterministic, file-by-file reproducibility report."""
from pathlib import Path
import hashlib
import json


def _manifest(path: Path) -> dict:
    return json.loads((path / "source_manifest.json").read_text(encoding="utf-8"))


def _row_count(manifest: dict, filename: str) -> int | str:
    stem = Path(filename).stem
    if stem in manifest.get("row_counts", {}):
        return manifest["row_counts"][stem]
    return "-"


def write_report(run_a: Path, run_b: Path, different_seed: Path, output: Path) -> None:
    a = _manifest(run_a)
    b = _manifest(run_b)
    different = _manifest(different_seed)
    names = sorted(set(a.get("files", {})) | set(b.get("files", {})))
    required = [name for name in names if name.endswith((".csv", ".ndjson", "seed.sql")) or name == "ground_truth.json"]
    lines = [
        "# Reproducibility report",
        "",
        f"- Seed: `{a['seed']}`",
        f"- Scale: `{a['scale']}`",
        f"- Generator version: `{a['generator_version']}`",
        "",
        "| File | Row count run A | Row count run B | SHA-256 run A | SHA-256 run B | Result |",
        "|---|---:|---:|---|---|---|",
    ]
    overall = True
    for name in required:
        hash_a = a.get("files", {}).get(name, "-")
        hash_b = b.get("files", {}).get(name, "-")
        count_a = _row_count(a, name)
        count_b = _row_count(b, name)
        match = hash_a == hash_b and count_a == count_b
        overall = overall and match
        lines.append(f"| `{name}` | {count_a} | {count_b} | `{hash_a}` | `{hash_b}` | {'MATCH' if match else 'DIFF'} |")
    changed = any(a.get("files", {}).get(name) != different.get("files", {}).get(name) for name in required)
    lines.extend(["", f"Different-seed starter checksums differ: **{'PASS' if changed else 'FAIL'}**.", "", f"Overall: **{'PASS' if overall else 'FAIL'}**"])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    parser.add_argument("different_seed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_report(args.run_a, args.run_b, args.different_seed, args.output)
