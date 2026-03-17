from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ZIG_SRC = ROOT / "zig" / "src"
LEAN_ROOT = ROOT / "lean" / "Fawn"
ZIG_IMPORT_RE = re.compile(r'@import\("([^"]+)"\)')
SYNTHETIC_RUNTIME_STATE_SUFFIX = "_runtime_state.zig"
FORBIDDEN_STUB_SUFFIX = "_stub.zig"
FORBIDDEN_SYNTHETIC_IMPORTS = {
    "metal_runtime_state.zig",
    "vulkan_runtime_state.zig",
}


def is_stub_file(candidate: Path) -> bool:
    return candidate.suffix == ".zig" and candidate.name.endswith(FORBIDDEN_STUB_SUFFIX)


def is_synthetic_runtime_state_file(candidate: Path) -> bool:
    return candidate.name in FORBIDDEN_SYNTHETIC_IMPORTS or candidate.name.endswith(
        SYNTHETIC_RUNTIME_STATE_SUFFIX
    )


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


def scan_synthetic_state_imports(errors: list[str]) -> None:
    for path in sorted(ZIG_SRC.rglob("*.zig")):
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            for match in ZIG_IMPORT_RE.finditer(line):
                import_path = match.group(1)
                candidate = (path.parent / import_path).resolve(strict=False)
                if is_synthetic_runtime_state_file(candidate) or is_stub_file(candidate):
                    errors.append(f"{path}:{line_no}: synthetic runtime-state import not allowed: {import_path}")


def scan_stub_file_presence(errors: list[str]) -> None:
    for file_path in sorted(ZIG_SRC.rglob("*_stub.zig")):
        if file_path.is_file():
            errors.append(f"forbidden stub file present: {file_path}")


def scan_stub_imports(errors: list[str]) -> None:
    for path in sorted(ZIG_SRC.rglob("*.zig")):
        for line_no, line in enumerate(path.read_text().splitlines(), start=1):
            for match in ZIG_IMPORT_RE.finditer(line):
                import_path = match.group(1)
                candidate = (path.parent / import_path).resolve(strict=False)
                if is_stub_file(candidate):
                    errors.append(f"{path}:{line_no}: stub import not allowed: {import_path}")


def scan_forbidden_runtime_state_files(errors: list[str]) -> None:
    for file_path in sorted(ZIG_SRC.rglob("*.zig")):
        if is_synthetic_runtime_state_file(file_path):
            errors.append(f"forbidden synthetic runtime-state file present: {file_path}")


def main() -> int:
    errors: list[str] = []
    scan_zig_core(errors)
    scan_lean_core(errors)
    scan_synthetic_state_imports(errors)
    scan_forbidden_runtime_state_files(errors)
    scan_stub_file_presence(errors)
    scan_stub_imports(errors)
    if not errors:
        return 0

    print("core/full import fence violations detected:", file=sys.stderr)
    for entry in errors:
        print(entry, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
