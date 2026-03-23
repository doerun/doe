import assert from 'node:assert/strict';

/**
 * Unit tests for the browser.js surface module.
 *
 * browser.js wraps the native browser WebGPU API (navigator.gpu).  Under
 * Node.js, navigator.gpu is unavailable, so these tests focus on:
 *
 *   - Export shape (all named and default exports exist with correct types).
 *   - Pure utility functions (normalizeOrigin2D, normalizeCanvasConfiguration).
 *   - CANVAS_* enum constants (values and freeze status).
 *   - providerInfo shape and error-path content.
 *   - Error messages when browser GPU is unavailable.
 *   - Internal helpers exposed via the module (normalize_origin3d, etc.).
 *
 * Run: node packages/webgpu/test/unit/test-unit-browser-surface.js
 */

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

// ---------------------------------------------------------------------------
// Imports — browser.js itself re-exports from shared modules and defines
// top-level functions.  The module loads without error under Node because it
// does not eagerly touch navigator.gpu.
// ---------------------------------------------------------------------------

import {
  createBrowserRuntime,
  create,
  createInstance,
  setupGlobals,
  requestAdapter,
  requestDevice,
  bindAdapter,
  bindDevice,
  createCanvasContext,
  providerInfo,
  globals,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
} from '../../src/browser.js';

import browserDefault from '../../src/browser.js';

// ============================================================
// Export shape — named exports
// ============================================================
console.log('\nexport shape — named exports');

test('createBrowserRuntime is a function', () => {
  assert.strictEqual(typeof createBrowserRuntime, 'function');
});

test('create is a function', () => {
  assert.strictEqual(typeof create, 'function');
});

test('createInstance is a function', () => {
  assert.strictEqual(typeof createInstance, 'function');
});

test('setupGlobals is a function', () => {
  assert.strictEqual(typeof setupGlobals, 'function');
});

test('requestAdapter is an async function', () => {
  assert.strictEqual(typeof requestAdapter, 'function');
});

test('requestDevice is an async function', () => {
  assert.strictEqual(typeof requestDevice, 'function');
});

test('bindAdapter is a function', () => {
  assert.strictEqual(typeof bindAdapter, 'function');
});

test('bindDevice is a function', () => {
  assert.strictEqual(typeof bindDevice, 'function');
});

test('createCanvasContext is a function', () => {
  assert.strictEqual(typeof createCanvasContext, 'function');
});

test('providerInfo is a function', () => {
  assert.strictEqual(typeof providerInfo, 'function');
});

test('globals is an object', () => {
  assert.strictEqual(typeof globals, 'object');
  assert.ok(globals !== null);
});

test('CANVAS_ALPHA_MODES is an object', () => {
  assert.strictEqual(typeof CANVAS_ALPHA_MODES, 'object');
});

test('CANVAS_TONE_MAPPING_MODES is an object', () => {
  assert.strictEqual(typeof CANVAS_TONE_MAPPING_MODES, 'object');
});

test('CANVAS_COLOR_SPACES is an object', () => {
  assert.strictEqual(typeof CANVAS_COLOR_SPACES, 'object');
});

test('normalizeOrigin2D is a function', () => {
  assert.strictEqual(typeof normalizeOrigin2D, 'function');
});

test('normalizeCanvasConfiguration is a function', () => {
  assert.strictEqual(typeof normalizeCanvasConfiguration, 'function');
});

test('createBrowserSurfaceClasses is a function', () => {
  assert.strictEqual(typeof createBrowserSurfaceClasses, 'function');
});

test('createNativeBrowserCanvasBackend is a function', () => {
  assert.strictEqual(typeof createNativeBrowserCanvasBackend, 'function');
});

// ============================================================
// Export shape — default export
// ============================================================
console.log('\nexport shape — default export');

test('default export has all expected keys', () => {
  const expected = [
    'createBrowserRuntime', 'create', 'createInstance', 'setupGlobals',
    'requestAdapter', 'requestDevice', 'bindAdapter', 'bindDevice',
    'createCanvasContext', 'providerInfo', 'globals',
    'CANVAS_ALPHA_MODES', 'CANVAS_TONE_MAPPING_MODES', 'CANVAS_COLOR_SPACES',
    'normalizeOrigin2D', 'normalizeCanvasConfiguration',
    'createBrowserSurfaceClasses', 'createNativeBrowserCanvasBackend',
  ];
  for (const key of expected) {
    assert.ok(key in browserDefault, `default export missing "${key}"`);
  }
});

