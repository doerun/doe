import { workloads } from '../workloads.js';
import {
  executePackageRunner,
  parsePackageRunnerArgs,
} from '../../../shared/lib/package-runner-core.js';

const args = parsePackageRunnerArgs();

async function loadProvider(name) {
  if (name === 'doe' || name === 'doe-api') {
    const doe = await import('../../../../packages/webgpu/src/index.js');
    return {
      create: doe.create,
      globals: { ...doe.globals, doeApi: true },
      name: '@simulatte/webgpu-doe (deno)',
    };
  }
  if (name === 'deno-webgpu') {
    if (typeof globalThis.navigator === 'undefined' || !globalThis.navigator.gpu) {
      throw new Error(
        'Deno built-in WebGPU not available. Run with: deno run --unstable-webgpu'
      );
    }
    const gpu = globalThis.navigator.gpu;
    return {
      create: () => gpu,
      globals: {
        GPUBufferUsage:  globalThis.GPUBufferUsage,
        GPUShaderStage:  globalThis.GPUShaderStage,
        GPUMapMode:      globalThis.GPUMapMode,
        GPUTextureUsage: globalThis.GPUTextureUsage,
      },
      name: 'deno-webgpu (built-in wgpu)',
    };
  }
  throw new Error(`Unknown provider: ${name}. Use 'doe' or 'deno-webgpu'.`);
}

async function main() {
  await executePackageRunner({
    args,
    workloads,
    loadProvider,
    runtimeInfo: { denoVersion: typeof Deno !== 'undefined' ? Deno.version.deno : 'unknown' },
    shouldDestroyDevice: () => true,
  });
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
