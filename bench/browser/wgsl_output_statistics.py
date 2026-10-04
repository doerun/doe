"""Paired direct-WGSL differences, clustered by independent browser process."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any


METRICS = ("pipelinePreparationMs", "gpuComputeMs", "completeOperationMs", "applicationMs")
ARMS = ("original", "disabled", "transformed")


def interval(values: list[float], settings: dict[str, Any]) -> list[float]:
    """Percentile bootstrap over process means, never individual GPU frames."""
    rng = random.Random(settings["bootstrapSeed"])
    samples = sorted(
        statistics.fmean(rng.choices(values, k=len(values)))
        for _ in range(settings["bootstrapResamples"])
    )
    tail = (1 - settings["confidence"]) / 2
    return [samples[int(tail * (len(samples) - 1))],
            samples[int((1 - tail) * (len(samples) - 1))]]


def paired_rows(rows: list[dict[str, Any]], orders: list[list[str]]) -> list[dict[str, Any]]:
    if len(rows) != len(orders) * len(ARMS):
        raise ValueError("Missing or extra measured trials")
    pairs = []
    for cohort in range(len(orders)):
        trial = [row for row in rows if row["cohort"] == cohort]
        if [row["variant"] for row in trial] != orders[cohort]:
            raise ValueError("Trial order disagrees with frozen plan")
        by_arm = {row["variant"]: row for row in trial}
        if set(by_arm) != set(ARMS):
            raise ValueError("Missing paired arm")
        original = by_arm["original"]
        if original["wgslHash"] != by_arm["disabled"]["wgslHash"]:
            raise ValueError("A/A shader text differs")
        for row in trial:
            if not row["oracle"]["passed"] or (row["parity"] and not row["parity"]["passed"]):
                raise ValueError("Numerical oracle failed")
            if row["workerRoundTripMs"] != 0 or row["compileMs"] != 0:
                raise ValueError("Compiler delivery leaked into direct measurement")
            for field in ("dispatches", "draws", "workgroupsPerDispatch", "copiedParticleBytes", "ownedBufferBytes"):
                if row[field] != original[field]:
                    raise ValueError(f"Work shape differs: {field}")
        for comparison, left, right in (("aa", "original", "disabled"),
                                        ("ab", "original", "transformed"),
                                        ("bc", "disabled", "transformed")):
            metrics = {}
            for metric in METRICS:
                a, b = by_arm[left][metric], by_arm[right][metric]
                if a is None and b is None:
                    continue
                if a is None or b is None or a <= 0 or b <= 0:
                    raise ValueError(f"Invalid paired metric: {metric}")
                metrics[metric] = {"differenceMs": b - a, "logCostRatio": math.log(b / a)}
            pairs.append({"cohort": cohort, "comparison": comparison, "metrics": metrics})
    return pairs


def summarize(process_pairs: list[list[dict[str, Any]]], settings: dict[str, Any],
              margin: float) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for comparison in ("aa", "ab", "bc"):
        result[comparison] = {}
        for metric in METRICS:
            groups = [[pair["metrics"][metric] for pair in pairs
                       if pair["comparison"] == comparison and metric in pair["metrics"]]
                      for pairs in process_pairs]
            if all(not group for group in groups):
                continue
            if any(not group for group in groups):
                raise ValueError("Missing process metric")
            differences = [statistics.fmean(x["differenceMs"] for x in group) for group in groups]
            log_ratios = [statistics.fmean(x["logCostRatio"] for x in group) for group in groups]
            log_bounds = interval(log_ratios, settings)
            bounds = [math.exp(x) for x in log_bounds]
            if bounds[0] >= 1 / margin and bounds[1] <= margin:
                decision = "within-practical-margin"
            elif bounds[0] > margin:
                decision = "meaningful-cost-increase"
            elif bounds[1] < 1 / margin:
                decision = "meaningful-cost-decrease"
            else:
                decision = "inconclusive"
            result[comparison][metric] = {
                "processMeanDifferencesMs": differences,
                "processMeanLogCostRatios": log_ratios,
                "meanPairedDifferenceMs": statistics.fmean(differences),
                "differenceIntervalMs": interval(differences, settings),
                "geometricPairedCostRatio": math.exp(statistics.fmean(log_ratios)),
                "costRatioInterval": bounds, "decision": decision,
            }
    return result


def adjudicate(output: Path) -> dict[str, Any]:
    frozen = json.loads((output / "frozen-plan.json").read_text())
    plan = frozen["plan"]
    environment = json.loads((output / "environment.json").read_text())
    if environment["plan"] != plan or len(environment["sessions"]) != plan["sessions"]:
        raise ValueError("Fixed stopping rule incomplete or settings changed")
    if environment["implementationSha256"] != frozen["implementationSha256"]:
        raise ValueError("Runner changed after plan freeze")
    if (output / "failure.json").exists():
        raise ValueError("Run failed; no successful-cohort selection allowed")
    identities = {(entry["browserVersion"], json.dumps(entry["adapter"], sort_keys=True))
                  for entry in environment["sessions"]}
    if len(identities) != 1:
        raise ValueError("Browser or adapter identity changed between processes")
    expected_warmup = plan["warmupCycles"] * len(plan["trialOrders"])
    if any(entry["warmupSamplesPerArmPerPhase"] != expected_warmup
           for entry in environment["sessions"]):
        raise ValueError("Warmup count differs across arms/processes")
    phases: dict[str, Any] = {}
    raw = []
    for phase in ("timestamped", "plain"):
        paired = []
        for session in range(plan["sessions"]):
            path = output / f"session-{session}-{phase}.json"
            data = json.loads(path.read_text())
            orders = [plan["trialOrders"][(cohort + session) % len(plan["trialOrders"])]
                      for cohort in range(len(plan["trialOrders"]))]
            if any(row["timestamps"] != (phase == "timestamped") for row in data["rows"]):
                raise ValueError("Timestamp scopes differ")
            paired.append(paired_rows(data["rows"], orders))
            raw.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        phases[phase] = {"processPairs": paired,
                         "summary": summarize(paired, plan["statistics"], data["contract"]["materialGainRatio"])}
    return {"schemaVersion": 1, "classification": "diagnostic", "performancePromoted": False,
            "settings": plan["statistics"], "pairDirection": "right cost minus left cost; ratios below one favor right",
            "unit": "process mean of matched cohort differences; independent processes are bootstrap blocks",
            "caveat": "Small fixed process sample; descriptive percentile intervals, no tail or universal equivalence claim. Persistent driver cache, system load and thermal state remain uncontrolled.",
            "raw": raw, "phases": phases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = adjudicate(args.output)
    (args.output / "paired-statistics.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