test('default export functions match named exports', () => {
  assert.strictEqual(browserDefault.create, create);
  assert.strictEqual(browserDefault.providerInfo, providerInfo);
  assert.strictEqual(browserDefault.globals, globals);
  assert.strictEqual(browserDefault.normalizeOrigin2D, normalizeOrigin2D);
});

// ============================================================
// globals
// ============================================================
console.log('\nglobals');

test('globals has GPUBufferUsage with standard flags', () => {
  assert.ok(globals.GPUBufferUsage);
  assert.strictEqual(globals.GPUBufferUsage.MAP_READ, 0x0001);
  assert.strictEqual(globals.GPUBufferUsage.MAP_WRITE, 0x0002);
  assert.strictEqual(globals.GPUBufferUsage.COPY_SRC, 0x0004);
  assert.strictEqual(globals.GPUBufferUsage.COPY_DST, 0x0008);
  assert.strictEqual(globals.GPUBufferUsage.UNIFORM, 0x0040);
  assert.strictEqual(globals.GPUBufferUsage.STORAGE, 0x0080);
});

test('globals has GPUShaderStage', () => {
  assert.ok(globals.GPUShaderStage);
  assert.strictEqual(globals.GPUShaderStage.VERTEX, 0x1);
  assert.strictEqual(globals.GPUShaderStage.FRAGMENT, 0x2);
  assert.strictEqual(globals.GPUShaderStage.COMPUTE, 0x4);
});

test('globals has GPUTextureUsage', () => {
  assert.ok(globals.GPUTextureUsage);
  assert.strictEqual(globals.GPUTextureUsage.RENDER_ATTACHMENT, 0x10);
});

test('globals has GPUMapMode', () => {
  assert.ok(globals.GPUMapMode);
  assert.strictEqual(globals.GPUMapMode.READ, 0x0001);
});

test('globals has GPUColorWrite', () => {
  assert.ok(globals.GPUColorWrite);
  assert.strictEqual(globals.GPUColorWrite.ALL, 0xf);
});

// ============================================================
// CANVAS_ALPHA_MODES
// ============================================================
console.log('\nCANVAS_ALPHA_MODES');

test('contains opaque and premultiplied', () => {
  assert.strictEqual(CANVAS_ALPHA_MODES.opaque, 'opaque');
  assert.strictEqual(CANVAS_ALPHA_MODES.premultiplied, 'premultiplied');
});

test('has exactly 2 keys', () => {
  assert.strictEqual(Object.keys(CANVAS_ALPHA_MODES).length, 2);
});

test('is frozen', () => {
  assert.ok(Object.isFrozen(CANVAS_ALPHA_MODES));
});

// ============================================================
// CANVAS_TONE_MAPPING_MODES
// ============================================================
console.log('\nCANVAS_TONE_MAPPING_MODES');

test('contains standard and extended', () => {
  assert.strictEqual(CANVAS_TONE_MAPPING_MODES.standard, 'standard');
  assert.strictEqual(CANVAS_TONE_MAPPING_MODES.extended, 'extended');
});

test('has exactly 2 keys', () => {
  assert.strictEqual(Object.keys(CANVAS_TONE_MAPPING_MODES).length, 2);
});

test('is frozen', () => {
  assert.ok(Object.isFrozen(CANVAS_TONE_MAPPING_MODES));
});

// ============================================================
// CANVAS_COLOR_SPACES
// ============================================================
console.log('\nCANVAS_COLOR_SPACES');

test('contains srgb and display-p3', () => {
  assert.strictEqual(CANVAS_COLOR_SPACES.srgb, 'srgb');
  assert.strictEqual(CANVAS_COLOR_SPACES['display-p3'], 'display-p3');
});

test('has exactly 2 keys', () => {
  assert.strictEqual(Object.keys(CANVAS_COLOR_SPACES).length, 2);
});

test('is frozen', () => {
  assert.ok(Object.isFrozen(CANVAS_COLOR_SPACES));
});

// ============================================================
// normalizeOrigin2D
// ============================================================
console.log('\nnormalizeOrigin2D');

test('undefined returns { x: 0, y: 0 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D(undefined, 'test'), { x: 0, y: 0 });
});

test('null returns { x: 0, y: 0 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D(null, 'test'), { x: 0, y: 0 });
});

