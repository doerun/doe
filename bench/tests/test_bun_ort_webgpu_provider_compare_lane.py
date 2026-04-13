#!/usr/bin/env python3
"""Regression tests for the same-stack Bun ORT WebGPU provider-compare lane."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / 'bench'
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules import config_support


BUN = shutil.which('bun')
WORKLOAD_ID = 'bun_ort_webgpu_provider_compare_gemma3_270m_prefill_32tok_decode_1tok'
WORKLOADS_PATH = (
    REPO_ROOT / 'bench' / 'workloads' / 'workloads.bun.ort-webgpu-provider-compare.json'
)
COMPARE_CONFIG_PATH = (
    REPO_ROOT
    / 'bench'
    / 'native-compare'
    / 'compare.config.bun.ort-webgpu-provider.gemma270m.prefill32.decode1.json'
)
SCENARIO_PATH = (
    REPO_ROOT
    / 'bench'
    / 'vendor-bun'
    / 'ort_webgpu_provider_compare_gemma270m_prefill32_decode1_commands.json'
)
SCENARIO_MODULE_URL = (
    REPO_ROOT / 'bench' / 'executors' / 'vendor-node' / 'scenario.js'
).resolve().as_uri()
SHARED_MODULE_URL = (
    REPO_ROOT / 'bench' / 'executors' / 'vendor-node' / 'shared.js'
).resolve().as_uri()


class BunOrtWebGpuProviderCompareLaneTests(unittest.TestCase):
    def test_workload_manifest_loads_strict_provider_compare_lane(self) -> None:
        workloads = config_support.load_workloads(
            WORKLOADS_PATH,
            '',
            include_noncomparable=True,
            include_extended=False,
            workload_cohort='all',
            selector={'ids': [WORKLOAD_ID]},
        )
        self.assertEqual(len(workloads), 1)
        workload = workloads[0]
        self.assertEqual(workload.id, WORKLOAD_ID)
        self.assertTrue(workload.comparable)
        self.assertEqual(workload.benchmark_class, 'comparable')
        self.assertTrue(workload.claim_eligible)
        self.assertEqual(
            workload.commands_path,
            'bench/vendor-bun/ort_webgpu_provider_compare_gemma270m_prefill32_decode1_commands.json',
        )
        self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_compare_config_is_strict_process_wall_claimable(self) -> None:
        payload = json.loads(COMPARE_CONFIG_PATH.read_text(encoding='utf-8'))
        self.assertEqual(payload['baseline']['executorId'], 'tjs_ort_bun_doe')
        self.assertEqual(payload['comparison']['executorId'], 'tjs_ort_bun_webgpu_package')
        self.assertEqual(payload['comparability']['mode'], 'strict')
        self.assertEqual(payload['comparability']['requireTimingClass'], 'process-wall')
        self.assertEqual(payload['claimability']['mode'], 'local')
        self.assertEqual(payload['claimability']['minTimedSamples'], 3)
        self.assertEqual(payload['selector']['ids'], [WORKLOAD_ID])

    def test_scenario_payload_matches_provider_compare_contract(self) -> None:
        payload = json.loads(SCENARIO_PATH.read_text(encoding='utf-8'))
        self.assertEqual(len(payload), 1)
        scenario = payload[0]
        self.assertEqual(scenario['kind'], 'vendor-node-benchmark-scenario')
        self.assertEqual(scenario['schemaVersion'], 1)
        self.assertEqual(scenario['scenarioId'], WORKLOAD_ID)
        self.assertEqual(scenario['promptWorkload']['prefillTokens'], 32)
        self.assertEqual(scenario['promptWorkload']['decodeTokens'], 1)
        self.assertEqual(scenario['tjs']['modelId'], 'onnx-community/gemma-3-270m-it-ONNX')
        self.assertEqual(
            scenario['tjs']['localModelPath'],
            '../../../doppler/node_modules/@huggingface/transformers/.cache',
        )

    def test_node_scenario_loader_resolves_bun_provider_compare_fields(self) -> None:
        script = f"""
import {{ loadVendorNodeScenario }} from {json.dumps(SCENARIO_MODULE_URL)};
const scenario = await loadVendorNodeScenario({json.dumps(str(SCENARIO_PATH))});
console.log(JSON.stringify({{
  scenarioId: scenario.scenarioId,
  cacheMode: scenario.cacheMode,
  loadMode: scenario.loadMode,
  dopplerRoot: scenario.dopplerRoot,
  tjsLocalModelPath: scenario.tjs.localModelPath,
}}));
"""
        result = subprocess.run(
            ['node', '--input-type=module', '-e', script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['scenarioId'], WORKLOAD_ID)
        self.assertEqual(payload['cacheMode'], 'warm')
        self.assertEqual(payload['loadMode'], 'http')
        self.assertTrue(payload['dopplerRoot'].endswith('/doppler'))
        self.assertTrue(payload['tjsLocalModelPath'].endswith('/doppler/node_modules/@huggingface/transformers/.cache'))

    @unittest.skipUnless(BUN, 'bun is required for Bun ORT provider helper tests')
    def test_bun_provider_helper_supports_doe_and_bun_webgpu(self) -> None:
        script = f"""
import {{ installTjsOrtWebGpuProvider }} from {json.dumps(SHARED_MODULE_URL)};
const doeProvider = await installTjsOrtWebGpuProvider('doe', 'bun');
const bunProvider = await installTjsOrtWebGpuProvider('bun-webgpu', 'bun');
console.log(JSON.stringify({{
  doeBackend: doeProvider.executionBackend,
  bunBackend: bunProvider.executionBackend,
  doeProviderName: doeProvider.providerName,
  bunProviderName: bunProvider.providerName,
  bunBackendType: bunProvider.adapterRequestOptions.backendType,
  bunForceFallbackAdapter: bunProvider.adapterRequestOptions.forceFallbackAdapter,
  hasDoeGpu: !!doeProvider.gpu,
  hasBunGpu: !!bunProvider.gpu,
}}));
"""
        env = dict(os.environ)
        env['DOE_WEBGPU_LIB'] = str(
            REPO_ROOT / 'runtime' / 'zig' / 'zig-out' / 'lib' / 'libwebgpu_doe.so'
        )
        result = subprocess.run(
            [BUN, '--eval', script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['doeBackend'], 'tjs_ort_bun_webgpu')
        self.assertEqual(payload['bunBackend'], 'tjs_ort_bun_webgpu_package')
        self.assertEqual(payload['doeProviderName'], 'doe-gpu')
        self.assertEqual(payload['bunProviderName'], 'bun-webgpu')
        self.assertEqual(payload['bunBackendType'], 6)
        self.assertFalse(payload['bunForceFallbackAdapter'])
        self.assertTrue(payload['hasDoeGpu'])
        self.assertTrue(payload['hasBunGpu'])


if __name__ == '__main__':
    unittest.main()
