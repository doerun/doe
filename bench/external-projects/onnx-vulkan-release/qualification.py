"""Physical acceptance of the installed bytes in a checkout-free namespace."""

from __future__ import annotations

import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any

from distribution import digest, inventory, verify, write_json


def isolation(root: Path, out: Path, environment: dict[str, str]) -> list[str]:
    """Expose declared system dependencies and installed files, never a checkout."""
    command = ["bwrap", "--die-with-parent", "--unshare-net", "--clearenv"]
    for name in ("/usr", "/bin", "/lib", "/lib64", "/etc", "/sys"):
        if Path(name).exists():
            command += ["--ro-bind", name, name]
    command += [
        "--dev-bind",
        "/dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--ro-bind",
        str(root),
        "/application",
        "--bind",
        str(out),
        "/results",
        "--chdir",
        "/application",
    ]
    for key, value in sorted(environment.items()):
        command += ["--setenv", key, value]
    return command


def loaded_libraries(log: str, root: Path) -> list[dict[str, str]]:
    """Bind loader-observed initializations, not merely requested library names."""
    names = sorted(set(re.findall(r"calling init:\s*([^\n]+)", log)))
    result = []
    for name in names:
        name = name.strip()
        actual = (
            root / name.removeprefix("/application/")
            if name.startswith("/application/")
            else Path(name)
        )
        if not actual.is_absolute() or not actual.is_file():
            raise ValueError(f"Cannot bind initialized library: {name}")
        result.append({"path": name, "sha256": digest(actual)})
    return result


