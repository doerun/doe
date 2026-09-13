"""Confirmation cannot reuse a physically valid evaluation process."""
from __future__ import annotations

import unittest

from bench.gates.command_storage_review_gate import verify_execution_sequence


class ReviewFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluation = {'bootId': 'boot-a', 'pid': 1, 'startedMonotonicNs': 10,
                           'completedMonotonicNs': 20, 'exitCode': 0}
        self.confirmation = {**self.evaluation, 'pid': 2, 'startedMonotonicNs': 30,
                             'completedMonotonicNs': 40}

    def test_fresh_evaluation_and_confirmation_pass(self) -> None:
        verify_execution_sequence([self.evaluation, self.confirmation])

    def test_reused_process_cannot_confirm_its_own_result(self) -> None:
        with self.assertRaisesRegex(ValueError, 'distinct physical'):
            verify_execution_sequence([self.evaluation, self.confirmation, self.evaluation.copy()])

    def test_new_pid_with_overlapping_or_reversed_execution_fails(self) -> None:
        for started in (1, 15):
            with self.assertRaisesRegex(ValueError, 'overlap'):
                verify_execution_sequence([self.evaluation, {**self.confirmation, 'startedMonotonicNs': started}])

    def test_pid_reuse_is_allowed_only_for_a_distinct_later_execution(self) -> None:
        verify_execution_sequence([self.evaluation, {**self.confirmation, 'pid': self.evaluation['pid']}])

    def test_empty_or_failed_execution_is_not_confirmation(self) -> None:
        for rows in ([], [{**self.evaluation, 'exitCode': 1}]):
            with self.assertRaises(ValueError):
                verify_execution_sequence(rows)


if __name__ == '__main__':
    unittest.main()
