"""Replay device lifecycle, recovery, unchanged applications, and evidence custody."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import importlib.util
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[3]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def payload(report: Path, name: str) -> bytes:
    path = (report / name).resolve()
    require(path.is_relative_to(report.resolve()), "Report path escaped root")
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == ".gz" else data


def load(report: Path, name: str) -> dict:
    return json.loads(payload(report, name))


def validate_rows(rows: list[dict], policy: dict, positive: bool) -> int:
    expected = {
        (name, mode): (2, name == "FinalReleaseWithResources")
        for name in ("Destroy", "FinalReleaseWithResources")
        for mode in (1, 2, 3)
    }
    expected.update({("FailedCreation", mode): (4, True) for mode in (2, 3)})
    expected.update({("ReuseAfterFailedCreation", mode): (2, False) for mode in (2, 3)})
    expected.update(
        {
            ("DestroyAfterSubmission", 1): (2, False),
            ("DestroyWithPendingPipeline", 1): (2, False),
            ("ReleaseInsideLostCallback", 1): (2, False),
            ("ReleaseBeforeLostDelivery", 1): (2, True),
        }
    )
    losses = [row for row in rows if row["kind"] == "loss"]
    require(
        Counter((r["operation"], r["mode"]) for r in losses)
        == Counter(expected.keys()),
        "Loss coverage changed",
    )
    failures = 0
    ids: set[int] = set()
    for row in losses:
        reason, null_device = expected[(row["operation"], row["mode"])]
        placement = row["mode"] == 3 or (
            row["before"] == 0
            and (
                row["afterEvents"] == 0 and row["phase"] == 2
                if row["mode"] == 1
                else row["phase"] == 3
            )
        )
        passed = (
            row["count"] == 1
            and row["reason"] == reason
            and row["pointer"]
            and row["nullDevice"] == null_device
            and placement
            and row["waited"]
        )
        require(row["passed"] == passed, "Loss verdict drift")
        failures += not passed
        if positive:
            require(passed, "Loss contract failed: " + row["operation"])
            if reason != 4:
                require(
                    row["future"] != 0 and row["future"] not in ids,
                    "Loss future identity reused",
                )
                ids.add(row["future"])
    pipelines = [row for row in rows if row["kind"] == "lost-pipeline"]
    require(
        [row["operation"] for row in pipelines]
        == ["PendingPipelineAtDestroy", "PipelineAfterDestroy"],
        "Lost pipeline coverage changed",
    )
    for row in pipelines:
        passed = (
            row["count"] == 1
            and row["status"] == 1
            and row["pipeline"]
            and row["waited"]
        )
        require(row["passed"] == passed, "Lost pipeline verdict drift")
        failures += not passed
        if positive:
            require(passed, "Lost async pipeline callback failed")
    checks = [row for row in rows if row["kind"] == "check"]
    expected_checks = Counter(
        {
            "physical-amd-vulkan": 1,
            "successful-request": 12,
            "failed-request": 2,
            "stable-loss-future": 3,
            "pending-loss-poll": 3,
            "destroy-release-exactly-once": 3,
            "remaining-external-reference": 3,
            "retained-resources-release-once": 3,
            "unchanged-submitted-copy-oracle": 1,
            "submitted-completion-settles": 1,
            "post-loss-map-rejected": 1,
            "drm-client-baseline-restored": 1,
        }
    )
    require(
        Counter(r["name"] for r in checks) == expected_checks,
        "Lifecycle control coverage changed",
    )
    failures += sum(not r["passed"] for r in checks)
    summary = rows[-1]
    require(
        summary["kind"] == "summary" and summary["failures"] == failures,
        "Lifecycle summary drift",
    )
    hardware = [r for r in rows if r["kind"] == "hardware"]
    require(
        len(hardware) == 1
        and hardware[0]["vendorId"] == 4098
        and hardware[0]["deviceId"] == 5510
        and hardware[0]["backend"] == 6,
        "Wrong hardware",
    )
    if positive:
        require(all(r["passed"] for r in checks), "Lifecycle behavior control failed")
        require(
            summary["initialDrmClients"] == summary["finalDrmClients"] == 0,
            "DRM ownership remained after teardown",
        )
        require(
            [r for r in rows if r["kind"] == "readback"]
            == [{"kind": "readback", "values": list(range(0x65430000, 0x65430010))}],
            "Submitted readback changed",
        )
        require(
            [r for r in rows if r["kind"] == "post-loss-map"]
            == [
                {
                    "kind": "post-loss-map",
                    "status": policy["postLossMapStatus"],
                    "waited": True,
                }
            ],
            "Destroyed device mapping admitted",
        )
    else:
        require(
            failures > 0
            and all(r["count"] == 0 for r in losses if r["operation"] == "Destroy"),
            "Baseline no longer reproduces missing loss",
        )
    return failures


def callback_verifier() -> object:
    spec = importlib.util.spec_from_file_location(
        "callback_regression",
        ROOT / "bench/external-projects/onnx-vulkan-callbacks/verify.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(
    report: Path, check_current: bool = False, with_custody: bool = False
) -> dict:
    manifest = load(report, "manifest.json")
    require(
        manifest["verdict"] == "qualified-tested-paths"
        and not manifest["performanceClaim"]
        and not manifest["generalConformance"],
        "Unqualified claim",
    )
    for name, identity in manifest["files"].items():
        require(
            digest((report / name).read_bytes()) == identity["sha256"],
            "Retained bytes changed: " + name,
        )
        require(
            digest(payload(report, name)) == identity["contentSha256"],
            "Retained content changed: " + name,
        )
    for path, reference in manifest["sourceSnapshots"].items():
        if check_current:
            require(
                digest((ROOT / path).read_bytes()) == reference["sha256"],
                "Current source changed: " + path,
            )
        require(
            digest(payload(report, reference["snapshot"])) == reference["sha256"],
            "Source snapshot changed",
        )
    for path, sha in manifest["historicalManifests"].items():
        require(
            digest((ROOT / path).read_bytes()) == sha, "Historical decision changed"
        )
    policy = load(report, "policy.json")
    receipt = load(report, "controls/receipt.json")
    require(
        receipt["policy"]["sha256"] == digest(payload(report, "policy.json")),
        "Policy identity changed",
    )
    for name in ("fixture", "producer"):
        entry = manifest["sourceSnapshots"][
            str(Path(receipt[name]["path"]).relative_to(ROOT))
        ]
        require(
            receipt[name]["sha256"] == entry["sha256"],
            "Executed harness identity changed",
        )
    require(
        Counter((r["arm"], r["index"]) for r in receipt["runs"])
        == Counter(
            (arm, i)
            for arm in ("before", "dawn", "native")
            for i in range(policy["independentProcesses"])
        ),
        "Process coverage changed",
    )
    for run in receipt["runs"]:
        arm = run["arm"]
        require(
            run["nativeBefore"] == run["nativeAfter"] == receipt["inputs"][arm],
            "Runtime mutated during qualification",
        )
        require(
            run["exitCode"] == run["expectedExitCode"] == (1 if arm == "before" else 0),
            "Unexpected process outcome",
        )
        name = f"controls/{arm}-{run['index']:02d}.jsonl"
        data = payload(report, name)
        require(digest(data) == run["stdout"]["sha256"], "Observation custody changed")
        require(
            digest(payload(report, f"controls/{arm}-{run['index']:02d}.stderr"))
            == run["stderr"]["sha256"],
            "Error log custody changed",
        )
        failed = validate_rows(
            [json.loads(line) for line in data.splitlines()], policy, arm != "before"
        )
        require(failed == run["failedObservations"], "Failure count drift")
    regression = load(report, "callback-controls/receipt.json")
    callback_policy = load(report, "callback-policy.json")
    callback_replay = callback_verifier()
    for name in ("fixture", "producer"):
        source_path = str(Path(regression[name]["path"]).relative_to(ROOT))
        require(
            regression[name]["sha256"]
            == manifest["sourceSnapshots"][source_path]["sha256"],
            "Callback harness identity changed",
        )
    require(
        Counter((r["arm"], r["index"]) for r in regression["runs"])
        == Counter(
            (arm, i)
            for arm in ("before", "dawn", "native")
            for i in range(callback_policy["independentProcesses"])
        ),
        "Callback regression coverage changed",
    )
    for arm in ("native", "dawn"):
        require(
            regression["inputs"][arm] == receipt["inputs"][arm],
            "Callback regression runtime differs",
        )
    for run in regression["runs"]:
        arm = run["arm"]
        require(
            run["nativeBefore"] == run["nativeAfter"] == regression["inputs"][arm],
            "Callback runtime mutated",
        )
        require(
            run["exitCode"] == run["expectedExitCode"] == (1 if arm == "before" else 0),
            "Callback regression failed",
        )
        data = payload(report, f"callback-controls/{arm}-{run['index']:02d}.jsonl")
        require(
            digest(data) == run["stdout"]["sha256"],
            "Callback observation custody changed",
        )
        failures = callback_replay.validate_rows(
            [json.loads(line) for line in data.splitlines()],
            callback_policy,
            arm != "before",
        )
        require(failures == run["failedObservations"], "Callback failure drift")
    consumer = load(report, "consumer-qualification.json")
    require(not consumer["performanceClaim"], "Consumer qualification became timing")
    producer_path = str(Path(consumer["producer"]["path"]).relative_to(ROOT))
    require(
        consumer["producer"]["sha256"]
        == manifest["sourceSnapshots"][producer_path]["sha256"],
        "Consumer producer identity changed",
    )
    jobs = {job["name"]: job for job in consumer["jobs"]}
    require(
        set(jobs)
        == {
            "safety-doe",
            "application-doe",
            "disabled-doe",
            "oracle-negative",
            "safety-dawn",
            "application-dawn",
            "disabled-dawn",
        },
        "Consumer process coverage changed",
    )
    for name, job in jobs.items():
        require(
            job["inputsBefore"] == job["inputsAfter"] == consumer["inputs"],
            "Consumer library changed during execution",
        )
        require(
            job["exitCode"]
            == job["expectedExitCode"]
            == (1 if name == "oracle-negative" else 0),
            "Consumer control failed",
        )
    require(
        len({job["pid"] for job in jobs.values()}) == len(jobs),
        "Consumer process identity reused",
    )
    require(
        consumer["inputs"]["native"] == receipt["inputs"]["native"]
        and consumer["inputs"]["dawn"] == receipt["inputs"]["dawn"],
        "Different consumer runtimes qualified",
    )
    shared = ["application", "provider", "bridge", "context", "reference"]
    for arm in ("doe", "dawn"):
        safety = load(report, f"safety/{arm}.json")
        require(
            safety["passed"]
            and safety["failure"] is None
            and safety["initialDrmClients"] == safety["finalDrmClients"] == [],
            "Safety/recovery failed",
        )
        for case in (
            "initializationRecovery",
            "descriptorRecovery",
            "failedSessionRecovery",
            "preexecutionCancellationReuse",
        ):
            require(safety[case]["reused"], "Recovery did not permit reuse")
        require(
            safety["preexecutionCancellationReuse"]["phase"] == "before-execution",
            "Cancellation scope changed",
        )
        require(
            len(safety["runs"]) == 3
            and all(r["observed"] == r["expected"] for r in safety["runs"]),
            "MatMul/Add regression failed",
        )
        profile_data = payload(report, f"safety/{arm}-profile.json.gz")
        safety_nodes = [
            row["args"]
            for row in json.loads(profile_data)
            if row.get("cat") == "Node" and "provider" in row.get("args", {})
        ]
        require(
            digest(profile_data) == safety["profile"]["sha256"]
            and [row["provider"] for row in safety_nodes] == safety["operatorProviders"]
            and [row["op_name"] for row in safety_nodes] == safety["operatorNames"],
            "Safety operator profile changed",
        )
        require(
            safety["operatorNames"] == ["MatMul", "Add"] * 3
            and set(safety["operatorProviders"]) == {"WebGpuExecutionProvider"},
            "Regression work/fallback changed",
        )
        require(
            safety["contextIdentity"]["backend"] == 6
            and safety["contextIdentity"]["vendor"] == 4098,
            "Wrong application context",
        )
        app = load(report, f"application/{arm}.json")
        require(
            app["passed"]
            and app["failure"] is None
            and app["exitCode"] == 0
            and not app["negativeControl"],
            "Application failed",
        )
        require(
            app["operatorProviders"]
            and set(app["operatorProviders"]) == {"WebGpuExecutionProvider"},
            "CPU fallback or missing work",
        )
        require(
            app["inputs"]["native"]["sha256"]
            == receipt["inputs"]["native" if arm == "doe" else "dawn"]["sha256"]
            == safety["libraries"]["native"]["sha256"],
            "Different runtime qualified",
        )
        log = payload(report, f"application/{arm}.log.gz")
        require(
            digest(log) == app["log"]["sha256"]
            and b"Done!" in log
            and b"oracle mismatch" not in log,
            "Application log changed",
        )
        names = load(report, "inputs/bridge-build.json")["procNames"]
        counts = {}
        for line in log.decode().splitlines():
            if line.startswith("CampaignCallCount "):
                _, index, count = line.split()
                counts[names[int(index)]] = int(count)
        require(counts == app["callCounts"], "Native call observation drift")
        require(
            app["timingSamples"] == []
            and payload(report, f"application/{arm}.observations") == b"",
            "Qualification became timing",
        )
        profile_name = manifest["applicationProfiles"][arm]
        profile = load(report, profile_name)
        providers = [
            e["args"]["provider"]
            for e in profile
            if e.get("cat") == "Node" and "provider" in e.get("args", {})
        ]
        require(
            providers == app["operatorProviders"]
            and digest(payload(report, profile_name)) == app["profile"]["sha256"],
            "Operator profile changed",
        )
        for name in (
            "deviceCreateShaderModule",
            "queueSubmit",
            "bufferMapAsync",
            "deviceDestroy",
            "deviceRelease",
        ):
            require(app["callCounts"].get(name, 0) > 0, "Missing native path: " + name)
        for name in ("native", "bridge", "context", "provider"):
            require(
                app["inputs"][name]["sha256"] == safety["libraries"][name]["sha256"],
                "Application/safety identity differs",
            )
        disabled = load(report, f"application/{arm}-disabled.json")
        require(
            disabled["passed"]
            and disabled["negativeControl"]
            and disabled["exitCode"] != 0
            and disabled["inputs"] == app["inputs"],
            "Native disabling control failed",
        )
    doe = load(report, "application/doe.json")
    dawn = load(report, "application/dawn.json")
    require(
        all(doe["inputs"][n] == dawn["inputs"][n] for n in shared),
        "Application conditions differ",
    )
    require(doe["operatorNames"] == dawn["operatorNames"], "Operator work differs")
    prior_application = json.loads(
        (
            ROOT
            / "reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-callbacks/application/doe.json"
        ).read_text()
    )
    require(
        doe["operatorNames"] == prior_application["operatorNames"]
        and len(doe["operatorProviders"])
        == len(prior_application["operatorProviders"]),
        "Unchanged application work differs",
    )
    require(
        all(
            doe["inputs"][name] == prior_application["inputs"][name] for name in shared
        ),
        "Pinned application inputs changed",
    )
    oracle = load(report, "application/oracle-negative.json")
    require(
        not oracle["passed"]
        and oracle["exitCode"] != 0
        and "Independent oracle mismatch" in oracle["failure"]["message"],
        "Oracle insensitive",
    )
    if with_custody:
        custody = manifest["custody"]
        archive = Path(custody["archive"]["path"])
        require(
            digest(archive.read_bytes()) == custody["archive"]["sha256"],
            "Binary archive changed",
        )
        indexed = {item["path"]: item["sha256"] for item in custody["members"]}
        required_assets = (
            list(receipt["inputs"].values())
            + list(regression["inputs"].values())
            + list(consumer["inputs"].values())
            + list(receipt["headers"].values())
            + [receipt["executable"], regression["executable"]]
        )
        for asset in required_assets:
            require(
                indexed.get(asset["path"]) == asset["sha256"],
                "Selected binary missing from custody",
            )
        with tarfile.open(archive) as bundle:
            for item in custody["members"]:
                stream = bundle.extractfile(item["member"])
                require(
                    stream is not None and digest(stream.read()) == item["sha256"],
                    "Custody member changed",
                )
    return {
        "deviceLifecycle": "qualified-tested-paths",
        "callbacks": "regressions-passed",
        "applications": "correct-unchanged",
        "performance": "no-claim",
        "generalConformance": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--check-current", action="store_true")
    parser.add_argument("--with-custody", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.report, args.check_current, args.with_custody)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
