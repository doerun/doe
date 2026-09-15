"""Check actual Zig build policy admission in an isolated source copy."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import resource
import subprocess

HERE = Path(__file__).resolve().parent
SCRATCH = HERE / "build-scratch"
POLICY = SCRATCH / "config/backend-runtime-policy.json"
CASES = HERE / "build-cases"
ZIG = "/home/x/.local/bin/zig"


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    CASES.mkdir(exist_ok=True)
    original = POLICY.read_bytes()
    baseline = json.loads(original)
    cases = [("accepted", baseline, True)]
    for name, mutate in (
        ("missing-lane", lambda p: p["lanes"].pop("metal_doe_release")),
        ("unknown-root-field", lambda p: p.update(typo=True)),
        ("unknown-lane-field", lambda p: p["lanes"]["metal_doe_app"].update(typo=True)),
        ("wrong-version", lambda p: p.update(schemaVersion=7)),
        ("empty-hash", lambda p: p.update(selectionPolicyHashSeed="")),
        ("missing-default", lambda p: p.pop("defaultLane")),
        ("fallback", lambda p: p["lanes"]["vulkan_doe_app"].update(allowFallback=True)),
        ("staged-upload", lambda p: p["lanes"]["metal_doe_release"].update(uploadPathPolicy="allow_mapped_shortcuts")),
        ("unknown-enum", lambda p: p["lanes"]["metal_doe_app"].update(queueFamilyPolicy="unrecognized")),
    ):
        payload = copy.deepcopy(baseline)
        mutate(payload)
        cases.append((name, payload, False))
    rows = ["case\texitCode\texpected\n"]
    try:
        for name, payload, accepted in cases:
            data = json.dumps(payload, indent=2) + "\n"
            POLICY.write_text(data)
            (CASES / f"{name}.json").write_text(data)
            result = subprocess.run(
                [ZIG, "build", "--help"], cwd=SCRATCH / "runtime/zig",
                capture_output=True, text=True, check=False,
            )
            (CASES / f"{name}.log").write_text(result.stdout + result.stderr)
            rows.append(f"{name}\t{result.returncode}\t{'accept' if accepted else 'reject'}\n")
            (HERE / "build-admission.tsv").write_text("".join(rows))
            assert (result.returncode == 0) == accepted, (name, result.returncode)
            if not accepted:
                assert "config/backend-runtime-policy.json" in result.stderr, name
            print(name, "pass", flush=True)
    finally:
        POLICY.write_bytes(original)


if __name__ == "__main__":
    main()
