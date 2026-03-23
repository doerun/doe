import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, statSync } from 'node:fs';
import { resolve, dirname, relative, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = resolve(__dirname, '..');
const WORKSPACE_ROOT = resolve(PKG_ROOT, '..', '..');

const WEBGPU_SRC = resolve(WORKSPACE_ROOT, 'packages', 'webgpu', 'src');
const DOE_SRC = resolve(WORKSPACE_ROOT, 'packages', 'webgpu-doe', 'src');
const VENDOR_DIR = resolve(PKG_ROOT, 'src', 'vendor');
const VENDOR_WEBGPU = resolve(VENDOR_DIR, 'webgpu');

// Files vendored from packages/webgpu/src/ into vendor/webgpu/.
// The shared/ directory is copied in full.
const WEBGPU_TOP_LEVEL_FILES = [
  'browser.js',
  'build-metadata.js',
  'bun-ffi.js',
  'bun.js',
  'compute.js',
  'deno.js',
  'full.js',
  'index.js',
  'runtime-cli.js',
  'webgpu-constants.js',
];

const DOE_NAMESPACE_HEADER =
  '// Vendored from @simulatte/webgpu-doe (packages/webgpu-doe/src/index.js).\n' +
  '// This file is self-contained with no external imports.\n\n';

function collectSharedFiles(dir) {
  const results = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isFile()) {
      results.push(entry);
    }
  }
  return results.sort();
}

function stripDeprecationBlock(source) {
  // Remove the leading deprecation warning guard:
  //   if (!globalThis.__SIMULATTE_WEBGPU_DOE_DEPRECATION_WARNED) { ... }
  // The block ends at the closing brace followed by a blank line.
  const marker = 'globalThis.__SIMULATTE_WEBGPU_DOE_DEPRECATION_WARNED';
  if (!source.includes(marker)) {
    return source;
  }
  const lines = source.split('\n');
  let blockStart = -1;
  let braceDepth = 0;
  let blockEnd = -1;

  for (let i = 0; i < lines.length; i++) {
    if (blockStart === -1 && lines[i].includes(marker)) {
      blockStart = i;
    }
    if (blockStart !== -1 && blockEnd === -1) {
      for (const ch of lines[i]) {
        if (ch === '{') braceDepth++;
        if (ch === '}') {
          braceDepth--;
          if (braceDepth === 0) {
            blockEnd = i;
            break;
          }
        }
      }
    }
  }

  if (blockStart === -1 || blockEnd === -1) {
    return source;
  }

  // Also strip any blank lines immediately after the block.
  let trimEnd = blockEnd + 1;
  while (trimEnd < lines.length && lines[trimEnd].trim() === '') {
    trimEnd++;
  }

  const kept = [...lines.slice(0, blockStart), ...lines.slice(trimEnd)];
  return kept.join('\n');
}

function ensureDir(dir) {
  mkdirSync(dir, { recursive: true });
}

function syncFile(src, dest, transform) {
  if (!existsSync(src)) {
    const rel = relative(WORKSPACE_ROOT, src);
    console.error(`MISSING: ${rel}`);
    return false;
  }
  ensureDir(dirname(dest));
  let content = readFileSync(src, 'utf8');
  if (transform) {
    content = transform(content);
  }
  writeFileSync(dest, content);
  const relSrc = relative(WORKSPACE_ROOT, src);
  const relDest = relative(WORKSPACE_ROOT, dest);
  console.log(`  ${relSrc} -> ${relDest}`);
  return true;
}

function main() {
  console.log('sync-vendor: syncing vendored files into doe-gpu\n');

  let ok = true;

  // 1. Sync webgpu top-level .js files.
  console.log('webgpu/src/ -> vendor/webgpu/');
  for (const file of WEBGPU_TOP_LEVEL_FILES) {
    if (!syncFile(resolve(WEBGPU_SRC, file), resolve(VENDOR_WEBGPU, file))) {
      ok = false;
    }
  }

  // 2. Sync webgpu/src/shared/ directory (all .js files present in source).
  const sharedSrc = resolve(WEBGPU_SRC, 'shared');
  const sharedDest = resolve(VENDOR_WEBGPU, 'shared');
  if (!existsSync(sharedSrc)) {
    console.error(`MISSING: ${relative(WORKSPACE_ROOT, sharedSrc)}`);
    ok = false;
  } else {
    console.log('\nwebgpu/src/shared/ -> vendor/webgpu/shared/');
    const sharedFiles = collectSharedFiles(sharedSrc);
    for (const file of sharedFiles) {
      if (!syncFile(resolve(sharedSrc, file), resolve(sharedDest, file))) {
        ok = false;
      }
    }
  }

  // 3. Sync webgpu-doe/src/index.js -> vendor/doe-namespace.js (strip deprecation).
  console.log('\nwebgpu-doe/src/ -> vendor/doe-namespace.*');
  if (!syncFile(
    resolve(DOE_SRC, 'index.js'),
    resolve(VENDOR_DIR, 'doe-namespace.js'),
    (content) => DOE_NAMESPACE_HEADER + stripDeprecationBlock(content),
  )) {
    ok = false;
  }

  // 4. Sync webgpu-doe/src/index.d.ts -> vendor/doe-namespace.d.ts.
  if (!syncFile(
    resolve(DOE_SRC, 'index.d.ts'),
    resolve(VENDOR_DIR, 'doe-namespace.d.ts'),
  )) {
    ok = false;
  }

  console.log('');
  if (!ok) {
    console.error('sync-vendor: one or more source files missing, exiting with error');
    process.exit(1);
  }
  console.log('sync-vendor: done');
}

main();
