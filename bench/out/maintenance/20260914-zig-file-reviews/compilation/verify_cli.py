"""Exercise compilation CLI contracts against an installed diagnostic binary."""
from pathlib import Path
import argparse
import csv
import json
import resource
import subprocess
import sys

import jsonschema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--label", default="after")
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent
    repo = evidence.parents[4]
    binary = args.binary.resolve()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    schema = json.loads((repo / "config/zig-compilation-bench.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    name = 'quote"line\nslash\\'
    tier = 'tier"\t'
    basic = ["--iterations", "1", "--warmup", "0"]
    external = [*basic, "--shader-path", str(evidence / "valid.wgsl")]
    cases = (
        ("corpus", basic, 0, 31),
        ("warmup", ["--iterations", "3", "--warmup", "2"], 0, 31),
        ("duplicate", [*basic, "--filter", "empty_compute", "--filter", "empty_compute"], 0, 7),
        ("escaped-name", [*external, "--shader-name", name, "--shader-tier", tier], 0, 7),
        ("zero", ["--iterations", "0"], 1, 0),
        ("cap", ["--iterations", "5001"], 1, 0),
        ("missing", ["--iterations"], 1, 0),
        ("invalid", ["--iterations", "bad"], 1, 0),
        ("unknown-filter", ["--filter", "__missing__"], 1, 0),
        ("unknown-target", ["--target", "absent"], 1, 0),
        ("unknown-option", ["--typo", "1"], 1, 0),
        ("invalid-source", [*basic, "--shader-path", str(evidence / "invalid.wgsl")], 1, 1),
        ("output-failure", [*external, "--out", "/dev/full"], 1, 0),
    )
    rows = []
    all_records = []
    with (evidence / f"{args.label}-diagnostics.log").open("wb") as log:
        for case, options, expected_exit, expected_rows in cases:
            result = subprocess.run([str(binary), *options], capture_output=True, timeout=60, check=False)
            log.write(f"case: {case}\n".encode() + result.stderr + b"\n")
            records = [json.loads(line) for line in result.stdout.splitlines()]
            for record in records:
                validator.validate(record)
            clean = b"leaked" not in result.stderr
            matched = result.returncode == expected_exit and len(records) == expected_rows and clean
            rows.append([case, result.returncode, len(records), clean, matched])
            if not matched:
                raise AssertionError((rows[-1], result.stderr.decode(errors="replace")))
            if expected_exit == 0:
                all_records.extend(records)
                (evidence / f"{args.label}-{case}.ndjson").write_bytes(result.stdout)
            if case == "invalid-source":
                assert b"UnexpectedToken" in result.stderr
            if case == "escaped-name":
                for record in records:
                    if record["kind"] == "compilation_bench":
                        assert record["shader"] == name and record["tier"] == tier
                        assert record["sourceLines"] == 1
    before = [json.loads(line) for line in (evidence / "before-corpus.ndjson").read_text().splitlines()]
    after = [json.loads(line) for line in (evidence / f"{args.label}-corpus.ndjson").read_text().splitlines()]
    excluded = {"version", "compilerLoc"}
    identity = lambda row: {key: value for key, value in row.items() if key not in excluded and not key.endswith(("_ns", "_us")) and key != "timerOverheadP50Ns"}
    assert [identity(row) for row in before] == [identity(row) for row in after]
    assert all(set(old) - {"compilerLoc"} == set(new) for old, new in zip(before, after, strict=True))
    sys.path.insert(0, str(repo / "bench"))
    from native_compare_modules.compilation_runner import _parse_compilation_ndjson
    parsed = _parse_compilation_ndjson(evidence / f"{args.label}-escaped-name.ndjson", name)
    assert parsed["version"] == 2 and parsed["tier"] == tier and parsed["bytesOut"] > 0
    with (evidence / f"{args.label}-cases.tsv").open("w", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["case", "exitCode", "rows", "noAllocatorLeakReport", "matched"])
        writer.writerows(rows)
    if args.label == "after":
        (evidence / "contract-rows.json").write_text(json.dumps(all_records, indent=2, sort_keys=True) + "\n")
    print(f"{args.label}: CLI cases, schema validation, row identities, output sizes, and existing consumer parsing passed")


if __name__ == "__main__":
    main()
