"""Audit retained safety, equivalent work, raw measurements and rejected advantage."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import tarfile

import jsonschema

import numpy as np

REQUIRED_CALLS = [
    "deviceCreateShaderModule",
    "queueSubmit",
    "bufferMapAsync",
    "deviceDestroy",
    "deviceRelease",
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def measurement_values(measurement: dict, policy: dict) -> dict:
    """Recompute paired estimates from raw independent process samples."""
    settings = policy["measurement"]
    require(
        measurement["schemaVersion"] == 2, "Persistent cache scope was not qualified"
    )
    rows = measurement["rows"]
    require(measurement["failure"] is None, "Measurement execution failed")
    for row in rows:
        require(row["exitCode"] == 0, "Failed measured process")
        require(
            Path(row["cacheHome"]) == Path(row["cache"]) / "home",
            "Native cache HOME escaped its scope",
        )
        if row["stage"] == "cold":
            require(not row["cacheStateBefore"], "Cold process inherited cached work")
        if row["stage"] == "warm" and row["arm"] == "doe":
            require(
                any(
                    entry["path"].startswith(
                        "home/.cache/doe/shader_translation_cache/"
                    )
                    for entry in row["cacheStateBefore"]
                ),
                "Doe warm cache not preconditioned",
            )
        for entry in row["cacheStateBefore"] + row["cacheStateAfter"]:
            require(
                not Path(entry["path"]).is_absolute()
                and ".." not in Path(entry["path"]).parts,
                "Cache inventory escaped root",
            )
        count = (
            1
            if row["stage"] in ["cold", "cache-precondition"]
            else settings["runsPerProcess"]
        )
        require(
            len(row["runWallNs"]) == len(row["runCpuNs"]) == count, "Run count drift"
        )
        require(
            min(row["runWallNs"]) > 0 and min(row["runCpuNs"]) > 0,
            "Missing complete timing",
        )
        require(
            row["processWallNs"] > 0 and row["peakRssBytes"] > 0,
            "Missing process controls",
        )
    require(
        len(rows)
        == 2
        + settings["aaPairs"] * 2
        + settings["coldProcessesPerArm"] * 2
        + settings["processPairs"] * 2,
        "Independent process population drift",
    )

    def selected(stage: str, index: int, arm: str) -> dict:
        items = [
            row
            for row in rows
            if row["stage"] == stage and row["index"] == index and row["arm"] == arm
        ]
        require(len(items) == 1, "Duplicate or missing process: " + stage)
        return items[0]

    aa = [
        statistics.median(selected("aa-first", index, "dawn")["runWallNs"])
        / statistics.median(selected("aa-second", index, "dawn")["runWallNs"])
        for index in range(settings["aaPairs"])
    ]
    aa_ratio = statistics.median(aa)
    aa_ratio = max(aa_ratio, 1 / aa_ratio)
    require(aa_ratio <= settings["maximumAaMedianRatio"], "A/A failed")
    warm = [row for row in rows if row["stage"] == "warm"]
    cold = [row for row in rows if row["stage"] == "cold"]
    for stage in ["cold", "warm"]:
        population = [row for row in rows if row["stage"] == stage]
        for index in range(len(population) // 2):
            require(
                [row["arm"] for row in population[index * 2 : index * 2 + 2]]
                == (["dawn", "doe"] if index % 2 == 0 else ["doe", "dawn"]),
                "Unbalanced arm order",
            )
    require(
        len(set(row["cache"] for row in cold)) == len(cold),
        "Cold processes reused a cache",
    )
    for arm in ["dawn", "doe"]:
        require(
            len(set(row["cache"] for row in warm if row["arm"] == arm)) == 1,
            "Warm cache scope changed",
        )
    ratios = np.array(
        [
            statistics.median(selected("warm", index, "dawn")["runWallNs"])
            / statistics.median(selected("warm", index, "doe")["runWallNs"])
            for index in range(settings["processPairs"])
        ]
    )
    estimates = np.median(
        np.random.default_rng(settings["bootstrapSeed"]).choice(
            ratios, (settings["bootstrapResamples"], len(ratios))
        ),
        axis=1,
    )
    lower = float(np.quantile(estimates, (1 - settings["confidence"]) / 2))
    regressions = {}
    for name, population, field in [
        ("warmP95", warm, "runWallNs"),
        ("coldProcessWall", cold, "processWallNs"),
        ("processCpu", warm, "runCpuNs"),
        ("peakRss", warm, "peakRssBytes"),
    ]:

        def value(row: dict) -> float:
            raw = row[field]
            if name == "warmP95":
                return float(np.quantile(raw, 0.95))
            if name == "processCpu":
                return float(statistics.median(raw))
            return float(raw)

        medians = {
            arm: statistics.median(
                value(row) for row in population if row["arm"] == arm
            )
            for arm in ["dawn", "doe"]
        }
        regressions[name] = medians["doe"] / medians["dawn"]
    primary = float(np.median(ratios))
    passed = (
        primary >= settings["materialGainRatio"]
        and lower >= settings["minimumLowerConfidenceRatio"]
        and all(
            value <= settings["regressionMaximumRatios"][name]
            for name, value in regressions.items()
        )
    )
    return {
        "aaMedianRatio": aa_ratio,
        "primaryRatio": primary,
        "lowerConfidenceRatio": lower,
        "regressionRatios": regressions,
        "passed": passed,
    }


def verify(report: Path, repo: Path, with_custody: bool = False) -> dict:
    """Validate immutable files before evaluating any result or deployment claim."""
    manifest = json.loads((report / "manifest.json").read_text())
    original = {}
    decoded = {}
    for name, record in manifest["files"].items():
        path = (report / name).resolve()
        require(path.is_relative_to(report.resolve()), "Report path escaped root")
        data = path.read_bytes()
        require(digest(data) == record["sha256"], "Retained artifact changed: " + name)
        content = gzip.decompress(data) if record["compression"] == "gzip" else data
        require(
            digest(content) == record["contentSha256"],
            "Decoded artifact changed: " + name,
        )
        original[record["originalPath"]] = content
        decoded[name.removesuffix(".gz")] = content
    for name, expected in manifest["sources"].items():
        require(
            (repo / name).resolve().is_relative_to(repo.resolve()),
            "Source path escaped root",
        )
        require(
            digest((repo / name).read_bytes()) == expected,
            "Current source drift: " + name,
        )

    custody_entries = json.loads(decoded["custody-entries.json"])

    def read(name: str) -> dict:
        return json.loads(decoded[name])

    def bound(identity: dict) -> None:
        if identity["path"] in original:
            require(
                digest(original[identity["path"]]) == identity["sha256"],
                "Input hash mismatch",
            )
            return
        candidates = [
            entry
            for entry in custody_entries.values()
            if entry["kind"] == "file" and entry["sha256"] == identity["sha256"]
        ]
        require(
            bool(candidates), "Input absent from retained custody: " + identity["path"]
        )

    policy = read("policy.json")
    require(
        decoded["policy.json"]
        == (repo / "config/onnx-vulkan-campaign.json").read_bytes(),
        "Frozen policy changed",
    )
    app = read("raw/application-matched/preparation.json")
    require(
        app["upstreamSource"]["sha256"] == policy["application"]["sha256"],
        "Application source changed",
    )
    require(
        app["model"]["sha256"] == policy["application"]["modelSha256"], "Model changed"
    )
    require(app["applicationHeaders"]["tag"] == "v1.24.4", "Core/header ABI drift")
    bound(app["upstreamSource"])
    bound(app["preparedSource"])
    bound(app["patch"])
    bound(app["application"])
    bound(app["onnxCore"])
    require(
        digest(decoded["raw/execution-harness/prepare.py"]) == app["builder"]["sha256"],
        "Preparation source not retained",
    )
    require(
        digest(
            (
                repo
                / "bench/external-projects/onnx-vulkan-campaign/application-provider.h"
            ).read_bytes()
        )
        == app["providerIntegration"]["sha256"],
        "Provider integration source drift",
    )
    proc_names = read("raw/bridge-matched/build.json")["procNames"]
    expected_nodes = None
    native_hashes = {}
    for arm in ["dawn", "doe"]:
        safety = read("raw/safety/" + arm + "-matched.json")
        require(safety["passed"] and safety["failure"] is None, "Safety failed")
        require(
            safety["initialDrmClients"] == safety["finalDrmClients"],
            "DRM ownership did not settle",
        )
        for name in [
            "failedSessionRecovery",
            "preexecutionCancellationReuse",
        ]:
            require(safety[name]["reused"], "Recovery failed: " + name)
        require(
            safety["preexecutionCancellationReuse"]["phase"] == "before-execution",
            "Cancellation scope promoted",
        )
        controls = (
            safety if arm == "doe" else read("raw/safety/dawn-additional-controls.json")
        )
        require(
            controls["passed"] and controls["libraries"] == safety["libraries"],
            "Recovery control bytes drift",
        )
        require(
            controls["initializationRecovery"]["reused"]
            and controls["initializationRecovery"]["missing"]
            == "DoeBridgeLibraryOpenFailed"
            and controls["initializationRecovery"]["rebind"]
            == "DoeBridgeAlreadyInitialized",
            "Initialization recovery failed",
        )
        require(
            controls["descriptorRecovery"]["status"] == 0
            and controls["descriptorRecovery"]["reused"],
            "Descriptor recovery control failed",
        )
        for run in safety["runs"]:
            require(run["observed"] == run["expected"], "MatMul/Add regression failed")
        require(
            set(safety["operatorProviders"]) == {"WebGpuExecutionProvider"},
            "Regression CPU fallback",
        )
        for item in safety["libraries"].values():
            bound(item)
        require(
            safety["contextIdentity"]["vendor"] == policy["consumer"]["vendorId"]
            and safety["contextIdentity"]["backend"] == 6,
            "Physical backend drift",
        )
        q = read("raw/" + arm + "-matched.json")
        require(
            q["passed"] and not q["negativeControl"] and q["failure"] is None,
            "Application qualification failed",
        )
        require(
            set(q["operatorProviders"]) == {"WebGpuExecutionProvider"},
            "Application CPU fallback",
        )
        require(
            q["operatorNames"]
            and (expected_nodes is None or expected_nodes == q["operatorNames"]),
            "Application work differs",
        )
        expected_nodes = q["operatorNames"]
        for item in q["inputs"].values():
            bound(item)
        bound(q["safety"])
        bound(q["policy"])
        bound(q["profile"])
        bound(q["log"])
        profile = json.loads(original[q["profile"]["path"]])
        nodes = [
            event["args"]
            for event in profile
            if event.get("cat") == "Node" and "provider" in event.get("args", {})
        ]
        require(
            [node["op_name"] for node in nodes] == q["operatorNames"],
            "Profile operation sequence drift",
        )
        require(
            [node["provider"] for node in nodes] == q["operatorProviders"],
            "Profile placement drift",
        )
        require(
            all(q["callCounts"].get(name, 0) > 0 for name in REQUIRED_CALLS),
            "Native ownership incomplete",
        )
        for name in ["native", "provider", "bridge", "context"]:
            require(
                q["inputs"][name]["sha256"] == safety["libraries"][name]["sha256"],
                "Safety qualified different bytes",
            )
        negative = read("raw/" + arm + "-matched-disabled.json")
        require(
            negative["passed"]
            and negative["negativeControl"]
            and negative["exitCode"] != 0,
            "Native disabling control failed",
        )
        bound(negative["log"])
        logged_calls = {}
        for line in original[q["log"]["path"]].decode().splitlines():
            if line.startswith("CampaignCallCount "):
                _, index, count = line.split()
                logged_calls[proc_names[int(index)]] = int(count)
        require(
            logged_calls == q["callCounts"], "Raw native operation observations differ"
        )
        require(
            "Proc-table initialization failed"
            in original[negative["log"]["path"]].decode(),
            "Negative control failed elsewhere",
        )
        native_hashes[arm] = q["inputs"]["native"]["sha256"]
    dawn, doe = read("raw/dawn-matched.json"), read("raw/doe-matched.json")
    for key in ["application", "provider", "bridge", "context", "reference"]:
        require(
            dawn["inputs"][key] == doe["inputs"][key],
            "Unmatched common consumer input: " + key,
        )
    require(
        dawn["callCounts"] == doe["callCounts"],
        "Observed common operation shape differs",
    )
    oracle = read("raw/reference/reference.json")
    crosscheck = read("raw/reference/cpu-crosscheck.json")
    require(
        digest(decoded["raw/execution-harness/reference.py"]) == oracle["sourceSha256"],
        "Oracle source not retained",
    )
    require(
        crosscheck["passed"]
        and crosscheck["modelSha256"]
        == oracle["modelSha256"]
        == policy["application"]["modelSha256"],
        "Oracle model drift",
    )
    require(
        oracle["outputSha256"]
        == doe["inputs"]["reference"]["sha256"]
        == crosscheck["outputSha256"],
        "Independent oracle drift",
    )
    require(
        crosscheck["cpuTop1"] == oracle["top1"] == crosscheck["referenceTop1"],
        "Original application behavior differs",
    )
    dot = read("raw/compiler-reproduction/integer-dot-physical.json")
    require(
        dot["passed"]
        and dot["observed"] == dot["expected"]
        and dot["nativeSha256"] == native_hashes["doe"],
        "Integer dot physical regression",
    )
    full_shader = read("raw/compiler-reproduction/full-shader-final.json")
    shader_data = decoded["raw/compiler-reproduction/04-Conv2dMM.wgsl"]
    require(
        digest(shader_data) == full_shader["shaderSha256"], "Unchanged shader drift"
    )
    require(
        {row["mode"] for row in full_shader["rows"]}
        == {"default", "vulkan-compute-runtime"},
        "Missing compiler mode",
    )
    for row in full_shader["rows"]:
        require(
            row["exitCode"] == row["validationExitCode"] == 0,
            "Full shader validation failed",
        )
        require(
            digest(decoded["raw/compiler-reproduction/final-" + row["mode"] + ".spv"])
            == row["outputSha256"],
            "Full SPIR-V output drift",
        )
    require(
        "emit_dot" in decoded["raw/compiler-reproduction/debug-compile.log"].decode()
        and "UnsupportedConstruct"
        in decoded["raw/compiler-reproduction/compile.log"].decode(),
        "Original dot failure absent",
    )
    doppler = read("raw/safety/doppler-safety-final.json")
    require(
        doppler["passed"]
        and doppler["physical"]["destructionCalls"] == [1, 1]
        and doppler["physical"]["resources"]["deferredCleanup"]["count"] == 0,
        "Retirement did not settle exactly once",
    )
    require(
        doppler["physical"]["nativeSha256"] == native_hashes["doe"],
        "Doppler qualified a different native",
    )
    require(
        "Deferred destruction failed"
        in decoded[
            "raw/safety/doppler-replay/results/retirement-original.log"
        ].decode(),
        "Original warning was not reproduced",
    )
    for label in ["delivered-final-first", "delivered-final-reopen"]:
        prefix = "raw/safety/doppler-delivered/results/" + label
        require(
            read(prefix + "-audit.json")["passed"],
            "Installed generation qualification failed",
        )
        require(
            "Deferred destruction failed" not in decoded[prefix + ".log"].decode(),
            "Corrected warning persists",
        )
    require(
        doppler["physical"]["poolSha256"] == doppler["sourceSha256"],
        "Physical pool source drift",
    )
    require(
        custody_entries["doppler/node_modules/doppler-gpu/src/memory/buffer-pool.js"][
            "sha256"
        ]
        == doppler["sourceSha256"],
        "Delivered pool source drift",
    )
    require(
        custody_entries["doppler/archives/doppler-retirement-final.tgz"]["sha256"]
        == doppler["archiveSha256"],
        "Delivered package drift",
    )
    for audit in doppler["installedChecks"]:
        bound(audit)
        require(
            audit["passed"] and audit["warningAbsent"],
            "Installed retirement admission failed",
        )
    m = read("raw/measurement-qualified/measurement.json")
    schema = json.loads((repo / "config/onnx-vulkan-evidence.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).evolve(
        schema={"$ref": "#/$defs/measurementWithCacheState"}
    ).validate(m)
    audit = read("cache-audit.json")
    require(
        audit["originalDisposition"] == "diagnostic-invalid-cold-cache"
        and audit["qualifiedMeasurementSha256"]
        == digest(decoded["raw/measurement-qualified/measurement.json"]),
        "Cache audit decision drift",
    )
    require(
        audit["originalMeasurementSha256"]
        == digest(decoded["raw/measurement/measurement.json"]),
        "Original cohort altered",
    )
    bound(m["policy"])
    bound(m["dopplerSafety"])
    for arm in ["doe", "dawn"]:
        bound(m["qualification"][arm])
    for row in m["rows"]:
        bound(row["log"])
        bound(row["observations"])
        samples = [
            line.split()
            for line in original[row["observations"]["path"]].decode().splitlines()
        ]
        require(
            row["runWallNs"] == [int(parts[1]) for parts in samples]
            and row["runCpuNs"] == [float(parts[2]) for parts in samples],
            "Raw timing samples changed",
        )
        logged_rss = int(
            next(
                line.split()[1]
                for line in original[row["log"]["path"]].decode().splitlines()
                if line.startswith("CampaignPeakRss ")
            )
        )
        require(
            logged_rss == row["peakRssBytes"], "Raw resident-set observation changed"
        )
        require(
            "CampaignCleanupFailure" not in original[row["log"]["path"]].decode(),
            "Measured cleanup failure",
        )
    values = measurement_values(m, policy)
    for key in ["aaMedianRatio", "primaryRatio", "lowerConfidenceRatio"]:
        require(
            math.isclose(values[key], m[key], rel_tol=1e-12),
            "Derived statistic changed: " + key,
        )
    for name, ratio in values["regressionRatios"].items():
        require(
            math.isclose(ratio, m["regressionRatios"][name], rel_tol=1e-12),
            "Regression statistic changed",
        )
    require(
        values["passed"] == m["passed"]
        and m["performanceCorrections"] == manifest["performanceCorrections"] == 0,
        "Verdict or correction count drift",
    )
    require(
        not m["passed"] and m["disposition"] == "no-material-advantage",
        "Unfavorable result promoted",
    )
    summary = read("measurement-summary.json")
    for key in [
        "schemaVersion",
        "classification",
        "passed",
        "disposition",
        "aaMedianRatio",
        "primaryRatio",
        "lowerConfidenceRatio",
        "regressionRatios",
        "performanceCorrections",
    ]:
        require(summary[key] == m[key], "Measurement summary drift: " + key)
    require(
        summary["rawMeasurementSha256"]
        == digest(decoded["raw/measurement-qualified/measurement.json"]),
        "Summary not bound to raw cohort",
    )
    trace = json.loads((report / "trace-meta.json").read_text())
    require(
        trace["hash"] == summary["rawMeasurementSha256"]
        and trace["previousHash"] == digest(decoded["policy.json"]),
        "Trace hash chain drift",
    )
    replay = read("raw/deployment-final/results/replay.json")
    require(
        replay["passed"]
        and replay["network"] == "unshared"
        and replay["checkoutExposure"] == "none",
        "Isolated replay failed",
    )
    require(
        len(replay["rows"]) == 6 and all(row["passed"] for row in replay["rows"]),
        "Replay controls incomplete",
    )
    require(
        read("bundle.json")["qualifiedNativeHashes"] == native_hashes,
        "Deployment native differs",
    )
    delivery = read("raw/doppler-offline-final/delivery.json")
    installed = read("raw/doppler-offline-final/results/summary.json")
    require(
        delivery["nativeSha256"] == native_hashes["doe"]
        and delivery["dopplerArchiveSha256"] == doppler["archiveSha256"],
        "Offline delivery bytes drift",
    )
    require(
        installed["passed"]
        and installed["offlineReinstallationPassed"]
        and len(installed["checks"]) == 6
        and all(row["passed"] for row in installed["checks"]),
        "Offline installation controls failed",
    )
    require(
        installed["installationSha256"]
        == digest(decoded["raw/doppler-offline-final/installation.json"]),
        "Offline installation manifest drift",
    )
    for label in ["doe-first", "doe-reopen"]:
        prefix = "raw/doppler-offline-final/results/" + label
        require(
            read(prefix + "-audit.json")["passed"] and read(prefix + ".json")["passed"],
            "Offline generation failed",
        )
        require(
            "Deferred destruction failed" not in decoded[prefix + ".log"].decode(),
            "Offline retirement warning",
        )
    for row in replay["rows"]:
        command = row["command"]
        require(
            "--unshare-net" in command
            and "--clearenv" in command
            and "/home" not in command,
            "Isolation contract drift",
        )
        require(
            digest(decoded["raw/deployment-final/results/" + row["log"]])
            == row["logSha256"],
            "Replay log drift",
        )
    perf = read("raw/warm-profile/native-cpu-permission.json")
    require(
        not perf["passed"] and perf["exitCode"] != 0,
        "Native CPU attribution status drift",
    )
    require(
        "Access to performance monitoring"
        in decoded["raw/warm-profile/native-cpu-permission.log"].decode(),
        "Perf limitation not retained",
    )
    historical = manifest["historicalReport"]
    require(
        digest((repo / historical["path"]).read_bytes()) == historical["sha256"],
        "Historical report changed",
    )
    require(
        "PASS" in decoded["raw/historical-source/verification.log"].decode().upper(),
        "Historical custody replay did not pass",
    )
    if with_custody:
        custody = manifest["custody"]
        archive_path = Path(custody["archivePath"])
        require(
            digest(archive_path.read_bytes()) == custody["archiveSha256"],
            "Custody archive changed",
        )
        seen = set()
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive:
                require(
                    member.name not in seen and member.name in custody_entries,
                    "Unexpected custody member",
                )
                seen.add(member.name)
                item = custody_entries[member.name]
                if member.issym():
                    require(
                        item["kind"] == "symlink" and member.linkname == item["target"],
                        "Custody link drift",
                    )
                else:
                    require(
                        member.isfile() and item["kind"] == "file",
                        "Custody member type drift",
                    )
                    require(
                        digest(archive.extractfile(member).read()) == item["sha256"]
                        and member.size == item["bytes"],
                        "Custody bytes drift",
                    )
        require(seen == set(custody_entries), "Missing custody member")
    return {
        "safety": "passed",
        "application": "qualified-bounded-host",
        "advantage": "rejected",
        "performanceCorrection": "none",
        "custody": "verified" if with_custody else "local-not-opened",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report", type=Path, required=True, help="Retained campaign report"
    )
    parser.add_argument(
        "--with-custody",
        action="store_true",
        help="Also hash every local archive member",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            verify(args.report, Path(__file__).resolve().parents[3], args.with_custody),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
