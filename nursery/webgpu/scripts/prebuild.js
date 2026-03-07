#!/usr/bin/env node
// Build and package prebuilt native artifacts for the current platform.
//
// Usage:
//   node scripts/prebuild.js [--zig-out PATH]
//
// Produces:
//   prebuilds/<platform>-<arch>/
//     doe_napi.node          N-API addon
//     libwebgpu_doe.<ext>    Doe drop-in WebGPU library
//     libwebgpu_dawn.<ext>   Dawn sidecar (required by Doe for proc resolution)
//     metadata.json          Integrity manifest
//
// Prerequisites:
//   1. node-gyp rebuild (or existing build/Release/doe_napi.node)
//   2. zig build dropin (or existing zig-out/lib artifacts)

import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { parseArgs } from 'node:util';
import { readDoeBuildMetadataFile } from '../src/build_metadata.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = resolve(__dirname, '..');
const WORKSPACE_ROOT = resolve(PACKAGE_ROOT, '..', '..');

const { values: args } = parseArgs({
  options: {
    'zig-out': { type: 'string', default: '' },
    'skip-addon-build': { type: 'boolean', default: false },
  },
});

const platform = process.platform;
const arch = process.arch;
const ext = platform === 'darwin' ? 'dylib' : platform === 'win32' ? 'dll' : 'so';

const zigOutLib = args['zig-out']
  ? resolve(args['zig-out'], 'lib')
  : resolve(WORKSPACE_ROOT, 'zig', 'zig-out', 'lib');
const zigOutShare = args['zig-out']
  ? resolve(args['zig-out'], 'share')
  : resolve(WORKSPACE_ROOT, 'zig', 'zig-out', 'share');

const prebuildDir = resolve(PACKAGE_ROOT, 'prebuilds', `${platform}-${arch}`);

function sha256(filePath) {
  const data = readFileSync(filePath);
  return createHash('sha256').update(data).digest('hex');
}

function copyArtifact(src, destName) {
  if (!existsSync(src)) {
    console.error(`Missing: ${src}`);
    return null;
  }
  const dest = resolve(prebuildDir, destName);
  copyFileSync(src, dest);
  console.log(`  ${destName} <- ${src}`);
  return { name: destName, sha256: sha256(dest) };
}

// 1. Build addon if needed.
const addonSrc = resolve(PACKAGE_ROOT, 'build', 'Release', 'doe_napi.node');
if (!args['skip-addon-build'] || !existsSync(addonSrc)) {
  console.log('Building native addon...');
  execFileSync('node-gyp', ['rebuild'], { cwd: PACKAGE_ROOT, stdio: 'inherit' });
}

if (!existsSync(addonSrc)) {
  console.error(`Addon not found at ${addonSrc}. node-gyp rebuild may have failed.`);
  process.exit(1);
}

// 2. Locate Doe library.
const doeLib = resolve(zigOutLib, `libwebgpu_doe.${ext}`);
if (!existsSync(doeLib)) {
  console.error(`Doe library not found at ${doeLib}.`);
  console.error('Run: cd zig && zig build dropin');
  process.exit(1);
}

// 3. Locate Dawn sidecar.
const SIDECAR_CANDIDATES = {
  darwin: ['libwebgpu_dawn.dylib', 'libwebgpu.dylib'],
  linux: ['libwebgpu_dawn.so', 'libwebgpu.so'],
  win32: ['webgpu_dawn.dll', 'webgpu.dll'],
};

const candidates = SIDECAR_CANDIDATES[platform] || SIDECAR_CANDIDATES.linux;
let sidecarSrc = null;
let sidecarName = null;
for (const name of candidates) {
  const candidate = resolve(zigOutLib, name);
  if (existsSync(candidate)) {
    sidecarSrc = candidate;
    sidecarName = name;
    break;
  }
}

if (!sidecarSrc) {
  console.error(`Dawn sidecar not found in ${zigOutLib}. Expected one of: ${candidates.join(', ')}`);
  console.error('Run: cd zig && zig build dropin (with Dawn sidecar available)');
  process.exit(1);
}

const zigBuildMetadataPath = resolve(zigOutShare, 'doe-build-metadata.json');
const doeBuild = readDoeBuildMetadataFile(zigBuildMetadataPath);
if (!doeBuild) {
  console.error(`Doe build metadata not found or invalid at ${zigBuildMetadataPath}.`);
  console.error('Run: cd zig && zig build dropin [ -Dlean-verified=true ]');
  process.exit(1);
}

// 4. Assemble prebuild directory.
mkdirSync(prebuildDir, { recursive: true });
console.log(`\nAssembling prebuilds/${platform}-${arch}/`);

const files = {};
const addonEntry = copyArtifact(addonSrc, 'doe_napi.node');
if (addonEntry) files[addonEntry.name] = { sha256: addonEntry.sha256 };

const doeEntry = copyArtifact(doeLib, `libwebgpu_doe.${ext}`);
if (doeEntry) files[doeEntry.name] = { sha256: doeEntry.sha256 };

const sidecarEntry = copyArtifact(sidecarSrc, sidecarName);
if (sidecarEntry) files[sidecarEntry.name] = { sha256: sidecarEntry.sha256 };

// 5. Write metadata manifest.
const pkg = JSON.parse(readFileSync(resolve(PACKAGE_ROOT, 'package.json'), 'utf8'));
let doeVersion = 'unknown';
try {
  doeVersion = execFileSync('git', ['rev-parse', '--short', 'HEAD'], {
    cwd: WORKSPACE_ROOT,
    encoding: 'utf8',
  }).trim();
} catch { /* ignore */ }

const metadata = {
  schemaVersion: 1,
  package: pkg.name,
  packageVersion: pkg.version,
  platform,
  arch,
  nodeNapiVersion: 8,
  doeVersion,
  doeBuild: {
    artifact: 'libwebgpu_doe',
    leanVerifiedBuild: doeBuild.leanVerifiedBuild,
    proofArtifactSha256: doeBuild.proofArtifactSha256,
  },
  files,
  builtAt: new Date().toISOString(),
};

const metadataPath = resolve(prebuildDir, 'metadata.json');
writeFileSync(metadataPath, JSON.stringify(metadata, null, 2) + '\n');
console.log(`  metadata.json`);

// macOS: ad-hoc sign dylibs for distribution.
if (platform === 'darwin') {
  console.log('\nSigning dylibs (ad-hoc)...');
  for (const name of Object.keys(files)) {
    if (name.endsWith('.dylib')) {
      try {
        execFileSync('codesign', ['-s', '-', resolve(prebuildDir, name)], { stdio: 'inherit' });
      } catch {
        console.warn(`  Warning: codesign failed for ${name} (may already be signed)`);
      }
    }
  }
}

console.log(`\nDone. Prebuild artifacts in prebuilds/${platform}-${arch}/`);
console.log(`Total files: ${Object.keys(files).length}`);
