#!/usr/bin/env bun

import { fileURLToPath } from 'node:url';

import { runPackageWebGpuPlanCli } from './package-webgpu/runner-core.js';

const CLI_PATH = fileURLToPath(import.meta.url);

runPackageWebGpuPlanCli({
  runtimeHost: 'bun',
  defaultProvider: 'bun-webgpu',
  cliPath: CLI_PATH,
  childEnv: 'DOE_BUN_WEBGPU_CHILD',
  label: 'bun-webgpu',
  providerUsage: 'doe|bun-webgpu',
  usageCommand: 'bun bench/executors/run-bun-webgpu-plan.js',
}).catch((err) => {
  process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
  process.exit(1);
});
