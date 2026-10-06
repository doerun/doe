"""Physical recovery, failed initialization and unchanged MatMul/Add regression."""
from __future__ import annotations
import argparse
import ctypes
import gc
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import onnx
import onnxruntime as ort

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'onnx-webgpu-substitution'))
from run_adapter import ContextIdentity, drm_clients, model


def identity(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['native', 'bridge', 'context', 'recovery', 'provider', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arm', choices=['doe', 'dawn'], required=True)
    args = parser.parse_args()
    if args.out.exists(): parser.error('Output must be new')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = {'schemaVersion': 1, 'arm': args.arm, 'passed': False, 'failure': None,
              'libraries': {n: identity(getattr(args, n)) for n in ['native', 'bridge', 'context', 'recovery', 'provider']},
              'initialDrmClients': drm_clients(), 'finalDrmClients': None,
              'initializationRecovery': None, 'descriptorRecovery': None,
              'failedSessionRecovery': None, 'preexecutionCancellationReuse': None,
              'runs': [], 'operatorNames': [], 'operatorProviders': [], 'callCounts': {}}
    instance, device = ctypes.c_void_p(), ctypes.c_void_p()
    context = ctypes.CDLL(str(args.context.resolve()))
    context.doeExternalContextCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
         ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ContextIdentity)]
    context.doeExternalContextRelease.argtypes = [ctypes.c_void_p] * 3
    registered = False
    session = None
    table = None
    try:
        native = ctypes.CDLL(str(args.native.resolve()))
        if args.arm == 'doe':
            bridge = ctypes.CDLL(str(args.bridge.resolve()))
            bridge.doeDawnBridgeInitialize.argtypes = [ctypes.c_char_p]
            bridge.doeDawnBridgeInitialize.restype = ctypes.c_void_p
            bridge.doeDawnBridgeTakeError.restype = ctypes.c_char_p
            if bridge.doeDawnBridgeInitialize(b'/missing/doe-library.so'):
                raise ValueError('Missing library was admitted')
            missing = bridge.doeDawnBridgeTakeError().decode()
            if bridge.doeDawnBridgeInitialize(b'libc.so.6'):
                raise ValueError('Incomplete library was admitted')
            incomplete = bridge.doeDawnBridgeTakeError().decode()
            table = bridge.doeDawnBridgeInitialize(str(args.native.resolve()).encode())
            if not table: raise ValueError('Valid library failed after initialization errors')
            if bridge.doeDawnBridgeInitialize(str(args.native.resolve()).encode()):
                raise ValueError('Live rebinding was admitted')
            rebind = bridge.doeDawnBridgeTakeError().decode()
            result['initializationRecovery'] = {'missing': missing, 'incomplete': incomplete,
                'rebind': rebind, 'reused': True}
        else:
            bridge = ctypes.CDLL(str(args.bridge.resolve()))
            bridge.doeDawnBridgeInitializeControl.argtypes = [ctypes.c_char_p]
            bridge.doeDawnBridgeInitializeControl.restype = ctypes.c_void_p
            table = bridge.doeDawnBridgeInitializeControl(str(args.native.resolve()).encode())
        physical = ContextIdentity()
        status = context.doeExternalContextCreate(table, ctypes.byref(instance), ctypes.byref(device), ctypes.byref(physical))
        if status: raise ValueError(f'Physical context failure: {status}')
        result['contextIdentity'] = {k: getattr(physical, k) for k, _ in physical._fields_}
        if args.arm == 'doe':
            control = ctypes.CDLL(str(args.recovery.resolve()))
            control.doeRecoverableControl.argtypes = [ctypes.c_void_p] * 4
            status = control.doeRecoverableControl(table, instance, device,
                        ctypes.cast(bridge.doeDawnBridgeTakeError, ctypes.c_void_p))
            result['descriptorRecovery'] = {'status': status, 'reused': status == 0}
            if status: raise ValueError(f'Recoverable control failed: {status}')
        ort.register_execution_provider_library('campaign', str(args.provider.resolve()))
        registered = True
        devices = [d for d in ort.get_ep_devices() if d.ep_name == 'WebGpuExecutionProvider' and d.device.vendor_id == 0x1002]
        if len(devices) != 1: raise ValueError('AMD provider inventory mismatch')
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
        options.add_provider_for_devices(devices, {'dawnBackendType': 'Vulkan', 'validationMode': 'full',
             'dawnProcTable': str(table), 'deviceId': '0', 'webgpuInstance': str(instance.value), 'webgpuDevice': str(device.value)})
        invalid = onnx.helper.make_model(onnx.helper.make_graph([
            onnx.helper.make_node('NonZero', ['x'], ['indices'])], 'unsupported_initialization',
            [onnx.helper.make_tensor_value_info('x', onnx.TensorProto.FLOAT, [4])],
            [onnx.helper.make_tensor_value_info('indices', onnx.TensorProto.INT64, [1, None])]),
            opset_imports=[onnx.helper.make_opsetid('', 21)], ir_version=10)
        try:
            failed = ort.InferenceSession(invalid.SerializeToString(), options, enable_fallback=False)
        except Exception as error:
            result['failedSessionRecovery'] = {'message': str(error), 'reused': False}
        else:
            failed = None
            raise ValueError('Unsupported initializer did not fail; revise the negative control')
        options.enable_profiling = True
        options.profile_file_prefix = str(args.out.with_suffix(''))
        graph = args.out.with_suffix('.onnx')
        model(graph)
        session = ort.InferenceSession(str(graph), options, enable_fallback=False)
        cancel = ort.RunOptions(); cancel.terminate = True
        try:
            session.run(None, {n: np.zeros((4, 4), np.float32) for n in ['a', 'b', 'bias']}, cancel)
        except Exception as error:
            if 'terminate' not in str(error).lower(): raise
            result['preexecutionCancellationReuse'] = {'phase': 'before-execution', 'reused': False, 'message': str(error)}
        else: raise ValueError('Pre-execution cancellation executed work')
        for index in range(3):
            a = np.arange(16, dtype=np.float32).reshape(4, 4) + index
            b = np.arange(16, dtype=np.float32).reshape(4, 4).T.copy() - index
            bias = np.full((4, 4), index + 1, np.float32)
            expected = a @ b + bias
            observed = session.run(None, {'a': a, 'b': b, 'bias': bias})[0]
            np.testing.assert_array_equal(observed, expected)
            result['runs'].append({'expected': expected.tolist(), 'observed': observed.tolist()})
        profile = Path(session.end_profiling())
        result['profile'] = identity(profile)
        nodes = [e['args'] for e in json.loads(profile.read_text()) if e.get('cat') == 'Node' and 'provider' in e.get('args', {})]
        result['operatorNames'] = [e['op_name'] for e in nodes]
        result['operatorProviders'] = [e['provider'] for e in nodes]
        if result['operatorNames'] != ['MatMul', 'Add'] * 3 or set(result['operatorProviders']) != {'WebGpuExecutionProvider'}:
            raise ValueError('Operator placement failed')
        result['failedSessionRecovery']['reused'] = True
        result['preexecutionCancellationReuse']['reused'] = True
        bridge.doeDawnBridgeCallCount.argtypes = [ctypes.c_size_t]
        bridge.doeDawnBridgeCallCount.restype = ctypes.c_uint64
        names = json.loads((args.bridge.parent / 'build.json').read_text())['procNames']
        result['callCounts'] = {name: bridge.doeDawnBridgeCallCount(i) for i, name in enumerate(names)}
        if not result['callCounts']['queueSubmit']: raise ValueError('No native submission')
        result['passed'] = True
    except Exception as error:
        result['failure'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        session = None; gc.collect()
        if registered: ort.unregister_execution_provider_library('campaign')
        if table: context.doeExternalContextRelease(table, instance, device)
        result['finalDrmClients'] = drm_clients()
        if result['finalDrmClients'] != result['initialDrmClients']:
            result['passed'] = False
            result['failure'] = {'type': 'ResourceLeak', 'message': 'DRM clients survived cleanup'}
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