def application_evidence(
    root: Path, out: Path, content: str, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Join operator placement, native dispatch, output checks, and loaded bytes."""
    profiles = re.findall(r"^CampaignProfile (/results/[^\n]+)$", content, re.M)
    if len(profiles) != 1:
        raise ValueError("Missing unique application profile")
    profile_path = out / Path(profiles[0]).name
    nodes = [
        event["args"]
        for event in json.loads(profile_path.read_text("utf-8"))
        if event.get("cat") == "Node" and "provider" in event.get("args", {})
    ]
    if not nodes or any(
        node["provider"] != "WebGpuExecutionProvider" for node in nodes
    ):
        raise ValueError("Application operators did not all execute on WebGPU")
    names = json.loads((root / "bridge-build.json").read_text("utf-8"))["procNames"]
    counts = {
        names[int(index)]: int(count)
        for index, count in re.findall(
            r"^CampaignCallCount (\d+) (\d+)$", content, re.M
        )
    }
    for name in (
        "deviceCreateShaderModule",
        "computePassEncoderDispatchWorkgroups",
        "queueSubmit",
        "bufferMapAsync",
        "deviceDestroy",
        "deviceRelease",
    ):
        if counts.get(name, 0) <= 0:
            raise ValueError(f"Missing executed native operation: {name}")
    contexts = re.findall(r"^CampaignContext (\d+) (\d+) (\d+) (\d+)$", content, re.M)
    if (
        len(contexts) != 1
        or int(contexts[0][1]) != manifest["qualification"]["vendorId"]
    ):
        raise ValueError("Application did not select the declared AMD device")
    libraries = loaded_libraries(content, root)
    observed = {item["path"]: item["sha256"] for item in libraries}
    for name in (
        "doe.so",
        "bridge.so",
        "context.so",
        "provider.so",
        "libonnxruntime.so.1",
        "libonnxruntime_providers_shared.so",
    ):
        if observed.get("/application/" + name) != manifest["files"][name]["sha256"]:
            raise ValueError(f"Installed library was not observed executing: {name}")
    if not any("vulkan" in item["path"].lower() for item in libraries):
        raise ValueError("No Vulkan loader or driver was observed")
    trace = [
        json.loads(line)
        for line in (out / "native.jsonl").read_text("utf-8").splitlines()
    ]
    dispatches = [row for row in trace if row.get("event") == "dispatch_encoded"]
    submits = [row for row in trace if row.get("event") == "submission_succeeded"]
    if not dispatches or not submits:
        raise ValueError("Native journal lacks dispatch or submission evidence")
    if len({row["processId"] for row in trace}) != 1:
        raise ValueError("Native journal mixed multiple processes")
    if [row["sequence"] for row in trace] != list(range(1, len(trace) + 1)):
        raise ValueError("Native journal sequence is incomplete")
    if submits[-1]["sequence"] <= dispatches[-1]["sequence"]:
        raise ValueError("Encoded dispatch lacks subsequent successful submission")
    for row in dispatches:
        if row.get("backend") != "doe_vulkan" or not re.fullmatch(
            "[0-9a-f]{64}", row["wgslSha256"]
        ):
            raise ValueError("Invalid native shader/backend identity")
        artifact = row["backendArtifactFile"]
        if (
            Path(artifact).name != artifact
            or digest(out / artifact) != row["backendArtifactSha256"]
        ):
            raise ValueError("Missing or changed executed SPIR-V")
    if (out / "observations").read_text("utf-8"):
        raise ValueError("Qualification unexpectedly entered timing mode")
    return {
        "actualProvider": "doe_vulkan",
        "context": [int(value) for value in contexts[0]],
        "operatorNames": [node["op_name"] for node in nodes],
        "callCounts": counts,
        "dispatchCount": len(dispatches),
        "submissionCount": len(submits),
        "loadedLibraries": libraries,
    }


def execute(root: Path, out: Path, complete: bool) -> dict[str, Any]:
    """Run acceptance, retaining every completed or failed child observation."""
    manifest = verify(root)
    root, out = root.resolve(), out.resolve()
    if out.is_relative_to(root) or root.is_relative_to(out):
        raise ValueError("Results must be outside the installation directory")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("This archive requires Linux x86_64 with AMD Vulkan")
    if not shutil.which("bwrap"):
        raise FileNotFoundError("Install bubblewrap (bwrap) for isolated evaluation")
    out.mkdir(parents=True, exist_ok=False)
    policy = manifest["qualification"]
    numerical = json.loads((root / "policy.json").read_text("utf-8"))["correctness"]
    jobs = []
    if complete:
        jobs += [("initialization", "initialization")]
        jobs += [("callbacks", "fixture"), ("lifecycle", "fixture")]
    jobs += [
        (f"application-{i}", "positive")
        for i in range(policy["applicationProcesses"] if complete else 1)
    ]
    if complete:
        jobs += [
            ("native-disabled", "native-disabled"),
            ("oracle-corrupted", "oracle-corrupted"),
        ]
    result = {
        "schemaVersion": 1,
        "kind": "doe-onnx-vulkan-installation",
        "version": manifest["version"],
        "manifestSha256": digest(root / "manifest.json"),
        "mode": "qualify" if complete else "run",
        "performanceClaim": False,
        "externalAdoption": False,
        "passed": False,
        "host": {
            "system": platform.system(),
            "machine": platform.machine(),
            "kernel": platform.release(),
        },
        "isolation": {
            "checkoutExposure": "none",
            "network": "unshared",
            "systemReadOnlyRoots": ["/usr", "/bin", "/lib", "/lib64", "/etc", "/sys"],
            "hostDevices": "/dev",
            "writableRoots": ["/results", "/tmp"],
        },
        "jobs": [],
    }
    for label, kind in jobs:
        job = out / label
        job.mkdir()
        (job / "native.jsonl").touch()
        env = {
            "HOME": "/tmp",
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LD_DEBUG": "libs",
            "XDG_CACHE_HOME": "/tmp/cache",
            "MESA_SHADER_CACHE_DIR": "/tmp/cache",
        }
        if kind == "initialization":
            program = ["/usr/bin/python3", "/application/check_init.py", "/application"]
        elif kind == "fixture":
            program = [
                f"/application/checks/{label}",
                "/application/bridge.so",
                "/application/doe.so",
                "doe",
                str(policy["fixtureDeadlineNs"]),
            ]
        else:
            env.update(
                {
                    "CAMPAIGN_ARM": "doe",
                    "CAMPAIGN_MODE": "qualification",
                    "CAMPAIGN_PROVIDER": "/application/provider.so",
                    "CAMPAIGN_NATIVE": "/application/doe.so",
                    "CAMPAIGN_BRIDGE": "/application/bridge.so",
                    "CAMPAIGN_CONTEXT": "/application/context.so",
                    "CAMPAIGN_REFERENCE": "/application/reference.f32",
                    "CAMPAIGN_PROFILE": "/results/application.profile",
                    "CAMPAIGN_OBSERVATIONS": "/results/observations",
                    "CAMPAIGN_WARMUP": "0",
                    "CAMPAIGN_RUNS": str(policy["runsPerProcess"]),
                    "CAMPAIGN_ATOL": str(numerical["absoluteTolerance"]),
                    "CAMPAIGN_RTOL": str(numerical["relativeTolerance"]),
                    "DOE_PROGRAM_IDENTITY_TRACE_PATH": "/results/native.jsonl",
                }
            )
            if kind == "native-disabled":
                env["CAMPAIGN_NATIVE"] = "/missing/selected-native-library.so"
            if kind == "oracle-corrupted":
                env["CAMPAIGN_REFERENCE"] = "/application/corrupted.f32"
            program = ["/application/application"]
        command = isolation(root, job, env) + ["--", *program]
        row = {
            "name": label,
            "passed": False,
            "exitCode": None,
            "failure": None,
            "command": command,
            "execution": None,
        }
        try:
            with (job / "stdout.log").open("w", encoding="utf-8") as stdout, (
                job / "stderr.log"
            ).open("w", encoding="utf-8") as stderr:
                child = subprocess.run(
                    command,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=policy["processDeadlineSeconds"],
                )
            row["exitCode"] = child.returncode
            output = (job / "stdout.log").read_text("utf-8")
            content = output + (job / "stderr.log").read_text("utf-8")
            if "CampaignCleanupFailure " in content:
                raise ValueError("Application cleanup failed")
            if kind == "native-disabled":
                row["passed"] = (
                    child.returncode != 0
                    and "Proc-table initialization failed" in content
                )
            elif kind == "oracle-corrupted":
                row["passed"] = (
                    child.returncode != 0 and "Independent oracle mismatch" in content
                )
            elif child.returncode != 0:
                raise ValueError(f"Child exited {child.returncode}")
            elif kind == "positive":
                row["execution"] = application_evidence(root, job, content, manifest)
                row["passed"] = True
            else:
                lines = [
                    json.loads(line)
                    for line in output.splitlines()
                    if line.startswith("{")
                ]
                if not lines:
                    raise ValueError("Missing initialization or lifecycle checks")
                row["passed"] = all(item.get("passed", True) for item in lines)
                if kind == "fixture":
                    row["passed"] &= (
                        lines[-1].get("kind") == "summary"
                        and lines[-1].get("failures") == 0
                    )
                row["execution"] = {
                    "checks": lines,
                    "loadedLibraries": loaded_libraries(content, root),
                }
            verify(root)
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
            row["failure"] = str(error)
            row["passed"] = False
        row["artifacts"] = inventory(job)
        result["jobs"].append(row)
        write_json(out / "qualification.json", result)
        print(f"{label}: {'PASS' if row['passed'] else 'FAIL'}", flush=True)
        if not row["passed"]:
            break
    result["passed"] = len(result["jobs"]) == len(jobs) and all(
        row["passed"] for row in result["jobs"]
    )
    write_json(out / "qualification.json", result)
    return result
