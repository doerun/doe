#!/usr/bin/env python3
"""Advisory nightly canary for TSIR bootstrap parity receipt plumbing."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools import doe_parity, tsir_manifest_lowering  # noqa: E402


DEFAULT_FIXTURE_DIR = REPO_ROOT / "bench" / "fixtures" / "tsir-manifest-entries"
DEFAULT_INPUTS_DIR = REPO_ROOT / "bench" / "fixtures" / "tsir-bootstrap-inputs"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "bench" / "out" / "nightly-tsir-parity-canary"
PARITY_CLI = REPO_ROOT / "bench" / "tools" / "doe_parity.py"
EXPECTED_FIXTURE_COUNT = 12
FAIL_STATUSES = {"fail"}
KERNEL_REF_PREFIXES = ("doe.tsir.bootstrap.", "doe.tsir.real.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help="Directory containing TSIR manifest lowering entry fixtures.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=EXPECTED_FIXTURE_COUNT,
        help=(
            "Expected number of fixture files in --fixture-dir. Defaults to 6 "
            "(the bootstrap set); set higher when running against real-kernel "
            "fixture sets that include additional kernel/backend pairings."
        ),
    )
    parser.add_argument(
        "--doppler-transcripts-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing per-kernel doppler.reference-transcript/v1 "
            "JSON files named <kernel>.doppler-transcript.json. Required "
            "when running against real-kernel fixtures (kernelRef prefix "
            "doe.tsir.real.*); "
            "ignored for bootstrap kernels. doe_parity.py rejects real "
            "kernels without --doppler-transcript and rejects bootstrap "
            "kernels with one, so the canary routes per-kernel based on "
            "the fixture's kernelRef prefix."
        ),
    )
    parser.add_argument(
        "--doppler-kernel-probes-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory containing per-kernel probe-hash files "
            "named <kernel>.kernel-probe-hash (single line, 64-char hex). "
            "Only consumed for real kernels; bootstrap kernels skip this."
        ),
    )
    parser.add_argument(
        "--inputs-dir",
        type=Path,
        default=DEFAULT_INPUTS_DIR,
        help="Directory containing TSIR bootstrap input-tensor fixtures "
        "(paired with manifest fixtures by kernel name: `<kernel>.json`).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for per-fixture receipts and the canary report.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to invoke the parity CLI.",
    )
    return parser.parse_args()


def _kernel_name(entry: dict[str, Any]) -> str:
    kernel_ref = entry["kernelRef"]
    for prefix in KERNEL_REF_PREFIXES:
        if kernel_ref.startswith(prefix):
            return kernel_ref.removeprefix(prefix)
    raise ValueError(
        f"unexpected kernelRef: {kernel_ref!r}; expected one of "
        f"{KERNEL_REF_PREFIXES}"
    )


def _entry_backend(entry: dict[str, Any]) -> str:
    backend = entry["backend"]
    if not isinstance(backend, str) or not backend:
        raise ValueError("manifest lowering backend must be non-empty")
    return backend


def load_fixture_entries(
    fixture_dir: Path, expected_count: int = EXPECTED_FIXTURE_COUNT
) -> list[tuple[Path, dict[str, Any]]]:
    paths = sorted(fixture_dir.glob("*.json"))
    if len(paths) != expected_count:
        raise ValueError(
            f"expected {expected_count} TSIR manifest fixtures, "
            f"got {len(paths)} in {fixture_dir}"
        )
    entries = [(path, tsir_manifest_lowering.load_entry_doc(path)) for path in paths]
    seen = set()
    for _, entry in entries:
        pair = (_kernel_name(entry), _entry_backend(entry))
        if pair in seen:
            raise ValueError(f"duplicate TSIR manifest fixture pair: {pair}")
        seen.add(pair)
    return entries


def _receipt_dir(output_dir: Path, entry: dict[str, Any]) -> Path:
    return output_dir / "receipts" / f"{_kernel_name(entry)}.{_entry_backend(entry)}"


def _expected_identity(entry: dict[str, Any]) -> dict[str, str]:
    return {
        "emitterDigest": entry["emitterDigest"],
        "targetDescriptorCorrectnessHash": entry["targetDescriptorCorrectnessHash"],
        "tsirRealizationDigest": entry["tsirRealizationDigest"],
        "tsirSemanticDigest": entry["tsirSemanticDigest"],
    }


def _inputs_path(inputs_dir: Path, entry: dict[str, Any]) -> Path:
    candidate = inputs_dir / f"{_kernel_name(entry)}.json"
    if not candidate.is_file():
        raise FileNotFoundError(
            f"TSIR bootstrap input fixture missing: {candidate}"
        )
    return candidate


def _is_real_kernel(entry: dict[str, Any]) -> bool:
    kernel_ref = entry["kernelRef"]
    return kernel_ref.startswith("doe.tsir.real.")


def _doppler_transcript_for(
    kernel: str, transcripts_dir: Path | None
) -> Path | None:
    if transcripts_dir is None:
        return None
    candidate = transcripts_dir / f"{kernel}.doppler-transcript.json"
    if not candidate.is_file():
        raise FileNotFoundError(
            f"Doppler transcript missing for real kernel {kernel!r}: "
            f"{candidate}"
        )
    return candidate


def _doppler_probe_hash_for(
    kernel: str,
    probes_dir: Path | None,
    transcript_path: Path | None = None,
) -> str | None:
    """Locate a per-kernel probe hash.

    Priority order:
      1. `<probes-dir>/<kernel>.kernel-probe-hash` if `probes_dir` is given.
      2. The transcript JSON's `kernelProbe.hash` field if the transcript file
         carries one. This lets the harness consume self-contained transcripts
         that bundle the probe hash inline (the format authored by
         `bench/fixtures/tsir-real-doppler-transcripts/`).
    Returns None when neither source has a probe hash.
    """
    if probes_dir is not None:
        candidate = probes_dir / f"{kernel}.kernel-probe-hash"
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8").strip()
            if text:
                return text
    if transcript_path is not None and transcript_path.is_file():
        try:
            doc = json.loads(transcript_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(doc, dict):
            probe = doc.get("kernelProbe")
            if isinstance(probe, dict):
                value = probe.get("hash")
                if isinstance(value, str) and value:
                    return value
    return None


def run_fixture(
    path: Path,
    entry: dict[str, Any],
    output_dir: Path,
    inputs_dir: Path,
    python: str,
    doppler_transcripts_dir: Path | None = None,
    doppler_probes_dir: Path | None = None,
) -> dict[str, Any]:
    kernel = _kernel_name(entry)
    receipt_dir = _receipt_dir(output_dir, entry)
    inputs_path = _inputs_path(inputs_dir, entry)
    cmd = [
        python,
        str(PARITY_CLI),
        kernel,
        "--class",
        entry["exactness"]["class"],
        "--inputs",
        str(inputs_path),
        "--manifest-lowering-entry",
        str(path),
        "--receipt-dir",
        str(receipt_dir),
    ]
    if _is_real_kernel(entry):
        transcript_path = _doppler_transcript_for(kernel, doppler_transcripts_dir)
        if transcript_path is None:
            raise ValueError(
                f"Real kernel {kernel!r} requires --doppler-transcripts-dir "
                "with a per-kernel transcript file."
            )
        cmd.extend(["--doppler-transcript", str(transcript_path)])
        probe_hash = _doppler_probe_hash_for(
            kernel, doppler_probes_dir, transcript_path=transcript_path
        )
        if probe_hash is not None:
            cmd.extend(["--doppler-kernel-probe-hash", probe_hash])
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    receipt_path = receipt_dir / f"{kernel}.parity.json"
    result: dict[str, Any] = {
        "backend": _entry_backend(entry),
        "cliExitCode": proc.returncode,
        "fixture": path.relative_to(REPO_ROOT).as_posix(),
        "inputsFixture": inputs_path.relative_to(REPO_ROOT).as_posix()
        if inputs_path.is_relative_to(REPO_ROOT)
        else str(inputs_path),
        "kernel": kernel,
        "receiptPath": receipt_path.relative_to(REPO_ROOT).as_posix()
        if receipt_path.is_relative_to(REPO_ROOT)
        else str(receipt_path),
        "stderr": proc.stderr,
        "stdout": proc.stdout,
        "statuses": [],
    }
    if not receipt_path.is_file():
        result["failure"] = "parity CLI did not write a receipt"
        return result

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        result["failure"] = "parity receipt must be a JSON object"
        return result
    doe_parity.validate_receipt_doc(receipt)
    identity = receipt.get("loweringIdentity")
    if identity != _expected_identity(entry):
        result["failure"] = "parity receipt lowering identity mismatch"
        result["loweringIdentity"] = identity
        return result

    statuses = [
        comparison.get("status")
        for comparison in receipt.get("comparisons", [])
        if isinstance(comparison, dict)
    ]
    result["statuses"] = statuses
    result["loweringIdentity"] = identity
    if any(status in FAIL_STATUSES for status in statuses):
        result["failure"] = f"parity receipt contains failing status: {statuses}"
    return result


def build_report(
    fixture_dir: Path,
    inputs_dir: Path,
    output_dir: Path,
    python: str,
    expected_count: int = EXPECTED_FIXTURE_COUNT,
    doppler_transcripts_dir: Path | None = None,
    doppler_probes_dir: Path | None = None,
) -> dict[str, Any]:
    entries = load_fixture_entries(fixture_dir, expected_count=expected_count)
    results = [
        run_fixture(
            path,
            entry,
            output_dir,
            inputs_dir,
            python,
            doppler_transcripts_dir=doppler_transcripts_dir,
            doppler_probes_dir=doppler_probes_dir,
        )
        for path, entry in entries
    ]
    failures = [
        f"{result['fixture']}: {result['failure']}"
        for result in results
        if "failure" in result
    ]
    return {
        "artifactKind": "tsir_nightly_parity_canary",
        "schemaVersion": 1,
        "fixtureCount": len(results),
        "failures": failures,
        "results": results,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "nightly-tsir-parity-canary.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path


def main() -> int:
    args = parse_args()
    try:
        report = build_report(
            args.fixture_dir,
            args.inputs_dir,
            args.output_dir,
            args.python,
            expected_count=args.expected_count,
            doppler_transcripts_dir=args.doppler_transcripts_dir,
            doppler_probes_dir=args.doppler_kernel_probes_dir,
        )
        report_path = write_report(report, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: nightly TSIR parity canary: {exc}")
        return 1

    display_path: Path | str
    try:
        display_path = report_path.relative_to(REPO_ROOT)
    except ValueError:
        display_path = report_path

    if report["failures"]:
        print(f"FAIL: nightly TSIR parity canary ({display_path})")
        for failure in report["failures"]:
            print(f"  {failure}")
        return 1

    print(
        "PASS: nightly TSIR parity canary "
        f"({report['fixtureCount']} fixture receipts, report={display_path})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
