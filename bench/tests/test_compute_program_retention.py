"""Evidence retention must preserve bytes, paths, and failed writes."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bench.lib.compute_program_retention import (
    ProcessOutputRetention, deduplicate_outputs, write_json,
)


class RetentionTests(unittest.TestCase):
    def test_identical_bytes_share_storage_and_distinct_outputs_stay_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = {'a.f32': b'accepted', 'b.f32': b'accepted',
                      'c.f32': b'distinct', 'd.json': b'accepted'}
            for name, data in before.items():
                (root / name).write_bytes(data)
            report = deduplicate_outputs(root)
            self.assertEqual(report, {'filesLinked': 1, 'duplicateLogicalBytes': len(b'accepted')})
            self.assertTrue((root / 'a.f32').samefile(root / 'b.f32'))
            self.assertFalse((root / 'a.f32').samefile(root / 'c.f32'))
            for name, data in before.items():
                self.assertEqual((root / name).read_bytes(), data)
            self.assertEqual(deduplicate_outputs(root)['filesLinked'], 0)

    def test_failed_replacement_preserves_original_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('a.f32', 'b.f32'):
                (root / name).write_bytes(b'unchanged')
            with patch('bench.lib.compute_program_retention.os.replace', side_effect=OSError('full')):
                with self.assertRaises(OSError):
                    deduplicate_outputs(root)
            self.assertEqual((root / 'b.f32').read_bytes(), b'unchanged')
            self.assertFalse(list(root.glob('*.verified-link')))

    def test_failed_report_sync_keeps_last_valid_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            write_json(path, {'status': 'incomplete'})
            before = path.read_bytes()
            with patch('bench.lib.compute_program_retention.os.fsync', side_effect=OSError('full')):
                with self.assertRaises(OSError):
                    write_json(path, {'status': 'consistent'})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_each_child_reclaims_duplicates_even_when_the_child_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retention = ProcessOutputRetention(root, 'hardlink-identical-outputs', 1)
            first = root / 'first.json'
            with retention.process(first):
                (root / 'first.json.output.f32').write_bytes(b'accepted')
            with self.assertRaisesRegex(ValueError, 'numerical failure'):
                with retention.process(root / 'second.json'):
                    (root / 'second.json.output.f32').write_bytes(b'accepted')
                    (root / 'second.json.unique.f32').write_bytes(b'failed-but-retained')
                    raise ValueError('numerical failure')
            self.assertTrue((root / 'first.json.output.f32').samefile(root / 'second.json.output.f32'))
            self.assertEqual((root / 'second.json.unique.f32').read_bytes(), b'failed-but-retained')
            record = json.loads((root / 'process-output-retention.json').read_text())
            self.assertEqual(record['filesLinked'], 1)
            with self.assertRaisesRegex(ValueError, 'fresh path'):
                with retention.process(first):
                    self.fail('Reused execution entered')

    def test_disk_admission_rechecks_before_the_next_child(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retention = ProcessOutputRetention(root, 'hardlink-identical-outputs', 100)
            from types import SimpleNamespace
            with patch('bench.lib.compute_program_retention.shutil.disk_usage',
                       side_effect=[SimpleNamespace(free=100), SimpleNamespace(free=99)]):
                with retention.process(root / 'first.json'):
                    pass
                with self.assertRaisesRegex(ValueError, 'before application process'):
                    with retention.process(root / 'second.json'):
                        self.fail('Insufficient-space child launched')

    def test_changed_representative_cannot_replace_new_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retention = ProcessOutputRetention(root, 'hardlink-identical-outputs', 1)
            owner = root / 'first.json.output.f32'
            with retention.process(root / 'first.json'):
                owner.write_bytes(b'accepted')
            owner.write_bytes(b'corrupted')
            duplicate = root / 'second.json.output.f32'
            with self.assertRaisesRegex(ValueError, 'changed during retention'):
                with retention.process(root / 'second.json'):
                    duplicate.write_bytes(b'accepted')
            self.assertEqual(duplicate.read_bytes(), b'accepted')

    def test_retention_requires_the_declared_space_bound(self) -> None:
        for bound in (None, 0, -1):
            with self.assertRaisesRegex(ValueError, 'positive configured'):
                ProcessOutputRetention(Path('.'), 'hardlink-identical-outputs', bound)


if __name__ == '__main__':
    unittest.main()
