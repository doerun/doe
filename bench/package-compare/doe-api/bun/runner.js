#!/usr/bin/env bun

import { workloads } from '../workloads.js';
import {
  executePackageRunner,
  parsePackageRunnerArgs,
} from '../../../shared/lib/package-runner-core.js';

const args = parsePackageRunnerArgs();

async function loadProvider(name) {
  if (name === 'doe' || name === 'doe-api') {
    const doe = await import('../../../../packages/webgpu/src/bun.js');
    return {
      create: doe.create,
      globals: { ...doe.globals, doeApi: true },
      name: '@simulatte/webgpu-doe (bun)',
    };
  }
  if (name === 'bun-webgpu') {
    const mod = await import('bun-webgpu');
    if (typeof mod.setupGlobals !== 'function') {
      throw new Error('bun-webgpu does not export setupGlobals()');
    }
    mod.setupGlobals();
    if (typeof navigator === 'undefined' || !navigator.gpu) {
      throw new Error('bun-webgpu did not install navigator.gpu');
    }
    const gpu = navigator.gpu;
    return {
      create: () => gpu,
      globals: {
        GPUBufferUsage:  globalThis.GPUBufferUsage,
        GPUShaderStage:  globalThis.GPUShaderStage,
        GPUMapMode:      globalThis.GPUMapMode,
        GPUTextureUsage: globalThis.GPUTextureUsage,
      },
      name: 'bun-webgpu (package)',
    };
  }
  throw new Error(`Unknown provider: ${name}. Use 'doe' or 'bun-webgpu'.`);
}

async function main() {
  await executePackageRunner({
    args,
    workloads,
    loadProvider,
    runtimeInfo: { bunVersion: typeof Bun !== 'undefined' ? Bun.version : 'unknown' },
    shouldDestroyDevice: () => true,
  });
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
