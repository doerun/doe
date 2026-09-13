"""Uncertainty must not turn dependent invocations or missing power into wins."""
from __future__ import annotations

import copy
import itertools
import json
import unittest
from pathlib import Path
from dataclasses import replace

from bench.lib.compute_program_uncertainty import (
    ProcessPair, assess_uncertainty, candidate_verdict, median_interval,
)
import bench.tests.test_compute_program_calibration as calibration_fixtures

ROOT = Path(__file__).resolve().parents[2]


class IntervalTests(unittest.TestCase):
    def test_exact_small_sample_coverage_by_enumeration(self) -> None:
        # Every equally likely sign pattern, independent of interval code.
        count, failures = 10, 0
        for signs in itertools.product((-1, 1), repeat=count):
            values = [1 + sign * (i + 1) / 100 for i, sign in enumerate(signs)]
            interval = median_interval(values, .05)
            failures += not interval['lowerRatio'] <= 1 <= interval['upperRatio']
        self.assertLessEqual(failures / 2 ** count, .05)
        self.assertEqual(failures, 22)

    def test_ties_do_not_create_precision_with_too_few_processes(self) -> None:
        result = median_interval([1] * 4, .01)
        self.assertIsNone(result['lowerRatio'])
        self.assertIsNone(result['upperRatio'])

    def test_more_endpoints_never_narrow_the_interval(self) -> None:
        values = [1 + i / 1000 for i in range(32)]
        single = median_interval(values, .01)
        family = median_interval(values, .01 / 168)
        self.assertLessEqual(family['lowerRatio'], single['lowerRatio'])
        self.assertGreaterEqual(family['upperRatio'], single['upperRatio'])

    def test_invalid_measurements_fail(self) -> None:
        for value in [0, -1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                median_interval([value], .01)


class ProcessDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = calibration_fixtures.CalibrationTests()
        fixture.setUp()
        self.tail = fixture.tail
        self.report = fixture.groups['baseline'][0]
        self.decision = json.loads((ROOT / 'config/compute-program-decision.json').read_text())
        self.pairs = [ProcessPair(app, cohort, i, ('baseline', 'candidate')[(cohort + i) % 2],
                                  copy.deepcopy(self.report), copy.deepcopy(self.report))
                      for app in [self.tail['developmentApplication'], *self.tail['transferApplications']]
                      for cohort in range(self.decision['cohorts'])
                      for i in range(self.tail['expandedProcessPairs'])]

    def assess(self) -> dict:
        return assess_uncertainty(self.pairs, self.tail, self.decision)

    def verdict(self, raw: bool = True, resolved: bool = True) -> dict:
        return candidate_verdict(self.assess(), [{'acceptancePassed': raw}], self.tail,
                                 calibration_resolved=resolved)

    def test_identical_packages_never_become_an_improvement(self) -> None:
        self.assertTrue(self.assess()['nullConsistent'])
        self.assertEqual(self.verdict()['verdict'], 'reject')

    def test_missing_duplicate_or_reordered_pairs_fail(self) -> None:
        for pairs in [self.pairs[:-1], [*self.pairs, self.pairs[0]]]:
            with self.assertRaises(ValueError):
                assess_uncertainty(pairs, self.tail, self.decision)
        pair = self.pairs[0]
        self.pairs[0] = ProcessPair(pair.application, pair.cohort, pair.index, 'candidate',
                                    pair.baseline, pair.candidate)
        with self.assertRaisesRegex(ValueError, 'order'):
            self.assess()

    def test_invocation_duplication_does_not_increase_confidence(self) -> None:
        before = self.assess()
        for pair in self.pairs:
            pair.baseline['samples'] *= 2
            pair.candidate['samples'] *= 2
        self.assertEqual(before, self.assess())

    def test_duplicate_physical_executions_do_not_become_fresh_pairs(self) -> None:
        self.pairs = [replace(pair, execution_ids=('same-execution', 'same-execution'))
                      for pair in self.pairs]
        with self.assertRaisesRegex(ValueError, 'distinct physical'):
            self.assess()

    def test_order_bias_is_not_cancelled_by_opposite_order(self) -> None:
        for pair in self.pairs:
            pair.candidate['preparationMs'] *= 2 if pair.first == 'baseline' else .5
        self.assertFalse(self.assess()['nullConsistent'])
        self.assertEqual(self.verdict()['verdict'], 'reject')

    def test_raw_guards_and_calibration_precision_still_required(self) -> None:
        for pair in self.pairs:
            for sample in pair.candidate['samples']:
                sample['wallMs'] /= 2
        self.assertEqual(self.verdict()['verdict'], 'confirm')
        self.assertEqual(self.verdict(raw=False)['verdict'], 'inconclusive')
        self.assertEqual(self.verdict(resolved=False)['verdict'], 'inconclusive')

    def test_one_extreme_tail_cannot_be_discarded_by_acceptance(self) -> None:
        for pair in self.pairs:
            for sample in pair.candidate['samples']:
                sample['wallMs'] /= 2
        self.pairs[0].candidate['samples'][-1]['wallMs'] *= 1000
        self.assertEqual(self.verdict(raw=False)['verdict'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
