"""Verify the stage benchmark's actual CLI, row coverage, and cleanup."""
from pathlib import Path
import argparse
import csv
import json
import resource
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--label", default="after")
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    evidence = Path(__file__).resolve().parent
    binary = args.binary.resolve()
    cases = (
        ("corpus", ["--iterations", "1", "--warmup", "0"], 0, 35),
        ("warmup", ["--iterations", "3", "--warmup", "2"], 0, 35),
        ("zero", ["--iterations", "0"], 1, 0),
        ("cap", ["--iterations", "2001"], 1, 0),
        ("duplicate", ["--iterations", "1", "--warmup", "0", "--filter", "compute_simple", "--filter", "compute_simple"], 0, 7),
        ("missing", ["--iterations"], 1, 0),
        ("invalid", ["--iterations", "invalid"], 1, 0),
        ("unknown-option", ["--typo", "1"], 1, 0),
        ("unknown-filter", ["--filter", "__missing__"], 1, 0),
        ("output-failure", ["--iterations", "1", "--warmup", "0", "--filter", "compute_simple", "--out", "/dev/full"], 1, 0),
    )
    rows = []
    for name, options, expected_exit, expected_rows in cases:
        result = subprocess.run([str(binary), *options], capture_output=True, timeout=60, check=False)
        (evidence / f"{args.label}-{name}.stdout").write_bytes(result.stdout)
        (evidence / f"{args.label}-{name}.stderr").write_bytes(result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        clean = b"leaked" not in result.stderr
        matched = result.returncode == expected_exit and len(records) == expected_rows and clean
        rows.append((name, " ".join(options), result.returncode, len(records), clean, matched))
        if not matched:
            raise AssertionError((rows[-1], result.stderr.decode(errors="replace")))
    baseline = [json.loads(line) for line in (evidence / "before-corpus.stdout").read_bytes().splitlines()]
    current = [json.loads(line) for line in (evidence / f"{args.label}-corpus.stdout").read_bytes().splitlines()]
    timing_fields = {"min_ns", "max_ns", "mean_ns", "p50_ns", "p95_ns", "p99_ns"}
    identity = lambda row: {key: value for key, value in row.items() if key not in timing_fields}
    assert [identity(row) for row in baseline] == [identity(row) for row in current]
    assert all(set(row) == set(baseline[0]) for row in current)
    with (evidence / f"{args.label}-cases.tsv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("case", "arguments", "exitCode", "rows", "noAllocatorLeaks", "matched"))
        writer.writerows(rows)
    print(f"{args.label}: CLI cases passed; corpus order, output sizes, and row fields match the runnable predecessor")


if __name__ == "__main__":
    main()
