import unittest
from copy import deepcopy

from bench.runners.run_selective_stable_rerun_probe import evaluate_lane
from bench.runners.run_selective_stable_rerun_probe import find_first_divergence


class SelectiveStableRerunProbeTests(unittest.TestCase):
    def _source_report(self):
        return {
            "scenarioId": "demo",
            "captures": [
                {
                    "semanticOpId": "matmul.logits",
                    "semanticStage": "micro_matmul_logits",
                    "semanticPhase": "logits",
                },
                {
                    "semanticOpId": "sample.token",
                    "semanticStage": "micro_matmul_logits",
                    "semanticPhase": "selected_token",
                },
            ],
            "variants": {
                "pairwise": {
                    "lanes": {
                        "doe": {
                            "operators": {
                                "matmul.logits": {"dominantDigest": "fast-logits"},
                                "sample.token": {"dominantDigest": "fast-token", "dominantDecodedValue": 0},
                            }
                        }
                    }
                },
                "forward": {
                    "lanes": {
                        "doe": {
                            "operators": {
                                "matmul.logits": {"dominantDigest": "stable-logits"},
                                "sample.token": {"dominantDigest": "stable-token", "dominantDecodedValue": 1},
                            }
                        }
                    }
                },
            },
            "laneVariantSummary": {
                "doe": {
                    "variantOutputs": [
                        {
                            "variantId": "pairwise",
                            "policyId": "matmul-logits/pairwise-tree-v1",
                            "sampledToken": 0,
                            "matchesExactReferenceTopToken": False,
                        },
                        {
                            "variantId": "forward",
                            "policyId": "matmul-logits/forward-serial-v1",
                            "sampledToken": 1,
                            "matchesExactReferenceTopToken": True,
                        },
                    ]
                }
            },
            "claim": {
                "exactReferenceTopToken": 1
            },
        }

    def _registry(self):
        return {
            "registryVersion": "2026-03-29-route-taxonomy-v2",
            "routeTaxonomyVersion": "numeric-stability-routes-v1",
            "proofArtifactPath": "pipeline/lean/artifacts/proven-conditions.json",
            "routeDecisions": ["accept-fast", "prefer-stable", "abstain"],
            "routeDecisionMetadata": [
                {
                    "decision": "accept-fast",
                    "selectionMode": "fast",
                    "proofLinks": [
                        {
                            "theorem": "selectedValueForRoute_acceptFast_returns_fast",
                            "module": "Doe.Core.NumericStabilityPolicy",
                            "category": "lean_verified",
                            "relation": "numeric-stability-route-select-fast",
                            "artifactPath": "pipeline/lean/artifacts/proven-conditions.json",
                        }
                    ],
                },
                {
                    "decision": "prefer-stable",
                    "selectionMode": "stable",
                    "proofLinks": [
                        {
                            "theorem": "selectedValueForRoute_preferStable_returns_stable",
                            "module": "Doe.Core.NumericStabilityPolicy",
                            "category": "lean_verified",
                            "relation": "numeric-stability-route-select-stable",
                            "artifactPath": "pipeline/lean/artifacts/proven-conditions.json",
                        }
                    ],
                },
                {
                    "decision": "abstain",
                    "selectionMode": "none",
                    "proofLinks": [
                        {
                            "theorem": "selectedValueForRoute_abstain_returns_none",
                            "module": "Doe.Core.NumericStabilityPolicy",
                            "category": "lean_verified",
                            "relation": "numeric-stability-route-select-none",
                            "artifactPath": "pipeline/lean/artifacts/proven-conditions.json",
                        }
                    ],
                },
            ],
            "triggerPolicies": [
                {
                    "triggerPolicyId": "numeric-instability/selected-token-disagreement-with-reference-improvement-v1",
                    "requireFirstDivergence": True,
                    "requireSelectedTokenDisagreement": True,
                    "requireStableMatchesExactReference": True,
                    "requireFastMissesExactReference": True,
                    "allowedSensitiveOperators": ["matmul.logits"],
                    "proofLinks": [
                        {
                            "theorem": "selectedTokenReferenceImprovementTriggered_iff_all_checks",
                            "module": "Doe.Core.NumericStabilityPolicy",
                            "category": "lean_verified",
                            "relation": "numeric-stability-trigger-all-checks",
                            "artifactPath": "pipeline/lean/artifacts/proven-conditions.json",
                        }
                    ],
                }
            ],
            "routingPolicies": [
                {
                    "policyId": "numeric-stability/prefer-stable-on-selected-token-disagreement-v1",
                    "triggerPolicyId": "numeric-instability/selected-token-disagreement-with-reference-improvement-v1",
                    "triggeredDecision": "prefer-stable",
                    "fallbackDecision": "accept-fast",
                    "proofLinks": [
                        {
                            "theorem": "routeDecisionForTrigger_prefers_triggered_decision_when_true",
                            "module": "Doe.Core.NumericStabilityPolicy",
                            "category": "lean_verified",
                            "relation": "numeric-stability-route-triggered",
                            "artifactPath": "pipeline/lean/artifacts/proven-conditions.json",
                        },
                        {
                            "theorem": "routeDecisionForTrigger_prefers_fallback_decision_when_false",
                            "module": "Doe.Core.NumericStabilityPolicy",
                            "category": "lean_verified",
                            "relation": "numeric-stability-route-fallback",
                            "artifactPath": "pipeline/lean/artifacts/proven-conditions.json",
                        },
                    ],
                }
            ],
        }

    def _fixture(self):
        return {
            "fastVariantId": "pairwise",
            "stableVariantId": "forward",
            "triggerPolicyId": "numeric-instability/selected-token-disagreement-with-reference-improvement-v1",
            "routingPolicyId": "numeric-stability/prefer-stable-on-selected-token-disagreement-v1",
            "selectedTokenOpId": "sample.token",
            "operatorFamily": "logits-matmul",
            "sensitiveOperators": ["matmul.logits"],
        }

    def test_find_first_divergence_returns_first_capture_mismatch(self):
        divergence = find_first_divergence(
            self._source_report(),
            lane_id="doe",
            fast_variant_id="pairwise",
            stable_variant_id="forward",
        )
        self.assertEqual(divergence["semanticOpId"], "matmul.logits")

    def test_evaluate_lane_prefers_stable_when_trigger_fires(self):
        result = evaluate_lane(
            self._source_report(),
            self._registry(),
            self._fixture(),
            lane_id="doe",
        )
        self.assertTrue(result["trigger"]["fired"])
        self.assertEqual(result["route"]["decision"], "prefer-stable")
        self.assertEqual(result["route"]["selectionMode"], "stable")
        self.assertEqual(result["route"]["selectedVariantId"], "forward")
        self.assertEqual(result["route"]["selectedToken"], 1)
        self.assertEqual(
            result["trigger"]["proofLinks"][0]["theorem"],
            "selectedTokenReferenceImprovementTriggered_iff_all_checks",
        )
        self.assertEqual(
            result["route"]["proofLinks"][0]["theorem"],
            "routeDecisionForTrigger_prefers_triggered_decision_when_true",
        )
        self.assertEqual(
            result["route"]["selectionProofLinks"][0]["theorem"],
            "selectedValueForRoute_preferStable_returns_stable",
        )

    def test_evaluate_lane_accepts_fast_when_stable_misses_exact_reference(self):
        source = deepcopy(self._source_report())
        source["variants"]["pairwise"]["lanes"]["doe"]["operators"]["sample.token"]["dominantDecodedValue"] = 0
        source["variants"]["forward"]["lanes"]["doe"]["operators"]["sample.token"]["dominantDecodedValue"] = 1
        source["laneVariantSummary"]["doe"]["variantOutputs"][0]["matchesExactReferenceTopToken"] = True
        source["laneVariantSummary"]["doe"]["variantOutputs"][1]["matchesExactReferenceTopToken"] = False
        source["claim"]["exactReferenceTopToken"] = 0

        result = evaluate_lane(
            source,
            self._registry(),
            self._fixture(),
            lane_id="doe",
        )
        self.assertFalse(result["trigger"]["fired"])
        self.assertTrue(result["trigger"]["checks"]["sensitiveOperatorMatched"])
        self.assertTrue(result["selectedToken"]["changed"])
        self.assertFalse(result["selectedToken"]["stableMatchesExactReference"])
        self.assertTrue(result["selectedToken"]["fastMatchesExactReference"])
        self.assertEqual(result["route"]["decision"], "accept-fast")
        self.assertEqual(result["route"]["selectionMode"], "fast")
        self.assertEqual(result["route"]["selectedVariantId"], "pairwise")
        self.assertEqual(result["route"]["selectedToken"], 0)


if __name__ == "__main__":
    unittest.main()
