#!/usr/bin/env bun

import { workloads } from '../node/workloads.js';
import {
  executePackageRunner,
  parsePackageRunnerArgs,
} from '../../shared/lib/package-runner-core.js';

const args = parsePackageRunnerArgs();

async function loadProvider(name) {
  if (name === 'doe') {
    const doe = await import('../../../packages/doe-gpu/src/bun.js');
    return { create: doe.create, globals: doe.globals, name: 'doe-gpu (bun default)' };
  }
  if (name === 'bun-webgpu') {
    // Community Bun WebGPU package: installs navigator.gpu via setupGlobals().
    const mod = await import('bun-webgpu');
    if (typeof mod.setupGlobals !== 'function') {
      throw new Error('bun-webgpu does not export setupGlobals()');
    }
    mod.setupGlobals();
    if (typeof navigator === 'undefined' || !navigator.gpu) {
      throw new Error('bun-webgpu did not install navigator.gpu');
    }
    const gpu = navigator.gpu;
    const globals = {
      GPUBufferUsage:  globalThis.GPUBufferUsage,
      GPUShaderStage:  globalThis.GPUShaderStage,
      GPUMapMode:      globalThis.GPUMapMode,
      GPUTextureUsage: globalThis.GPUTextureUsage,
    };
    return {
      create: () => gpu,
      globals,
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
