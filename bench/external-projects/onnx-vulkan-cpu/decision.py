"""Apply diagnostic admission and stop without an evidenced general correction."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import struct

from probe import identity


def read_cpu(directory: Path) -> float:
    rows = [
        line.split() for line in (directory / "observations").read_text().splitlines()
    ]
    return statistics.median(float(row[2]) for row in rows)


def evaluate(root: Path, policy: dict) -> dict:
    """Admit attribution separately from any application advantage decision."""
    settings = policy["diagnostic"]
    collection = root / "caller-collection"
    checks = []
    profiles = []
    control_ratios = []
    original_ratios = []
    projections = []
    repo = Path(__file__).resolve().parents[3]
    historical = repo / policy["historicalReport"]
    site_names = json.loads((historical / "raw/bridge-matched/build.json").read_text())[
        "procNames"
    ]
    site_totals = Counter()
    site_samples = 0
    native_leaves = Counter()
    native_samples = 0
    for index in range(settings["processPairs"]):
        doe = read_cpu(collection / f"{index}-original-doe")
        dawn = read_cpu(collection / f"{index}-original-dawn")
        original_ratios.append(doe / dawn)
        for arm in ["doe", "dawn"]:
            original = read_cpu(collection / f"{index}-original-{arm}")
            off = read_cpu(collection / f"{index}-off-{arm}")
            ratio = off / original
            checks.append(
                {
                    "id": f"{index}-{arm}-hooks",
                    "observed": ratio,
                    "limit": settings["maximumSamplingCpuRatio"],
                    "passed": ratio <= settings["maximumSamplingCpuRatio"],
                }
            )
            for period in settings["periodsUs"]:
                path = collection / f"{index}-sample-{period}-{arm}"
                profile = json.loads((path / "profile-final.json").read_text())
                profiles.append(identity(path / "profile-final.json"))
                ratio = profile["medianCpuNs"] / off
                control_ratios.append(ratio)
                summary = profile["summary"]
                admitted = (
                    profile["samples"] >= settings["minimumSamples"]
                    and profile["unmappedSamples"] / profile["samples"]
                    <= settings["maximumUnmappedFraction"]
                    and summary["dropped"] <= settings["maximumDroppedSamples"]
                    and summary["mainThreadCpuShare"]
                    >= settings["minimumMainThreadCpuShare"]
                    and ratio <= settings["maximumSamplingCpuRatio"]
                    and len(profile["threadIds"]) == 1
                )
                checks.append(
                    {
                        "id": path.name,
                        "observed": ratio,
                        "limit": settings["maximumSamplingCpuRatio"],
                        "passed": admitted,
                    }
                )
                if arm == "doe":
                    records = list(
                        struct.iter_unpack(
                            "<" + "Q" * 16, (path / "samples.bin").read_bytes()
                        )
                    )
                    sites = Counter(row[3] for row in records)
                    site_totals.update(sites)
                    site_samples += len(records)
                    for item in profile["locations"]:
                        if item["libraryPath"].endswith("libwebgpu_doe.so"):
                            native_leaves[item["inlineFrames"][-1]["function"]] += item[
                                "samples"
                            ]
                            native_samples += item["samples"]
                    # Deliberately optimistic, approximate projection: remove the
                    # complete API site's sampled cost, including required work.
                    for name in [
                        "deviceCreateBindGroup",
                        "computePassEncoderDispatchWorkgroups",
                        "bufferRelease",
                        "deviceCreateBuffer",
                    ]:
                        share = sites[site_names.index(name)] / len(records)
                        projected_doe = doe * (1 - share)
                        projections.append(
                            {
                                "run": path.name,
                                "owner": name,
                                "sampleShare": share,
                                "ownerAdmission": share
                                >= settings["minimumOwnerCpuShare"],
                                "idealizedRetainedDoeGainRatio": 1 / (1 - share),
                                "idealizedDawnGainRatio": dawn / projected_doe,
                                "passesProjectedCriteria": (
                                    share >= settings["minimumOwnerCpuShare"]
                                    and 1 / (1 - share)
                                    >= policy["candidate"]["minimumPredictedGainRatio"]
                                    and dawn / projected_doe
                                    >= policy["candidate"]["minimumPredictedGainRatio"]
                                ),
                                "requiredGainRatio": policy["candidate"][
                                    "minimumPredictedGainRatio"
                                ],
                                "qualifiedPrediction": False,
                            }
                        )
    intrusive = []
    for index in range(settings["processPairs"]):
        for arm in ["doe", "dawn"]:
            first = root / "collection"
            ratio = read_cpu(first / f"{index}-spans-{arm}") / read_cpu(
                first / f"{index}-off-{arm}"
            )
            intrusive.append(
                {
                    "run": f"{index}-spans-{arm}",
                    "cpuRatio": ratio,
                    "limit": settings["maximumSpanCpuRatio"],
                    "admitted": ratio <= settings["maximumSpanCpuRatio"],
                }
            )
    original_aa = {}
    for arm in ["doe", "dawn"]:
        values = [
            read_cpu(collection / f"{i}-original-{arm}")
            for i in range(settings["processPairs"])
        ]
        original_aa[arm] = max(values) / min(values)
        checks.append(
            {
                "id": arm + "-original-process-control",
                "observed": original_aa[arm],
                "limit": policy["candidate"]["maximumAaMedianRatio"],
                "passed": original_aa[arm]
                <= policy["candidate"]["maximumAaMedianRatio"],
            }
        )
    admitted = all(item["passed"] for item in checks)
    if any(item["passesProjectedCriteria"] for item in projections):
        raise ValueError(
            "A projected opportunity requires independent owner proof before a no-patch decision"
        )
    return {
        "schemaVersion": 1,
        "classification": "vulkan-cpu-attribution-decision",
        "diagnosticAdmission": admitted,
        "disposition": (
            "no-admitted-candidate" if admitted else "stopped-diagnostic-admission"
        ),
        "policy": identity(root / "caller-collection/policy.json"),
        "checks": checks,
        "profiles": profiles,
        "originalDoeOverDawnCpuRatios": original_ratios,
        "originalProcessControls": original_aa,
        "samplingCpuRatios": control_ratios,
        "intrusiveSpanControls": intrusive,
        "siteShares": [
            {
                "owner": (
                    site_names[index] if index < len(site_names) else "outside-bridge"
                ),
                "samples": count,
                "share": count / site_samples,
            }
            for index, count in site_totals.most_common()
        ],
        "nativeInstructionLocations": [
            {
                "function": function,
                "samples": count,
                "nativeShare": count / native_samples,
            }
            for function, count in native_leaves.most_common()
        ],
        "projections": projections,
        "performanceCorrections": 0,
        "performanceClaim": False,
        "reason": "Matched processes reproduce excess CPU work. Binding-group creation, compute recording and retirement contribute; driver work remains common. No general correction has independently demonstrated the frozen predicted advantage against retained Doe and source-built Dawn. Intrusive timings and approximate sample projections cannot admit a patch.",
        "limitations": [
            "Main-thread CPU PC sampling; other threads are bounded by separate process CPU measurements.",
            "Timer overruns are retained and never assigned to the observed instruction.",
            "Frame pointers are bounded caller candidates; inline frames are symbolizer observations, not a complete unwind.",
            "Stripped-library labels can identify nearby exports rather than the executing function.",
            "No candidate or independent performance confirmation was executed.",
            "General callback/future conformance and submitted-work interruption remain open.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", type=Path, required=True, help="Completed diagnostic root"
    )
    parser.add_argument("--out", type=Path, required=True, help="New decision receipt")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Decision must be new")
    policy = json.loads((args.run / "caller-collection/policy.json").read_text())
    result = evaluate(args.run, policy)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["diagnosticAdmission"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
