"""GDB-only, bounded storage observations on the retained Linux x86-64 library.

Invoke with gdb -batch -x this-file --args node ... . Set
DOE_STORAGE_DIAGNOSTIC_OUTPUT to a new TSV filename. Breakpoint timing is
perturbed and must never be used as performance evidence.
"""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any

import gdb

POLICY = json.loads(Path('config/compute-program-tail-experiment.json').read_text(encoding='utf-8'))
MAX_EVENTS = POLICY['diagnosticMaxEvents']
OUTPUT = Path(os.environ['DOE_STORAGE_DIAGNOSTIC_OUTPUT'])
ROWS: list[dict[str, Any]] = []
ACTIVE: dict[int, dict[str, Any]] = {}
ALLOCATORS: set[int] = set()
FAILURES: list[str] = []
PROBES_INSTALLED = False


def record_failure(error: object) -> None:
    if not FAILURES:
        FAILURES.append(str(error))


def thread_id() -> int:
    return gdb.selected_thread().global_num


def encoder_type() -> Any:
    return gdb.parse_and_eval("'native.command.doe_command_recording.reserve'").type.fields()[0].type


def row(event: str, encoder: int = 0) -> dict[str, Any]:
    return {'event': event, 'encoder': encoder, 'reuseReason': '',
            'commandRequestedCapacity': 0, 'commandCapacityBefore': 0, 'commandCapacityAfter': 0,
            'referenceRequestedCapacity': 0, 'referenceCapacityBefore': 0, 'referenceCapacityAfter': 0,
            'allocationCalls': 0, 'allocationSuccesses': 0, 'resizeCalls': 0, 'resizeSuccesses': 0,
            'remapCalls': 0, 'remapSuccesses': 0, 'contendedLockCalls': 0, 'debuggerLockWaitNs': 0}


def retain(value: dict[str, Any]) -> None:
    if len(ROWS) >= MAX_EVENTS:
        raise RuntimeError('Native diagnostic record bound exceeded')
    ROWS.append(value)


class Returned(gdb.FinishBreakpoint):
    def __init__(self, action: Any) -> None:
        super().__init__(gdb.newest_frame(), internal=True)
        self.action = action

    def stop(self) -> bool:
        try:
            self.action(self.return_value)
        except (gdb.error, RuntimeError, KeyError, TypeError) as error:
            record_failure(error)
        return False


class AllocatorCall(gdb.Breakpoint):
    def __init__(self, address: int, action: str) -> None:
        super().__init__(f'*{address}', internal=True)
        self.action = action

    def stop(self) -> bool:
        current = ACTIVE.get(thread_id())
        if current is not None:
            current[f'{self.action}Calls'] += 1

            def returned(value: Any) -> None:
                if int(value):
                    current[f'{self.action}Successes'] += 1

            Returned(returned)
        return False


def observe_allocator(allocator: Any) -> None:
    for name, action in [('alloc', 'allocation'), ('resize', 'resize'), ('remap', 'remap')]:
        address = int(allocator['vtable'].dereference()[name])
        if address not in ALLOCATORS:
            ALLOCATORS.add(address)
            AllocatorCall(address, action)


