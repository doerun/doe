"""Capture build-generated options without compiling or installing a runtime."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[4]
    runtime = repo / "runtime/zig"
    destination = Path(__file__).resolve().parent / args.phase
    destination.mkdir(exist_ok=True)
    probe = runtime / "build.style_probe.zig"
    if probe.exists():
        raise FileExistsError(probe)
    original = (runtime / "build.zig").read_text(encoding="utf-8")
    records = ["lean_verified\toptions\tsha256\tbytes"]
    try:
        for verified in (False, True):
            mode = str(verified).lower()
            injection = ""
            for name in ("build_options", "compute_build_options", "full_build_options"):
                output = destination / f"{mode}-{name}.txt"
                injection += (
                    '    std.fs.cwd().writeFile(.{ .sub_path = "'
                    + output.as_posix()
                    + '", .data = '
                    + name
                    + '.contents.items }) catch @panic("option capture failed");\n'
                )
            marker = "    const shader_bench_exe = b.addExecutable(.{"
            if original.count(marker) != 1:
                raise ValueError("expected one build probe insertion point")
            probe.write_text(original.replace(marker, injection + marker), encoding="utf-8")
            result = subprocess.run(
                ["zig", "build", "--build-file", probe.name,
                 f"-Dlean-verified={mode}", "--help"],
                cwd=runtime, capture_output=True, text=True, check=False,
            )
            (destination / f"{mode}.log").write_text(
                result.stdout + result.stderr, encoding="utf-8"
            )
            result.check_returncode()
            for name in ("build_options", "compute_build_options", "full_build_options"):
                data = (destination / f"{mode}-{name}.txt").read_bytes()
                records.append(
                    f"{mode}\t{name}\t{hashlib.sha256(data).hexdigest()}\t{len(data)}"
                )
    finally:
        probe.unlink(missing_ok=True)
    (destination / "options.tsv").write_text("\n".join(records) + "\n", encoding="utf-8")
    print("\n".join(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
