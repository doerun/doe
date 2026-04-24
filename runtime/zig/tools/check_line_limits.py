from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ZIG_SRC = ROOT / "zig" / "src"
LINE_LIMIT = 999
# Each allowlist entry names a tracked sharding follow-up. These files
# exceed the 999-line cap because TSIR Phase A landed as single cohesive
# modules; the split plan is in docs/status/tsir.md. Do not add new
# entries without an owner and a concrete next-split target recorded in
# that status shard.
ALLOWLIST: dict[str, str] = {
    "tsir/reference_interpreter.zig": (
        "TSIR Phase A oracle; split by family dispatch "
        "(fused_gemv, rms_norm, gather, trySimpleReduction) pending — "
        "see docs/status/tsir.md"
    ),
    "tsir/frontend.zig": (
        "TSIR Phase A WGSL IR → semantic lowering; split by pass "
        "(axis recovery, reduction recovery, body inference, epsilon "
        "resolution) pending — see docs/status/tsir.md"
    ),
    "tsir/digest.zig": (
        "TSIR canonical serialization + SHA-256 digests; split by "
        "tier (semantic, realization, emitter-code) pending — "
        "see docs/status/tsir.md"
    ),
}


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def main() -> int:
    errors: list[str] = []
    allowlisted: list[str] = []

    for path in sorted(ZIG_SRC.rglob("*.zig")):
        line_count = count_lines(path)
        if line_count <= LINE_LIMIT:
            continue
        rel_path = path.relative_to(ZIG_SRC).as_posix()
        if rel_path in ALLOWLIST:
            allowlisted.append(
                f"{path}: {line_count} lines exceeds {LINE_LIMIT} (allowlisted: {ALLOWLIST[rel_path]})"
            )
            continue
        errors.append(f"{path}: {line_count} lines exceeds {LINE_LIMIT}")

    if allowlisted:
        print("allowlisted Zig source files still exceed the line limit:", file=sys.stderr)
        for entry in allowlisted:
            print(entry, file=sys.stderr)

    if not errors:
        return 0

    print("Zig source line-limit violations detected:", file=sys.stderr)
    for entry in errors:
        print(entry, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
