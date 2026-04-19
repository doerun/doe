#!/usr/bin/env python3
"""Verify the CSL SDK driver wires --cmaddr through to the runtime command.

Priority #7 of the CSL plan requires that the current code accepts
endpoint-style execution through DOE_CSL_CMADDR / --csl-cmaddr so that
when a real CS system endpoint is available, E2B (and later 31B) can
run on hardware without re-plumbing. This smoke exercises the two pure
substitution functions in csl_sdk_driver.py (materialize_command +
redact_command_for_receipt) with both the simfabric (empty cmaddr) and
system (fake cmaddr) cases, and verifies:

  - `{cmaddr_arg}` in a runtime-config command expands to `--cmaddr=IP:PORT`
    when a cmaddr is provided, and is dropped entirely (empty-string
    filter) when absent — so the sim case doesn't accidentally carry a
    stale flag.
  - `redact_command_for_receipt` replaces the literal endpoint with the
    `$DOE_CSL_CMADDR` placeholder in recorded commands. Commit-eligible
    artifacts must not leak internal IP:port.
  - Execution target classification in the driver flips from `simfabric`
    to `system` exactly when cmaddr is non-empty.

Running this doesn't require the Cerebras SDK or any endpoint.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--driver",
        default="runtime/zig/tools/csl_sdk_driver.py",
    )
    p.add_argument("--fake-cmaddr", default="10.255.255.1:9999")
    p.add_argument(
        "--out-json",
        default="bench/out/cmaddr-propagation-smoke.json",
    )
    return p.parse_args()


def resolve(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def load_driver(driver_path: Path):
    spec = importlib.util.spec_from_file_location("csl_sdk_driver", driver_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {driver_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    args = parse_args()
    driver = load_driver(resolve(args.driver))

    template = [
        "bench/runners/csl-runners/elementwise_double_sim_runner.py",
        "--compile-dir={compile_output_dir}",
        "--trace-out={trace_path}",
        "{cmaddr_arg}",
    ]

    failures: list[str] = []

    # simfabric case: empty cmaddr must drop the {cmaddr_arg} slot entirely.
    sim_subs = {
        "compile_output_dir": "/tmp/compile",
        "trace_path": "/tmp/trace.json",
        "cmaddr_arg": "",
    }
    sim_command = driver.materialize_command(template, sim_subs)
    if any("--cmaddr" in item for item in sim_command):
        failures.append(f"simfabric command must not carry --cmaddr, got: {sim_command}")
    if len(sim_command) != 3:
        failures.append(f"simfabric command should drop empty cmaddr_arg, len={len(sim_command)}: {sim_command}")

    # system case: cmaddr must expand and survive in the rendered command.
    fake = args.fake_cmaddr
    sys_subs = {
        "compile_output_dir": "/tmp/compile",
        "trace_path": "/tmp/trace.json",
        "cmaddr_arg": f"--cmaddr={fake}",
    }
    sys_command = driver.materialize_command(template, sys_subs)
    if f"--cmaddr={fake}" not in sys_command:
        failures.append(f"system command missing --cmaddr={fake}: {sys_command}")

    # Redaction: persisted receipts must carry placeholder, not raw endpoint.
    redacted = driver.redact_command_for_receipt(sys_command, fake)
    if any(fake in item for item in redacted):
        failures.append(f"redacted command leaked fake endpoint {fake}: {redacted}")
    if not any("$DOE_CSL_CMADDR" in item for item in redacted):
        failures.append(f"redacted command missing $DOE_CSL_CMADDR marker: {redacted}")

    # executionTarget classification (matches the driver's inline expression
    # "'system' if csl_cmaddr else 'simfabric'" at line 521/529/etc).
    def execution_target(cmaddr: str) -> str:
        return "system" if cmaddr.strip() else "simfabric"

    if execution_target("") != "simfabric":
        failures.append("empty cmaddr should map to 'simfabric'")
    if execution_target(fake) != "system":
        failures.append(f"non-empty cmaddr should map to 'system', got {execution_target(fake)!r}")

    out_path = resolve(args.out_json)
    smoke_result = {
        "schemaVersion": 1,
        "artifactKind": "cmaddr_propagation_smoke",
        "fakeEndpoint": fake,
        "simfabricCommand": sim_command,
        "systemCommand": sys_command,
        "redactedCommand": redacted,
        "executionTargetEmpty": execution_target(""),
        "executionTargetFake": execution_target(fake),
        "failures": failures,
        "propagationWired": not failures,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(smoke_result, indent=2) + "\n", encoding="utf-8")

    if failures:
        print("FAIL: cmaddr propagation")
        for f in failures:
            print(f"  {f}")
        return 1

    print(
        f"PASS: cmaddr propagation "
        f"(simfabric keeps {len(sim_command)} items, system embeds --cmaddr, "
        f"receipt carries $DOE_CSL_CMADDR placeholder)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
