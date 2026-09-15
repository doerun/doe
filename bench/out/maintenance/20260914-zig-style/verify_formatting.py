"""Verify formatter rejection, repair, and exclusion on temporary Zig files."""

from __future__ import annotations

from pathlib import Path
import subprocess


def main() -> int:
    evidence = Path(__file__).resolve().parent
    runtime = evidence.parents[3] / "runtime/zig"
    original = b"const value=1;\n"
    expected = b"const value = 1;\n"
    rows = ["directory\tcheck_exit\tformat_exit\tunchanged_after_check\tfinal_bytes"]
    for directory in (".", "src", "tests", "bench", "tools", "vendor", ".zig-cache", "zig-out"):
        excluded = directory in ("vendor", ".zig-cache", "zig-out")
        probe = runtime / directory / "style_format_probe.zig"
        if probe.exists():
            raise FileExistsError(probe)
        probe.write_bytes(original)
        label = directory.replace(".", "root")
        try:
            check = subprocess.run(
                ["zig", "build", "fmt-check", "--summary", "all"],
                cwd=runtime, capture_output=True, check=False,
            )
            (evidence / f"format-{label}-check.log").write_bytes(check.stdout + check.stderr)
            assert (check.returncode == 0) == excluded, directory
            assert probe.read_bytes() == original, directory
            repair = subprocess.run(
                ["zig", "build", "fmt", "--summary", "all"],
                cwd=runtime, capture_output=True, check=False,
            )
            (evidence / f"format-{label}-repair.log").write_bytes(repair.stdout + repair.stderr)
            repair.check_returncode()
            assert probe.read_bytes() == (original if excluded else expected), directory
            rows.append(
                f"{directory}\t{check.returncode}\t{repair.returncode}\ttrue\t"
                + ("unchanged" if excluded else "formatted")
            )
        finally:
            probe.unlink(missing_ok=True)
    (evidence / "formatting.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
