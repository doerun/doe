from __future__ import annotations

import unittest

from bench.lib import report_conformance


class TestValidateClaimRowHashLinks(unittest.TestCase):
    def _build_payload(self) -> dict[str, object]:
        workload_id = "inference_gemma3_270m_prefill_64tok_decode_64tok"
        workload_contract_sha = "1" * 64
        benchmark_policy_sha = "2" * 64
        config_contract_sha = "3" * 64
        baseline_hashes = ["4" * 64]
        comparison_hashes = ["5" * 64]
        delta_percent = {
            "p10Percent": 1.0,
            "p50Percent": 2.0,
            "p95Percent": 3.0,
            "p99Percent": 4.0,
            "meanPercent": 2.5,
        }
        comparability = {
            "comparable": True,
            "blockingFailedObligations": [],
        }
        claimability = {
            "mode": "local",
            "evaluated": True,
            "claimable": True,
            "reasons": [],
        }
        context = {
            "workloadId": workload_id,
            "workloadContractSha256": workload_contract_sha,
            "benchmarkPolicySha256": benchmark_policy_sha,
            "configContractSha256": config_contract_sha,
            "baselineTraceMetaSha256": baseline_hashes,
            "comparisonTraceMetaSha256": comparison_hashes,
            "deltaPercent": delta_percent,
            "comparability": comparability,
            "claimability": claimability,
        }
        previous_hash = report_conformance.SHA256_ZERO
        row_hash = report_conformance.json_sha256(
            {
                "previousHash": previous_hash,
                "context": context,
            }
        )
        workload = {
            "id": workload_id,
            "traceMetaHashes": {
                "baseline": [
                    {
                        "path": "bench/out/example.baseline.meta.json",
                        "sha256": baseline_hashes[0],
                    }
                ],
                "comparison": [
                    {
                        "path": "bench/out/example.comparison.meta.json",
                        "sha256": comparison_hashes[0],
                    }
                ],
            },
            "deltaPercent": delta_percent,
            "comparability": comparability,
            "claimability": claimability,
            "claimWorkloadHash": {
                "algorithm": "sha256",
                "previousHash": previous_hash,
                "hash": row_hash,
                "context": context,
            },
        }
        return {
            "workloadContract": {"sha256": workload_contract_sha},
            "benchmarkPolicy": {"sha256": benchmark_policy_sha},
            "configContract": {"sha256": config_contract_sha},
            "claimWorkloadHashChain": {
                "algorithm": "sha256",
                "count": 1,
                "startPreviousHash": previous_hash,
                "finalHash": row_hash,
            },
            "workloads": [workload],
        }

    def test_validate_claim_row_hash_links_accepts_matching_trace_meta_hashes(self) -> None:
        payload = self._build_payload()
        ok, reason = report_conformance.validate_claim_row_hash_links(
            payload=payload,
            require_config_contract=True,
            require_non_empty_trace_hashes=True,
        )
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "")

    def test_validate_claim_row_hash_links_rejects_mismatched_baseline_hashes(self) -> None:
        payload = self._build_payload()
        workload = payload["workloads"][0]
        workload["claimWorkloadHash"]["context"]["baselineTraceMetaSha256"] = ["6" * 64]
        ok, reason = report_conformance.validate_claim_row_hash_links(
            payload=payload,
            require_config_contract=True,
            require_non_empty_trace_hashes=True,
        )
        self.assertFalse(ok)
        self.assertIn("baselineTraceMetaSha256 mismatch", reason)


if __name__ == "__main__":
    unittest.main()
