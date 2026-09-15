"""Check runtime compile-report admission, emitted bytes, and schema compatibility."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import jsonschema


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SCHEMA = json.loads((ROOT / "config/runtime-compile-report.schema.json").read_text())
SOURCE = ROOT / "bench/out/maintenance/20260914-zig-file-reviews/compilation/valid.wgsl"


def execute(binary: Path, label: str, name: str, options: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([str(binary), "--shader-path", str(SOURCE), *options], capture_output=True, text=True, cwd=ROOT, timeout=30)
    (HERE / f"{label}-{name}.stdout").write_text(result.stdout)
    (HERE / f"{label}-{name}.stderr").write_text(result.stderr)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    binary = args.binary.resolve()
    rows = ["case\texit\tresult"]
    for target in ("msl", "spirv"):
        output = HERE / f"{args.label}.{target}"
        report = HERE / f"{args.label}-{target}.json"
        result = execute(binary, args.label, target, ["--target", target, "--out", str(report), "--emit-" + target, str(output)])
        assert result.returncode == 0 and not result.stdout and not result.stderr
        data = json.loads(report.read_text())
        jsonschema.validate(data, SCHEMA)
        assert data["outputBytes"] == output.stat().st_size
        if not args.baseline:
            before = json.loads((HERE / f"baseline-{target}.json").read_text())
            assert {k: v for k, v in data.items() if k not in ("phaseTimingsNs", "shaderPath")} == {k: v for k, v in before.items() if k not in ("phaseTimingsNs", "shaderPath")}
            assert output.read_bytes() == (HERE / f"baseline.{target}").read_bytes()
        rows.append(f"{target}\t0\tvalid schema and output bytes")
    cases = [
        ("quoted", ["--shader-name", 'quote"name\n'], None),
        ("duplicate", ["--shader-name", "first", "--shader-name", "second"], None),
        ("unknown", ["--typo"], "UnknownArgument"),
        ("missing", ["--shader-name"], "MissingArgumentValue"),
        ("empty_name", ["--shader-name", ""], "InvalidShaderName"),
        ("target", ["--target", "hlsl"], "InvalidTarget"),
    ]
    for name, options, error in cases:
        result = execute(binary, args.label, name, options)
        if not args.baseline:
            assert "leaked" not in result.stderr
            if error is not None:
                assert result.returncode != 0 and error in result.stderr and not result.stdout, name
            else:
                assert result.returncode == 0 and not result.stderr
                data = json.loads(result.stdout)
                jsonschema.validate(data, SCHEMA)
                assert data["shader"] == options[-1]
        rows.append(f"{name}\t{result.returncode}\t{'characterized' if args.baseline else 'checked'}")
    protected = HERE / f"{args.label}-protected.msl"
    protected.write_text("preserve\n")
    result = execute(binary, args.label, "mixed_emit", ["--emit-msl", str(protected), "--emit-spirv", str(HERE / f"{args.label}-incompatible.spv")])
    assert result.returncode != 0 and "EmitTargetMismatch" in result.stderr
    preserved = protected.read_text() == "preserve\n"
    if not args.baseline:
        assert preserved
    rows.append(f"mixed_emit\t{result.returncode}\tpreserved={preserved}")
    if not args.baseline:
        quoted_source = HERE / 'quoted " source.wgsl'
        quoted_source.write_bytes(SOURCE.read_bytes())
        result = execute(binary, args.label, "quoted_path", ["--shader-path", str(quoted_source)])
        assert result.returncode == 0 and not result.stderr
        data = json.loads(result.stdout)
        jsonschema.validate(data, SCHEMA)
        assert data["shaderPath"] == str(quoted_source)
        rows.append("quoted_path\t0\tvalid escaped path")
        protected.write_text("preserve\n")
        invalid = ROOT / "bench/out/maintenance/20260914-zig-file-reviews/compilation/invalid.wgsl"
        result = execute(binary, args.label, "invalid_source", ["--shader-path", str(invalid), "--out", str(protected)])
        assert result.returncode != 0 and "UnexpectedToken" in result.stderr and protected.read_text() == "preserve\n"
        assert "leaked" not in result.stderr
        rows.append(f"invalid_source\t{result.returncode}\toriginal error; output preserved")
        result = execute(binary, args.label, "full", ["--out", "/dev/full"])
        assert result.returncode != 0 and "NoSpaceLeft" in result.stderr and "leaked" not in result.stderr
        rows.append(f"full\t{result.returncode}\toriginal output error")
    (HERE / f"{args.label}-cases.tsv").write_text("\n".join(rows) + "\n")
    print(f"{args.label}: report and emitted-output checks complete")


if __name__ == "__main__":
    main()
