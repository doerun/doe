#!/usr/bin/env node

// doe-gpu — rebuild the native drop-in shared library from the Zig source
// before a platform package is published.
//
// Invoked from `prepublishOnly` on platform packages (`doe-gpu-linux-x64`,
// `doe-gpu-darwin-arm64`, ...). Intent: make it impossible to publish a
// binary that predates the current WGSL compiler source tree.
//
// Behaviour:
//   - When the current host matches the target package's os/cpu, run
//     `zig build dropin -Doptimize=ReleaseFast` to refresh zig-out/lib
//     and zig-out/share/doe-build-metadata.json. The subsequent `prepack`
//     hook copies these into the package's bin/ and re-runs the
//     freshness guard in stage-platform-package.js.
//   - When the current host does not match the target (cross-host
//     publish), skip the rebuild. Staging will then require env
//     overrides (DOE_NAPI_ADDON, DOE_WEBGPU_LIB) that must point at
//     artifacts built on a matching host. The freshness guard still
//     runs against the metadata those artifacts ship with, so cross-host
//     publishers are equally protected against stale binaries.
//   - DOE_SKIP_NATIVE_REBUILD=1 bypasses this step. Only useful for
//     local npm pack dry runs; never for publish.

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

function readJsonFile(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function main() {
  if (process.env.DOE_SKIP_NATIVE_REBUILD === '1') {
    console.warn(
      'doe-gpu: DOE_SKIP_NATIVE_REBUILD=1 — skipping zig build; staging will still ' +
      'run the freshness guard in stage-platform-package.js. Never set this on publish.',
    );
    return;
  }

  const targetPackageRoot = process.cwd();
  const packageJsonPath = resolve(targetPackageRoot, 'package.json');
  if (!existsSync(packageJsonPath)) {
    throw new Error(`doe-gpu: missing package.json in "${targetPackageRoot}".`);
  }
  const packageJson = readJsonFile(packageJsonPath);
  const targetPlatform = Array.isArray(packageJson.os) ? packageJson.os[0] : null;
  const targetArch = Array.isArray(packageJson.cpu) ? packageJson.cpu[0] : null;
  if (!targetPlatform || !targetArch) {
    throw new Error(`doe-gpu: package "${packageJson.name}" must declare os/cpu for rebuild.`);
  }
  const targetHostTag = `${targetPlatform}-${targetArch}`;
  const currentHostTag = `${process.platform}-${process.arch}`;

  if (targetHostTag !== currentHostTag) {
    if (!process.env.DOE_NAPI_ADDON && !process.env.DOE_WEBGPU_LIB && !process.env.DOE_LIB) {
      throw new Error(
        `doe-gpu: ${packageJson.name} targets ${targetHostTag} but current host is ${currentHostTag}. ` +
        'Cross-host publish requires DOE_NAPI_ADDON and DOE_WEBGPU_LIB/DOE_LIB pointing at a build ' +
        'produced on a matching host; the freshness guard in stage will verify them against the current source.',
      );
    }
    console.log(
      `doe-gpu: ${packageJson.name}: cross-host publish detected (current=${currentHostTag}, ` +
      `target=${targetHostTag}). Skipping zig rebuild; staging will use DOE_NAPI_ADDON/DOE_WEBGPU_LIB env overrides.`,
    );
    return;
  }

  const workspaceRoot = resolve(targetPackageRoot, '..', '..');
  const zigRoot = resolve(workspaceRoot, 'runtime', 'zig');
  if (!existsSync(zigRoot)) {
    throw new Error(`doe-gpu: Zig build root not found at ${zigRoot}.`);
  }

  console.log(`doe-gpu: ${packageJson.name}: running \`zig build dropin -Doptimize=ReleaseFast\` in ${zigRoot}`);
  const result = spawnSync(
    'zig',
    ['build', 'dropin', '-Doptimize=ReleaseFast'],
    {
      cwd: zigRoot,
      stdio: 'inherit',
      env: process.env,
    },
  );
  if (result.error) {
    throw new Error(
      `doe-gpu: ${packageJson.name}: zig rebuild failed to start: ${result.error.message}. ` +
      'Ensure the `zig` executable is on PATH and matches the toolchain in config/toolchains.json.',
    );
  }
  if (typeof result.status === 'number' && result.status !== 0) {
    throw new Error(
      `doe-gpu: ${packageJson.name}: zig rebuild exited with status ${result.status}. ` +
      'Fix the zig build before publishing; the freshness guard in stage will otherwise reject stale artifacts.',
    );
  }
}

main();