test('array [10, 20] returns correct values', () => {
  const result = normalizeOrigin2D([10, 20], 'test');
  assert.strictEqual(result.x, 10);
  assert.strictEqual(result.y, 20);
});

test('array [5] fills missing y with 0', () => {
  const result = normalizeOrigin2D([5], 'test');
  assert.strictEqual(result.x, 5);
  assert.strictEqual(result.y, 0);
});

test('empty array returns { x: 0, y: 0 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D([], 'test'), { x: 0, y: 0 });
});

test('object { x: 3, y: 7 } returns matching values', () => {
  const result = normalizeOrigin2D({ x: 3, y: 7 }, 'test');
  assert.strictEqual(result.x, 3);
  assert.strictEqual(result.y, 7);
});

test('object with only x returns { x: value, y: 0 }', () => {
  const result = normalizeOrigin2D({ x: 42 }, 'test');
  assert.strictEqual(result.x, 42);
  assert.strictEqual(result.y, 0);
});

test('empty object returns { x: 0, y: 0 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D({}, 'test'), { x: 0, y: 0 });
});

// ============================================================
// normalizeCanvasConfiguration
// ============================================================
console.log('\nnormalizeCanvasConfiguration');

function makeLiveDevice(label = 'GPUDevice') {
  return { _native: {}, _destroyed: false, _resourceLabel: label, _resourceOwner: null };
}

test('accepts minimal valid configuration', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration({ device, format: 'bgra8unorm' }, 'test');
  assert.strictEqual(result.format, 'bgra8unorm');
  assert.strictEqual(result.alphaMode, 'opaque');
  assert.strictEqual(result.colorSpace, 'srgb');
  assert.strictEqual(result.toneMapping.mode, 'standard');
  assert.strictEqual(result.usage, 0x10);  // RENDER_ATTACHMENT
  assert.deepStrictEqual(result.viewFormats, []);
});

test('accepts premultiplied alphaMode', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'rgba8unorm', alphaMode: 'premultiplied' },
    'test',
  );
  assert.strictEqual(result.alphaMode, 'premultiplied');
});

test('accepts display-p3 colorSpace', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'bgra8unorm', colorSpace: 'display-p3' },
    'test',
  );
  assert.strictEqual(result.colorSpace, 'display-p3');
});

test('accepts extended toneMapping mode', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'bgra8unorm', toneMapping: { mode: 'extended' } },
    'test',
  );
  assert.strictEqual(result.toneMapping.mode, 'extended');
});

test('throws on missing format', () => {
  const device = makeLiveDevice();
  assert.throws(
    () => normalizeCanvasConfiguration({ device }, 'test'),
    /format is required/,
  );
});

test('throws on invalid alphaMode', () => {
  const device = makeLiveDevice();
  assert.throws(
    () => normalizeCanvasConfiguration({ device, format: 'bgra8unorm', alphaMode: 'postmultiplied' }, 'test'),
    /alphaMode must be one of/,
  );
});

test('throws on invalid colorSpace', () => {
  const device = makeLiveDevice();
  assert.throws(
    () => normalizeCanvasConfiguration({ device, format: 'bgra8unorm', colorSpace: 'prophoto' }, 'test'),
    /colorSpace must be one of/,
  );
});

test('throws on invalid toneMapping mode', () => {
  const device = makeLiveDevice();
  assert.throws(
    () => normalizeCanvasConfiguration({ device, format: 'bgra8unorm', toneMapping: { mode: 'filmic' } }, 'test'),
    /toneMapping\.mode must be one of/,
  );
});

test('throws when device is null', () => {
  assert.throws(
    () => normalizeCanvasConfiguration({ device: null, format: 'bgra8unorm' }, 'test'),
  );
});

test('throws when device is destroyed', () => {
  const device = makeLiveDevice();
  device._destroyed = true;
  assert.throws(
    () => normalizeCanvasConfiguration({ device, format: 'bgra8unorm' }, 'test'),
  );
});

test('preserves viewFormats', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'bgra8unorm', viewFormats: ['rgba8unorm', 'bgra8unorm-srgb'] },
    'test',
  );
  assert.deepStrictEqual(result.viewFormats, ['rgba8unorm', 'bgra8unorm-srgb']);
});

test('non-array viewFormats defaults to empty array', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'bgra8unorm', viewFormats: 'not-an-array' },
    'test',
  );
  assert.deepStrictEqual(result.viewFormats, []);
});

