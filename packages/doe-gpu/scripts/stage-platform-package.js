#!/usr/bin/env node

// doe-gpu — stage a platform package bin payload from workspace native artifacts.

import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const LIBRARY_FILENAMES = Object.freeze({
  darwin: 'libwebgpu_doe.dylib',
  linux: 'libwebgpu_doe.so',
  win32: 'webgpu_doe.dll',
});

const __dirname = dirname(fileURLToPath(import.meta.url));

function readJsonFile(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function resolveExistingPath(candidates, label) {
  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error(`doe-gpu: missing ${label}. Checked: ${candidates.filter(Boolean).join(', ')}`);
}

function parseBuildMetadata(metadataPath) {
  const parsed = readJsonFile(metadataPath);
  if (parsed?.schemaVersion !== 1 || parsed?.artifact !== 'libwebgpu_doe') {
    throw new Error(`doe-gpu: unsupported Doe build metadata at "${metadataPath}".`);
  }
  return parsed;
}

function writePrebuildMetadata(sidecar, metadataPath) {
  const payload = {
    schemaVersion: 1,
    doeBuild: {
      artifact: sidecar.artifact,
      leanVerifiedBuild: sidecar.leanVerifiedBuild,
      proofArtifactSha256: sidecar.proofArtifactSha256 ?? null,
    },
  };
  writeFileSync(metadataPath, `${JSON.stringify(payload, null, 2)}\n`);
}

function currentHostTag() {
  return `${process.platform}-${process.arch}`;
}

function main() {
  const targetPackageRoot = process.cwd();
  const packageJsonPath = resolve(targetPackageRoot, 'package.json');
  if (!existsSync(packageJsonPath)) {
    throw new Error(`doe-gpu: missing package.json in "${targetPackageRoot}".`);
  }
  const packageJson = readJsonFile(packageJsonPath);
  const targetPlatform = Array.isArray(packageJson.os) ? packageJson.os[0] : null;
  const targetArch = Array.isArray(packageJson.cpu) ? packageJson.cpu[0] : null;
  if (!targetPlatform || !targetArch) {
    throw new Error(`doe-gpu: package "${packageJson.name}" must declare os/cpu for staging.`);
  }

  const workspaceRoot = resolve(targetPackageRoot, '..', '..');
  const targetHostTag = `${targetPlatform}-${targetArch}`;
  const expectedCurrentHost = currentHostTag();
  const libraryFilename = LIBRARY_FILENAMES[targetPlatform];
  if (!libraryFilename) {
    throw new Error(`doe-gpu: unsupported package platform "${targetPlatform}".`);
  }

  if (
    targetHostTag !== expectedCurrentHost
    && !process.env.DOE_NAPI_ADDON
    && !process.env.DOE_WEBGPU_LIB
    && !process.env.DOE_LIB
  ) {
    throw new Error(
      `doe-gpu: ${packageJson.name} targets ${targetHostTag}, but the current host is ${expectedCurrentHost}. ` +
      'Provide DOE_NAPI_ADDON and DOE_WEBGPU_LIB/DOE_LIB from a matching build artifact when staging cross-host packages.',
    );
  }

  const addonPath = resolveExistingPath([
    process.env.DOE_NAPI_ADDON,
    resolve(workspaceRoot, 'packages', 'doe-gpu', 'build', 'Release', 'doe_napi.node'),
    resolve(workspaceRoot, 'packages', 'doe-gpu', 'src', 'vendor', 'build', 'Release', 'doe_napi.node'),
  ], `${packageJson.name} addon`);
  const libraryPath = resolveExistingPath([
    process.env.DOE_WEBGPU_LIB,
    process.env.DOE_LIB,
    resolve(workspaceRoot, 'runtime', 'zig', 'zig-out', 'lib', libraryFilename),
  ], `${packageJson.name} shared library`);
  const buildMetadataPath = resolveExistingPath([
    process.env.DOE_BUILD_METADATA,
    resolve(workspaceRoot, 'runtime', 'zig', 'zig-out', 'share', 'doe-build-metadata.json'),
  ], `${packageJson.name} build metadata`);

  const buildMetadata = parseBuildMetadata(buildMetadataPath);
  const binRoot = resolve(targetPackageRoot, 'bin');
  rmSync(binRoot, { recursive: true, force: true });
  mkdirSync(binRoot, { recursive: true });

  copyFileSync(addonPath, resolve(binRoot, 'doe_napi.node'));
  copyFileSync(libraryPath, resolve(binRoot, libraryFilename));
  copyFileSync(buildMetadataPath, resolve(binRoot, 'doe-build-metadata.json'));
  writePrebuildMetadata(buildMetadata, resolve(binRoot, 'metadata.json'));

  console.log(`doe-gpu: staged ${packageJson.name} from workspace artifacts`);
}

main();
