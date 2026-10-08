"""Replay callback placement, recovery, unchanged applications, and evidence custody."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
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
    expected = {(op, mode): 1 for op in policy["operations"] for mode in (1, 2, 3)}
    expected.update(
        {
            (name, mode): status
            for name, mode, status in [
                ("invalid-map-alignment", 1, 3),
                ("map-validation-error-scope", 1, 1),
                ("unmap-pending", 1, 4),
                ("mapping-reuse", 1, 1),
                ("destroy-pending-caller-release", 1, 4),
                ("pop-without-scope", 1, 3),
                ("isolated-queue", 2, 1),
                ("unselected-queue", 1, 1),
                ("pipeline-unsupported-descriptor", 1, 3),
                ("pipeline-reuse-after-error", 1, 1),
                ("pending-queue-caller-release", 1, 1),
            ]
        }
    )
    callbacks = [r for r in rows if r["kind"] == "callback"]
    require(
        Counter((r["operation"], r["mode"]) for r in callbacks)
        == Counter(expected.keys()),
        "Callback coverage changed",
    )
    ids: set[int] = set()
    failures = 0
    for row in callbacks:
        mode = row["mode"]
        placement = mode == 3 or (
            row["before"] == 0
            and (
                row["afterEvents"] == 0 and row["phase"] == 2
                if mode == 1
                else row["phase"] == 3
            )
        )
        unique = row["future"] not in ids
        ids.add(row["future"])
        status = expected[(row["operation"], mode)]
        require(row["expectedStatus"] == status, "Changed expected callback status")
        passed = (
            placement
            and row["count"] == 1
            and row["status"] == status
            and unique
            and row["waited"]
            and row["repeated"]
        )
        require(
            row["unique"] == unique and row["passed"] == passed,
            "Callback verdict drift",
        )
        if positive:
            require(passed, "Callback contract failed: " + row["operation"])
            if row["operation"] in ("PopErrorScope", "pop-without-scope"):
                require(row["errorType"] == 1, "Invalid scope error type")
            if row["operation"] == "map-validation-error-scope":
                require(row["errorType"] == 2, "Mapping error was not captured")
        failures += not passed
    checks = [r for r in rows if r["kind"] == "check"]
    required_checks = Counter(
        {
            "physical-amd-vulkan": 1,
            "empty-valid-scope-no-error": 3,
            "submitted-copy-readback": 3,
            "map-error-captured": 1,
            "map-state-pending": 1,
            "failed-pop-no-error-type": 1,
            "instance-pump-isolation": 1,
            "wait-selects-supplied-future": 1,
            "selected-queue-exactly-once": 1,
            "process-events-mode-wait-any": 1,
            "native-drm-release-before-process-exit": 1,
        }
    )
    require(
        Counter(r["name"] for r in checks) == required_checks,
        "Control coverage changed",
    )
    failures += sum(not r["passed"] for r in checks)
    require(
        rows[-1] == {"kind": "summary", "failures": failures, "passed": failures == 0},
        "Summary drift",
    )
    hardware = [r for r in rows if r["kind"] == "hardware"]
    require(
        len(hardware) == 1
        and hardware[0]["vendorId"] == 4098
        and hardware[0]["backend"] == 6,
        "Wrong hardware",
    )
    if positive:
        require(all(r["passed"] for r in checks), "Behavior control failed")
        readbacks = [r for r in rows if r["kind"] == "readback"]
        require(
            len(readbacks) == 3
            and all(
                r["available"] and r["values"] == list(range(0x12340000, 0x12340010))
                for r in readbacks
            ),
            "Submitted readback changed",
        )
        require(
            [r for r in rows if r["kind"] == "map-state"]
            == [{"kind": "map-state", "state": 2, "rangeUnavailable": True}],
            "Mapping was exposed before delivery",
        )
        require(
            [r for r in rows if r["kind"] == "selection"]
            == [
                {
                    "kind": "selection",
                    "count": 1,
                    "phase": 2,
                    "otherCount": 0,
                    "selectedAgain": True,
                }
            ],
            "WaitAny delivered an unrelated callback",
        )
        require(
            [r for r in rows if r["kind"] == "drm"]
            == [{"kind": "drm", "initial": 0, "final": 0}],
            "DRM ownership remained after teardown",
        )
    else:
        require(
            failures > 0
            and any(
                r["operation"] == "RequestAdapter"
                and r["mode"] == 1
                and r["before"] != 0
                for r in callbacks
            ),
            "Baseline no longer reproduces mismatch",
        )
    return failures


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
        with tarfile.open(archive) as bundle:
            for item in custody["members"]:
                stream = bundle.extractfile(item["member"])
                require(
                    stream is not None and digest(stream.read()) == item["sha256"],
                    "Custody member changed",
                )
    return {
        "callbacks": "qualified-tested-paths",
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
