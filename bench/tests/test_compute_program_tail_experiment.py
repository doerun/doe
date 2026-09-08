"""Reject work and instrumentation mismatches before accepting tail comparisons."""
from __future__ import annotations

import copy
import unittest

from bench.runners.run_compute_program_tail_experiment import assert_control_identity


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


if __name__ == '__main__':
    unittest.main()
