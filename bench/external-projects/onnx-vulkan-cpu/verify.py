"""Replay CPU diagnostic admission from retained raw observations."""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import struct
import tarfile
import tempfile

import jsonschema

from decision import evaluate


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def replay_locations(directory: Path, profile: dict, records: list[tuple]) -> None:
    """Replay every mapped PC and caller candidate using retained ELF load metadata."""
    mappings = profile["mappingLoads"]
    raw_maps = {}
    for line in (directory / "maps").read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and "x" in fields[1]:
            start, end = (int(value, 16) for value in fields[0].split("-"))
            raw_maps[(start, end, fields[5])] = int(fields[2], 16)
    for item in mappings:
        key = (item["start"], item["end"], item["library"]["path"])
        require(key in raw_maps, "Invented executable mapping")
        offset = raw_maps[key]
        require(
            any(
                item["loadBias"]
                == item["start"]
                - (segment["virtualAddress"] - segment["offset"] + offset)
                for segment in item["segments"]
            ),
            "ELF load bias drift",
        )

    def location(pc: int) -> tuple[str, int] | None:
        for item in mappings:
            if item["start"] <= pc < item["end"]:
                return item["library"]["path"], pc - item["loadBias"]
        return None

    leaves = Counter()
    callers = Counter()
    unmapped = 0
    for row in records:
        leaf = location(row[0])
        if leaf is None:
            unmapped += 1
            continue
        leaves[leaf] += 1
        for index in range(row[4]):
            caller = location(row[5 + index] - 1)
            if caller is not None:
                callers[(caller, leaf)] += 1
    require(unmapped == profile["unmappedSamples"], "Unmapped PC drift")
    require(
        leaves
        == Counter(
            {
                (item["libraryPath"], int(item["address"], 16)): item["samples"]
                for item in profile["locations"]
            }
        ),
        "Instruction location drift",
    )
    expected_callers = Counter()
    for item in profile["frameCandidates"]:
        require(
            item["samples"] == sum(leaf["samples"] for leaf in item["leaves"]),
            "Caller sample total drift",
        )
        for leaf in item["leaves"]:
            expected_callers[
                (
                    (item["libraryPath"], int(item["address"], 16)),
                    (leaf["libraryPath"], int(leaf["address"], 16)),
                )
            ] = leaf["samples"]
    require(callers == expected_callers, "Caller candidate drift")
    module_counts = Counter()
    for (path, _), count in leaves.items():
        module_counts[path] += count
    require(
        module_counts
        == Counter(
            {item["library"]["path"]: item["samples"] for item in profile["modules"]}
        ),
        "Module sample drift",
    )


