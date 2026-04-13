#!/usr/bin/env python3
"""Regression tests for the same-stack Node ORT WebGPU provider-compare lane."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / 'bench'
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules import config_support


WORKLOAD_ID = 'node_ort_webgpu_provider_compare_gemma3_270m_prefill_64tok_decode_64tok'
WORKLOADS_PATH = (
    REPO_ROOT / 'bench' / 'workloads' / 'workloads.node.ort-webgpu-provider-compare.json'
)
COMPARE_CONFIG_PATH = (
    REPO_ROOT
    / 'bench'
    / 'native-compare'
    / 'compare.config.node.ort-webgpu-provider.gemma270m.json'
)
SCENARIO_PATH = (
    REPO_ROOT / 'bench' / 'vendor-node' / 'ort_webgpu_provider_compare_gemma270m_commands.json'
)
SCENARIO_MODULE_URL = (
    REPO_ROOT / 'bench' / 'executors' / 'vendor-node' / 'scenario.js'
).resolve().as_uri()
TRACE_ARTIFACT_MODULE_URL = (
    REPO_ROOT / 'bench' / 'executors' / 'vendor-node' / 'trace-artifact.js'
).resolve().as_uri()


class NodeOrtWebGpuProviderCompareLaneTests(unittest.TestCase):
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
            'bench/vendor-node/ort_webgpu_provider_compare_gemma270m_commands.json',
        )
        self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_compare_config_is_strict_process_wall_claimable(self) -> None:
        payload = json.loads(COMPARE_CONFIG_PATH.read_text(encoding='utf-8'))
        self.assertEqual(payload['baseline']['executorId'], 'tjs_ort_node_doe')
        self.assertEqual(payload['comparison']['name'], 'tjs_ort_node_webgpu_package')
        self.assertIn("DOE_NODE_WEBGPU_ADAPTER='Radeon 8060S Graphics (RADV STRIX_HALO)'", payload['comparison']['commandTemplate'])
        self.assertIn('run-node-tjs-ort-webgpu.js', payload['comparison']['commandTemplate'])
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
        self.assertEqual(scenario['promptWorkload']['prefillTokens'], 64)
        self.assertEqual(scenario['promptWorkload']['decodeTokens'], 64)
        self.assertEqual(scenario['tjs']['modelId'], 'onnx-community/gemma-3-270m-it-ONNX')
        self.assertEqual(
            scenario['doppler']['modelPath'],
            '../../../doppler/models/local/gemma-3-270m-it-q4k-ehf16-af32',
        )
        self.assertEqual(
            scenario['tjs']['localModelPath'],
            '../../../doppler/node_modules/@huggingface/transformers/.cache',
        )

    def test_node_scenario_loader_resolves_provider_compare_fields(self) -> None:
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

    def test_trace_artifact_writer_emits_custom_provider_compare_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix='doe-node-ort-webgpu-provider-compare-') as tmpdir:
            tmp = Path(tmpdir)
            meta_path = tmp / 'trace.meta.json'
            jsonl_path = tmp / 'trace.ndjson'
            script = f"""
import {{ readFile }} from 'node:fs/promises';
import {{
  writeVendorNodeSuccessTrace,
  writeVendorNodeFailureTrace,
}} from {json.dumps(TRACE_ARTIFACT_MODULE_URL)};

const traceMetaPath = {json.dumps(str(meta_path))};
const traceJsonlPath = {json.dumps(str(jsonl_path))};
await writeVendorNodeSuccessTrace({{
  runtimeHost: 'bun',
  traceMetaPath,
  traceJsonlPath,
  benchmarkLane: 'node-ort-webgpu-provider-compare',
  workloadId: {json.dumps(WORKLOAD_ID)},
  scenarioId: {json.dumps(WORKLOAD_ID)},
  executionBackend: 'tjs_ort_node_webgpu',
  executionLabel: 'Transformers.js ORT node WebGPU on doe-gpu',
  executionProvider: 'doe',
  executionProviderName: 'doe-gpu',
  processWallMs: 42.5,
  adapterInfo: {{ vendor: 'AMD', architecture: 'gfx11', device: 'mock', description: '', subgroupMinSize: 32, subgroupMaxSize: 64 }},
  phaseTimingsMs: {{ promptSynthesisMs: 10, pipelineLoadMs: 12, generationMs: 20.5 }},
  promptSummary: {{ promptSource: 'synthetic', promptLength: 512, prefillTokens: 64, decodeTokens: 64 }},
  resultSummary: {{ generatedTextLength: 64, generatedTextPreview: 'alpha' }},
  extraMeta: {{ vendorStack: 'transformers.js+onnxruntime-node' }},
}});
const successMeta = JSON.parse(await readFile(traceMetaPath, 'utf8'));
const successRows = (await readFile(traceJsonlPath, 'utf8')).trim().split('\\n').map((line) => JSON.parse(line));

await writeVendorNodeFailureTrace({{
  runtimeHost: 'bun',
  traceMetaPath,
  traceJsonlPath,
  benchmarkLane: 'node-ort-webgpu-provider-compare',
  workloadId: {json.dumps(WORKLOAD_ID)},
  scenarioId: {json.dumps(WORKLOAD_ID)},
  executionBackend: 'tjs_ort_node_webgpu_package',
  executionLabel: 'Transformers.js ORT node WebGPU on node-webgpu',
  executionProvider: 'node-webgpu',
  executionProviderName: 'node-webgpu',
  processWallMs: 11.25,
  errorMessage: 'node-webgpu adapter unavailable',
}});
const failureMeta = JSON.parse(await readFile(traceMetaPath, 'utf8'));
const failureRows = (await readFile(traceJsonlPath, 'utf8')).trim().split('\\n').map((line) => JSON.parse(line));

console.log(JSON.stringify({{
  successMeta,
  successRows,
  failureMeta,
  failureRows,
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
            success_meta = payload['successMeta']
            success_row = payload['successRows'][0]
            failure_meta = payload['failureMeta']
            failure_row = payload['failureRows'][0]

        self.assertEqual(success_meta['benchmarkLane'], 'node-ort-webgpu-provider-compare')
        self.assertEqual(success_meta['runtimeHost'], 'bun')
        self.assertEqual(success_meta['executionProvider'], 'doe')
        self.assertEqual(success_meta['executionProviderName'], 'doe-gpu')
        self.assertEqual(success_meta['executionSuccessCount'], 1)
        self.assertEqual(success_meta['executionErrorCount'], 0)
        self.assertEqual(success_meta['phaseTimingsMs']['generationMs'], 20.5)
        self.assertEqual(success_row['status'], 'success')

        self.assertEqual(failure_meta['benchmarkLane'], 'node-ort-webgpu-provider-compare')
        self.assertEqual(failure_meta['runtimeHost'], 'bun')
        self.assertEqual(failure_meta['executionProvider'], 'node-webgpu')
        self.assertEqual(failure_meta['executionProviderName'], 'node-webgpu')
        self.assertEqual(failure_meta['executionSuccessCount'], 0)
        self.assertEqual(failure_meta['executionErrorCount'], 1)
        self.assertEqual(failure_row['status'], 'error')
        self.assertIn('adapter unavailable', failure_row['errorMessage'])


if __name__ == '__main__':
    unittest.main()
