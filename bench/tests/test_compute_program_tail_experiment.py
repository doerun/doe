"""Reject work and instrumentation mismatches before accepting tail comparisons."""
from __future__ import annotations

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from bench.runners.run_compute_program_tail_experiment import (
    POLICY, assert_control_identity, summarize,
)


class TailIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        receipt = dict(inputHashes={'input': 'frozen'}, dispatchCount=32,
                       submissionCount=1, clearedBytes=512, uploadedBytes=256,
                       readbackBytes=272, readbackPath='mapAsync-copy-unmap',
                       completionMode='queue-and-map', execution='webgpu',
                       timingMs=dict(upload=1, encode=1, submitWait=1, readback=1, total=4))
        self.control = dict(programHash='frozen-program', backend='vulkan',
                            runtime={'name': 'node', 'version': 'pinned'},
                            adapter=dict(isFallbackAdapter=False, vendorID=1, deviceID=2),
                            cold={'receipt': receipt}, samples=[{'receipt': receipt}])

    def test_same_work_allows_a_different_qualified_binary(self) -> None:
        report = copy.deepcopy(self.control)
        report['providerArtifact'] = {'hash': 'different-qualified-binary'}
        assert_control_identity(self.control, report)

    def test_changed_program_and_host_are_rejected(self) -> None:
        for key, value in [('programHash', 'different'), ('backend', 'metal'),
                           ('runtime', {'name': 'deno', 'version': 'pinned'})]:
            with self.subTest(key=key):
                report = copy.deepcopy(self.control)
                report[key] = value
                with self.assertRaises(ValueError):
                    assert_control_identity(self.control, report)

    def test_missing_work_and_completion_asymmetry_are_rejected(self) -> None:
        for key, value in [('dispatchCount', 0), ('readbackBytes', 0),
                           ('readbackPath', 'native-map-copy-unmap'), ('completionMode', 'queue-only')]:
            with self.subTest(key=key):
                report = copy.deepcopy(self.control)
                report['cold']['receipt'][key] = value
                with self.assertRaisesRegex(ValueError, key):
                    assert_control_identity(self.control, report)

    def test_zero_encode_phase_is_rejected(self) -> None:
        report = copy.deepcopy(self.control)
        report['samples'][0]['receipt']['timingMs']['encode'] = 0
        with self.assertRaisesRegex(ValueError, 'Missing execution timing phase'):
            assert_control_identity(self.control, report)


class TailCpuAcceptanceTests(unittest.TestCase):
    def decision(self, candidate_cpu: list[float]) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            policy = json.loads(POLICY.read_text(encoding='utf-8'))
            for variant, wall, cpu in (
                ('baseline', 10, [1.0] * len(candidate_cpu)),
                ('candidate', 8, candidate_cpu),
            ):
                report = dict(deviceStartupMs=1, preparationMs=1, teardownMs=1,
                              peakProcessRssBytes=1024, allocatedBufferBytes=1024,
                              cold={'wallMs': 10}, latencyStatsMs={'median': wall},
                              samples=[])
                for index, cost in enumerate(cpu):
                    report['samples'].append({
                        'wallMs': wall, 'cpuMs': cost,
                        'receipt': dict(
                            programInstance=variant, run=index,
                            timingMs=dict(upload=1, encode=1, submitWait=1,
                                          readback=1, total=4),
                            gpuTiming={'elapsedNs': 100}, dispatchCount=1,
                            submissionCount=1, readbackBytes=256,
                            allocatedBufferBytes=1024,
                        ),
                    })
                path = output / f'heat_diffusion.{variant}.process-00.json'
                path.write_text(json.dumps(report), encoding='utf-8')
            summarize(output, policy)
            with (output / 'acceptance.tsv').open(encoding='utf-8') as stream:
                return next(csv.DictReader(stream, delimiter='\t'))

    def test_cpu_median_regression_rejects_faster_application(self) -> None:
        decision = self.decision([2.0] * 64)
        self.assertEqual(decision['costsPass'], 'False')
        self.assertEqual(decision['acceptancePassed'], 'False')

    def test_cpu_tail_regression_rejects_faster_application(self) -> None:
        decision = self.decision([1.0] * 56 + [2.0] * 8)
        self.assertEqual(decision['costsPass'], 'False')
        self.assertEqual(decision['acceptancePassed'], 'False')

    def test_cpu_within_budget_preserves_application_acceptance(self) -> None:
        decision = self.decision([1.05] * 64)
        self.assertEqual(decision['costsPass'], 'True')
        self.assertEqual(decision['acceptancePassed'], 'True')


if __name__ == '__main__':
    unittest.main()
