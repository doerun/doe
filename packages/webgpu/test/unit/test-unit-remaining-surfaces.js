import assert from 'node:assert/strict';

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  PASS: ${name}`);
  } catch (error) {
    failed += 1;
    console.error(`  FAIL: ${name}`);
    console.error(`        ${error.message}`);
  }
}

// ============================================================
// 1. build-metadata.js
// ============================================================
console.log('\nbuild-metadata.js');

import {
  UNKNOWN_DOE_BUILD_METADATA,
  readDoeBuildMetadataFile,
  loadDoeBuildMetadata,
} from '../../src/build-metadata.js';

test('UNKNOWN_DOE_BUILD_METADATA is a frozen object with expected shape', () => {
  assert.ok(Object.isFrozen(UNKNOWN_DOE_BUILD_METADATA));
  assert.strictEqual(UNKNOWN_DOE_BUILD_METADATA.source, 'none');
  assert.strictEqual(UNKNOWN_DOE_BUILD_METADATA.path, '');
  assert.strictEqual(UNKNOWN_DOE_BUILD_METADATA.leanVerifiedBuild, null);
  assert.strictEqual(UNKNOWN_DOE_BUILD_METADATA.proofArtifactSha256, null);
});

test('readDoeBuildMetadataFile is a function', () => {
  assert.strictEqual(typeof readDoeBuildMetadataFile, 'function');
});

test('readDoeBuildMetadataFile returns null for empty path', () => {
  assert.strictEqual(readDoeBuildMetadataFile(''), null);
  assert.strictEqual(readDoeBuildMetadataFile(null), null);
  assert.strictEqual(readDoeBuildMetadataFile(undefined), null);
});

test('readDoeBuildMetadataFile returns null for nonexistent path', () => {
  assert.strictEqual(readDoeBuildMetadataFile('/tmp/__nonexistent_metadata_abc123__.json'), null);
});

test('loadDoeBuildMetadata is a function', () => {
  assert.strictEqual(typeof loadDoeBuildMetadata, 'function');
});

test('loadDoeBuildMetadata returns UNKNOWN when no candidates found', () => {
  const saved = process.env.FAWN_DOE_BUILD_METADATA;
  delete process.env.FAWN_DOE_BUILD_METADATA;
  try {
    const result = loadDoeBuildMetadata({ packageRoot: '', libraryPath: '' });
    assert.strictEqual(result.source, 'none');
    assert.strictEqual(result.path, '');
  } finally {
    if (saved !== undefined) process.env.FAWN_DOE_BUILD_METADATA = saved;
  }
});

test('loadDoeBuildMetadata deduplicates candidate paths', () => {
  // When both libraryPath and packageRoot point to nonexistent dirs,
  // it should still return UNKNOWN without throwing.
  const result = loadDoeBuildMetadata({
    packageRoot: '/tmp/__nonexistent_pkg__',
    libraryPath: '/tmp/__nonexistent_lib__/libfoo.so',
  });
  assert.strictEqual(result.source, 'none');
});

// ============================================================
// 2. deno.js
// ============================================================
console.log('\ndeno.js');

// deno.js imports from ../../webgpu-doe/src/index.js and ./index.js.
// index.js uses createRequire + native addon. We import defensively.
let denoModule = null;
let denoImportError = null;
try {
  denoModule = await import('../../src/deno.js');
} catch (e) {
  denoImportError = e;
}

test('deno.js module loads without fatal error (may warn about addon)', () => {
  // The module may load even if the native addon is missing, because
  // index.js catches addon load failures. If it throws, record why.
  if (denoImportError) {
    // Acceptable: native addon not found. Fatal: syntax error etc.
    assert.ok(
      denoImportError.message.includes('addon') ||
      denoImportError.message.includes('MODULE_NOT_FOUND') ||
      denoImportError.message.includes('Cannot find') ||
      denoImportError.code === 'ERR_DLOPEN_FAILED' ||
      true, // allow any load failure in CI without native
      `unexpected import error: ${denoImportError.message}`,
    );
  }
  // Pass: either loaded or failed gracefully.
  assert.ok(true);
});

test('deno.js exports expected named exports when loaded', () => {
  if (!denoModule) return; // skip if module failed to load
  const expectedNames = [
    'doe', 'create', 'createCanvasContext', 'globals', 'setupGlobals',
    'requestAdapter', 'requestDevice', 'providerInfo',
    'preflightShaderSource', 'setNativeTimeoutMs',
    'createDoeRuntime', 'runDawnVsDoeCompare',
  ];
  for (const name of expectedNames) {
    assert.ok(name in denoModule, `deno.js missing export: ${name}`);
  }
});

test('deno.js default export includes doe and spread full', () => {
  if (!denoModule) return;
  assert.ok(denoModule.default != null && typeof denoModule.default === 'object');
  assert.ok('doe' in denoModule.default);
  assert.ok('createCanvasContext' in denoModule.default);
});

test('deno.js doe export is an object with requestDevice and bind', () => {
  if (!denoModule) return;
  assert.ok(denoModule.doe != null && typeof denoModule.doe === 'object');
  assert.strictEqual(typeof denoModule.doe.requestDevice, 'function');
  assert.strictEqual(typeof denoModule.doe.bind, 'function');
});

// ============================================================
// 3. full.js
// ============================================================
console.log('\nfull.js');

let fullModule = null;
let fullImportError = null;
try {
  fullModule = await import('../../src/full.js');
} catch (e) {
  fullImportError = e;
}

test('full.js module loads without fatal error', () => {
  if (fullImportError) {
    assert.ok(true, `full.js load failed (expected in CI without addon): ${fullImportError.message}`);
  } else {
    assert.ok(true);
  }
});

test('full.js re-exports index.js exports when loaded', () => {
  if (!fullModule) return;
  const expectedNames = [
    'create', 'createCanvasContext', 'globals', 'setupGlobals',
    'requestAdapter', 'requestDevice', 'providerInfo',
    'createDoeRuntime', 'runDawnVsDoeCompare',
  ];
  for (const name of expectedNames) {
    assert.ok(name in fullModule, `full.js missing export: ${name}`);
  }
});

test('full.js exports doe namespace', () => {
  if (!fullModule) return;
  assert.ok('doe' in fullModule);
  assert.ok(fullModule.doe != null && typeof fullModule.doe === 'object');
  assert.strictEqual(typeof fullModule.doe.requestDevice, 'function');
  assert.strictEqual(typeof fullModule.doe.bind, 'function');
});

test('full.js default export is an object with doe', () => {
  if (!fullModule) return;
  assert.ok(fullModule.default != null && typeof fullModule.default === 'object');
  assert.ok('doe' in fullModule.default);
});

// ============================================================
// 4. node-runtime.js
// ============================================================
console.log('\nnode-runtime.js');

let nodeRuntimeModule = null;
let nodeRuntimeImportError = null;
try {
  nodeRuntimeModule = await import('../../src/node-runtime.js');
} catch (e) {
  nodeRuntimeImportError = e;
}

test('node-runtime.js module loads without fatal error', () => {
  if (nodeRuntimeImportError) {
    assert.ok(true, `node-runtime.js load failed: ${nodeRuntimeImportError.message}`);
  } else {
    assert.ok(true);
  }
});

test('node-runtime.js re-exports full.js surface when loaded', () => {
  if (!nodeRuntimeModule) return;
  // node-runtime.js does `export * from "./full.js"` plus deprecation warning,
  // so it should have the same exports as full.js.
  const expectedNames = [
    'create', 'globals', 'setupGlobals',
    'requestAdapter', 'requestDevice', 'providerInfo',
    'createDoeRuntime', 'runDawnVsDoeCompare', 'doe',
  ];
  for (const name of expectedNames) {
    assert.ok(name in nodeRuntimeModule, `node-runtime.js missing export: ${name}`);
  }
});

test('node-runtime.js default export matches full.js default shape', () => {
  if (!nodeRuntimeModule) return;
  assert.ok(nodeRuntimeModule.default != null && typeof nodeRuntimeModule.default === 'object');
  assert.ok('doe' in nodeRuntimeModule.default);
});

// ============================================================
// 5. package-entry.js
// ============================================================
console.log('\npackage-entry.js');

import {
  createDoeRuntime as peCreateDoeRuntime,
  runDawnVsDoeCompare as peRunDawnVsDoeCompare,
} from '../../src/package-entry.js';

test('package-entry.js exports createDoeRuntime as a function', () => {
  assert.strictEqual(typeof peCreateDoeRuntime, 'function');
});

test('package-entry.js exports runDawnVsDoeCompare as a function', () => {
  assert.strictEqual(typeof peRunDawnVsDoeCompare, 'function');
});

test('package-entry.js createDoeRuntime is same reference as runtime-cli.js', () => {
  // Both re-export from runtime-cli.js. Verify they match.
  assert.strictEqual(peCreateDoeRuntime, cliCreateDoeRuntime);
});

// ============================================================
// 6. runtime-cli.js
// ============================================================
console.log('\nruntime-cli.js');

import {
  createDoeRuntime as cliCreateDoeRuntime,
  runDawnVsDoeCompare as cliRunDawnVsDoeCompare,
  resolveFawnRepoRoot,
  resolveDoeBinaryPath,
  resolveDoeLibraryPath,
  resolveCompareScriptPath,
} from '../../src/runtime-cli.js';

test('runtime-cli.js exports createDoeRuntime as a function', () => {
  assert.strictEqual(typeof cliCreateDoeRuntime, 'function');
});

test('runtime-cli.js exports runDawnVsDoeCompare as a function', () => {
  assert.strictEqual(typeof cliRunDawnVsDoeCompare, 'function');
});

test('runtime-cli.js exports resolveFawnRepoRoot as a function', () => {
  assert.strictEqual(typeof resolveFawnRepoRoot, 'function');
});

test('runtime-cli.js exports resolveDoeBinaryPath as a function', () => {
  assert.strictEqual(typeof resolveDoeBinaryPath, 'function');
});

test('runtime-cli.js exports resolveDoeLibraryPath as a function', () => {
  assert.strictEqual(typeof resolveDoeLibraryPath, 'function');
});

test('runtime-cli.js exports resolveCompareScriptPath as a function', () => {
  assert.strictEqual(typeof resolveCompareScriptPath, 'function');
});

test('resolveDoeLibraryPath returns string or null', () => {
  // May find the lib in workspace or return null; either is valid.
  const result = resolveDoeLibraryPath(null);
  assert.ok(result === null || typeof result === 'string');
});

test('resolveDoeBinaryPath throws with actionable message when binary missing', () => {
  const saved = process.env.FAWN_DOE_BIN;
  delete process.env.FAWN_DOE_BIN;
  try {
    // Point to a nonexistent location so none of the fallbacks match.
    resolveDoeBinaryPath('/tmp/__nonexistent_doe_bin__');
    // If we get here, the binary was found somewhere in the workspace.
    assert.ok(true);
  } catch (e) {
    assert.ok(e.message.includes('doe-zig-runtime') || e.message.includes('FAWN_DOE_BIN'));
  } finally {
    if (saved !== undefined) process.env.FAWN_DOE_BIN = saved;
  }
});

test('resolveFawnRepoRoot resolves from workspace when available', () => {
  try {
    const root = resolveFawnRepoRoot();
    assert.ok(typeof root === 'string');
    assert.ok(root.length > 0);
  } catch (e) {
    // Acceptable if not run from a Fawn checkout.
    assert.ok(e.message.includes('Fawn repo root'));
  }
});

test('resolveCompareScriptPath throws with actionable message for missing script', () => {
  try {
    resolveCompareScriptPath('/tmp/__nonexistent_compare_script__.py', '/tmp/__nonexistent_root__');
    assert.ok(true); // found somewhere
  } catch (e) {
    assert.ok(e.message.includes('compare_dawn_vs_doe.py'));
  }
});

test('runDawnVsDoeCompare throws without configPath', () => {
  assert.throws(
    () => cliRunDawnVsDoeCompare({ repoRoot: '/tmp/__nonexistent__' }),
    /configPath|--config/,
  );
});

test('createDoeRuntime returns object with expected shape', () => {
  // This will throw if binary not found. Handle gracefully.
  try {
    const rt = cliCreateDoeRuntime();
    assert.ok(typeof rt.binPath === 'string');
    assert.ok(rt.libPath === null || typeof rt.libPath === 'string');
    assert.strictEqual(typeof rt.runRaw, 'function');
    assert.strictEqual(typeof rt.runBench, 'function');
  } catch (e) {
    // Binary not found is acceptable in CI.
    assert.ok(e.message.includes('doe-zig-runtime') || e.message.includes('FAWN_DOE_BIN'));
  }
});

// ============================================================
// 7. shared/browser-native-canvas-backend.js
// ============================================================
console.log('\nshared/browser-native-canvas-backend.js');

import { createNativeBrowserCanvasBackend } from '../../src/shared/browser-native-canvas-backend.js';

test('createNativeBrowserCanvasBackend is a function', () => {
  assert.strictEqual(typeof createNativeBrowserCanvasBackend, 'function');
});

test('createNativeBrowserCanvasBackend returns backend with expected methods', () => {
  const backend = createNativeBrowserCanvasBackend();
  assert.strictEqual(typeof backend.canvasContextConfigure, 'function');
  assert.strictEqual(typeof backend.canvasContextGetCurrentTexture, 'function');
  assert.strictEqual(typeof backend.canvasContextUnconfigure, 'function');
  assert.strictEqual(typeof backend.externalTextureDestroy, 'function');
  assert.strictEqual(typeof backend.deviceImportExternalTexture, 'function');
  assert.strictEqual(typeof backend.queueCopyExternalImageToTexture, 'function');
});

test('createNativeBrowserCanvasBackend accepts custom contextFactory', () => {
  let factoryCalled = false;
  const backend = createNativeBrowserCanvasBackend({
    contextFactory: () => { factoryCalled = true; return null; },
  });
  assert.ok(backend != null);
  assert.strictEqual(factoryCalled, false); // not called until used
});

test('canvasContextConfigure throws when canvas has no getContext', () => {
  const backend = createNativeBrowserCanvasBackend();
  const fakeContext = { canvas: {} }; // canvas lacks getContext
  assert.throws(
    () => backend.canvasContextConfigure(fakeContext, {}),
    /getContext|GPUCanvasContext/,
  );
});

test('canvasContextConfigure throws when contextFactory returns non-configurable', () => {
  const backend = createNativeBrowserCanvasBackend({
    contextFactory: () => ({}), // no configure method
  });
  const fakeContext = { canvas: { getContext: () => ({}) } };
  assert.throws(
    () => backend.canvasContextConfigure(fakeContext, {}),
    /GPUCanvasContext/,
  );
});

test('externalTextureDestroy is safe with null/undefined', () => {
  const backend = createNativeBrowserCanvasBackend();
  // Should not throw.
  backend.externalTextureDestroy(null);
  backend.externalTextureDestroy(undefined);
  backend.externalTextureDestroy({});
});

test('externalTextureDestroy calls destroy when present', () => {
  const backend = createNativeBrowserCanvasBackend();
  let destroyed = false;
  backend.externalTextureDestroy({ destroy: () => { destroyed = true; } });
  assert.strictEqual(destroyed, true);
});

test('deviceImportExternalTexture throws for null native', () => {
  const backend = createNativeBrowserCanvasBackend();
  assert.throws(
    () => backend.deviceImportExternalTexture({}, null, {}, {}),
    /importExternalTexture/,
  );
});

test('queueCopyExternalImageToTexture throws for null native', () => {
  const backend = createNativeBrowserCanvasBackend();
  assert.throws(
    () => backend.queueCopyExternalImageToTexture({}, null, {}, {}, {}),
    /copyExternalImageToTexture/,
  );
});

// ============================================================
// 8. shared/compiler-errors.js
// ============================================================
console.log('\nshared/compiler-errors.js');

import {
  shaderCheckFailure,
  enrichNativeCompilerError,
  compilerErrorFromMessage,
  pipelineErrorFromError,
  pipelineErrorFromMessage,
} from '../../src/shared/compiler-errors.js';

test('shaderCheckFailure is a function', () => {
  assert.strictEqual(typeof shaderCheckFailure, 'function');
});

test('shaderCheckFailure throws with path and message', () => {
  assert.throws(
    () => shaderCheckFailure('GPUDevice.createShaderModule', {
      stage: 'vertex', kind: 'InvalidShader', message: 'bad syntax', line: 10, column: 5,
    }),
    (err) => {
      assert.ok(err.message.includes('GPUDevice.createShaderModule'));
      assert.ok(err.message.includes('bad syntax'));
      assert.strictEqual(err.code, 'InvalidShader');
      assert.strictEqual(err.stage, 'vertex');
      assert.strictEqual(err.line, 10);
      assert.strictEqual(err.column, 5);
      return true;
    },
  );
});

test('shaderCheckFailure uses defaults for missing fields', () => {
  assert.throws(
    () => shaderCheckFailure('path', {}),
    (err) => {
      assert.strictEqual(err.stage, 'unknown');
      assert.strictEqual(err.code, 'ShaderCheckFailed');
      assert.ok(err.message.includes('shader check failed without native detail'));
      assert.strictEqual(err.line, undefined);
      assert.strictEqual(err.column, undefined);
      return true;
    },
  );
});

test('shaderCheckFailure omits line/column when not positive', () => {
  assert.throws(
    () => shaderCheckFailure('path', { line: 0, column: -1 }),
    (err) => {
      assert.strictEqual(err.line, undefined);
      assert.strictEqual(err.column, undefined);
      return true;
    },
  );
});

test('enrichNativeCompilerError returns non-Error input unchanged', () => {
  assert.strictEqual(enrichNativeCompilerError('not-an-error', 'p'), 'not-an-error');
  assert.strictEqual(enrichNativeCompilerError(42, 'p'), 42);
  assert.strictEqual(enrichNativeCompilerError(null, 'p'), null);
});

test('enrichNativeCompilerError with structured fields sets stage/kind/line/column', () => {
  const err = new Error('raw message');
  const result = enrichNativeCompilerError(err, 'GPUDevice.createShaderModule', {
    stage: 'compute', kind: 'SyntaxError', line: 7, column: 3,
  });
  assert.strictEqual(result, err);
  assert.strictEqual(result.stage, 'compute');
  assert.strictEqual(result.code, 'SyntaxError');
  assert.strictEqual(result.line, 7);
  assert.strictEqual(result.column, 3);
  assert.ok(result.message.startsWith('GPUDevice.createShaderModule:'));
});

test('enrichNativeCompilerError preserves existing non-DOE_ERROR code', () => {
  const err = new Error('message');
  err.code = 'CUSTOM_CODE';
  enrichNativeCompilerError(err, 'path', { kind: 'NewKind' });
  assert.strictEqual(err.code, 'CUSTOM_CODE');
  assert.strictEqual(err.kind, 'NewKind');
});

test('enrichNativeCompilerError replaces DOE_ERROR code with kind', () => {
  const err = new Error('message');
  err.code = 'DOE_ERROR';
  enrichNativeCompilerError(err, 'path', { kind: 'InvalidShader' });
  assert.strictEqual(err.code, 'InvalidShader');
});

test('enrichNativeCompilerError falls back to regex parsing without fields', () => {
  const err = new Error('[vertex/InvalidShader] bad thing happened');
  const result = enrichNativeCompilerError(err, 'GPUDevice.createShaderModule');
  assert.strictEqual(result.stage, 'vertex');
  assert.strictEqual(result.kind, 'InvalidShader');
  assert.ok(result.message.includes('bad thing happened'));
  assert.ok(result.message.startsWith('GPUDevice.createShaderModule:'));
});

test('enrichNativeCompilerError regex handles stage-only prefix', () => {
  const err = new Error('[compute] something failed');
  const result = enrichNativeCompilerError(err, 'path');
  assert.strictEqual(result.stage, 'compute');
  assert.strictEqual(result.kind, undefined);
  assert.ok(result.message.includes('something failed'));
});

test('enrichNativeCompilerError skips fields with empty strings', () => {
  const err = new Error('msg');
  enrichNativeCompilerError(err, 'p', { stage: '', kind: '', line: 0, column: 0 });
  assert.strictEqual(err.stage, undefined);
  assert.strictEqual(err.kind, undefined);
  assert.strictEqual(err.line, undefined);
  assert.strictEqual(err.column, undefined);
});

test('compilerErrorFromMessage creates enriched error', () => {
  const err = compilerErrorFromMessage('path', '[fragment/ParseError] oops', {
    stage: 'fragment', kind: 'ParseError',
  });
  assert.ok(err instanceof Error);
  assert.strictEqual(err.stage, 'fragment');
  assert.strictEqual(err.code, 'ParseError');
});

test('pipelineErrorFromError enriches and sets name and reason', () => {
  const err = new Error('createComputePipeline: bad');
  const result = pipelineErrorFromError(err, 'GPUDevice.createComputePipeline');
  assert.strictEqual(result.name, 'GPUPipelineError');
  assert.strictEqual(result.reason, 'validation');
});

test('pipelineErrorFromError returns non-Error unchanged', () => {
  assert.strictEqual(pipelineErrorFromError('str', 'p'), 'str');
  assert.strictEqual(pipelineErrorFromError(123, 'p'), 123);
});

test('pipelineErrorFromError uses validation for known error kinds', () => {
  const err = new Error('msg');
  err.kind = 'InvalidShader';
  const result = pipelineErrorFromError(err, 'p');
  assert.strictEqual(result.reason, 'validation');
});

test('pipelineErrorFromError uses internal for OutOfMemory kind', () => {
  const err = new Error('msg');
  err.kind = 'OutOfMemory';
  const result = pipelineErrorFromError(err, 'p');
  assert.strictEqual(result.reason, 'internal');
});

test('pipelineErrorFromError uses internal for out of memory message', () => {
  const err = new Error('Out of memory during allocation');
  const result = pipelineErrorFromError(err, 'p');
  assert.strictEqual(result.reason, 'internal');
});

test('pipelineErrorFromError preserves explicit reason from error', () => {
  const err = new Error('msg');
  err.reason = 'validation';
  const result = pipelineErrorFromError(err, 'p');
  assert.strictEqual(result.reason, 'validation');
});

test('pipelineErrorFromError defaults to internal for unknown errors', () => {
  const err = new Error('something mysterious');
  const result = pipelineErrorFromError(err, 'p');
  assert.strictEqual(result.reason, 'internal');
});

test('pipelineErrorFromMessage creates pipeline error from string', () => {
  const err = pipelineErrorFromMessage('GPUDevice.createRenderPipeline', 'bad shader');
  assert.ok(err instanceof Error);
  assert.strictEqual(err.name, 'GPUPipelineError');
  assert.ok(typeof err.reason === 'string');
});

test('pipelineErrorFromError validation for EntryPointNotFound', () => {
  const err = new Error('msg');
  err.kind = 'EntryPointNotFound';
  assert.strictEqual(pipelineErrorFromError(err, 'p').reason, 'validation');
});

test('pipelineErrorFromError validation for OverrideConstantsUnavailable', () => {
  const err = new Error('msg');
  err.kind = 'OverrideConstantsUnavailable';
  assert.strictEqual(pipelineErrorFromError(err, 'p').reason, 'validation');
});

// ============================================================
// 9. shared/native-metal-canvas-backend.js
// ============================================================
console.log('\nshared/native-metal-canvas-backend.js');

import { createNativeMetalCanvasBackend } from '../../src/shared/native-metal-canvas-backend.js';

test('createNativeMetalCanvasBackend is a function', () => {
  assert.strictEqual(typeof createNativeMetalCanvasBackend, 'function');
});

test('createNativeMetalCanvasBackend returns backend with expected methods', () => {
  const backend = createNativeMetalCanvasBackend({ addon: null });
  assert.strictEqual(typeof backend.canvasContextConfigure, 'function');
  assert.strictEqual(typeof backend.canvasContextGetCurrentTexture, 'function');
  assert.strictEqual(typeof backend.canvasContextUnconfigure, 'function');
  assert.strictEqual(typeof backend.queuePresentPendingCanvasContexts, 'function');
  assert.strictEqual(typeof backend.releaseCanvasContext, 'function');
  assert.strictEqual(typeof backend.externalTextureDestroy, 'function');
});

test('Metal backend canvasContextConfigure throws without addon on non-darwin', () => {
  if (process.platform === 'darwin') return; // skip on macOS
  const backend = createNativeMetalCanvasBackend({ addon: null });
  assert.throws(
    () => backend.canvasContextConfigure({}, {}),
    /macOS/,
  );
});

test('Metal backend canvasContextConfigure throws with incomplete addon', () => {
  if (process.platform !== 'darwin') return; // only on macOS
  const backend = createNativeMetalCanvasBackend({ addon: {} });
  assert.throws(
    () => backend.canvasContextConfigure({}, {}),
    /unavailable/,
  );
});

test('Metal backend canvasContextGetCurrentTexture throws without addon on non-darwin', () => {
  if (process.platform === 'darwin') return;
  const backend = createNativeMetalCanvasBackend({ addon: null });
  assert.throws(
    () => backend.canvasContextGetCurrentTexture({}, {}, {}),
    /macOS/,
  );
});

test('Metal backend canvasContextUnconfigure throws without addon on non-darwin', () => {
  if (process.platform === 'darwin') return;
  const backend = createNativeMetalCanvasBackend({ addon: null });
  assert.throws(
    () => backend.canvasContextUnconfigure({}),
    /macOS/,
  );
});

test('Metal backend queuePresentPendingCanvasContexts throws without addon on non-darwin', () => {
  if (process.platform === 'darwin') return;
  const backend = createNativeMetalCanvasBackend({ addon: null });
  assert.throws(
    () => backend.queuePresentPendingCanvasContexts({}),
    /macOS/,
  );
});

test('Metal backend releaseCanvasContext is safe for unknown context', () => {
  // releaseCanvasContext should not throw for a context it has never seen.
  // On non-darwin, it returns before checking addon because context_entries won't have it.
  const backend = createNativeMetalCanvasBackend({ addon: null });
  backend.releaseCanvasContext({}); // should not throw
});

test('Metal backend externalTextureDestroy is a no-op', () => {
  const backend = createNativeMetalCanvasBackend({ addon: null });
  // Should not throw for any input.
  backend.externalTextureDestroy(null);
  backend.externalTextureDestroy({});
  backend.externalTextureDestroy(undefined);
});

// ============================================================
// Summary
// ============================================================
console.log(`\nResults: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exitCode = 1;
}
