"""Execute identical application bytes in independent source-matched native arms."""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def identity(path: Path) -> dict[str, str]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "application",
        "provider",
        "native",
        "bridge",
        "context",
        "reference",
        "safety",
        "out",
    ]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--arm", choices=["doe", "dawn"], required=True)
    parser.add_argument("--disable-native", action="store_true")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Source capture diagnostic; never a timing run",
    )
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output must be new")
    safety = json.loads(args.safety.read_text())
    if not safety["passed"] or safety["arm"] != args.arm:
        raise ValueError("Arm safety has not passed")
    for name in ["native", "bridge", "context", "provider"]:
        if (
            identity(getattr(args, name))["sha256"]
            != safety["libraries"][name]["sha256"]
        ):
            raise ValueError("Safety was qualified with different " + name + " bytes")
    preparation = json.loads((args.application.parent / "preparation.json").read_text())
    if identity(args.application)["sha256"] != preparation["application"]["sha256"]:
        raise ValueError("Prepared application integrity failure")
    policy_path = (
        Path(__file__).resolve().parents[3] / "config/onnx-vulkan-campaign.json"
    )
    policy = json.loads(policy_path.read_text())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    log = args.out.with_suffix(".log")
    observations = args.out.with_suffix(".observations")
    cache = args.out.with_suffix(".cache")
    cache.mkdir(exist_ok=False)
    environment = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "LD_PRELOAD",
            "LD_LIBRARY_PATH",
            "DOE_WEBGPU_LIB",
            "MESA_SHADER_CACHE_DIR",
            "XDG_CACHE_HOME",
        )
        and not k.startswith("CAMPAIGN_")
    }
    environment.update(
        {
            "CAMPAIGN_ARM": args.arm,
            "CAMPAIGN_MODE": "qualification",
            "CAMPAIGN_PROVIDER": str(args.provider.resolve()),
            "CAMPAIGN_NATIVE": str(args.native.resolve()),
            "CAMPAIGN_BRIDGE": str(args.bridge.resolve()),
            "CAMPAIGN_CONTEXT": str(args.context.resolve()),
            "CAMPAIGN_REFERENCE": str(args.reference.resolve()),
            "CAMPAIGN_PROFILE": str(args.out.with_suffix(".profile").resolve()),
            "CAMPAIGN_OBSERVATIONS": str(observations.resolve()),
            "CAMPAIGN_WARMUP": "0",
            "CAMPAIGN_RUNS": "3",
            "CAMPAIGN_ATOL": str(policy["correctness"]["absoluteTolerance"]),
            "CAMPAIGN_RTOL": str(policy["correctness"]["relativeTolerance"]),
            "MESA_SHADER_CACHE_DIR": str(cache.resolve()),
            "XDG_CACHE_HOME": str(cache.resolve()),
        }
    )
    if args.disable_native:
        environment["CAMPAIGN_NATIVE"] = "/missing/selected-native-library.so"
    if args.verbose:
        environment["CAMPAIGN_VERBOSE"] = "1"
    with log.open("w") as stream:
        completed = subprocess.run(
            [str(args.application.resolve())],
            cwd=args.application.parent,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    content = log.read_text()
    result = {
        "schemaVersion": 1,
        "arm": args.arm,
        "classification": "application-qualification",
        "passed": False,
        "failure": None,
        "negativeControl": args.disable_native,
        "exitCode": completed.returncode,
        "policy": identity(policy_path),
        "safety": identity(args.safety),
        "inputs": {
            n: identity(getattr(args, n))
            for n in [
                "application",
                "provider",
                "native",
                "bridge",
                "context",
                "reference",
            ]
        },
        "log": identity(log),
        "profile": None,
        "operatorNames": [],
        "operatorProviders": [],
        "callCounts": {},
        "timingSamples": [],
    }
    if "CampaignCleanupFailure " in content:
        result["failure"] = {"type": "CleanupFailure", "message": content[-6000:]}
    elif args.disable_native:
        result["passed"] = completed.returncode != 0 and (
            "Proc-table initialization failed" in content
            or "selected-native-library" in content
        )
    elif completed.returncode:
        result["failure"] = {"type": "ApplicationFailure", "message": content[-6000:]}
    else:
        try:
            line = next(
                line
                for line in content.splitlines()
                if line.startswith("CampaignProfile ")
            )
            profile = Path(line.removeprefix("CampaignProfile "))
            nodes = [
                e["args"]
                for e in json.loads(profile.read_text())
                if e.get("cat") == "Node" and "provider" in e.get("args", {})
            ]
            result["profile"] = identity(profile)
            result["operatorNames"] = [n["op_name"] for n in nodes]
            result["operatorProviders"] = [n["provider"] for n in nodes]
            if not nodes or any(
                n["provider"] != "WebGpuExecutionProvider" for n in nodes
            ):
                raise ValueError("Actual operator placement failed")
            names = json.loads((args.bridge.parent / "build.json").read_text())[
                "procNames"
            ]
            for line in content.splitlines():
                if line.startswith("CampaignCallCount "):
                    _, index, count = line.split()
                    result["callCounts"][names[int(index)]] = int(count)
            for name in [
                "deviceCreateShaderModule",
                "queueSubmit",
                "bufferMapAsync",
                "deviceDestroy",
                "deviceRelease",
            ]:
                if not result["callCounts"].get(name):
                    raise ValueError("Selected native arm did not own " + name)
            if observations.read_text():
                raise ValueError("Timing collected before qualification")
            result["passed"] = True
        except Exception as error:
            result["failure"] = {"type": type(error).__name__, "message": str(error)}
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
