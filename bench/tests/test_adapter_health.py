#!/usr/bin/env python3
"""Regression tests for package/ORT adapter health checks."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_HEALTH_MODULE_URL = (
    REPO_ROOT / 'bench' / 'executors' / 'adapter_health.js'
).resolve().as_uri()
VENDOR_SHARED_MODULE_URL = (
    REPO_ROOT / 'bench' / 'executors' / 'vendor-node' / 'shared.js'
).resolve().as_uri()


class AdapterHealthTests(unittest.TestCase):
    def test_adapter_health_flags_null_backend_signatures(self) -> None:
        script = f"""
import {{
  adapterInfoIsNullBackend,
  describeUnusableAdapterInfo,
}} from {json.dumps(ADAPTER_HEALTH_MODULE_URL)};

console.log(JSON.stringify({{
  byBackendType: adapterInfoIsNullBackend({{ backendType: 1 }}),
  byDeviceName: adapterInfoIsNullBackend({{ device: 'null-backend' }}),
  healthy: adapterInfoIsNullBackend({{ backendType: 5, device: 'apple-m3-max' }}),
  detail: describeUnusableAdapterInfo(
    {{ backendType: 1, device: 'null-backend' }},
    'bun-webgpu',
  ),
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
        self.assertTrue(payload['byBackendType'])
        self.assertTrue(payload['byDeviceName'])
        self.assertFalse(payload['healthy'])
        self.assertIn('null-backend adapter', payload['detail'])

    def test_vendor_request_adapter_rejects_null_backend_before_request_device(self) -> None:
        script = f"""
import {{ requestAdapterAndDevice }} from {json.dumps(VENDOR_SHARED_MODULE_URL)};

let requestDeviceCalls = 0;
const providerRuntime = {{
  providerName: 'bun-webgpu',
  adapterRequestOptions: {{ powerPreference: 'high-performance' }},
  compute: null,
  gpu: {{
    async requestAdapter() {{
      return {{
        info: {{
          backendType: 1,
          device: 'null-backend',
        }},
        async requestDevice() {{
          requestDeviceCalls += 1;
          return {{
            adapterInfo: {{
              backendType: 1,
              device: 'null-backend',
            }},
          }};
        }},
      }};
    }},
  }},
}};

try {{
  await requestAdapterAndDevice(providerRuntime);
  console.log(JSON.stringify({{ ok: true, requestDeviceCalls }}));
}} catch (error) {{
  console.log(JSON.stringify({{
    ok: false,
    requestDeviceCalls,
    message: error instanceof Error ? error.message : String(error),
  }}));
}}
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
        self.assertFalse(payload['ok'])
        self.assertEqual(payload['requestDeviceCalls'], 0)
        self.assertIn('null-backend adapter', payload['message'])


if __name__ == '__main__':
    unittest.main()
