#!/usr/bin/env cs_python
"""Load one compiled INT4 PLE target and resolve the required device symbols."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile-dir", required=True)
    parser.add_argument("--launch-fn", required=True)
    parser.add_argument("--receipt-out", required=True)
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--cmaddr", default="")
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    receipt_path = Path(args.receipt_out)
    compile_dir = Path(args.compile_dir)
    cmaddr = args.cmaddr.strip() or None
    blockers: list[str] = []
    resolved_symbols: dict[str, int] = {}

    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "int4ple_target_session_probe",
        "status": "blocked",
        "compileDir": str(compile_dir),
        "launchFunction": args.launch_fn,
        "cmaddrProvided": cmaddr is not None,
        "resolvedSymbols": resolved_symbols,
        "blockers": blockers,
    }

    if not compile_dir.is_dir():
        blockers.append(f"compile_dir_missing:{compile_dir}")
        write_json(receipt_path, receipt)
        return 1

    try:
        # pylint: disable=import-error,import-outside-toplevel
        from cerebras.sdk.runtime.sdkruntimepybind import SdkRuntime
    except Exception as exc:  # pragma: no cover - SDK import path
        blockers.append(f"sdk_import_failed:{type(exc).__name__}:{exc}")
        write_json(receipt_path, receipt)
        return 1

    runner = None
    try:
        runner = SdkRuntime(str(compile_dir), cmaddr=cmaddr)
        for symbol in args.symbol:
            try:
                resolved_symbols[symbol] = int(runner.get_id(symbol))
            except Exception as exc:  # pragma: no cover - SDK path
                blockers.append(
                    f"symbol_unresolved:{symbol}:{type(exc).__name__}:{str(exc)[:160]}"
                )
    except Exception as exc:  # pragma: no cover - SDK path
        blockers.append(
            f"runtime_constructor_failed:{type(exc).__name__}:{str(exc)[:160]}"
        )
    finally:
        if runner is not None:
            try:
                runner.stop()
            except Exception:
                pass

    receipt["status"] = "resolved" if not blockers else "blocked"
    write_json(receipt_path, receipt)
    if blockers:
        print(f"FAIL: target session probe {compile_dir}", file=sys.stderr)
        return 1
    print(f"PASS: target session probe {compile_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
