#!/usr/bin/env python3
"""Validate Worker 3 INT4 PLE identity and hash freshness."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PENDING = {"", "pending", "<pending>"}
DEFAULT_PROGRAM_BUNDLE = (
    "/home/x/deco/doppler/examples/program-bundles/"
    "gemma-4-e2b-it-q4k-ehf16-af32-int4ple.program-bundle.json"
)
DEFAULT_REFERENCE_EXPORT = (
    "bench/out/doppler-reference/"
    "gemma-4-e2b-int4ple-production-final-logits/"
    "doppler_program_bundle_reference_export.json"
)
DEFAULT_TRANSCRIPT_RECEIPT = (
    "bench/out/doppler-reference/"
    "gemma-4-e2b-int4ple-doe-csl-transcript.blocked.json"
)
DEFAULT_PARITY_RECEIPT = (
    "bench/out/doppler-reference/"
    "gemma-4-e2b-int4ple-doe-csl-reference-parity.pending.json"
)
DEFAULT_HARDWARE_RECEIPT = (
    "bench/out/doppler-reference/"
    "gemma-4-e2b-int4ple-doe-csl-hardware-receipt.pending.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--program-bundle",
        default=DEFAULT_PROGRAM_BUNDLE,
        help="Canonical Doppler Program Bundle path.",
    )
    parser.add_argument(
        "--reference-export",
        default=DEFAULT_REFERENCE_EXPORT,
        help="Doppler reference export receipt.",
    )
    parser.add_argument(
        "--transcript-receipt",
        default=DEFAULT_TRANSCRIPT_RECEIPT,
        help="Doe CSL transcript receipt.",
    )
    parser.add_argument(
        "--parity-receipt",
        default=DEFAULT_PARITY_RECEIPT,
        help="Doe-vs-Doppler parity receipt.",
    )
    parser.add_argument(
        "--hardware-receipt",
        default=DEFAULT_HARDWARE_RECEIPT,
        help="Pending or completed hardware receipt.",
    )
    parser.add_argument(
        "--allow-missing-hardware-receipt",
        action="store_true",
        help="Skip hardware receipt checks if that receipt is absent.",
    )
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_sha256_prefix(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.removeprefix("sha256:")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fail_if(
    condition: bool,
    failures: list[str],
    message: str,
) -> None:
    if condition:
        failures.append(message)


def check_file(path: Path, label: str, failures: list[str]) -> None:
    if not path.is_file():
        failures.append(f"{label} missing: {path}")


def check_path_hash(
    label: str,
    path_text: Any,
    expected: Any,
    failures: list[str],
) -> None:
    if not isinstance(path_text, str) or not isinstance(expected, str):
        failures.append(f"{label}.path/hash must be strings")
        return
    path_pending = path_text in PENDING
    hash_pending = expected in PENDING
    if path_pending and hash_pending:
        return
    if path_pending != hash_pending:
        failures.append(f"{label}.path/hash partially pending")
        return
    path = resolve(path_text)
    if not path.is_file():
        failures.append(f"{label}.path missing: {path_text}")
        return
    actual = sha256_file(path)
    if actual != expected:
        failures.append(f"{label}.sha256={expected!r}, actual {actual!r}")


def walk_hash_links(
    value: Any,
    label: str,
) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(value, list):
        links: list[tuple[str, dict[str, Any]]] = []
        for index, item in enumerate(value):
            links.extend(walk_hash_links(item, f"{label}[{index}]"))
        return links
    if not isinstance(value, dict):
        return []
    links = []
    if "path" in value and "sha256" in value:
        links.append((label, value))
    for key, item in value.items():
        child = f"{label}.{key}" if label else str(key)
        links.extend(walk_hash_links(item, child))
    return links


def expected_identity(
    program_bundle: dict[str, Any],
    reference_export: dict[str, Any],
    program_bundle_sha256: str,
) -> dict[str, str]:
    sources = program_bundle.get("sources") or {}
    manifest = sources.get("manifest") or {}
    graph = sources.get("executionGraph") or {}
    return {
        "programBundleId": str(program_bundle.get("bundleId") or ""),
        "programBundleSha256": program_bundle_sha256,
        "manifestSha256": strip_sha256_prefix(manifest.get("hash")),
        "graphSha256": strip_sha256_prefix(graph.get("hash")),
        "weightSha256": strip_sha256_prefix(sources.get("weightSetHash")),
        "inputSetSha256": str(reference_export.get("inputSetSha256") or ""),
    }


def check_reference_export(
    reference_export: dict[str, Any],
    identity: dict[str, str],
    failures: list[str],
) -> None:
    expected = {
        "programBundleId": identity["programBundleId"],
        "manifestSha256": identity["manifestSha256"],
        "executionGraphSha256": identity["graphSha256"],
        "weightSetSha256": identity["weightSha256"],
        "inputSetSha256": identity["inputSetSha256"],
    }
    for key, expected_value in expected.items():
        if reference_export.get(key) != expected_value:
            failures.append(
                f"referenceExport.{key}={reference_export.get(key)!r}, "
                f"expected {expected_value!r}"
            )


def normalized_source(
    receipt: dict[str, Any],
) -> dict[str, Any]:
    source = dict(receipt.get("sourceProgram") or {})
    reference = receipt.get("referenceRun") or {}
    if "inputSetSha256" not in source and reference.get("inputSetSha256"):
        source["inputSetSha256"] = reference.get("inputSetSha256")
    return source


def check_source_identity(
    label: str,
    receipt: dict[str, Any],
    identity: dict[str, str],
    failures: list[str],
) -> None:
    source = normalized_source(receipt)
    for key in (
        "programBundleId",
        "manifestSha256",
        "graphSha256",
        "weightSha256",
        "inputSetSha256",
    ):
        if source.get(key) != identity[key]:
            failures.append(
                f"{label}.sourceProgram.{key}={source.get(key)!r}, "
                f"expected {identity[key]!r}"
            )

    program_bundle = source.get("programBundle")
    if not isinstance(program_bundle, dict):
        failures.append(f"{label}.sourceProgram.programBundle missing")
        return
    check_path_hash(
        f"{label}.sourceProgram.programBundle",
        program_bundle.get("path", ""),
        program_bundle.get("sha256", ""),
        failures,
    )
    if program_bundle.get("sha256") != identity["programBundleSha256"]:
        failures.append(
            f"{label}.sourceProgram.programBundle.sha256="
            f"{program_bundle.get('sha256')!r}, "
            f"expected {identity['programBundleSha256']!r}"
        )


def check_source_file_hashes(
    label: str,
    receipt: dict[str, Any],
    identity: dict[str, str],
    failures: list[str],
) -> None:
    source = normalized_source(receipt)
    manifest_path = source.get("manifestPath")
    if isinstance(manifest_path, str):
        check_path_hash(
            f"{label}.sourceProgram.manifest",
            manifest_path,
            identity["manifestSha256"],
            failures,
        )
    graph_path = source.get("graphPath")
    if not isinstance(graph_path, str):
        failures.append(f"{label}.sourceProgram.graphPath missing")
        return
    graph_file = resolve(graph_path)
    if not graph_file.is_file():
        failures.append(f"{label}.sourceProgram.graphPath missing: {graph_path}")
        return
    graph_actual = sha256_file(graph_file)
    if graph_actual == identity["graphSha256"]:
        return
    try:
        graph = load_json(graph_file)
    except json.JSONDecodeError:
        failures.append(
            f"{label}.sourceProgram.graphSha256="
            f"{identity['graphSha256']!r}, actual {graph_actual!r}"
        )
        return
    projected = strip_sha256_prefix(
        graph.get("programBundleExecutionGraphSha256")
    )
    if projected != identity["graphSha256"]:
        failures.append(
            f"{label}.sourceProgram.graphSha256="
            f"{identity['graphSha256']!r}, actual {graph_actual!r}"
        )


def check_all_hash_links(
    label: str,
    receipt: dict[str, Any],
    failures: list[str],
) -> None:
    for link_label, link in walk_hash_links(receipt, label):
        check_path_hash(
            link_label,
            link.get("path", ""),
            link.get("sha256", ""),
            failures,
        )


def check_parity_points_to_transcript(
    parity: dict[str, Any],
    transcript_path: Path,
    failures: list[str],
) -> None:
    csl_run = parity.get("cslRun") or {}
    trace_path_text = csl_run.get("tracePath", "")
    trace_sha = csl_run.get("traceSha256", "")
    if trace_path_text in PENDING and trace_sha in PENDING:
        return
    trace_path = resolve(trace_path_text)
    if trace_path != transcript_path.resolve():
        failures.append(
            f"parity.cslRun.tracePath={trace_path_text!r}, "
            f"expected {transcript_path}"
        )
    expected_sha = sha256_file(transcript_path)
    if trace_sha != expected_sha:
        failures.append(
            f"parity.cslRun.traceSha256={trace_sha!r}, "
            f"expected {expected_sha!r}"
        )


def check_hardware_links_current_receipts(
    hardware: dict[str, Any],
    parity_path: Path,
    transcript_path: Path,
    failures: list[str],
) -> None:
    expected = {
        "simulatorParityReceipt": parity_path,
        "simulatorTranscriptReceipt": transcript_path,
    }
    for key, expected_path in expected.items():
        link = hardware.get(key) or {}
        check_path_hash(
            f"hardware.{key}",
            link.get("path", ""),
            link.get("sha256", ""),
            failures,
        )
        if resolve(link.get("path", "")) != expected_path.resolve():
            failures.append(
                f"hardware.{key}.path={link.get('path')!r}, "
                f"expected {expected_path}"
            )
        expected_sha = sha256_file(expected_path)
        if link.get("sha256") != expected_sha:
            failures.append(
                f"hardware.{key}.sha256={link.get('sha256')!r}, "
                f"expected {expected_sha!r}"
            )


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    program_bundle_path = resolve(args.program_bundle)
    reference_export_path = resolve(args.reference_export)
    transcript_path = resolve(args.transcript_receipt)
    parity_path = resolve(args.parity_receipt)
    hardware_path = resolve(args.hardware_receipt)

    for label, path in (
        ("program bundle", program_bundle_path),
        ("reference export", reference_export_path),
        ("transcript receipt", transcript_path),
        ("parity receipt", parity_path),
    ):
        check_file(path, label, failures)
    if not hardware_path.is_file() and not args.allow_missing_hardware_receipt:
        failures.append(f"hardware receipt missing: {hardware_path}")
    if failures:
        print("FAIL: INT4 PLE Worker 3 freshness gate")
        for failure in failures:
            print(f"  {failure}")
        return 1

    try:
        program_bundle = load_json(program_bundle_path)
        reference_export = load_json(reference_export_path)
        transcript = load_json(transcript_path)
        parity = load_json(parity_path)
        hardware = (
            load_json(hardware_path)
            if hardware_path.is_file()
            else None
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: INT4 PLE Worker 3 freshness gate: {exc}")
        return 1

    identity = expected_identity(
        program_bundle,
        reference_export,
        sha256_file(program_bundle_path),
    )
    if program_bundle.get("schema") != "doppler.program-bundle/v1":
        failures.append(
            f"programBundle.schema={program_bundle.get('schema')!r}, "
            "expected 'doppler.program-bundle/v1'"
        )
    check_reference_export(reference_export, identity, failures)

    receipts: list[tuple[str, dict[str, Any]]] = [
        ("transcript", transcript),
        ("parity", parity),
    ]
    if isinstance(hardware, dict):
        receipts.append(("hardware", hardware))
    for label, receipt in receipts:
        check_source_identity(label, receipt, identity, failures)
        check_source_file_hashes(label, receipt, identity, failures)
        check_all_hash_links(label, receipt, failures)

    check_parity_points_to_transcript(parity, transcript_path, failures)
    if isinstance(hardware, dict):
        check_hardware_links_current_receipts(
            hardware,
            parity_path,
            transcript_path,
            failures,
        )

    if failures:
        print("FAIL: INT4 PLE Worker 3 freshness gate")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(
        "PASS: INT4 PLE Worker 3 freshness gate "
        f"(bundle={identity['programBundleId']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
