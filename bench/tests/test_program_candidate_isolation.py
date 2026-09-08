"""Exercise the real Linux boundary with adversarial host operations."""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from bench.lib.program_candidate_isolation import build_command, execute, load_policy

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'config/program-candidate-isolation.json'
TEST_TIMEOUT_MS = 10000
STOP_TIMEOUT_MS = 2000
MEMORY_PROBE_BYTES = 100663296


class CandidateIsolationPolicyTests(unittest.TestCase):
    def test_no_unrestricted_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            data = json.loads(POLICY.read_text(encoding='utf-8'))
            data['mode'] = 'unrestricted'
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(jsonschema.ValidationError):
                load_policy(path, ROOT)

    def test_missing_tool_is_explicitly_unsupported(self) -> None:
        policy = json.loads(POLICY.read_text(encoding='utf-8'))
        with patch('bench.lib.program_candidate_isolation.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'no unisolated fallback'):
                build_command(policy, ['/usr/bin/true'], ROOT, [], [])

    def test_historical_reports_do_not_gain_isolation(self) -> None:
        schema = json.loads((ROOT / 'config/program-candidate-report.schema.json').read_text())
        validator = jsonschema.Draft202012Validator(schema)
        report = {'schemaVersion': 1, 'kind': 'program_candidate_acceptance',
                  'claimStatus': 'diagnostic', 'status': 'rejected', 'error': 'example',
                  'jobHash': '0' * 64, 'candidateHash': '0' * 64,
                  'environmentHash': None, 'previous': None, 'environmentChanged': None,
                  'requalification': 'fresh-execution-required', 'artifacts': []}
        validator.validate(report)
        report['isolation'] = None
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(report)
        report['schemaVersion'] = 2
        validator.validate(report)
        del report['isolation']
        with self.assertRaises(jsonschema.ValidationError):
            validator.validate(report)


@unittest.skipUnless(sys.platform == 'linux', 'Physical Linux isolation required')
class CandidateIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if any(shutil.which(name) is None for name in ('bwrap', 'systemd-run', 'systemctl', 'node')):
            raise unittest.SkipTest('Linux isolation tools unavailable')
        probe = subprocess.run(['systemctl', '--user', 'show-environment'],
                               capture_output=True, timeout=STOP_TIMEOUT_MS / 1000)
        if probe.returncode:
            raise unittest.SkipTest('User service manager unavailable')

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / 'output'
        self.output.mkdir()
        self.policy = load_policy(POLICY, ROOT)

    def run_node(self, code: str, *, timeout_ms: int = TEST_TIMEOUT_MS,
                 writable: list[Path] | None = None) -> int:
        node = Path(shutil.which('node')).resolve()
        return execute(self.policy, [str(node), '-e', code], self.output,
                       [node], writable or [], ROOT, timeout_ms, STOP_TIMEOUT_MS)[0]

    def test_private_files_network_environment_and_frozen_inputs_are_inaccessible(self) -> None:
        outside = self.root / 'private.txt'
        outside.write_text('benign sentinel', encoding='utf-8')
        frozen = self.output / 'oracle.json'
        frozen.write_text('original', encoding='utf-8')
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen()
            code = '''
const fs = require('fs'), net = require('net');
const assert = require('assert/strict');
assert.throws(() => fs.readFileSync(PRIVATE_PATH_TOKEN));
assert.throws(() => fs.writeFileSync(FROZEN, 'forged'));
assert.throws(() => fs.unlinkSync(FROZEN));
assert.equal(process.env.DOE_TEST_PRIVATE, undefined);
assert.equal(fs.existsSync('/run/user'), false);
const socket = net.connect(PORT, '127.0.0.1');
socket.on('connect', () => { socket.destroy(); process.exitCode = 1; });
socket.on('error', () => console.log('denied file, mutation, environment, host network'));
'''.replace('PRIVATE_PATH_TOKEN', json.dumps(str(outside))).replace('FROZEN', json.dumps(str(frozen)))
            code = code.replace('PORT', str(server.getsockname()[1]))
            with patch.dict('os.environ', {'DOE_TEST_PRIVATE': 'benign-secret'}):
                self.assertEqual(self.run_node(code), 0)
        self.assertEqual(frozen.read_text(encoding='utf-8'), 'original')
        self.assertIn('denied file', (self.output / 'controller.stdout').read_text())

    def test_memory_limit_kills_the_job(self) -> None:
        self.policy['maximumHostMemoryBytes'] = MEMORY_PROBE_BYTES
        self.assertNotEqual(self.run_node('''
const retained = [];
for (;;) retained.push(Buffer.alloc(16 * 1024 * 1024, 1));
'''), 0)
        admission = json.loads((self.output / 'isolation-admission.json').read_text())
        self.assertEqual(admission['memory.max'], str(MEMORY_PROBE_BYTES))

    def test_deadline_removes_detached_descendants(self) -> None:
        result = self.output / 'descendant.txt'
        result.touch()
        code = '''
const { spawn } = require('child_process');
const child = spawn(process.execPath, ['-e', CHILD], {detached: true, stdio: 'ignore'});
child.unref();
setInterval(() => {}, 1000);
'''.replace('CHILD', json.dumps("require('fs').writeFileSync(" + json.dumps(str(result))
            + ", require('fs').readFileSync('/proc/self/status')); setInterval(() => {}, 1000);"))
        self.assertNotEqual(self.run_node(code, timeout_ms=500, writable=[result]), 0)
        self.assertIn('Name:', result.read_text())
        record = json.loads((self.output / 'isolation.json').read_text())
        state = subprocess.run(['systemctl', '--user', 'is-active', record['unit']],
                               capture_output=True, text=True, timeout=STOP_TIMEOUT_MS / 1000)
        self.assertNotEqual(state.returncode, 0)
        self.assertTrue(record['cleanupConfirmed'])


if __name__ == '__main__':
    unittest.main()
