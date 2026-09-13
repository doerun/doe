"""Ordered diagnosis must preserve every sample and distinguish timing scopes."""
from __future__ import annotations

import copy
import csv
import tempfile
import unittest
from pathlib import Path

from bench.gates.compute_program_resolution_gate import (
    check_execution_contract, check_tsv, verify_reference,
)

from bench.lib.compute_program_resolution import (
    cpu_profile_rows, process_blocks, sample_costs, summarize_blocks,
)


def process() -> dict:
    samples = []
    for run in range(1, 10):
        samples.append({'wallMs': 20 / run, 'cpuMs': 8 / run,
                        'oracle': {'passed': True}, 'receipt': {
                            'run': run, 'programInstance': 'same', 'programHash': 'shader',
                            'execution': 'webgpu', 'dispatchCount': 1, 'submissionCount': 1,
                            'readbackPath': 'mapAsync-copy-unmap', 'completionMode': 'queue-and-map',
                            'gpuTiming': {'elapsedNs': 1_000_000},
                            'timingMs': dict(upload=1/run, encode=1/run,
                                             submitWait=1/run, readback=1/run, total=10/run)}})
    return {'status': 'passed', 'phase': 'measure', 'cold': samples[0],
            'warmups': samples[1:2], 'samples': samples[2:]}


class ResolutionTests(unittest.TestCase):
    def test_another_qualified_package_cannot_replace_the_accepted_package(self) -> None:
        data = {'provider': 'doe-webgpu', 'application': 'app', 'backend': 'vulkan',
                'runtime': {'name': 'node'}, 'policyHash': 'policy',
                'packageQualification': {'hash': 'accepted'},
                'providerArtifact': {'hash': 'library'}}
        check_execution_contract(data, 'app', 'policy', 'accepted', 'library')
        for key, replacement in [('packageQualification', {'hash': 'other-qualified'}),
                                 ('providerArtifact', {'hash': 'other-library'}),
                                 ('runtime', {'name': 'bun'}), ('policyHash', 'other-policy'),
                                 ('backend', 'metal')]:
            changed = {**data, key: replacement}
            with self.assertRaisesRegex(ValueError, 'accepted package'):
                check_execution_contract(changed, 'app', 'policy', 'accepted', 'library')

    def test_all_samples_belong_to_one_ordered_block(self) -> None:
        rows = [r for r in process_blocks(process(), 3) if r['metric'] == 'wallMs']
        self.assertEqual([r['samples'] for r in rows], [2, 2, 3])
        self.assertEqual([(r['firstRun'], r['lastRun']) for r in rows], [(3, 4), (5, 6), (7, 9)])

    def test_gpu_time_is_not_subtracted_from_host_scope(self) -> None:
        row = process()['cold']
        values = sample_costs(row)
        self.assertEqual(values['outsideReceiptMs'], 10)
        self.assertEqual(values['unassignedReceiptMs'], 6)
        row['receipt']['gpuTiming']['elapsedNs'] *= 100
        self.assertEqual(sample_costs(row)['unassignedReceiptMs'], 6)

    def test_unsupported_gpu_measurement_stays_unavailable(self) -> None:
        report = process()
        for sample in [report['cold'], *report['warmups'], *report['samples']]:
            sample['receipt']['gpuTiming'] = None
        rows = process_blocks(report, 3)
        self.assertTrue(all(r['medianMs'] is None for r in rows if r['metric'] == 'gpuMs'))

    def test_changed_work_or_reordered_samples_fail(self) -> None:
        for key, value in [('run', 1), ('dispatchCount', 0), ('programInstance', 'other')]:
            report = process()
            report['samples'][0]['receipt'][key] = value
            with self.assertRaisesRegex(ValueError, 'sequence'):
                process_blocks(report, 3)

    def test_processes_receive_equal_weight(self) -> None:
        rows = [{'application': 'app', 'treatment': 'test', 'process': name, **row}
                for name in ('one', 'two') for row in process_blocks(process(), 3)]
        result = summarize_blocks(rows)
        self.assertTrue(all(row['processes'] == 2 for row in result))
        wall = next(row for row in result if row['metric'] == 'wallMs')
        self.assertEqual(wall['decreasedProcesses'], 2)
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            summarize_blocks([*rows, copy.deepcopy(rows[0])])

    def test_profile_requires_valid_nodes_and_durations(self) -> None:
        profile = {'nodes': [{'id': 1, 'callFrame': {
            'functionName': 'main', 'url': 'test.js', 'lineNumber': 0}}],
            'samples': [1, 1], 'timeDeltas': [10, 20]}
        self.assertEqual(cpu_profile_rows(profile)[0]['signedDeltaUs'], 30)
        profile['timeDeltas'][0] = -1
        result = cpu_profile_rows(profile)[0]
        self.assertEqual(result['negativeDeltas'], 1)
        self.assertEqual(result['signedDeltaUs'], 19)
        profile['samples'][0] = 2
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            cpu_profile_rows(profile)

    def test_review_rejects_changed_projection_and_input(self) -> None:
        from bench.gates.compute_program_gate import digest

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cost.tsv'
            rows = [{'cost': 1, 'unavailable': None}]
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t')
                writer.writeheader()
                writer.writerows(rows)
            reference = {'path': str(path), 'hash': digest(path)}
            check_tsv(path, rows)
            verify_reference(reference)
            path.write_text('cost\tunavailable\n0\t\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'projection'):
                check_tsv(path, rows)
            with self.assertRaisesRegex(ValueError, 'changed'):
                verify_reference(reference)


if __name__ == '__main__':
    unittest.main()
