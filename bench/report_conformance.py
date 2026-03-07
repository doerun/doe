#!/usr/bin/env python3
"""Shared conformance checks for compare_dawn_vs_doe report artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPORT_SCHEMA_VERSION = 4
SHA256_HEX_LENGTH = 64
SHA256_ZERO = "0" * SHA256_HEX_LENGTH


def parse_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_sha256_hex(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_HEX_LENGTH
        and all(ch in "0123456789abcdef" for ch in value)
    )


def load_obligation_contract(path: Path) -> tuple[int, set[str]]:
    payload = load_json_object(path)
    schema_version = parse_int(payload.get("schemaVersion"))
    if schema_version is None:
        raise ValueError(
            f"invalid comparability obligation contract: schemaVersion missing/invalid in {path}"
        )
    raw_ids = payload.get("obligationIds")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError(
            f"invalid comparability obligation contract: obligationIds missing/invalid in {path}"
        )
    obligation_ids: set[str] = set()
    for index, raw in enumerate(raw_ids):
        if not isinstance(raw, str) or not raw:
            raise ValueError(
                "invalid comparability obligation contract: "
                f"obligationIds[{index}] must be non-empty string in {path}"
            )
        obligation_ids.add(raw)
    return schema_version, obligation_ids


def resolve_contract_path(
    *,
    report_path: Path,
    repo_root: Path,
    raw_contract_path: str,
) -> Path:
    direct = Path(raw_contract_path)
    if direct.is_absolute():
        return direct

    repo_relative = (repo_root / direct).resolve()
    if repo_relative.exists():
        return repo_relative

    report_relative = (report_path.parent / direct).resolve()
    if report_relative.exists():
        return report_relative

    return repo_relative


def load_contract_workload_ids(path: Path) -> set[str]:
    return set(load_contract_workloads_by_id(path))


def load_contract_workloads_by_id(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json_object(path)
    raw_workloads = payload.get("workloads")
    if not isinstance(raw_workloads, list):
        raise ValueError(f"invalid workload contract: missing workloads[] in {path}")
    rows_by_id: dict[str, dict[str, Any]] = {}
    for row in raw_workloads:
        if not isinstance(row, dict):
            continue
        workload_id = row.get("id")
        if isinstance(workload_id, str) and workload_id:
            rows_by_id[workload_id] = row
    if not rows_by_id:
        raise ValueError(f"invalid workload contract: no workload IDs in {path}")
    return rows_by_id


def validate_report_conformance(
    *,
    payload: dict[str, Any],
    report_path: Path,
    repo_root: Path,
    expected_obligation_schema_version: int,
    expected_obligation_ids: set[str],
) -> tuple[bool, str]:
    schema_version = parse_int(payload.get("schemaVersion"))
    if schema_version != REPORT_SCHEMA_VERSION:
        return (
            False,
            f"schemaVersion must be {REPORT_SCHEMA_VERSION} (found {payload.get('schemaVersion')!r})",
        )

    workloads = payload.get("workloads")
    if not isinstance(workloads, list) or not workloads:
        return False, "missing or empty workloads list"

    comparison_status = payload.get("comparisonStatus")
    if not isinstance(comparison_status, str) or not comparison_status:
        return False, "missing comparisonStatus"

    claim_status = payload.get("claimStatus")
    if not isinstance(claim_status, str) or not claim_status:
        return False, "missing claimStatus"

    comparability_policy = payload.get("comparabilityPolicy")
    if not isinstance(comparability_policy, dict):
        return False, "missing comparabilityPolicy"
    obligation_contract = comparability_policy.get("obligationContract")
    if not isinstance(obligation_contract, dict):
        return False, "missing comparabilityPolicy.obligationContract"
    if parse_int(obligation_contract.get("schemaVersion")) != expected_obligation_schema_version:
        return (
            False,
            "comparabilityPolicy.obligationContract.schemaVersion mismatch",
        )

    workload_contract = payload.get("workloadContract")
    if not isinstance(workload_contract, dict):
        return False, "missing workloadContract object"

    raw_contract_path = workload_contract.get("path")
    if not isinstance(raw_contract_path, str) or not raw_contract_path.strip():
        return False, "workloadContract.path missing or invalid"
    report_contract_hash = workload_contract.get("sha256")
    if not isinstance(report_contract_hash, str) or not report_contract_hash.strip():
        return False, "workloadContract.sha256 missing or invalid"

    resolved_contract_path = resolve_contract_path(
        report_path=report_path,
        repo_root=repo_root,
        raw_contract_path=raw_contract_path,
    )
    if not resolved_contract_path.exists():
        return False, f"workload contract path does not exist: {resolved_contract_path}"
    expected_contract_hash = file_sha256(resolved_contract_path)
    if report_contract_hash != expected_contract_hash:
        return (
            False,
            "workloadContract.sha256 mismatch "
            f"(report={report_contract_hash} expected={expected_contract_hash})",
        )

    try:
        contract_workload_rows = load_contract_workloads_by_id(resolved_contract_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return False, str(exc)
    contract_workload_ids = set(contract_workload_rows)

    seen_workload_ids: set[str] = set()
    for workload_index, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            return False, f"workloads[{workload_index}] must be an object"
        workload_id = workload.get("id")
        if not isinstance(workload_id, str) or not workload_id:
            return False, f"workloads[{workload_index}].id must be a non-empty string"
        if workload_id in seen_workload_ids:
            return False, f"duplicate workload id in report: {workload_id}"
        seen_workload_ids.add(workload_id)
        if workload_id not in contract_workload_ids:
            return False, f"workload id not present in workload contract: {workload_id}"
        contract_row = contract_workload_rows[workload_id]
        workload_path_asymmetry = workload.get("pathAsymmetry")
        if workload_path_asymmetry is not None and not isinstance(workload_path_asymmetry, bool):
            return False, f"{workload_id}: pathAsymmetry must be bool when present"
        workload_path_asymmetry_note = workload.get("pathAsymmetryNote")
        if workload_path_asymmetry_note is not None and not isinstance(
            workload_path_asymmetry_note, str
        ):
            return False, f"{workload_id}: pathAsymmetryNote must be string when present"
        contract_path_asymmetry = bool(contract_row.get("pathAsymmetry", False))
        if (
            isinstance(workload_path_asymmetry, bool)
            and workload_path_asymmetry != contract_path_asymmetry
        ):
            return False, (
                f"{workload_id}: pathAsymmetry does not match workload contract "
                f"({workload_path_asymmetry} vs {contract_path_asymmetry})"
            )
        contract_path_asymmetry_note = str(contract_row.get("pathAsymmetryNote", ""))
        if (
            isinstance(workload_path_asymmetry_note, str)
            and workload_path_asymmetry_note != contract_path_asymmetry_note
        ):
            return False, (
                f"{workload_id}: pathAsymmetryNote does not match workload contract"
            )

        comparability = workload.get("comparability")
        if not isinstance(comparability, dict):
            return False, f"{workload_id}: missing comparability object"
        if (
            parse_int(comparability.get("obligationSchemaVersion"))
            != expected_obligation_schema_version
        ):
            return (
                False,
                f"{workload_id}: comparability.obligationSchemaVersion mismatch",
            )

        obligations = comparability.get("obligations")
        if not isinstance(obligations, list) or not obligations:
            return False, f"{workload_id}: comparability.obligations must be a non-empty list"
        for obligation_index, obligation in enumerate(obligations):
            if not isinstance(obligation, dict):
                return (
                    False,
                    f"{workload_id}: comparability.obligations[{obligation_index}] must be object",
                )
            obligation_id = obligation.get("id")
            if not isinstance(obligation_id, str) or not obligation_id:
                return (
                    False,
                    f"{workload_id}: comparability.obligations[{obligation_index}].id invalid",
                )
            if obligation_id not in expected_obligation_ids:
                return (
                    False,
                    f"{workload_id}: obligation id not in canonical contract: {obligation_id}",
                )
            for field_name in ("blocking", "applicable", "passes"):
                if not isinstance(obligation.get(field_name), bool):
                    return (
                        False,
                        f"{workload_id}: comparability.obligations[{obligation_index}].{field_name} must be bool",
                    )

        blocking_failed = comparability.get("blockingFailedObligations")
        if not isinstance(blocking_failed, list):
            return False, f"{workload_id}: comparability.blockingFailedObligations must be list"
        for failed_index, failed in enumerate(blocking_failed):
            if not isinstance(failed, str) or not failed:
                return (
                    False,
                    f"{workload_id}: comparability.blockingFailedObligations[{failed_index}] invalid",
                )
            if failed not in expected_obligation_ids:
                return (
                    False,
                    f"{workload_id}: unknown blocking failed obligation id {failed}",
                )
        if comparability.get("comparable") is True and blocking_failed:
            return (
                False,
                f"{workload_id}: comparable workload must not include blockingFailedObligations",
            )

    return True, ""


def _extract_trace_meta_hashes(
    *,
    workload_id: str,
    side_name: str,
    trace_meta_hashes: Any,
) -> tuple[bool, list[str], str]:
    if not isinstance(trace_meta_hashes, list):
        return False, [], f"{workload_id}: traceMetaHashes.{side_name} must be a list"
    hashes: list[str] = []
    seen_paths: set[str] = set()
    for index, row in enumerate(trace_meta_hashes):
        if not isinstance(row, dict):
            return (
                False,
                [],
                f"{workload_id}: traceMetaHashes.{side_name}[{index}] must be an object",
            )
        path = row.get("path")
        sha256 = row.get("sha256")
        if not isinstance(path, str) or not path.strip():
            return (
                False,
                [],
                f"{workload_id}: traceMetaHashes.{side_name}[{index}].path missing/invalid",
            )
        if path in seen_paths:
            return (
                False,
                [],
                f"{workload_id}: duplicate traceMetaHashes.{side_name} path {path!r}",
            )
        seen_paths.add(path)
        if not is_sha256_hex(sha256):
            return (
                False,
                [],
                f"{workload_id}: traceMetaHashes.{side_name}[{index}].sha256 invalid",
            )
        hashes.append(str(sha256))
    return True, hashes, ""


def validate_claim_row_hash_links(
    *,
    payload: dict[str, Any],
    require_config_contract: bool,
    require_non_empty_trace_hashes: bool,
) -> tuple[bool, str]:
    workloads = payload.get("workloads")
    if not isinstance(workloads, list) or not workloads:
        return False, "missing or empty workloads list"

    workload_contract = payload.get("workloadContract")
    if not isinstance(workload_contract, dict):
        return False, "missing workloadContract object"
    workload_contract_sha = workload_contract.get("sha256")
    if not is_sha256_hex(workload_contract_sha):
        return False, "workloadContract.sha256 missing/invalid"

    benchmark_policy = payload.get("benchmarkPolicy")
    if not isinstance(benchmark_policy, dict):
        return False, "missing benchmarkPolicy object"
    benchmark_policy_sha = benchmark_policy.get("sha256")
    if not is_sha256_hex(benchmark_policy_sha):
        return False, "benchmarkPolicy.sha256 missing/invalid"

    config_contract = payload.get("configContract")
    config_contract_sha = ""
    if isinstance(config_contract, dict):
        config_sha_candidate = config_contract.get("sha256")
        if not is_sha256_hex(config_sha_candidate):
            return False, "configContract.sha256 invalid"
        config_contract_sha = str(config_sha_candidate)
    elif require_config_contract:
        return False, "missing configContract object"

    hash_chain = payload.get("claimRowHashChain")
    if not isinstance(hash_chain, dict):
        return False, "missing claimRowHashChain object"
    if hash_chain.get("algorithm") != "sha256":
        return False, "claimRowHashChain.algorithm must be 'sha256'"
    chain_count = parse_int(hash_chain.get("count"))
    if chain_count is None:
        return False, "claimRowHashChain.count missing/invalid"
    if chain_count != len(workloads):
        return (
            False,
            "claimRowHashChain.count mismatch "
            f"(chain={chain_count} workloads={len(workloads)})",
        )
    start_previous_hash = hash_chain.get("startPreviousHash")
    if not is_sha256_hex(start_previous_hash):
        return False, "claimRowHashChain.startPreviousHash missing/invalid"
    if str(start_previous_hash) != SHA256_ZERO:
        return False, "claimRowHashChain.startPreviousHash must be 64 zeroes"
    final_hash = hash_chain.get("finalHash")
    if workloads:
        if not is_sha256_hex(final_hash):
            return False, "claimRowHashChain.finalHash missing/invalid"
    elif final_hash not in ("", None):
        return False, "claimRowHashChain.finalHash must be empty for zero workloads"

    previous_hash = str(start_previous_hash)
    for index, workload in enumerate(workloads):
        if not isinstance(workload, dict):
            return False, f"workloads[{index}] must be an object"
        workload_id = workload.get("id")
        if not isinstance(workload_id, str) or not workload_id:
            return False, f"workloads[{index}].id missing/invalid"

        trace_meta_hashes = workload.get("traceMetaHashes")
        if not isinstance(trace_meta_hashes, dict):
            return False, f"{workload_id}: missing traceMetaHashes object"
        left_ok, left_hashes, left_error = _extract_trace_meta_hashes(
            workload_id=workload_id,
            side_name="left",
            trace_meta_hashes=trace_meta_hashes.get("left"),
        )
        if not left_ok:
            return False, left_error
        right_ok, right_hashes, right_error = _extract_trace_meta_hashes(
            workload_id=workload_id,
            side_name="right",
            trace_meta_hashes=trace_meta_hashes.get("right"),
        )
        if not right_ok:
            return False, right_error
        if require_non_empty_trace_hashes and (not left_hashes or not right_hashes):
            return (
                False,
                f"{workload_id}: claimable rows require non-empty traceMetaHashes left/right",
            )

        claim_row_hash = workload.get("claimRowHash")
        if not isinstance(claim_row_hash, dict):
            return False, f"{workload_id}: missing claimRowHash object"
        if claim_row_hash.get("algorithm") != "sha256":
            return False, f"{workload_id}: claimRowHash.algorithm must be 'sha256'"
        row_previous_hash = claim_row_hash.get("previousHash")
        if not is_sha256_hex(row_previous_hash):
            return False, f"{workload_id}: claimRowHash.previousHash missing/invalid"
        if str(row_previous_hash) != previous_hash:
            return (
                False,
                f"{workload_id}: claimRowHash.previousHash mismatch "
                f"(row={row_previous_hash} expected={previous_hash})",
            )
        row_hash_value = claim_row_hash.get("hash")
        if not is_sha256_hex(row_hash_value):
            return False, f"{workload_id}: claimRowHash.hash missing/invalid"
        context = claim_row_hash.get("context")
        if not isinstance(context, dict):
            return False, f"{workload_id}: claimRowHash.context missing/invalid"
        if context.get("workloadId") != workload_id:
            return False, f"{workload_id}: claimRowHash.context.workloadId mismatch"
        if context.get("workloadContractSha256") != workload_contract_sha:
            return False, (
                f"{workload_id}: claimRowHash.context.workloadContractSha256 mismatch"
            )
        if context.get("benchmarkPolicySha256") != benchmark_policy_sha:
            return False, (
                f"{workload_id}: claimRowHash.context.benchmarkPolicySha256 mismatch"
            )
        expected_config_sha = config_contract_sha
        context_config_sha = context.get("configContractSha256")
        if not isinstance(context_config_sha, str):
            return False, (
                f"{workload_id}: claimRowHash.context.configContractSha256 missing/invalid"
            )
        if context_config_sha != expected_config_sha:
            return False, (
                f"{workload_id}: claimRowHash.context.configContractSha256 mismatch"
            )

        context_left_hashes = context.get("leftTraceMetaSha256")
        context_right_hashes = context.get("rightTraceMetaSha256")
        if (
            not isinstance(context_left_hashes, list)
            or any(not is_sha256_hex(item) for item in context_left_hashes)
        ):
            return False, (
                f"{workload_id}: claimRowHash.context.leftTraceMetaSha256 missing/invalid"
            )
        if (
            not isinstance(context_right_hashes, list)
            or any(not is_sha256_hex(item) for item in context_right_hashes)
        ):
            return False, (
                f"{workload_id}: claimRowHash.context.rightTraceMetaSha256 missing/invalid"
            )
        if context_left_hashes != left_hashes:
            return False, (
                f"{workload_id}: claimRowHash.context.leftTraceMetaSha256 mismatch"
            )
        if context_right_hashes != right_hashes:
            return False, (
                f"{workload_id}: claimRowHash.context.rightTraceMetaSha256 mismatch"
            )

        if context.get("deltaPercent") != workload.get("deltaPercent"):
            return False, f"{workload_id}: claimRowHash.context.deltaPercent mismatch"
        if "workloadPathAsymmetry" in context and context.get("workloadPathAsymmetry") != workload.get(
            "pathAsymmetry"
        ):
            return False, f"{workload_id}: claimRowHash.context.workloadPathAsymmetry mismatch"
        if "workloadPathAsymmetryNote" in context and context.get(
            "workloadPathAsymmetryNote"
        ) != workload.get("pathAsymmetryNote"):
            return False, f"{workload_id}: claimRowHash.context.workloadPathAsymmetryNote mismatch"

        comparability = workload.get("comparability")
        context_comparability = context.get("comparability")
        if not isinstance(comparability, dict) or not isinstance(context_comparability, dict):
            return False, f"{workload_id}: comparability snapshot missing/invalid"
        if context_comparability.get("comparable") != comparability.get("comparable"):
            return False, (
                f"{workload_id}: claimRowHash.context.comparability.comparable mismatch"
            )
        if context_comparability.get("blockingFailedObligations", []) != comparability.get(
            "blockingFailedObligations", []
        ):
            return False, (
                f"{workload_id}: claimRowHash.context.comparability.blockingFailedObligations mismatch"
            )

        claimability = workload.get("claimability")
        context_claimability = context.get("claimability")
        if not isinstance(claimability, dict) or not isinstance(context_claimability, dict):
            return False, f"{workload_id}: claimability snapshot missing/invalid"
        if context_claimability.get("evaluated") != claimability.get("evaluated"):
            return False, (
                f"{workload_id}: claimRowHash.context.claimability.evaluated mismatch"
            )
        if context_claimability.get("claimable") != claimability.get("claimable"):
            return False, (
                f"{workload_id}: claimRowHash.context.claimability.claimable mismatch"
            )
        if context_claimability.get("reasons", []) != claimability.get("reasons", []):
            return False, (
                f"{workload_id}: claimRowHash.context.claimability.reasons mismatch"
            )

        recomputed_hash = json_sha256(
            {
                "previousHash": str(row_previous_hash),
                "context": context,
            }
        )
        if recomputed_hash != row_hash_value:
            return False, (
                f"{workload_id}: claimRowHash.hash mismatch "
                f"(report={row_hash_value} recomputed={recomputed_hash})"
            )
        previous_hash = str(row_hash_value)

    if workloads and str(final_hash) != previous_hash:
        return (
            False,
            "claimRowHashChain.finalHash mismatch "
            f"(chain={final_hash} expected={previous_hash})",
        )
    return True, ""
