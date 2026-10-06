"""Pack qualified application bytes and replay without checkouts or networking."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(bundle: Path, out: Path) -> dict:
    """Verify inventory before isolated positives and execution-disabling controls."""
    manifest = json.loads((bundle / "bundle.json").read_text())
    for name, expected in manifest["files"].items():
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle.resolve()) or digest(path) != expected:
            raise ValueError("Bundle integrity failure: " + name)
    out.mkdir(parents=True, exist_ok=False)
    policy = json.loads((bundle / "policy.json").read_text())
    names = json.loads((bundle / "bridge-build.json").read_text())["procNames"]
    rows = []
    roots = ["/usr", "/bin", "/lib", "/lib64", "/etc", "/sys"]
    for arm in ["dawn", "doe"]:
        for control in ["positive", "native-disabled", "oracle-corrupted"]:
            label = arm + "-" + control
            profile = "/results/" + label + ".profile"
            environment = {
                "HOME": "/tmp",
                "PATH": "/usr/bin:/bin",
                "CAMPAIGN_ARM": arm,
                "CAMPAIGN_MODE": "qualification",
                "CAMPAIGN_PROVIDER": "/application/provider.so",
                "CAMPAIGN_NATIVE": "/application/" + arm + ".so",
                "CAMPAIGN_BRIDGE": "/application/bridge.so",
                "CAMPAIGN_CONTEXT": "/application/context.so",
                "CAMPAIGN_REFERENCE": "/application/reference.f32",
                "CAMPAIGN_PROFILE": profile,
                "CAMPAIGN_OBSERVATIONS": "/results/" + label + ".observations",
                "CAMPAIGN_WARMUP": "0",
                "CAMPAIGN_RUNS": "3",
                "CAMPAIGN_ATOL": str(policy["correctness"]["absoluteTolerance"]),
                "CAMPAIGN_RTOL": str(policy["correctness"]["relativeTolerance"]),
                "XDG_CACHE_HOME": "/tmp/cache",
                "MESA_SHADER_CACHE_DIR": "/tmp/cache",
            }
            if control == "native-disabled":
                environment["CAMPAIGN_NATIVE"] = "/missing/selected-native-library.so"
            if control == "oracle-corrupted":
                environment["CAMPAIGN_REFERENCE"] = "/application/corrupted.f32"
            command = ["bwrap", "--die-with-parent", "--unshare-net", "--clearenv"]
            for root in roots:
                if Path(root).exists():
                    command += ["--ro-bind", root, root]
            command += [
                "--dev-bind",
                "/dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                "--ro-bind",
                str(bundle.resolve()),
                "/application",
                "--bind",
                str(out.resolve()),
                "/results",
                "--chdir",
                "/application",
            ]
            for key, value in environment.items():
                command += ["--setenv", key, value]
            command += ["--", "/application/application"]
            log = out / (label + ".log")
            with log.open("w") as stream:
                child = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
            content = log.read_text()
            counts = {}
            operators = []
            profile_name = None
            if control == "positive" and child.returncode == 0:
                profile_name = next(
                    line.split(" ", 1)[1]
                    for line in content.splitlines()
                    if line.startswith("CampaignProfile ")
                ).replace("/results/", "")
                nodes = [
                    event["args"]
                    for event in json.loads((out / profile_name).read_text())
                    if event.get("cat") == "Node"
                    and "provider" in event.get("args", {})
                ]
                operators = [node["op_name"] for node in nodes]
                if not nodes or any(
                    node["provider"] != "WebGpuExecutionProvider" for node in nodes
                ):
                    raise ValueError("Bundle operator placement failed")
                for line in content.splitlines():
                    if line.startswith("CampaignCallCount "):
                        _, index, count = line.split()
                        counts[names[int(index)]] = int(count)
                required = [
                    "deviceCreateShaderModule",
                    "queueSubmit",
                    "bufferMapAsync",
                    "deviceDestroy",
                    "deviceRelease",
                ]
                passed = all(counts.get(name, 0) > 0 for name in required)
                passed = passed and not (out / (label + ".observations")).read_text()
            elif control == "native-disabled":
                passed = (
                    child.returncode != 0
                    and "Proc-table initialization failed" in content
                )
            elif control == "oracle-corrupted":
                passed = (
                    child.returncode != 0 and "Independent oracle mismatch" in content
                )
            else:
                passed = False
            passed = passed and "CampaignCleanupFailure " not in content
            rows.append(
                {
                    "arm": arm,
                    "control": control,
                    "passed": passed,
                    "exitCode": child.returncode,
                    "log": log.name,
                    "logSha256": digest(log),
                    "profile": profile_name,
                    "operatorNames": operators,
                    "callCounts": counts,
                    "command": command,
                }
            )
    result = {
        "schemaVersion": 1,
        "classification": "isolated-application-replay",
        "passed": all(row["passed"] for row in rows),
        "bundleSha256": digest(bundle / "bundle.json"),
        "network": "unshared",
        "checkoutExposure": "none",
        "systemReadOnlyRoots": roots,
        "hostDevices": "/dev",
        "writableRoots": ["/results", "/tmp"],
        "rows": rows,
    }
    (out / "replay.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doe", type=Path, help="Qualified Doe application receipt")
    parser.add_argument("--dawn", type=Path, help="Qualified source-built Dawn receipt")
    parser.add_argument(
        "--bundle",
        type=Path,
        required=True,
        help="New bundle, or existing verified bundle",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="New isolated replay output"
    )
    parser.add_argument(
        "--replay-only",
        action="store_true",
        help="Replay an existing inventory without packing",
    )
    args = parser.parse_args()
    if not args.replay_only:
        if not args.doe or not args.dawn:
            parser.error("Packing requires both qualified receipts")
        qualified = {
            arm: json.loads(getattr(args, arm).read_text()) for arm in ["doe", "dawn"]
        }
        for arm, item in qualified.items():
            if not item["passed"] or item["negativeControl"]:
                raise ValueError("Unqualified arm: " + arm)
            for source in item["inputs"].values():
                if digest(Path(source["path"])) != source["sha256"]:
                    raise ValueError("Qualified bytes changed")
        for key in ["application", "provider", "bridge", "context", "reference"]:
            if qualified["doe"]["inputs"][key] != qualified["dawn"]["inputs"][key]:
                raise ValueError("Unmatched bundle input: " + key)
        args.bundle.mkdir(parents=True, exist_ok=False)
        inputs = qualified["doe"]["inputs"]
        for key, name in [
            ("application", "application"),
            ("provider", "provider.so"),
            ("bridge", "bridge.so"),
            ("context", "context.so"),
            ("reference", "reference.f32"),
        ]:
            shutil.copy2(inputs[key]["path"], args.bundle / name)
        for arm in qualified:
            shutil.copy2(
                qualified[arm]["inputs"]["native"]["path"], args.bundle / (arm + ".so")
            )
        app = Path(inputs["application"]["path"]).parent
        for name in ["libonnxruntime.so.1", "squeezenet.onnx"]:
            shutil.copy2(app / name, args.bundle / name)
        preparation = json.loads((app / "preparation.json").read_text())
        core_directory = Path(preparation["onnxCore"]["path"]).parent
        shutil.copy2(
            core_directory / "libonnxruntime_providers_shared.so",
            args.bundle / "libonnxruntime_providers_shared.so",
        )
        shutil.copy2(qualified["doe"]["policy"]["path"], args.bundle / "policy.json")
        shutil.copy2(
            Path(inputs["bridge"]["path"]).parent / "build.json",
            args.bundle / "bridge-build.json",
        )
        (args.bundle / "corrupted.f32").write_bytes(
            bytes(Path(inputs["reference"]["path"]).stat().st_size)
        )
        files = {path.name: digest(path) for path in sorted(args.bundle.iterdir())}
        manifest = {
            "schemaVersion": 1,
            "classification": "host-local-qualified-application-bundle",
            "files": files,
            "qualifiedNativeHashes": {
                arm: qualified[arm]["inputs"]["native"]["sha256"] for arm in qualified
            },
            "scope": "Linux AMD Vulkan on the tested host; system loader, drivers and libraries required",
        }
        (args.bundle / "bundle.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
    return 0 if replay(args.bundle, args.out)["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
