"""Retirement admission must retain controls and historical verdicts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / 'bench/external-projects/doppler-generation'
HISTORY = ROOT / 'reports/benchmarks/amd-vulkan/20261004-doppler-generation'


class RetirementAdmissionTests(unittest.TestCase):
    def compare(self, before, after, policy=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in [('before', before), ('after', after)]:
                (root / f'{name}.json').write_text(json.dumps(value))
            command = [sys.executable, str(HARNESS / 'compare.py'),
                       '--baseline', str(root / 'before.json'),
                       '--candidate', str(root / 'after.json'),
                       '--contract', str(HARNESS / 'contract.json'),
                       '--out', str(root / 'decision.json')]
            if policy:
                command.extend(['--candidate-policy', str(HARNESS / 'retirement-candidate.json')])
            subprocess.run(command, check=True, capture_output=True, text=True)
            return json.loads((root / 'decision.json').read_text())

    def passing_pair(self):
        before = json.loads((HISTORY / 'baseline-summary.json').read_text())
        for provider in before['providers'].values():
            for control in provider['controls'].values():
                control['stable'] = True
        after = copy.deepcopy(before)
        for percentile in ['p50', 'p95']:
            after['providers']['doe']['timingsMs']['resident']['completeMs'][percentile] *= 0.8
        return before, after

    def test_complete_gain_does_not_require_first_token_gain(self):
        result = self.compare(*self.passing_pair())
        self.assertTrue(result['timingAdmissionPassed'])
        self.assertFalse(result['performancePromoted'])
        self.assertAlmostEqual(result['primaryGainRatio'], 1.25)

    def test_failed_controls_cannot_be_rescued_by_gain(self):
        for lane in ['doe', 'dawn']:
            for metric in ['firstTokenMs', 'completeMs']:
                before, after = self.passing_pair()
                before['providers'][lane]['controls'][metric]['stable'] = False
                result = self.compare(before, after)
                self.assertFalse(result['timingAdmissionPassed'], (lane, metric))

    def test_incumbent_complete_drift_rejects_candidate(self):
        before, after = self.passing_pair()
        after['providers']['dawn']['timingsMs']['resident']['completeMs']['p50'] *= 1.2
        self.assertFalse(self.compare(before, after)['timingAdmissionPassed'])

    def test_legacy_decision_is_preserved(self):
        before = json.loads((HISTORY / 'baseline-summary.json').read_text())
        after = json.loads((HISTORY / 'candidate-summary.json').read_text())
        expected = json.loads((HISTORY / 'disposition.json').read_text())
        observed = self.compare(before, after, policy=False)
        # Temporary serialization changes input bytes, but never historical policy.
        for key in ['baselineSummarySha256', 'candidateSummarySha256']:
            observed.pop(key)
            expected.pop(key)
        self.assertEqual(observed, expected)


class PhaseObserverTests(unittest.TestCase):
    def test_observer_preserves_results_errors_and_destruction(self):
        subprocess.run(['node', '--input-type=module', '-e', '''
import assert from 'node:assert/strict';
import { observeDevicePhases } from './bench/external-projects/doppler-generation/observe-phases.mjs';
const events = [];
const failure = new Error('queue closed');
const buffer = { label: 'allocation', destroy() { return 'destroyed'; } };
const device = {
  createBuffer() { return buffer; },
  createBindGroup() { throw null; },
  queue: {
    submit() { throw failure; },
    onSubmittedWorkDone() { return Promise.reject(failure); },
    writeBuffer() { return 42; },
  },
};
observeDevicePhases(device, events, () => 'cleanup');
assert.equal(device.createBuffer({ size: 16 }), buffer);
assert.equal(buffer.destroy(), 'destroyed');
assert.throws(() => device.queue.submit(), error => error === failure);
await assert.rejects(device.queue.onSubmittedWorkDone(), error => error === failure);
assert.equal(device.queue.writeBuffer(), 42);
let threw = false;
try { device.createBindGroup({}); } catch (error) { threw = true;assert.equal(error, null); }
assert(threw);
assert.equal(events.length, 6);
assert.equal(events.find(event => event.method === 'destroy').bytes, 16);
assert.equal(events.find(event => event.method === 'createBindGroup').failure, 'null');
for (const method of ['submit', 'onSubmittedWorkDone']) {
  const event = events.find(event => event.method === method);
  assert.equal(event.failure, failure.stack);
  assert.equal(event.durationMs, event.endedMs - event.startedMs);
  assert.equal(event.phase, 'cleanup');
}
'''], cwd=ROOT, check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
