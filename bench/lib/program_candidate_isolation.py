"""Linux candidate execution with explicit mounts and a bounded cgroup."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import jsonschema

from bench.lib.hash_utils import file_sha256
from bench.lib.program_candidate import write_json


def load_policy(path: Path, repository: Path) -> dict[str, Any]:
    """Reject unsupported isolation policies before loading candidate code."""
    policy = json.loads(path.read_text(encoding='utf-8'))
    schema = json.loads((repository / 'config/program-candidate-isolation.schema.json')
                        .read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(policy)
    if sys.platform != 'linux':
        raise ValueError('Candidate isolation requires Linux user namespaces and cgroup v2')
    return policy


def build_command(policy: dict[str, Any], command: list[str],
                  output: Path, readonly: list[Path], writable: list[Path],
                  render_node: Path | None = None) -> tuple[list[str], dict[str, str]]:
    """Expose only system dependencies, frozen inputs, and declared outputs."""
    tools = {}
    for name in ('bwrap', 'systemd-run', 'systemctl'):
        tool = shutil.which(name)
        if tool is None:
            raise ValueError(f'Candidate isolation requires {name}; no unisolated fallback')
        tools[name] = str(Path(tool).resolve())
    for directory in ('/usr', '/lib', '/lib64'):
        if not Path(directory).is_dir():
            raise ValueError(f'Candidate isolation requires system library path {directory}')
    wrapped = [tools['bwrap'], '--unshare-all', '--unshare-user', '--disable-userns',
               '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
               '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin',
               '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'HOME', '/tmp/home',
               '--setenv', 'TMPDIR', '/tmp', '--proc', '/proc', '--dev', '/dev',
               '--size', str(policy['maximumTemporaryBytes']), '--tmpfs', '/tmp',
               '--dir', '/tmp/home']
    for path in ['/usr', '/lib', '/lib64', '/sys', '/etc/ld.so.cache',
                 '/etc/vulkan', '/etc/drirc']:
        if Path(path).exists():
            wrapped.extend(['--ro-bind', path, path])
    wrapped.extend(['--ro-bind', str(output), str(output)])
    for path in readonly:
        wrapped.extend(['--ro-bind', str(path), str(path)])
    for path in writable:
        if not path.resolve().is_relative_to(output.resolve()):
            raise ValueError(f'Writable candidate path escapes output: {path}')
        wrapped.extend(['--bind', str(path), str(path)])
    if render_node is not None:
        render_node = render_node.resolve()
        if (render_node.parent != Path('/dev/dri')
                or not render_node.name.startswith('renderD')
                or not render_node.is_char_device()):
            raise ValueError('Candidate GPU access requires one /dev/dri/renderD* character device')
        wrapped.extend(['--dev-bind', str(render_node), str(render_node)])
    wrapped.extend(['--chdir', str(output), '--', *command])
    return wrapped, tools


def execute(policy: dict[str, Any], command: list[str], output: Path,
            readonly: list[Path], writable: list[Path], repository: Path,
            timeout_ms: int, stop_timeout_ms: int,
            render_node: Path | None = None) -> tuple[int, dict[str, Any]]:
    """Run one owned service; admission verifies effective kernel limits."""
    wrapped, tools = build_command(policy, command, output, readonly, writable, render_node)
    policy_path = output / 'isolation-policy.json'
    write_json(policy_path, policy)
    bootstrap = output / 'isolation-bootstrap.py'
    bootstrap.write_bytes(
        (repository / 'bench/runners/program-candidate-isolation.py').read_bytes())
    unit = f'doe-candidate-{uuid.uuid4().hex}.service'
    properties = {
        'MemoryMax': str(policy['maximumHostMemoryBytes']), 'MemorySwapMax': '0',
        'TasksMax': str(policy['maximumTasks']), 'OOMPolicy': 'kill',
        'KillMode': 'control-group', 'SendSIGKILL': 'yes', 'LimitCORE': '0',
        'LimitFSIZE': str(policy['maximumFileBytes']),
        'RuntimeMaxSec': f'{timeout_ms}ms', 'TimeoutStopSec': f'{stop_timeout_ms}ms',
    }
    launched = [tools['systemd-run'], '--user', '--quiet', '--wait', '--pipe',
                '--expand-environment=no',
                '--service-type=exec', f'--unit={unit}']
    for key, value in properties.items():
        launched.append(f'--property={key}={value}')
    launched.extend([sys.executable, str(bootstrap), str(policy_path),
                     str(output / 'isolation-admission.json'), *wrapped])
    record = {'schemaVersion': 1, 'policyHash': file_sha256(policy_path),
              'tools': {name: {'path': path, 'hash': file_sha256(Path(path))}
                        for name, path in tools.items()},
              'unit': unit, 'command': launched, 'returnCode': None,
              'effectiveLimits': None, 'cleanupConfirmed': False}
    write_json(output / 'isolation.json', record)
    environment = {key: value for key, value in os.environ.items()
                   if key in ('PATH', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'LANG')}
    process = None
    try:
        with (output / 'controller.stdout').open('w', encoding='utf-8') as stdout, (
                output / 'controller.stderr').open('w', encoding='utf-8') as stderr:
            process = subprocess.Popen(launched, cwd=output, env=environment,
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            try:
                process.wait(timeout=(timeout_ms + stop_timeout_ms) / 1000)
            except subprocess.TimeoutExpired as error:
                raise ValueError('Candidate isolation exceeded the outer deadline') from error
        record['returnCode'] = process.returncode
        admission_path = output / 'isolation-admission.json'
        if not admission_path.is_file():
            raise ValueError('Candidate isolation admission failed; inspect controller.stderr')
        admission = json.loads(admission_path.read_text(encoding='utf-8'))
        expected = {'memory.max': str(policy['maximumHostMemoryBytes']),
                    'memory.swap.max': '0', 'pids.max': str(policy['maximumTasks'])}
        if admission != expected:
            raise ValueError('Candidate kernel limits differ from the declared isolation policy')
        record['effectiveLimits'] = admission
        return process.returncode, record
    finally:
        # The service owns detached grandchildren as well as the Node controller.
        cleanup_errors = []
        for operation in (['kill', '--signal=KILL'], ['stop'], ['reset-failed']):
            try:
                subprocess.run([tools['systemctl'], '--user', *operation, unit],
                               env=environment, capture_output=True,
                               timeout=stop_timeout_ms / 1000)
            except (OSError, subprocess.TimeoutExpired) as error:
                cleanup_errors.append(str(error))
        try:
            state = subprocess.run([tools['systemctl'], '--user', 'is-active', unit],
                                   env=environment, capture_output=True, text=True,
                                   timeout=stop_timeout_ms / 1000)
            record['cleanupConfirmed'] = (state.returncode in (3, 4)
                                          and state.stdout.strip() in ('inactive', 'failed', 'unknown'))
            if not record['cleanupConfirmed']:
                cleanup_errors.append(
                    f'Cannot confirm service stopped: {state.stdout} {state.stderr}')
        except (OSError, subprocess.TimeoutExpired) as error:
            cleanup_errors.append(str(error))
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait()
            record['returnCode'] = process.returncode
        write_json(output / 'isolation.json', record)
        if cleanup_errors:
            raise ValueError(f'Candidate service cleanup failed: {cleanup_errors}')
