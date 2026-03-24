#!/usr/bin/env node

import { workloads } from './workloads.js';
import {
  executePackageRunner,
  parsePackageRunnerArgs,
} from '../../shared/lib/package-runner-core.js';

const args = parsePackageRunnerArgs();

async function loadProvider(name) {
  if (name === 'doe') {
    const doe = await import('../../../packages/doe-gpu/src/index.js');
    return { create: doe.create, globals: doe.globals, name: 'doe-gpu' };
  }
  if (name === 'dawn') {
    // The `webgpu` npm package uses: import { create, globals } from 'webgpu';
    const dawn = await import('webgpu');
    return { create: dawn.create, globals: dawn.globals, name: 'webgpu (dawn)' };
  }
  throw new Error(`Unknown provider: ${name}. Use 'doe' or 'dawn'.`);
}

async function main() {
  await executePackageRunner({
    args,
    workloads,
    loadProvider,
    runtimeInfo: { nodeVersion: process.version },
    shouldDestroyDevice: (provider) => provider !== 'dawn',
  });
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
