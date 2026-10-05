"""Run the existing native ONNX WebGPU EP and inspect a library-preload seam."""
from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import onnxruntime_ep_webgpu as webgpu


def file_identity(path: Path) -> dict[str, str]:
    with path.open('rb') as stream:
        return {'path': str(path.resolve()),
                'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}


def observe_probe(path: Path) -> dict:
    """Observe the explicitly preloaded libraries and exported call counters."""
    probe = ctypes.CDLL(str(path.resolve()))
    counters = {}
    for label, symbol in [('instances', 'doeProbeInstanceCalls'),
                          ('shaders', 'doeProbeShaderCalls'),
                          ('submissions', 'doeProbeSubmissionCalls')]:
        method = getattr(probe, symbol)
        method.restype = ctypes.c_uint64
        counters[label] = method()
    native = Path(os.environ['DOE_WEBGPU_LIB']).resolve()
    maps = Path('/proc/self/maps').read_text(encoding='utf-8')
    observation = {
        'library': file_identity(path), 'counters': counters,
        'doeLibrary': file_identity(native),
        'doeLibraryLoaded': str(native) in maps,
        'probeLibraryLoaded': str(path.resolve()) in maps,
    }
    if not observation['doeLibraryLoaded'] or not observation['probeLibraryLoaded']:
        raise RuntimeError('Both Doe and the counter probe must be explicitly preloaded')
    return observation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True,
                        help='New result JSON, with generated model/profile beside it')
    parser.add_argument('--preload-probe', type=Path,
                        help='Preloaded counter library; observation cannot imply Doe execution')
    parser.add_argument('--verify-probe', action='store_true',
                        help='Positive control: forward instance creation, not ONNX execution')
    parser.add_argument('--invalid-proc-table', action='store_true',
                        help='Test option parsing with an invalid string, never a callable pointer')
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f'Result already exists: {args.out}')
    if args.verify_probe and not args.preload_probe:
        parser.error('--verify-probe requires --preload-probe')
    if args.invalid_proc_table and args.preload_probe:
        parser.error('The option parsing control must run without preloaded libraries')
    assert ort.__version__ == '1.24.1'
    assert importlib.metadata.version('onnxruntime-ep-webgpu') == '0.1.0'
    assert onnx.__version__ == '1.20.1'
    result = {'schemaVersion': 1, 'classification': 'framework-substitution-diagnostic',
              'passed': False, 'failure': None, 'doeExecutionEstablished': False}
    result['packages'] = {name: importlib.metadata.version(name) for name in (
        'onnxruntime', 'onnxruntime-ep-webgpu', 'onnx', 'numpy')}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    model_path = args.out.with_suffix('.onnx')
    result['runner'] = file_identity(Path(__file__))
    library = Path(webgpu.get_library_path())
    result['providerLibrary'] = file_identity(library)
    result['preloadProbe'] = None
    result['executionOptions'] = {'graphOptimization': 'disabled',
                                  'cpuFallback': 'disabled', 'backend': 'Vulkan',
                                  'validation': 'full'}
    result['mode'] = 'probe-positive-control' if args.verify_probe else 'onnx-execution'
    if args.invalid_proc_table:
        result['mode'] = 'proc-table-option-control'
    result['expectedConfigurationRejection'] = None
    registered = False
    session = None
    try:
        if args.preload_probe:
            result['preloadProbe'] = observe_probe(args.preload_probe)
        if args.verify_probe:
            probe = ctypes.CDLL(str(args.preload_probe.resolve()))
            probe.wgpuCreateInstance.argtypes = [ctypes.c_void_p]
            probe.wgpuCreateInstance.restype = ctypes.c_void_p
            instance = probe.wgpuCreateInstance(None)
            if not instance:
                raise RuntimeError('Doe did not return an instance through the probe')
            native = ctypes.CDLL(os.environ['DOE_WEBGPU_LIB'])
            native.wgpuInstanceRelease.argtypes = [ctypes.c_void_p]
            native.wgpuInstanceRelease(instance)
            result['preloadProbe'] = observe_probe(args.preload_probe)
            assert result['preloadProbe']['counters'] == {
                'instances': 1, 'shaders': 0, 'submissions': 0}
            result['passed'] = True
            return 0
        graph = onnx.helper.make_graph([
            onnx.helper.make_node('MatMul', ['a', 'b'], ['product']),
            onnx.helper.make_node('Add', ['product', 'bias'], ['output']),
        ], 'unchanged_dense_operations', [
            onnx.helper.make_tensor_value_info(name, onnx.TensorProto.FLOAT, [4, 4])
            for name in ['a', 'b', 'bias']
        ], [onnx.helper.make_tensor_value_info('output', onnx.TensorProto.FLOAT, [4, 4])])
        model = onnx.helper.make_model(graph, producer_name='doe-framework-seam-check',
                                      opset_imports=[onnx.helper.make_opsetid('', 21)],
                                      ir_version=10)
        onnx.checker.check_model(model)
        onnx.save(model, model_path)
        result['model'] = file_identity(model_path)
        a = np.arange(16, dtype=np.float32).reshape(4, 4)
        b = np.arange(16, dtype=np.float32).reshape(4, 4).T.copy()
        bias = np.ones((4, 4), dtype=np.float32)
        expected = a @ b + bias
        ort.register_execution_provider_library('webgpu_seam', str(library))
        registered = True
        devices = [item for item in ort.get_ep_devices()
                   if item.ep_name == webgpu.get_ep_name()
                   and item.device.vendor_id == 0x1002]
        if len(devices) != 1:
            raise RuntimeError('Expected one physical AMD WebGPU execution device')
        result['device'] = {'provider': devices[0].ep_name,
                            'vendorId': devices[0].device.vendor_id,
                            'metadata': dict(devices[0].ep_metadata)}
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        options.enable_profiling = True
        options.profile_file_prefix = str(args.out.with_suffix(''))
        options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
        provider_options = {
            'dawnBackendType': 'Vulkan', 'validationMode': 'full',
        }
        if args.invalid_proc_table:
            provider_options['dawnProcTable'] = 'not-a-pointer'
        options.add_provider_for_devices(devices, provider_options)
        session = ort.InferenceSession(str(model_path), options, enable_fallback=False)
        if args.invalid_proc_table:
            raise RuntimeError('Provider unexpectedly accepted the invalid proc-table string')
        observed = session.run(None, {'a': a, 'b': b, 'bias': bias})[0]
        np.testing.assert_array_equal(observed, expected)
        result['expected'] = expected.tolist()
        result['observed'] = observed.tolist()
        profile = Path(session.end_profiling())
        result['profile'] = file_identity(profile)
        nodes = [event for event in json.loads(profile.read_text(encoding='utf-8'))
                 if event.get('cat') == 'Node' and 'provider' in event.get('args', {})]
        result['operatorProviders'] = [event['args']['provider'] for event in nodes]
        result['operatorNames'] = [event['args']['op_name'] for event in nodes]
        if len(nodes) != 2 or any(event['args']['provider'] != 'WebGpuExecutionProvider'
                                  for event in nodes):
            raise RuntimeError('Expected both original operators on WebGPU, without CPU fallback')
        maps = Path('/proc/self/maps').read_text(encoding='utf-8')
        result['loadedProviderObserved'] = str(library.resolve()) in maps
        assert result['loadedProviderObserved']
        if args.preload_probe:
            result['preloadProbe'] = observe_probe(args.preload_probe)
        result['passed'] = True
    except (AssertionError, RuntimeError, ValueError, OSError) as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
        if args.invalid_proc_table and 'dawn_proc_table_str' in str(error) and 'from_chars' in str(error):
            result['expectedConfigurationRejection'] = failure
            result['passed'] = True
        else:
            result['failure'] = failure
    finally:
        session = None
        gc.collect()
        if registered:
            ort.unregister_execution_provider_library('webgpu_seam')
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n',
                            encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'failure': result['failure'],
                      'preloadProbe': result['preloadProbe']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
