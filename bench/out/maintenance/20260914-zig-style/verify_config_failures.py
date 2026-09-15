"""Compare configuration failure order in isolated predecessor/current builds."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile


def main() -> int:
    evidence = Path(__file__).resolve().parent
    repo = evidence.parents[3]
    runtime = repo / "runtime/zig"
    sources = {
        "before": subprocess.check_output(
            ["git", "show", "ded78ed29:runtime/zig/build.zig"], cwd=repo
        ),
        "after": (runtime / "build.zig").read_bytes(),
    }
    names = ("comparability-obligations.json", "dropin-abi-behavior.json", "dropin-symbol-ownership.json")
    rows = ["phase\tmissing_configs\texit\tfirst_failure"]
    with tempfile.TemporaryDirectory(prefix="doe-build-style-") as temporary:
        shadow = Path(temporary)
        for child in repo.iterdir():
            if child.name not in ("runtime", "config"):
                (shadow / child.name).symlink_to(child, target_is_directory=child.is_dir())
        shadow_runtime = shadow / "runtime/zig"
        shadow_runtime.mkdir(parents=True)
        for child in runtime.iterdir():
            if child.name not in ("build.zig", ".zig-cache"):
                (shadow_runtime / child.name).symlink_to(child, target_is_directory=child.is_dir())
        shadow_config = shadow / "config"
        shadow_config.mkdir()
        for child in (repo / "config").iterdir():
            (shadow_config / child.name).symlink_to(child, target_is_directory=child.is_dir())
        for phase, source in sources.items():
            (shadow_runtime / "build.zig").write_bytes(source)
            for index, first in enumerate(names):
                missing = names[index:]
                for name in missing:
                    (shadow_config / name).unlink()
                try:
                    result = subprocess.run(
                        ["zig", "build", "--cache-dir", str(runtime / ".zig-cache"), "--help"],
                        cwd=shadow_runtime, capture_output=True, text=True, check=False,
                    )
                    output = result.stdout + result.stderr
                    (evidence / f"config-{phase}-{index}.log").write_text(output, encoding="utf-8")
                    match = re.search(r"panic: ([^\n]+)", output)
                    expected = f"config/{first} not found"
                    if result.returncode == 0 or match is None or match[1] != expected:
                        raise AssertionError(f"{phase}: expected {expected}: {output}")
                    rows.append(f"{phase}\t{','.join(missing)}\t{result.returncode}\t{match[1]}")
                finally:
                    for name in missing:
                        (shadow_config / name).symlink_to(repo / "config" / name)
    (evidence / "config-failures.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
