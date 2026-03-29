import unittest

from bench.runners.run_route_branch_continuation import compare_token_sequences
from bench.runners.run_route_branch_continuation import dominant_route_result
from bench.runners.run_route_branch_continuation import summarize_routes
from bench.runners.run_route_branch_continuation import validate_route_summary


class RouteBranchContinuationTests(unittest.TestCase):
    def test_compare_token_sequences_reports_first_difference(self):
        self.assertEqual(compare_token_sequences([1, 2, 3], [1, 9, 3]), 1)
        self.assertEqual(compare_token_sequences([1, 2], [1, 2, 3]), 2)
        self.assertIsNone(compare_token_sequences([1, 2, 3], [1, 2, 3]))

    def test_dominant_route_result_uses_most_common_tail(self):
        dominant = dominant_route_result(
            [
                {"continuationTokenIds": [1, 2, 3], "decodedTailText": "a"},
                {"continuationTokenIds": [1, 2, 3], "decodedTailText": "a"},
                {"continuationTokenIds": [9, 9, 9], "decodedTailText": "b"},
            ]
        )
        self.assertEqual(dominant["continuationTokenIds"], [1, 2, 3])

    def test_summarize_routes_builds_pairwise_comparisons(self):
        summary = summarize_routes(
            {
                "runs": [
                    {
                        "routeResults": [
                            {
                                "id": "raw",
                                "seedToken": 1,
                                "seedTokenText": " a",
                                "continuationTokenIds": [2, 3],
                                "continuationTokenTexts": [" b", " c"],
                                "decodedTailText": " a b c",
                            },
                            {
                                "id": "stable-choice",
                                "seedToken": 4,
                                "seedTokenText": " unsafe",
                                "continuationTokenIds": [5, 6],
                                "continuationTokenTexts": [" x", " y"],
                                "decodedTailText": " unsafe x y",
                            },
                        ]
                    },
                    {
                        "routeResults": [
                            {
                                "id": "raw",
                                "seedToken": 1,
                                "seedTokenText": " a",
                                "continuationTokenIds": [2, 3],
                                "continuationTokenTexts": [" b", " c"],
                                "decodedTailText": " a b c",
                            },
                            {
                                "id": "stable-choice",
                                "seedToken": 4,
                                "seedTokenText": " unsafe",
                                "continuationTokenIds": [5, 7],
                                "continuationTokenTexts": [" x", " z"],
                                "decodedTailText": " unsafe x z",
                            },
                        ]
                    },
                ]
            },
            route_token_metadata={
                "raw": {"seedToken": 1, "seedTokenText": " a", "selectedBy": "raw-greedy", "receipt": None},
                "stable-choice": {
                    "seedToken": 4,
                    "seedTokenText": " unsafe",
                    "selectedBy": "stable-choice-policy",
                    "receipt": {"selectedBy": "stable-choice-policy"},
                },
            },
        )
        self.assertEqual(len(summary["routes"]), 2)
        raw = next(route for route in summary["routes"] if route["routeId"] == "raw")
        self.assertTrue(raw["continuationStable"])
        comparison = summary["comparisons"][0]
        self.assertEqual(comparison["leftRouteId"], "raw")
        self.assertEqual(comparison["rightRouteId"], "stable-choice")
        self.assertEqual(comparison["firstDivergenceStepIndex"], 0)

    def test_validate_route_summary_rejects_same_seed_divergence(self):
        with self.assertRaisesRegex(RuntimeError, "same seed token diverged"):
            validate_route_summary(
                {
                    "comparisons": [
                        {
                            "leftRouteId": "raw",
                            "rightRouteId": "stable-token",
                            "sameSeedToken": True,
                            "sameContinuation": False,
                            "firstDivergenceStepIndex": 0,
                        }
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
