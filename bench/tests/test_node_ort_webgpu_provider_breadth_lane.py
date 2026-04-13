#!/usr/bin/env python3
"""Regression tests for the broader Node ORT WebGPU provider-compare matrix."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = REPO_ROOT / 'bench'
for _path_entry in (str(REPO_ROOT), str(BENCH_ROOT)):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

from bench.native_compare_modules import config_support


WORKLOADS_PATH = (
    REPO_ROOT / 'bench' / 'workloads' / 'workloads.node.ort-webgpu-provider-compare.breadth.json'
)
COMPARE_CONFIG_PATH = (
    REPO_ROOT / 'bench' / 'native-compare' / 'compare.config.node.ort-webgpu-provider.breadth.json'
)

EXPECTED_IDS = [
    'node_ort_webgpu_provider_compare_gemma3_270m_prefill_64tok_decode_64tok',
    'node_ort_webgpu_provider_compare_gemma3_270m_prefill_32tok_decode_1tok',
    'node_ort_webgpu_provider_compare_gemma3_270m_prefill_256tok_decode_1tok',
    'node_ort_webgpu_provider_compare_gemma3_270m_prefill_32tok_decode_128tok',
    'node_ort_webgpu_provider_compare_gemma3_1b_prefill_32tok_decode_1tok',
]


class NodeOrtWebGpuProviderBreadthLaneTests(unittest.TestCase):
    def test_workload_manifest_loads_all_breadth_ids(self) -> None:
      workloads = config_support.load_workloads(
          WORKLOADS_PATH,
          '',
          include_noncomparable=True,
          include_extended=False,
          workload_cohort='all',
          selector={'ids': EXPECTED_IDS},
      )
      self.assertEqual([workload.id for workload in workloads], EXPECTED_IDS)
      for workload in workloads:
          self.assertTrue(workload.comparable)
          self.assertTrue(workload.claim_eligible)
          self.assertTrue((REPO_ROOT / workload.commands_path).exists())

    def test_compare_config_tracks_expected_breadth_ids(self) -> None:
        payload = json.loads(COMPARE_CONFIG_PATH.read_text(encoding='utf-8'))
        self.assertEqual(payload['baseline']['executorId'], 'tjs_ort_node_doe')
        self.assertEqual(payload['comparison']['name'], 'tjs_ort_node_webgpu_package')
        self.assertIn("DOE_NODE_WEBGPU_ADAPTER='Radeon 8060S Graphics (RADV STRIX_HALO)'", payload['comparison']['commandTemplate'])
        self.assertEqual(payload['comparability']['mode'], 'strict')
        self.assertEqual(payload['comparability']['requireTimingClass'], 'process-wall')
        self.assertEqual(payload['claimability']['mode'], 'off')
        self.assertEqual(payload['selector']['ids'], EXPECTED_IDS)


if __name__ == '__main__':
    unittest.main()
