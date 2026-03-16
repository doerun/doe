#!/usr/bin/env node
// Prebuild-aware install script.
// Uses prebuilt binaries when available; falls back to node-gyp for contributors.

import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = resolve(__dirname, '..');

const platform = process.platform;
const arch = process.arch;
const prebuildDir = resolve(PACKAGE_ROOT, 'prebuilds', `${platform}-${arch}`);
const addonPath = resolve(prebuildDir, 'doe_napi.node');

if (existsSync(addonPath)) {
  console.log(`@simulatte/webgpu: using prebuilt binary for ${platform}-${arch}`);
  process.exit(0);
}

// No prebuild — compile from source.
console.log(`@simulatte/webgpu: no prebuild for ${platform}-${arch}, compiling from source...`);

try {
  execFileSync('node-gyp', ['rebuild'], {
    cwd: PACKAGE_ROOT,
    stdio: 'inherit',
  });
} catch (err) {
  console.error('@simulatte/webgpu: native addon build failed.');
  console.error('Ensure you have a C compiler and node-gyp prerequisites installed.');
  console.error('See https://github.com/nodejs/node-gyp#installation');
  process.exit(1);
}
