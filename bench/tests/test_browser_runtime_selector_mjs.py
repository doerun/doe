from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_selector_probe(policy: Path, mode: str, doe_lib: str, env_literal: str = "{}") -> dict:
    script = f"""
import assert from 'node:assert/strict';
import {{
  loadRuntimeSelectorPolicy,
  resolveRuntimeSelection,
}} from './browser/chromium/scripts/browser-runtime-selector.mjs';

const policy = loadRuntimeSelectorPolicy({json.dumps(str(policy))});
const result = resolveRuntimeSelection({{
  requestedMode: {json.dumps(mode)},
  doeLibPath: {json.dumps(doe_lib)},
  policy,
  env: {env_literal},
}});
assert.equal(typeof result, 'object');
console.log(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return json.loads(completed.stdout)


def test_auto_mode_falls_back_to_dawn_when_runtime_artifact_missing(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "emergencyKillSwitch": {
                    "controlName": "DOE_BROWSER_DISABLE_DOE_RUNTIME",
                    "reasonCode": "global_disable_active",
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_selector_probe(policy, "auto", str(tmp_path / "missing-lib.so"))

    assert result["selectionMode"] == "auto"
    assert result["selectedRuntime"] == "dawn"
    assert result["forcedMode"] is None
    assert result["fallbackApplied"] is True
    assert result["fallbackReasonCode"] == "runtime_artifact_missing"


def test_auto_mode_kill_switch_selects_dawn(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    doe_lib = tmp_path / "libwebgpu_doe_full.so"
    doe_lib.write_bytes(b"doe")
    policy.write_text(
        json.dumps(
            {
                "emergencyKillSwitch": {
                    "controlName": "DOE_BROWSER_DISABLE_DOE_RUNTIME",
                    "reasonCode": "global_disable_active",
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_selector_probe(
        policy,
        "auto",
        str(doe_lib),
        '{"DOE_BROWSER_DISABLE_DOE_RUNTIME":"1"}',
    )

    assert result["selectedRuntime"] == "dawn"
    assert result["fallbackReasonCode"] == "global_disable_active"


def test_auto_mode_profile_denylist_selects_dawn(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    doe_lib = tmp_path / "libwebgpu_doe_full.so"
    doe_lib.write_bytes(b"doe")
    policy.write_text(
        json.dumps(
            {
                "denylist": {
                    "reasonCode": "profile_denylisted",
                    "profiles": [
                        {
                            "profileId": "blocked-profile",
                            "vendor": "acme",
                            "api": "vulkan",
                            "deviceFamily": "lab",
                            "driverPattern": "blocked",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    script = f"""
import {{
  loadRuntimeSelectorPolicy,
  resolveRuntimeSelection,
}} from './browser/chromium/scripts/browser-runtime-selector.mjs';
const policy = loadRuntimeSelectorPolicy({json.dumps(str(policy))});
const result = resolveRuntimeSelection({{
  requestedMode: 'auto',
  doeLibPath: {json.dumps(str(doe_lib))},
  policy,
  profile: {{ profileId: 'blocked-profile', vendor: 'acme', api: 'vulkan', deviceFamily: 'lab', driver: 'blocked' }},
  env: {{}},
}});
console.log(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["selectedRuntime"] == "dawn"
    assert result["fallbackReasonCode"] == "profile_denylisted"
    assert result["profile"]["profileId"] == "blocked-profile"
    assert result["adapterDenylist"] == {
        "matched": True,
        "reasonCode": "profile_denylisted",
        "profileId": "blocked-profile",
        "vendor": "acme",
        "api": "vulkan",
        "deviceFamily": "lab",
        "driverPattern": "blocked",
    }


def test_auto_mode_profile_denylist_matches_adapter_fields(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    doe_lib = tmp_path / "libwebgpu_doe_full.so"
    doe_lib.write_bytes(b"doe")
    policy.write_text(
        json.dumps(
            {
                "denylist": {
                    "reasonCode": "profile_denylisted",
                    "profiles": [
                        {
                            "profileId": "apple-metal-lab",
                            "vendor": "apple",
                            "api": "metal",
                            "deviceFamily": "m3-max",
                            "driverPattern": "^23\\.",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    script = f"""
import {{
  loadRuntimeSelectorPolicy,
  resolveRuntimeSelection,
}} from './browser/chromium/scripts/browser-runtime-selector.mjs';
const policy = loadRuntimeSelectorPolicy({json.dumps(str(policy))});
const result = resolveRuntimeSelection({{
  requestedMode: 'auto',
  doeLibPath: {json.dumps(str(doe_lib))},
  policy,
  profile: {{ vendor: 'apple', api: 'metal', deviceFamily: 'm3-max', driver: '23.5.1' }},
  env: {{}},
}});
console.log(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["selectedRuntime"] == "dawn"
    assert result["fallbackReasonCode"] == "profile_denylisted"
    assert result["adapterDenylist"]["matched"] is True
    assert result["adapterDenylist"]["profileId"] == "apple-metal-lab"


def test_forced_doe_mode_does_not_fallback(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text("{}", encoding="utf-8")

    result = run_selector_probe(policy, "doe", str(tmp_path / "missing-lib.so"))

    assert result["selectionMode"] == "doe"
    assert result["selectedRuntime"] == "doe"
    assert result["forcedMode"] == "doe"
    assert result["fallbackApplied"] is False
    assert result["fallbackReasonCode"] == ""
    assert result["adapterDenylist"]["matched"] is False


def test_forced_doe_mode_carries_denylist_detail_without_fallback(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "denylist": {
                    "reasonCode": "profile_denylisted",
                    "profiles": [
                        {
                            "profileId": "blocked-profile",
                            "vendor": "acme",
                            "api": "vulkan",
                            "deviceFamily": "lab",
                            "driverPattern": "blocked",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    script = f"""
import {{
  loadRuntimeSelectorPolicy,
  resolveRuntimeSelection,
}} from './browser/chromium/scripts/browser-runtime-selector.mjs';
const policy = loadRuntimeSelectorPolicy({json.dumps(str(policy))});
const result = resolveRuntimeSelection({{
  requestedMode: 'doe',
  doeLibPath: '/does/not/matter/libwebgpu_doe_full.so',
  policy,
  profile: {{ profileId: 'blocked-profile', vendor: 'acme', api: 'vulkan', deviceFamily: 'lab', driver: 'blocked' }},
  env: {{}},
}});
console.log(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["selectionMode"] == "doe"
    assert result["selectedRuntime"] == "doe"
    assert result["fallbackApplied"] is False
    assert result["fallbackReasonCode"] == ""
    assert result["adapterDenylist"]["matched"] is True
    assert result["adapterDenylist"]["reasonCode"] == "profile_denylisted"
