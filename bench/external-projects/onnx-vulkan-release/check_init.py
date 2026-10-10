"""Exercise bridge initialization rejection, retry, and live-table protection."""

from __future__ import annotations

import ctypes
import json
from pathlib import Path
import sys


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    bridge = ctypes.CDLL(str(root / "bridge.so"))
    initialize = bridge.doeDawnBridgeInitialize
    initialize.argtypes = [ctypes.c_char_p]
    initialize.restype = ctypes.c_void_p
    error = bridge.doeDawnBridgeTakeError
    error.restype = ctypes.c_char_p
    checks = {}
    for label, path in (
        ("missing-library-rejected", root / "absent.so"),
        ("incomplete-library-rejected", root / "context.so"),
    ):
        rejected = not initialize(str(path).encode())
        diagnostic = error()
        checks[label] = bool(rejected and diagnostic and error() is None)
    checks["retry-succeeds"] = bool(initialize(str(root / "doe.so").encode()))
    checks["live-rebind-rejected"] = not initialize(str(root / "doe.so").encode())
    checks["rebind-diagnostic"] = bool(error())
    passed = all(checks.values())
    print(json.dumps({"checks": checks, "passed": passed}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
