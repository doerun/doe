"""Reproduce host benchmark admission and diagnostic artifact checks."""

from __future__ import annotations

import argparse
import copy
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import jsonschema


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SCHEMA = json.loads((ROOT / "config/zig-host-hotpath-bench.schema.json").read_text())


def run(binary: Path, label: str, name: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=60, cwd=ROOT)
    (HERE / f"{label}-{name}.stdout").write_text(result.stdout)
    (HERE / f"{label}-{name}.stderr").write_text(result.stderr)
    return result


def check_artifact(artifact: dict[str, Any], iterations: int) -> None:
    jsonschema.validate(artifact, SCHEMA)
    before = json.loads((HERE / "before.json").read_text())
    assert [case["case_id"] for case in artifact["cases"]] == [case["case_id"] for case in before["cases"]]
    for case, old in zip(artifact["cases"], before["cases"], strict=True):
        assert case["category"] == old["category"]
        for variant, old_variant in zip(case["variants"], old["variants"], strict=True):
            for field in ("variant", "input_bytes", "work_items", "warmup"):
                assert variant[field] == old_variant[field], (case["case_id"], field)
            scaled = case["case_id"] in ("numeric_attention_seq128_head64", "task_queue_submit_drain_4096")
            assert variant["iterations"] == (20 if scaled else iterations)
            assert variant["min_ns"] <= variant["mean_ns"] <= variant["max_ns"]
            assert variant["min_ns"] <= variant["p50_ns"] <= variant["p95_ns"] <= variant["p99_ns"] <= variant["max_ns"]
        means = [variant["mean_ns"] for variant in case["variants"]]
        ratio = case["comparison"]["speedup"]
        assert ratio is None if 0 in means else math.isclose(ratio, means[0] / means[1])
        if case["category"] in ("trace", "lexer", "coordination"):
            assert case["comparison"]["output_hash_match"]
        if case["category"] == "coordination":
            for variant in case["variants"]:
                count = variant["work_items"]
                expected = count * (count - 1) // 2
                assert variant["output_hash"] == expected
                assert variant["checksum"] == (expected if variant["iterations"] % 2 else 0)
        if case["category"] in ("trace", "lexer"):
            assert [v["output_hash"] for v in case["variants"]] == [v["output_hash"] for v in old["variants"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    binary = args.binary.resolve()
    rows = ["case\texit\tresult"]
    invalid = {
        "zero": (["--iterations", "0"], "InvalidIterations"),
        "missing": (["--iterations"], "MissingArgumentValue"),
        "unknown": (["--unknown", "1"], "UnknownArgument"),
        "negative": (["--iterations", "-1"], "Overflow"),
        "overflow": (["--iterations", "4294967296"], "Overflow"),
        "bad_warmup": (["--warmup", "no"], "InvalidCharacter"),
    }
    for name, (extra, error) in invalid.items():
        result = run(binary, args.label, name, ["--iterations", "2", "--warmup", "0", *extra])
        if not args.baseline:
            assert result.returncode != 0 and error in result.stderr and not result.stdout, name
        rows.append(f"{name}\t{result.returncode}\t{'characterized' if args.baseline else 'rejected'}")
    if args.baseline:
        (HERE / f"{args.label}-cases.tsv").write_text("\n".join(rows) + "\n")
        return
    for name, count in (("even", 2), ("odd", 3)):
        result = run(binary, args.label, name, ["--iterations", str(count), "--warmup", "0"])
        assert result.returncode == 0 and not result.stderr
        artifact = json.loads(result.stdout)
        check_artifact(artifact, count)
        (HERE / f"{args.label}-{name}.json").write_text(result.stdout)
        rows.append(f"{name}\t0\tvalidated")
    first, second = (HERE / f"{args.label}-{name}.json" for name in ("first", "second"))
    first.write_text("preserve\n")
    result = run(binary, args.label, "duplicate_out", ["--iterations", "2", "--warmup", "0", "--out", str(first), "--out", str(second)])
    assert result.returncode == 0 and not result.stdout and not result.stderr
    assert first.read_text() == "preserve\n"
    check_artifact(json.loads(second.read_text()), 2)
    rows.append("duplicate_out\t0\tlast option wins; first preserved")
    result = run(binary, args.label, "invalid_preserves_output", ["--iterations", "0", "--out", str(first)])
    assert result.returncode != 0 and first.read_text() == "preserve\n"
    rows.append(f"invalid_preserves_output\t{result.returncode}\tpreserved")
    result = run(binary, args.label, "full", ["--iterations", "2", "--warmup", "0", "--out", "/dev/full"])
    assert result.returncode != 0 and "NoSpaceLeft" in result.stderr
    rows.append(f"full\t{result.returncode}\toriginal output error")
    (HERE / f"{args.label}-cases.tsv").write_text("\n".join(rows) + "\n")
    if args.label == "debug":
        artifact = json.loads((HERE / "debug-even.json").read_text())
        (HERE / "after.json").write_text(json.dumps(artifact, indent=2) + "\n")
        mutations = []
        for name in ("version", "claim", "unknown", "zero_samples", "negative_ratio"):
            changed = copy.deepcopy(artifact)
            if name == "version":
                changed["schema_version"] = 1
            elif name == "claim":
                changed["claimStatus"] = "claimable"
            elif name == "unknown":
                changed["invented"] = 0
            elif name == "zero_samples":
                changed["cases"][0]["variants"][0]["iterations"] = 0
            else:
                changed["cases"][0]["comparison"]["speedup"] = -1
            try:
                jsonschema.validate(changed, SCHEMA)
            except jsonschema.ValidationError:
                mutations.append(f"{name}\trejected")
            else:
                raise AssertionError(name)
        (HERE / "schema-negative.tsv").write_text("case\tresult\n" + "\n".join(mutations) + "\n")
    print(f"{args.label}: CLI, output identity, allocation-error taxonomy, and schema checks passed")


if __name__ == "__main__":
    main()
