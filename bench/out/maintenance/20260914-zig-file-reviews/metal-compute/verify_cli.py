"""Check Metal benchmark admission on a Linux host without GPU execution."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--tool", choices=("compute", "staged-write"), required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        raise RuntimeError("This check requires Linux and expects UnsupportedPlatform; it does not qualify Metal execution.")
    output = HERE if args.tool == "compute" else HERE.parent / "metal-staged-write"
    cases = [
        ("default", [], "UnsupportedPlatform"),
        ("zero", ["--iterations", "0"], "InvalidArgument"),
        ("missing", ["--iterations"], "MissingArgument"),
        ("unknown", ["--typo"], "UnknownArgument"),
        ("negative", ["--iterations", "-1"], "InvalidCharacter"),
        ("overflow", ["--iterations", "4294967296"], "Overflow"),
        ("corruption", ["--iterations", "1", "--inject-corruption"], "UnsupportedPlatform"),
    ]
    if args.tool == "compute":
        cases.append(("too_many", ["--iterations", "17"], "InvalidArgument"))
    else:
        cases += [
            ("too_many", ["--iterations", "129"], "InvalidArgument"),
            ("zero_bytes", ["--bytes", "0"], "InvalidArgument"),
            ("missing_bytes", ["--bytes"], "MissingArgument"),
            ("too_large", ["--bytes", "67108865"], "InvalidArgument"),
            ("repeated_bytes", ["--bytes", "2", "--bytes", "1"], "UnsupportedPlatform"),
        ]
    rows = ["case\texit\terror"]
    for name, options, expected in cases:
        result = subprocess.run([str(args.binary.resolve()), *options], capture_output=True, text=True, cwd=ROOT / "runtime/zig", timeout=20)
        (output / f"{args.label}-{name}.stderr").write_text(result.stderr)
        assert result.returncode == 1 and not result.stdout and expected in result.stderr, (name, result.stderr)
        assert "leaked" not in result.stderr, name
        rows.append(f"{name}\t{result.returncode}\t{expected}")
    (output / f"{args.label}-cases.tsv").write_text("\n".join(rows) + "\n")
    print(f"{args.tool} {args.label}: admission and unsupported-host checks passed")


if __name__ == "__main__":
    main()
