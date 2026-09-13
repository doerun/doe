"""Evidence retention must preserve bytes, paths, and failed writes."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bench.lib.compute_program_retention import deduplicate_outputs
from bench.runners.run_compute_program_calibration import write_json


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
            with patch('bench.runners.run_compute_program_calibration.os.fsync', side_effect=OSError('full')):
                with self.assertRaises(OSError):
                    write_json(path, {'status': 'consistent'})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
