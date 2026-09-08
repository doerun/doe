"""Faster startup must not conceal warm, cold, CPU, or memory regressions."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from bench.runners.assess_compute_program_startup import assess_application

ROOT = Path(__file__).resolve().parents[2]


class StartupAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.startup = json.loads(
            (ROOT / 'config/compute-program-startup-experiment.json').read_text())
        self.tail = json.loads(
            (ROOT / self.startup['tailExperimentPolicy']).read_text())
        receipt = dict(inputHashes={'input': 'fixed'}, dispatchCount=32,
                       submissionCount=1, clearedBytes=512, uploadedBytes=256,
                       readbackBytes=272, readbackPath='mapAsync-copy-unmap',
                       completionMode='queue-and-map', execution='webgpu',
                       timingMs=dict(upload=1, encode=1, submitWait=1,
                                     readback=1, total=4))
        sample = dict(receipt=receipt, wallMs=10, cpuMs=2)
        report = dict(
            schemaVersion=6, deviceStartupTimingScope=self.startup['deviceStartupTimingScope'],
            programHash='fixed', runtime={'name': 'node', 'version': 'pinned'},
            backend='vulkan', adapter=dict(isFallbackAdapter=False, vendorID=1, deviceID=2),
            deviceStartupMs=100, preparationMs=10, teardownMs=10,
            peakProcessRssBytes=1024, allocatedBufferBytes=1024,
            cold=copy.deepcopy(sample), samples=[copy.deepcopy(sample)
                                                 for _ in range(self.tail['expandedTimedRuns'])],
        )
        self.groups = {v: [copy.deepcopy(report) for _ in range(self.tail['expandedProcessPairs'])]
                       for v in ('baseline', 'candidate')}
        for candidate in self.groups['candidate']:
            candidate['deviceStartupMs'] = 80

    def accepted(self, application: str = 'heat_diffusion') -> bool:
        decision, _ = assess_application(
            self.groups, application, self.startup, self.tail)
        return decision['acceptancePassed']

    def test_startup_benefit_does_not_require_warm_speedup(self) -> None:
        self.assertTrue(self.accepted())

    def test_warm_tail_rejects_startup_benefit(self) -> None:
        for candidate in self.groups['candidate']:
            candidate['samples'][-1]['wallMs'] = 50
            candidate['samples'][-2]['wallMs'] = 50
        self.assertFalse(self.accepted())

    def test_startup_tail_rejects_median_gain(self) -> None:
        self.groups['candidate'][-1]['deviceStartupMs'] = 200
        self.assertFalse(self.accepted())

    def test_cold_preparation_cleanup_and_resource_regressions_reject(self) -> None:
        for metric in ('preparationMs', 'teardownMs', 'peakProcessRssBytes', 'allocatedBufferBytes'):
            with self.subTest(metric=metric):
                original = self.groups['candidate'][-1][metric]
                self.groups['candidate'][-1][metric] = original * 2
                self.assertFalse(self.accepted())
                self.groups['candidate'][-1][metric] = original
        self.groups['candidate'][-1]['cold']['wallMs'] *= 2
        self.assertFalse(self.accepted())

    def test_cold_cpu_regression_rejects_startup_benefit(self) -> None:
        self.groups['candidate'][-1]['cold']['cpuMs'] *= 2
        self.assertFalse(self.accepted())

    def test_matching_pair_drift_still_rejects_changed_application(self) -> None:
        for variant in ('baseline', 'candidate'):
            self.groups[variant][-1]['programHash'] = 'different-application'
        with self.assertRaisesRegex(ValueError, 'program'):
            self.accepted()

    def test_cpu_tail_rejects_startup_benefit(self) -> None:
        for candidate in self.groups['candidate']:
            for sample in candidate['samples'][-2:]:
                sample['cpuMs'] *= 2
        self.assertFalse(self.accepted())

    def test_missing_process_or_samples_is_not_partial_acceptance(self) -> None:
        original = self.groups['candidate'].pop()
        with self.assertRaisesRegex(ValueError, 'complete expanded pairs'):
            self.accepted()
        self.groups['candidate'].append(original)
        original['samples'].pop()
        with self.assertRaisesRegex(ValueError, 'expanded samples'):
            self.accepted()

    def test_work_and_timing_scope_must_match(self) -> None:
        self.groups['candidate'][0]['cold']['receipt']['dispatchCount'] = 0
        with self.assertRaisesRegex(ValueError, 'dispatchCount'):
            self.accepted()
        self.groups['candidate'][0]['schemaVersion'] = 5
        with self.assertRaisesRegex(ValueError, 'device-ready timing'):
            self.accepted()

    def test_transfer_allows_unchanged_startup_without_retuning(self) -> None:
        for candidate in self.groups['candidate']:
            candidate['deviceStartupMs'] = 100
        self.assertFalse(self.accepted())
        self.assertTrue(self.accepted('image_edges'))
        self.assertTrue(self.accepted('holoscript_lif'))


if __name__ == '__main__':
    unittest.main()
