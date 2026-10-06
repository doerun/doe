"""Exercise the existing ONNX WebGPU provider through an explicit Doe proc table."""
from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnxruntime.capi.onnxruntime_pybind11_state import Fail


class ContextIdentity(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        'backend', 'vendor', 'device', 'adapterType')]


def identity(path: Path) -> dict[str, str]:
    return {'path': str(path.resolve()),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def drm_clients() -> list[str]:
    clients = []
    for path in Path('/proc/self/fdinfo').iterdir():
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except FileNotFoundError:
            continue
        clients.extend(line for line in lines if line.startswith('drm-client-id:'))
    return sorted(clients)


def model(path: Path) -> None:
    graph = onnx.helper.make_graph([
        onnx.helper.make_node('MatMul', ['a', 'b'], ['product']),
        onnx.helper.make_node('Add', ['product', 'bias'], ['output']),
    ], 'unchanged_dense_operations', [
        onnx.helper.make_tensor_value_info(name, onnx.TensorProto.FLOAT, [4, 4])
        for name in ['a', 'b', 'bias']
    ], [onnx.helper.make_tensor_value_info('output', onnx.TensorProto.FLOAT, [4, 4])])
    value = onnx.helper.make_model(graph, producer_name='doe-framework-seam-check',
                                   opset_imports=[onnx.helper.make_opsetid('', 21)],
                                   ir_version=10)
    onnx.checker.check_model(value)
    onnx.save(value, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', type=Path, required=True,
                        help='Exact source-built external-Dawn WebGPU provider')
    parser.add_argument('--bridge-build', type=Path, required=True,
                        help='Adapter build directory with build.json')
    parser.add_argument('--doe-library', type=Path, required=True,
                        help='Exact independently qualified Doe native library')
    parser.add_argument('--context', choices=['automatic', 'external'], required=True,
                        help='Provider-created device or explicit standard WebGPU context')
    parser.add_argument('--context-id', type=int, choices=[0, 1], default=1,
                        help='External context identity; preserve the upstream default control')
    parser.add_argument('--incumbent', action='store_true',
                        help='Published Dawn control; no external proc table')
    parser.add_argument('--future-control', action='store_true',
                        help='Only exercise blocked asynchronous pipeline delivery')
    parser.add_argument('--out', type=Path, required=True,
                        help='New immutable result path')
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f'Refusing to replace result: {args.out}')
    if ort.__version__ != '1.24.4':
        raise ValueError('This consumer pins ONNX Runtime 1.24.4')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    build = json.loads((args.bridge_build / 'build.json').read_text(encoding='utf-8'))
    bridge_path = args.bridge_build / 'libdoe_dawn_bridge.so'
    if identity(bridge_path)['sha256'] != build['library']['sha256']:
        raise ValueError('Bridge bytes differ from the qualified ABI build')
    bridge = ctypes.CDLL(str(bridge_path.resolve()))
    bridge.doeDawnBridgeInitialize.argtypes = [ctypes.c_char_p]
    bridge.doeDawnBridgeInitialize.restype = ctypes.c_void_p
    bridge.doeDawnBridgeCallCount.argtypes = [ctypes.c_size_t]
    bridge.doeDawnBridgeCallCount.restype = ctypes.c_uint64
    table = bridge.doeDawnBridgeInitialize(str(args.doe_library.resolve()).encode())
    if not table:
        raise RuntimeError('Bridge rejected the selected native library')
    instance = ctypes.c_void_p()
    device = ctypes.c_void_p()
    context_path = args.bridge_build / 'libexternal_context.so'
    if identity(context_path)['sha256'] != build['contextLibrary']['sha256']:
        raise ValueError('Context fixture differs from the qualified ABI build')
    context_identity = ContextIdentity()
    context = ctypes.CDLL(str((args.bridge_build / 'libexternal_context.so').resolve()))
    context.doeExternalContextCreate.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ContextIdentity)]
    context.doeExternalContextRelease.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                                 ctypes.c_void_p]
    result = {'schemaVersion': 1, 'classification': ('pipeline-future-control' if args.future_control
                                else ('published-dawn-control' if args.incumbent
                                      else 'framework-adapter-diagnostic')),
              'passed': False, 'failure': None, 'context': args.context,
              'contextId': args.context_id, 'doeExecutionEstablished': False,
              'executionOptions': {'graphOptimization': 'disabled',
                                   'cpuFallback': 'disabled',
                                   'backend': 'Vulkan', 'validation': 'full'},
              'runner': identity(Path(__file__)), 'provider': identity(args.provider),
              'doeLibrary': identity(args.doe_library),
              'bridgeBuild': identity(args.bridge_build / 'build.json'),
              'packages': {name: importlib.metadata.version(name) for name in (
                  'onnxruntime', 'onnx', 'numpy')}, 'runs': [], 'callCounts': {},
              'contextIdentity': None, 'cancellation': None, 'futureControl': None,
              'initialDrmClients': drm_clients(), 'finalDrmClients': None}
    session = None
    registered = False
    try:
        if args.context == 'external':
            status = context.doeExternalContextCreate(table, ctypes.byref(instance),
                                                       ctypes.byref(device), ctypes.byref(context_identity))
            if status != 0:
                raise RuntimeError(f'External Vulkan context creation failed: {status}')
        result['contextIdentity'] = {name: getattr(context_identity, name)
                                     for name, _ in ContextIdentity._fields_}
        if args.future_control:
            if args.context != 'external':
                raise ValueError('Future control requires an external device')
            context.doeExternalFutureControl.argtypes = [ctypes.c_void_p] * 3
            status = context.doeExternalFutureControl(table, instance, device)
            result['futureControl'] = {'status': status, 'passed': status == 0}
            result['passed'] = status == 0
            if status != 0:
                result['failure'] = {'type': 'PrematureCompletion',
                                      'message': 'WaitAny retired a blocked callback'}
            return 0 if result['passed'] else 1
        ort.register_execution_provider_library('doe_abi', str(args.provider.resolve()))
        registered = True
        devices = [item for item in ort.get_ep_devices()
                   if item.ep_name == 'WebGpuExecutionProvider'
                   and item.device.vendor_id == 0x1002]
        if len(devices) != 1:
            raise RuntimeError('Expected exactly one physical AMD execution device')
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.enable_profiling = True
        options.profile_file_prefix = str(args.out.with_suffix(''))
        options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
        settings = {'dawnBackendType': 'Vulkan', 'validationMode': 'full'}
        if args.incumbent:
            if args.context != 'automatic' or args.future_control:
                raise ValueError('Incumbent control requires automatic context')
        else:
            settings['dawnProcTable'] = str(table)
        if args.context == 'external':
            settings.update({'deviceId': str(args.context_id),
                             'webgpuInstance': str(instance.value),
                             'webgpuDevice': str(device.value)})
        options.add_provider_for_devices(devices, settings)
        model_path = args.out.with_suffix('.onnx')
        model(model_path)
        result['model'] = identity(model_path)
        session = ort.InferenceSession(str(model_path), options, enable_fallback=False)
        cancellation = ort.RunOptions()
        cancellation.terminate = True
        try:
            session.run(None, {name: np.zeros((4, 4), dtype=np.float32)
                               for name in ('a', 'b', 'bias')}, cancellation)
        except Fail as error:
            if 'terminate' not in str(error).lower():
                raise
            result['cancellation'] = {'phase': 'before-execution',
                                      'message': str(error), 'reused': False}
        else:
            raise RuntimeError('Terminated invocation unexpectedly executed')
        for index in range(3):
            a = np.arange(16, dtype=np.float32).reshape(4, 4) + index
            b = np.arange(16, dtype=np.float32).reshape(4, 4).T.copy() - index
            bias = np.full((4, 4), index + 1, dtype=np.float32)
            expected = a @ b + bias
            observed = session.run(None, {'a': a, 'b': b, 'bias': bias})[0]
            np.testing.assert_array_equal(observed, expected)
            result['runs'].append({'expected': expected.tolist(),
                                   'observed': observed.tolist()})
        result['cancellation']['reused'] = True
        profile_path = Path(session.end_profiling())
        result['profile'] = identity(profile_path)
        nodes = [event for event in json.loads(profile_path.read_text(encoding='utf-8'))
                 if event.get('cat') == 'Node' and 'provider' in event.get('args', {})]
        result['operatorProviders'] = [event['args']['provider'] for event in nodes]
        result['operatorNames'] = [event['args']['op_name'] for event in nodes]
        if result['operatorNames'] != ['MatMul', 'Add'] * 3 or any(
                name != 'WebGpuExecutionProvider' for name in result['operatorProviders']):
            raise RuntimeError('Original operators did not all execute on WebGPU')
        result['passed'] = True
    except Exception as error:
        result['failure'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        session = None
        gc.collect()
        if registered:
            ort.unregister_execution_provider_library('doe_abi')
        context.doeExternalContextRelease(table, instance, device)
        result['finalDrmClients'] = drm_clients()
        result['callCounts'] = {name: bridge.doeDawnBridgeCallCount(index)
                               for index, name in enumerate(build['procNames'])}
        result['doeExecutionEstablished'] = result['passed'] and all(
            result['callCounts'][name] > 0 for name in (
                'deviceCreateShaderModule', 'computePassEncoderDispatchWorkgroups',
                'queueSubmit', 'bufferMapAsync'))
        if result['passed'] and not args.future_control and not args.incumbent and not result['doeExecutionEstablished']:
            result['passed'] = False
            result['failure'] = {'type': 'RuntimeError',
                                  'message': 'Missing observed native execution calls'}
        if args.incumbent and any(result['callCounts'].values()):
            raise RuntimeError('Incumbent control unexpectedly called Doe')
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n',
                            encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'failure': result['failure'],
                      'doeExecutionEstablished': result['doeExecutionEstablished']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