class Reserve(gdb.Breakpoint):
    def stop(self) -> bool:
        try:
            pointer_type = encoder_type()
            field = next(field for field in pointer_type.target().fields() if field.name == self.collection)
            pointer = (gdb.parse_and_eval('$rdi').cast(gdb.lookup_type('unsigned long')) - field.bitpos // 8).cast(pointer_type)
            encoder = pointer.dereference()
            value = row(f'reserve-{self.collection}', int(pointer))
            request = int(gdb.parse_and_eval('$rdx'))
            value['commandRequestedCapacity'] = int(encoder['cmds']['items']['len']) + (request if self.collection == 'cmds' else 0)
            value['referenceRequestedCapacity'] = int(encoder['references']['items']['len']) + (request if self.collection == 'references' else 0)
            value['commandCapacityBefore'] = int(encoder['cmds']['capacity'])
            value['referenceCapacityBefore'] = int(encoder['references']['capacity'])
            observe_allocator(encoder['allocator'])
            thread = thread_id()
            ACTIVE[thread] = value

            def returned(_: Any) -> None:
                after = pointer.dereference()
                value['commandCapacityAfter'] = int(after['cmds']['capacity'])
                value['referenceCapacityAfter'] = int(after['references']['capacity'])
                ACTIVE.pop(thread, None)
                retain(value)

            Returned(returned)
        except (gdb.error, RuntimeError, KeyError, TypeError) as error:
            record_failure(error)
        return False


class CreateEncoder(gdb.Breakpoint):
    def stop(self) -> bool:
        global PROBES_INSTALLED
        try:
            if not PROBES_INSTALLED:
                for collection, element in [('cmds', 'native.support.doe_native_command_types.RecordedCmd'),
                                            ('references', 'contracts.resource_lease.ResourceLease')]:
                    symbol = f'array_list.Aligned({element},null).ensureUnusedCapacity'
                    address = int(gdb.parse_and_eval(f"'{symbol}'").address)
                    probe = Reserve(f'*{address}', internal=True)
                    probe.collection = collection
                address = int(gdb.parse_and_eval("'Thread.Mutex.FutexImpl.lockSlow'").address)
                ContendedLock(f'*{address}', internal=True)
                PROBES_INSTALLED = True
            pointer_type = encoder_type()
            device_type = next(field.type for field in pointer_type.target().fields() if field.name == 'dev')
            device = gdb.parse_and_eval('$rdi').cast(device_type).dereference()
            optional = device['command_storage']
            value = row('take')
            if int(optional['some']):
                pool = optional['data']
                value['commandCapacityBefore'] = int(pool['available']['capacity'])
                if 'available_references' in {field.name for field in pool.type.fields()}:
                    value['referenceCapacityBefore'] = int(pool['available_references']['capacity'])
                value['reuseReason'] = 'disabled' if int(pool['max_retained_bytes']) == 0 else (
                    'empty' if value['commandCapacityBefore'] == 0 else 'available')
            else:
                value['reuseReason'] = 'no-pool'
            thread = thread_id()
            ACTIVE[thread] = value

            def returned(result: Any) -> None:
                value['encoder'] = int(result)
                if int(result):
                    encoder = result.cast(pointer_type).dereference()
                    value['commandCapacityAfter'] = int(encoder['cmds']['capacity'])
                    value['referenceCapacityAfter'] = int(encoder['references']['capacity'])
                    if int(optional['some']):
                        expected, actual = optional['data']['allocator'], encoder['allocator']
                        if int(expected['ptr']) != int(actual['ptr']) or int(expected['vtable']) != int(actual['vtable']):
                            value['reuseReason'] = 'allocator-mismatch'
                ACTIVE.pop(thread, None)
                retain(value)

            Returned(returned)
        except (gdb.error, RuntimeError, KeyError, TypeError) as error:
            record_failure(error)
        return False


class ContendedLock(gdb.Breakpoint):
    def stop(self) -> bool:
        current = ACTIVE.get(thread_id())
        if current is not None:
            current['contendedLockCalls'] += 1
            start = time.monotonic_ns()

            def returned(_: Any) -> None:
                current['debuggerLockWaitNs'] += time.monotonic_ns() - start

            Returned(returned)
        return False


gdb.execute('set pagination off')
gdb.execute('set breakpoint pending on')
gdb.execute('set print thread-events off')
CreateEncoder('wgpuDeviceCreateCommandEncoder', internal=True)
gdb.execute('run')
if not ROWS:
    record_failure('No native storage observations captured')
if ROWS:
    with OUTPUT.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ROWS[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(ROWS)
OUTPUT.with_suffix('.limits.txt').write_text(
    'schemaVersion=1\nScope: retained Linux x86-64 native encoder creation and out-of-line command/reference ensureUnusedCapacity calls. '
    'Inlined array growth sites are not observed. Allocation calls are actual allocator-vtable calls within observed scopes; '
    'capacity changes are checked after the operation. Lock slow-path time includes debugger perturbation and is not a performance metric. '
    'Zero contended calls applies only to this observed execution. Records are written after process exit.\n'
    + '\n'.join(FAILURES) + '\n', encoding='utf-8')
if FAILURES:
    raise RuntimeError(f'Native storage diagnostic incomplete: {FAILURES[:5]}')
