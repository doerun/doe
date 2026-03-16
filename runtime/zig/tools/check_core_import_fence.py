from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ZIG_SRC = ROOT / "zig" / "src"
LEAN_ROOT = ROOT / "lean" / "Fawn"
ZIG_IMPORT_RE = re.compile(r'@import\("([^"]+)"\)')


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def scan_zig_core(errors: list[str]) -> None:
    core_dir = ZIG_SRC / "core"
    full_dir = ZIG_SRC / "full"
    if not core_dir.is_dir():
        return

    for path in sorted(core_dir.rglob("*.zig")):
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            for match in ZIG_IMPORT_RE.finditer(line):
                import_path = match.group(1)
                candidate = (path.parent / import_path).resolve(strict=False)
                if is_within(candidate, full_dir):
                    errors.append(f"{path}:{line_no}: core import reaches full: {import_path}")


def scan_lean_core(errors: list[str]) -> None:
    core_dir = LEAN_ROOT / "Core"
    if not core_dir.is_dir():
        return

    for path in sorted(core_dir.rglob("*.lean")):
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            if line.strip().startswith("import ") and "Fawn.Full" in line:
                errors.append(f"{path}:{line_no}: Lean Core import reaches Full: {line.strip()}")


def main() -> int:
    errors: list[str] = []
    scan_zig_core(errors)
    scan_lean_core(errors)
    if not errors:
        return 0

    print("core/full import fence violations detected:", file=sys.stderr)
    for entry in errors:
        print(entry, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