def verify(report: Path, repo: Path, with_custody: bool = False) -> dict:
    """Verify bytes, scope, observation sensitivity, and the no-patch stopping rule."""
    manifest = json.loads((report / "manifest.json").read_text())
    evidence_schema = json.loads(
        (repo / "config/onnx-vulkan-cpu-evidence.schema.json").read_text()
    )
    policy_schema = json.loads(
        (repo / "config/onnx-vulkan-cpu-investigation.schema.json").read_text()
    )
    jsonschema.validate(manifest, evidence_schema)
    require(manifest["performanceCorrections"] == 0, "Unexpected runtime correction")
    for name, expected in manifest["sources"].items():
        require(
            hashlib.sha256((repo / name).read_bytes()).hexdigest() == expected,
            "Current harness changed: " + name,
        )
    for name, expected in manifest["nativeSources"].items():
        require(
            hashlib.sha256((repo / name).read_bytes()).hexdigest() == expected,
            "Native owner changed: " + name,
        )
    historical = (
        repo
        / "reports/benchmarks/amd-vulkan/20261005-onnx-vulkan-campaign/manifest.json"
    )
    require(
        hashlib.sha256(historical.read_bytes()).hexdigest()
        == manifest["historicalManifest"]["sha256"],
        "Historical report changed",
    )
    with tempfile.TemporaryDirectory() as temporary:
        restored = Path(temporary)
        for name, item in manifest["files"].items():
            require(
                not Path(name).is_absolute() and ".." not in Path(name).parts,
                "Escaping retained path",
            )
            source = report / name
            data = source.read_bytes()
            require(
                hashlib.sha256(data).hexdigest() == item["sha256"],
                "Retained byte drift: " + name,
            )
            content = gzip.decompress(data) if item["compression"] == "gzip" else data
            require(
                hashlib.sha256(content).hexdigest() == item["contentSha256"]
                and len(content) == item["contentBytes"],
                "Decoded byte drift: " + name,
            )
            relative = (
                name.removesuffix(".gz") if item["compression"] == "gzip" else name
            )
            target = restored / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            if relative.endswith(".json"):
                value = json.loads(content)
                if isinstance(value, dict) and str(
                    value.get("classification", "")
                ).startswith(("diagnostic-cpu-", "vulkan-cpu-attribution-")):
                    jsonschema.validate(value, evidence_schema)
        run = restored / "raw"
        policy = json.loads((restored / "policy.json").read_text())
        jsonschema.validate(policy, policy_schema)
        require(
            policy
            == json.loads(
                (repo / "config/onnx-vulkan-cpu-investigation.json").read_text()
            ),
            "Frozen policy changed",
        )
        require(
            policy == json.loads((run / "caller-collection/policy.json").read_text()),
            "Collection policy mismatch",
        )
        names = json.loads((run / "qualification/build.json").read_text())["procNames"]
        qualified = {
            arm: json.loads((run / f"qualification/{arm}-matched.json").read_text())
            for arm in ["doe", "dawn"]
        }
        for arm, q in qualified.items():
            require(
                q["passed"] and not q["negativeControl"],
                "Application qualification failed",
            )
            require(
                q["operatorNames"]
                and set(q["operatorProviders"]) == {"WebGpuExecutionProvider"},
                "CPU fallback or missing operators",
            )
            safety = json.loads((run / f"safety-{arm}.json").read_text())
            require(
                safety["passed"]
                and safety["failure"] is None
                and safety["initialDrmClients"] == safety["finalDrmClients"],
                "Diagnostic bridge recovery failed",
            )
            require(
                safety["libraries"]["native"]["sha256"]
                == q["inputs"]["native"]["sha256"],
                "Safety selected another native",
            )
        require(
            qualified["doe"]["operatorNames"] == qualified["dawn"]["operatorNames"],
            "Operation placement differs",
        )
        build = json.loads((run / "diagnostic-v5/build.json").read_text())
        retained_builder = run / "diagnostic-v5/sources/probe.py"
        builder_hash = next(
            item["sha256"]
            for item in build["sources"]
            if item["path"].endswith("/probe.py")
        )
        require(
            hashlib.sha256(retained_builder.read_bytes()).hexdigest() == builder_hash,
            "Executed builder source missing",
        )
        sampler_hash = next(
            item["sha256"]
            for item in build["sources"]
            if item["path"].endswith("/sampler.c")
        )
        require(
            hashlib.sha256(
                (run / "diagnostic-v5/sources/sampler.c").read_bytes()
            ).hexdigest()
            == sampler_hash,
            "Executed sampler source missing",
        )
        require(
            hashlib.sha256((run / "diagnostic-v5/main.cpp").read_bytes()).hexdigest()
            == qualified_source_hash(run),
            "Application source changed",
        )
        header = (
            historical.parent / "raw/execution-harness/application-provider.h"
        ).read_text()
        header = header.replace(
            "inline std::vector<Ort::Value> campaign_run",
            'extern "C" void doeCpuProbeBegin();\nextern "C" void doeCpuProbeEnd();\nextern "C" void doeCpuProbeMaps();\ninline std::vector<Ort::Value> campaign_run',
        )
        header = header.replace(
            "        result = session.Run(",
            "        if (iteration >= 0) doeCpuProbeBegin();\n        result = session.Run(",
        )
        header = header.replace(
            "        auto cpu_end = std::clock();",
            "        if (iteration >= 0) doeCpuProbeEnd();\n        auto cpu_end = std::clock();",
        )
        header = header.replace(
            "    struct rusage usage{};",
            "    doeCpuProbeMaps();\n    struct rusage usage{};",
        )
        require(
            (run / "diagnostic-v5/application-provider.h").read_text() == header,
            "Diagnostic observation changed application semantics",
        )
        header_hash = next(
            item["sha256"]
            for item in build["sources"]
            if item["path"].endswith("/application-provider.h")
        )
        require(
            hashlib.sha256(header.encode()).hexdigest() == header_hash,
            "Executed application header drift",
        )
        adapter = (historical.parent / "raw/bridge-matched/adapter.zig").read_text()
        adapter = adapter.replace(
            'const std = @import("std");',
            'const std = @import("std");\nextern fn doeCpuProbeEnter(index: c_uint) callconv(.c) void;\nextern fn doeCpuProbeLeave() callconv(.c) void;',
        )
        adapter = adapter.replace(
            "    _ = calls[index].fetchAdd",
            "    doeCpuProbeEnter(index);\n    defer doeCpuProbeLeave();\n    _ = calls[index].fetchAdd",
        )
        require(
            (run / "diagnostic-v5/sources/adapter.zig").read_text() == adapter
            and (run / "diagnostic-v5/bridge/adapter.zig").read_text() == adapter,
            "Diagnostic observation changed bridge semantics",
        )
        process_counts = {}
        cache_homes = set()
        for directory in sorted((run / "caller-collection").iterdir()):
            if not directory.is_dir():
                continue
            receipt = json.loads((directory / "run.json").read_text())
            for field, name in [
                ("log", "application.log"),
                ("observations", "observations"),
                ("samples", "samples.bin"),
                ("maps", "maps"),
            ]:
                if receipt[field] is not None:
                    require(
                        receipt[field]["sha256"]
                        == hashlib.sha256((directory / name).read_bytes()).hexdigest(),
                        "Run input link drift: " + field,
                    )
            label = directory.name
            arm = label.rsplit("-", 1)[1]
            content = (directory / "application.log").read_text()
            require(
                receipt["exitCode"] == 0 and "CampaignCleanupFailure" not in content,
                "Application or cleanup failed",
            )
            require(
                "CampaignContext 6 4098 5510 " in content,
                "Physical AMD Vulkan identity changed",
            )
            q = qualified[arm]
            environment = receipt["environment"]
            home = environment["HOME"]
            require(
                home not in cache_homes and Path(home).parent.parent.name == label,
                "Processes reused a cache HOME",
            )
            cache_homes.add(home)
            require(
                Path(environment["XDG_CACHE_HOME"]) == Path(home).parent
                and Path(environment["MESA_SHADER_CACHE_DIR"]) == Path(home).parent,
                "Native cache escaped process scope",
            )
            for key, name in [
                ("NATIVE", "native"),
                ("PROVIDER", "provider"),
                ("CONTEXT", "context"),
                ("REFERENCE", "reference"),
            ]:
                require(
                    environment["CAMPAIGN_" + key] == q["inputs"][name]["path"],
                    "Selected native or consumer changed",
                )
            require(
                environment["CAMPAIGN_MODE"] == "timing"
                and int(environment["CAMPAIGN_RUNS"])
                == policy["diagnostic"]["runsPerProcess"]
                and int(environment["CAMPAIGN_WARMUP"])
                == policy["diagnostic"]["warmupRuns"],
                "Invocation schedule changed",
            )
            rows = [
                line.split()
                for line in (directory / "observations").read_text().splitlines()
            ]
            require(
                len(rows) == policy["diagnostic"]["runsPerProcess"]
                and [int(row[0]) for row in rows] == list(range(len(rows))),
                "Missing or duplicated invocation",
            )
            require(
                all(int(row[1]) > 0 and float(row[2]) > 0 for row in rows),
                "Unavailable CPU/wall observation",
            )
            profile = json.loads((directory / "profile-final.json").read_text())
            require(
                profile["run"]["sha256"]
                == hashlib.sha256((directory / "run.json").read_bytes()).hexdigest(),
                "Profile run link drift",
            )
            require(
                profile["medianCpuNs"]
                == statistics.median(float(row[2]) for row in rows)
                and profile["medianWallNs"]
                == statistics.median(int(row[1]) for row in rows),
                "Derived CPU or wall drift",
            )
            summaries = [
                line.split()[1:]
                for line in content.splitlines()
                if line.startswith("CpuProbeSummary ")
            ]
            if summaries:
                runs, thread, process, dropped = map(int, summaries[0])
                require(
                    profile["summary"]
                    == {
                        "runs": runs,
                        "threadCpuNs": thread,
                        "processCpuNs": process,
                        "mainThreadCpuShare": thread / process,
                        "dropped": dropped,
                    },
                    "CPU clock summary drift",
                )
            else:
                require(profile["summary"] is None, "Invented CPU clock summary")
            counts = {
                int(line.split()[1]): int(line.split()[2])
                for line in content.splitlines()
                if line.startswith("CampaignCallCount ")
            }
            require(
                all(
                    counts.get(names.index(name), 0) > 0
                    for name in [
                        "deviceCreateShaderModule",
                        "queueSubmit",
                        "bufferMapAsync",
                        "deviceDestroy",
                        "deviceRelease",
                    ]
                ),
                "Missing native work or cleanup",
            )
            process_counts[label] = counts
            if "sample-" in label:
                data = (directory / "samples.bin").read_bytes()
                require(len(data) % 128 == 0, "Truncated CPU records")
                records = list(struct.iter_unpack("<" + "Q" * 16, data))
                require(
                    len(records) == profile["samples"]
                    and len({row[1] for row in records}) == 1
                    and all(row[4] <= 8 for row in records),
                    "CPU sample population drift",
                )
                require(
                    profile["threadIds"] == sorted({row[1] for row in records}),
                    "Observed CPU thread drift",
                )
                sites = Counter(row[3] for row in records)
                require(
                    {item["index"]: item["samples"] for item in profile["sites"]}
                    == dict(sites),
                    "Call-site sample drift",
                )
                require(
                    sum(item["samples"] for item in profile["locations"])
                    + profile["unmappedSamples"]
                    == len(records),
                    "Missing symbolized work",
                )
                require(
                    profile["overruns"] == sum(row[2] for row in records),
                    "Lost timer overruns",
                )
                replay_locations(directory, profile, records)
                require(
                    any(
                        item["library"]["sha256"] == q["inputs"]["native"]["sha256"]
                        for item in profile["modules"]
                    ),
                    "Selected native has no CPU observation",
                )
            expected_app = (
                q["inputs"]["application"]["sha256"]
                if "original" in label
                else build["application"]["sha256"]
            )
            require(
                receipt["application"]["sha256"] == expected_app,
                "Unexpected application binary",
            )
            require(
                receipt["bridge"]["sha256"]
                == (
                    build["bridge"]["sha256"]
                    if "sample-" in label
                    else q["inputs"]["bridge"]["sha256"]
                ),
                "Unexpected bridge binary",
            )
        for arm in ["doe", "dawn"]:
            counts = [
                value
                for label, value in process_counts.items()
                if label.endswith("-" + arm)
            ]
            require(
                all(value == counts[0] for value in counts),
                "Instrumentation changed observable calls",
            )
            for control, marker in [
                ("native", "Proc-table initialization failed"),
                ("oracle", "Independent oracle mismatch"),
            ]:
                negative = run / f"negative-{arm}-{control}"
                receipt = json.loads((negative / "run.json").read_text())
                log = (negative / "application.log").read_text()
                require(
                    receipt["negativeControl"] == control
                    and receipt["exitCode"] != 0
                    and marker in log
                    and "CampaignCleanupFailure" not in log,
                    "Negative control lost sensitivity",
                )
                if control == "oracle":
                    corrupted = (negative / "corrupted-reference.f32").read_bytes()
                    require(
                        struct.unpack_from("<f", corrupted)[0] == 1.0
                        and hashlib.sha256(corrupted).hexdigest()
                        != qualified[arm]["inputs"]["reference"]["sha256"],
                        "Corrupted oracle control lost its input",
                    )
        expected = evaluate(run, policy)
        actual = json.loads((restored / "decision.json").read_text())
        # Restored paths differ; all numerical and disposition fields must replay.
        for key in actual:
            if key not in ["policy", "profiles"]:
                require(actual[key] == expected[key], "Decision replay drift: " + key)
        require(
            actual["policy"]["sha256"]
            == hashlib.sha256(
                (run / "caller-collection/policy.json").read_bytes()
            ).hexdigest(),
            "Decision policy link drift",
        )
        require(
            [item["sha256"] for item in actual["profiles"]]
            == [item["sha256"] for item in expected["profiles"]],
            "Decision profile links drift",
        )
        require(
            actual["diagnosticAdmission"]
            and actual["disposition"] == "no-admitted-candidate"
            and actual["performanceCorrections"] == 0
            and not actual["performanceClaim"],
            "Unqualified performance promotion",
        )
    if with_custody:
        archive = Path(manifest["custody"]["archive"]["path"])
        require(
            hashlib.sha256(archive.read_bytes()).hexdigest()
            == manifest["custody"]["archive"]["sha256"],
            "Custody archive changed",
        )
        with tarfile.open(archive) as bundle:
            for item in manifest["custody"]["entries"]:
                stream = bundle.extractfile(item["member"])
                require(
                    stream is not None
                    and hashlib.sha256(stream.read()).hexdigest() == item["sha256"],
                    "Custody member changed",
                )
    return {
        "attribution": "qualified-bounded-diagnostic",
        "candidate": "none",
        "performance": "no-claim",
    }


def qualified_source_hash(run: Path) -> str:
    return json.loads((run / "qualification/preparation.json").read_text())[
        "preparedSource"
    ]["sha256"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report", type=Path, required=True, help="Retained investigation report"
    )
    parser.add_argument(
        "--with-custody",
        action="store_true",
        help="Also verify ignored local executable archive",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            verify(args.report, Path(__file__).resolve().parents[3], args.with_custody)
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
