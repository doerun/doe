import { execFile } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  executePackageCompare,
  parsePackageCompareArgs,
} from '../../shared/lib/package-compare-core.js';
import { parseRunnerLines } from '../../shared/lib/runner_io.js';
import { RUNNER_MAX_BUFFER } from '../../shared/lib/constants.js';
import { workloads } from '../node/workloads.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNNER = resolve(__dirname, 'runner.js');
const args = parsePackageCompareArgs();

// Deno requires pre-script flags (--allow-all, --unstable-webgpu) that
// makeRunnerInvoker does not support, so we use a custom invoker.
function makeDenoRunnerInvoker({ denoPath, iterations, warmup }) {
  return function runProviderWorkload(provider, workloadId, extraArgs = []) {
    return new Promise((resolvePromise, reject) => {
      const denoFlags = ['run', '--allow-all'];
      if (provider === 'deno-webgpu') {
        denoFlags.push('--unstable-webgpu');
      }
      const cmdArgs = [
        ...denoFlags,
        RUNNER,
        '--provider',
        provider,
        '--iterations',
        iterations,
        '--warmup',
        warmup,
        '--workload',
        workloadId,
        '--validate',
        ...extraArgs,
      ];
      execFile(denoPath, cmdArgs, { maxBuffer: RUNNER_MAX_BUFFER }, (err, stdout, stderr) => {
        process.stderr.write(stderr);
        let lines;
        try {
          lines = parseRunnerLines(stdout);
        } catch (parseErr) {
          const detail = parseErr instanceof Error ? parseErr.message : String(parseErr);
          reject(new Error(`${provider} runner emitted invalid JSON: ${detail}`));
          return;
        }
        if (err) {
          reject(new Error(`${provider} runner failed: ${err.message}`));
          return;
        }
        resolvePromise(lines);
      });
    });
  };
}

async function main() {
  const denoPath = typeof Deno !== 'undefined' ? Deno.execPath() : 'deno';
  await executePackageCompare({
    args: { ...args, out: args.out ? resolve(args.out) : '' },
    workloads,
    laneId: 'deno_package_compare',
    banner: '=== Deno WebGPU Benchmark: Doe vs deno-webgpu (wgpu) ===',
    rightRunnerLabel: 'deno-webgpu',
    rightErrorHint: 'Deno built-in WebGPU requires: deno run --unstable-webgpu',
    rightTableLabel: 'Deno wgpu',
    reportFilePrefix: 'doe-vs-deno-webgpu',
    rightMissingStatus: 'deno_webgpu_missing',
    rightRawPrefix: 'deno-webgpu-raw',
    runtimeInfo: { denoVersion: typeof Deno !== 'undefined' ? Deno.version.deno : 'unknown' },
    runProviderWorkload: makeDenoRunnerInvoker({
      denoPath,
      iterations: args.iterations,
      warmup: args.warmup,
    }),
  });
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
