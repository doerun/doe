#!/usr/bin/env node

import { execFile } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  executePackageCompare,
  makeRunnerInvoker,
  parsePackageCompareArgs,
} from '../lib/package-compare-core.js';
import { workloads } from './workloads.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNNER = resolve(__dirname, 'runner.js');
const args = parsePackageCompareArgs();

async function main() {
  await executePackageCompare({
    args: { ...args, out: args.out ? resolve(args.out) : '' },
    workloads,
    laneId: 'node_package_compare',
    banner: '=== Node.js WebGPU Benchmark: Doe vs Dawn ===',
    rightRunnerLabel: 'dawn',
    rightErrorHint: 'Is the webgpu npm package installed? Run: npm install webgpu',
    rightTableLabel: 'Dawn',
    reportFilePrefix: 'doe-vs-dawn-node',
    rightMissingStatus: 'dawn_missing',
    rightRawPrefix: 'dawn-raw',
    runtimeInfo: { nodeVersion: process.version },
    runProviderWorkload: makeRunnerInvoker({
      command: process.execPath,
      execFile,
      runnerPath: RUNNER,
      iterations: args.iterations,
      warmup: args.warmup,
      salvageCompleteStream: true,
    }),
  });
}

main().catch((err) => {
  console.error(`Fatal: ${err.message}\n${err.stack}`);
  process.exit(1);
});
