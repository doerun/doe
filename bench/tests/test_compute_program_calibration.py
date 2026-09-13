"""A/A observations never establish an implementation improvement."""
from __future__ import annotations

import copy
import json
import unittest
import tempfile
from pathlib import Path

from bench.runners.run_compute_program_calibration import assess_round, load_policy
from bench.gates.compute_program_calibration_gate import validate_calibration

ROOT = Path(__file__).resolve().parents[2]


class CalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.startup = load_policy(
            ROOT / 'config/compute-program-startup-experiment.json',
            'compute-program-startup-experiment.schema.json')
        self.tail = load_policy(ROOT / self.startup['tailExperimentPolicy'],
                                'compute-program-tail-experiment.schema.json')
        receipt = dict(inputHashes={}, dispatchCount=1, submissionCount=1,
                       clearedBytes=4, uploadedBytes=4, readbackBytes=4,
                       readbackPath='mapAsync-copy-unmap', completionMode='queue-and-map',
                       execution='webgpu', timingMs=dict(upload=1, encode=1,
                                                        submitWait=1, readback=1, total=4))
        sample = dict(wallMs=5, cpuMs=2, receipt=receipt)
        report = dict(schemaVersion=6, deviceStartupTimingScope=self.startup['deviceStartupTimingScope'],
                      programHash='unchanged', runtime={'name': 'node', 'version': 'pinned'},
                      backend='vulkan', adapter={'vendorID': 1, 'deviceID': 2, 'isFallbackAdapter': False},
                      deviceStartupMs=100, preparationMs=10, teardownMs=10,
                      peakProcessRssBytes=1024, allocatedBufferBytes=4,
                      cold=sample, samples=[copy.deepcopy(sample)
                                            for _ in range(self.tail['expandedTimedRuns'])])
        self.groups = {v: [copy.deepcopy(report) for _ in range(self.tail['expandedProcessPairs'])]
                       for v in ('baseline', 'candidate')}

    def rows(self) -> list[dict]:
        return assess_round(self.groups, 'heat_diffusion', self.startup, self.tail)

    def test_equal_observations_pass_without_needing_a_speedup(self) -> None:
        self.assertTrue(all(r['regressionPassed'] for r in self.rows()))

    def test_apparent_aa_improvement_fails_the_reverse_direction(self) -> None:
        for report in self.groups['candidate']:
            report['deviceStartupMs'] /= 2
        rows = self.rows()
        self.assertTrue(all(r['regressionPassed'] for r in rows if r['direction'] == 'forward'))
        self.assertFalse(all(r['regressionPassed'] for r in rows if r['direction'] == 'reverse'))

    def test_single_process_tail_is_retained(self) -> None:
        self.groups['candidate'][-1]['teardownMs'] *= 2
        rows = [r for r in self.rows() if r['metric'] == 'teardownMs' and r['direction'] == 'forward']
        self.assertEqual([r['regressionPassed'] for r in rows], [True, False, False])

    def test_missing_samples_and_changed_work_fail_before_statistics(self) -> None:
        self.groups['candidate'][0]['samples'].pop()
        with self.assertRaisesRegex(ValueError, 'expanded samples'):
            self.rows()

    def test_calibration_policy_cannot_waive_a_failing_round(self) -> None:
        import jsonschema
        policy = load_policy(ROOT / 'config/compute-program-calibration.json',
                             'compute-program-calibration.schema.json')
        policy['maximumRegressionViolationRounds'] = 1
        schema = json.loads((ROOT / 'config/compute-program-calibration.schema.json').read_text())
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(policy, schema)

    def test_inconclusive_calibration_cannot_enter_a_candidate_decision(self) -> None:
        ref = {'path': 'not-admitted', 'hash': '0' * 64}
        report = dict(schemaVersion=1, kind='compute-program-calibration',
                      claimStatus='diagnostic', status='inconclusive',
                      candidateEvaluationAllowed=False, policy=ref, frozenInputs=ref,
                      packages=[ref, ref], rounds=[], artifacts=[], error=None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text(json.dumps(report), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'inconclusive'):
                validate_calibration(path)

    def test_status_only_promotion_is_rejected_by_schema(self) -> None:
        import jsonschema
        schema = json.loads((ROOT / 'config/compute-program-calibration-report.schema.json').read_text())
        ref = {'path': 'missing', 'hash': '0' * 64}
        report = dict(schemaVersion=1, kind='compute-program-calibration',
                      claimStatus='diagnostic', status='consistent',
                      candidateEvaluationAllowed=True, policy=ref, frozenInputs=ref,
                      packages=[ref, ref], rounds=[], artifacts=[], error=None)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(report, schema)


if __name__ == '__main__':
    unittest.main()