test('custom usage value is preserved', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'bgra8unorm', usage: 0x04 | 0x10 },
    'test',
  );
  assert.strictEqual(result.usage, 0x04 | 0x10);
});

// ============================================================
// providerInfo
// ============================================================
console.log('\nproviderInfo');

test('returns an object with expected fields', () => {
  const info = providerInfo();
  assert.strictEqual(typeof info, 'object');
  assert.ok('module' in info);
  assert.ok('loaded' in info);
  assert.ok('loadError' in info);
  assert.ok('doeNative' in info);
  assert.ok('libraryFlavor' in info);
  assert.ok('doeLibraryPath' in info);
  assert.ok('buildMetadataSource' in info);
  assert.ok('buildMetadataPath' in info);
  assert.ok('leanVerifiedBuild' in info);
  assert.ok('proofArtifactSha256' in info);
});

test('module name is @simulatte/webgpu/browser', () => {
  const info = providerInfo();
  assert.strictEqual(info.module, '@simulatte/webgpu/browser');
});

test('doeNative is false for browser surface', () => {
  const info = providerInfo();
  assert.strictEqual(info.doeNative, false);
});

test('libraryFlavor is browser-native', () => {
  const info = providerInfo();
  assert.strictEqual(info.libraryFlavor, 'browser-native');
});

test('doeLibraryPath is empty for browser surface', () => {
  const info = providerInfo();
  assert.strictEqual(info.doeLibraryPath, '');
});

test('loaded is false when navigator.gpu is unavailable', () => {
  // Under Node.js, navigator.gpu does not exist
  const info = providerInfo();
  assert.strictEqual(info.loaded, false);
});

test('loadError is actionable when navigator.gpu is unavailable', () => {
  const info = providerInfo();
  assert.ok(info.loadError.length > 0, 'loadError should be non-empty');
  assert.ok(
    /navigator\.gpu|unavailable/.test(info.loadError),
    `loadError should mention navigator.gpu, got: "${info.loadError}"`,
  );
});

test('leanVerifiedBuild is false for browser surface', () => {
  const info = providerInfo();
  assert.strictEqual(info.leanVerifiedBuild, false);
});

test('proofArtifactSha256 is null for browser surface', () => {
  const info = providerInfo();
  assert.strictEqual(info.proofArtifactSha256, null);
});

// ============================================================
// Error messages when browser GPU is unavailable
// ============================================================
console.log('\nerror messages — no browser GPU');

test('createBrowserRuntime throws when navigator.gpu is unavailable', () => {
  assert.throws(
    () => createBrowserRuntime(),
    /navigator\.gpu is unavailable|pass \{ gpu \} explicitly/,
  );
});

test('create throws when navigator.gpu is unavailable', () => {
  assert.throws(
    () => create(),
    /navigator\.gpu is unavailable|pass \{ gpu \} explicitly/,
  );
});

test('createInstance throws when navigator.gpu is unavailable', () => {
  assert.throws(
    () => createInstance(),
    /navigator\.gpu is unavailable|pass \{ gpu \} explicitly/,
  );
});

test('setupGlobals throws when navigator.gpu is unavailable', () => {
  assert.throws(
    () => setupGlobals({}),
    /navigator\.gpu is unavailable|pass \{ gpu \} explicitly/,
  );
});

test('requestAdapter rejects when navigator.gpu is unavailable', async () => {
  try {
    await requestAdapter();
    assert.fail('expected rejection');
  } catch (err) {
    assert.ok(
      /navigator\.gpu is unavailable|pass \{ gpu \} explicitly/.test(err.message),
      `expected actionable error, got: "${err.message}"`,
    );
  }
});

test('requestDevice rejects when navigator.gpu is unavailable', async () => {
  try {
    await requestDevice();
    assert.fail('expected rejection');
  } catch (err) {
    assert.ok(
      /navigator\.gpu is unavailable|pass \{ gpu \} explicitly/.test(err.message),
      `expected actionable error, got: "${err.message}"`,
    );
  }
});

test('bindAdapter throws when given non-object', () => {
  assert.throws(
    () => bindAdapter(null),
    /must be a native browser WebGPU object|navigator\.gpu/,
  );
});

test('bindDevice throws when given non-object', () => {
  assert.throws(
    () => bindDevice(null),
    /must be a native browser WebGPU object|navigator\.gpu/,
  );
});

// ============================================================
// Summary
// ============================================================
console.log(`\nResults: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exitCode = 1;
}
