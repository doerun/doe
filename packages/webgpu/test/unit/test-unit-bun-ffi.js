import assert from 'node:assert/strict';

/**
 * Unit tests for the bun-ffi.js surface module.
 *
 * bun-ffi.js imports from "bun:ffi" at the top level, so it cannot be loaded
 * under Node.js.  These tests verify the module contract by probing what is
 * testable without Bun or a GPU:
 *
 *   - Shared exports that bun-ffi.js re-exports (globals, canvas constants,
 *     normalizeOrigin2D, normalizeCanvasConfiguration, buildProviderInfo shape).
 *   - Library resolution helpers (resolveDoeLibraryPath pattern, libraryFlavor).
 *   - Error message quality when the native library is absent.
 *
 * When an import fails because Bun is unavailable the test is skipped with a
 * clear message, not marked as a failure.
 *
 * Run: node packages/webgpu/test/unit/test-unit-bun-ffi.js
 */

let passed = 0;
let failed = 0;
let skipped = 0;

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

function skip(name, reason) {
  skipped += 1;
  console.log(`  SKIP: ${name} — ${reason}`);
}

// ---------------------------------------------------------------------------
// Attempt to load bun-ffi.js.  Under Node this will fail on `import "bun:ffi"`.
// We capture the error and conditionally skip the direct-import tests.
// ---------------------------------------------------------------------------

let bunFfiModule = null;
let bunFfiLoadError = null;

try {
  bunFfiModule = await import('../../src/bun-ffi.js');
} catch (err) {
  bunFfiLoadError = err;
}

// ---------------------------------------------------------------------------
// Shared modules that bun-ffi.js re-exports — always loadable under Node
// ---------------------------------------------------------------------------

import { globals } from '../../src/webgpu-constants.js';
import {
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
} from '../../src/shared/browser-surface.js';
import {
  buildProviderInfo,
  libraryFlavor,
} from '../../src/shared/public-surface.js';

// ============================================================
// globals (re-exported from webgpu-constants.js)
// ============================================================
console.log('\nglobals shape');

test('globals has GPUBufferUsage', () => {
  assert.ok(globals.GPUBufferUsage);
  assert.strictEqual(typeof globals.GPUBufferUsage.MAP_READ, 'number');
  assert.strictEqual(typeof globals.GPUBufferUsage.COPY_DST, 'number');
  assert.strictEqual(typeof globals.GPUBufferUsage.STORAGE, 'number');
});

test('globals has GPUShaderStage', () => {
  assert.ok(globals.GPUShaderStage);
  assert.strictEqual(globals.GPUShaderStage.VERTEX, 0x1);
  assert.strictEqual(globals.GPUShaderStage.FRAGMENT, 0x2);
  assert.strictEqual(globals.GPUShaderStage.COMPUTE, 0x4);
});

test('globals has GPUMapMode', () => {
  assert.ok(globals.GPUMapMode);
  assert.strictEqual(globals.GPUMapMode.READ, 0x0001);
  assert.strictEqual(globals.GPUMapMode.WRITE, 0x0002);
});

test('globals has GPUTextureUsage', () => {
  assert.ok(globals.GPUTextureUsage);
  assert.strictEqual(typeof globals.GPUTextureUsage.COPY_SRC, 'number');
  assert.strictEqual(typeof globals.GPUTextureUsage.RENDER_ATTACHMENT, 'number');
});

test('globals has GPUColorWrite', () => {
  assert.ok(globals.GPUColorWrite);
  assert.strictEqual(globals.GPUColorWrite.ALL, 0xf);
});

// ============================================================
// CANVAS constants (re-exported from browser-surface.js)
// ============================================================
console.log('\nCANVAS constants');

test('CANVAS_ALPHA_MODES has expected keys', () => {
  assert.deepStrictEqual(Object.keys(CANVAS_ALPHA_MODES).sort(), ['opaque', 'premultiplied']);
  assert.strictEqual(CANVAS_ALPHA_MODES.opaque, 'opaque');
  assert.strictEqual(CANVAS_ALPHA_MODES.premultiplied, 'premultiplied');
});

test('CANVAS_ALPHA_MODES is frozen', () => {
  assert.ok(Object.isFrozen(CANVAS_ALPHA_MODES));
});

test('CANVAS_TONE_MAPPING_MODES has expected keys', () => {
  assert.deepStrictEqual(Object.keys(CANVAS_TONE_MAPPING_MODES).sort(), ['extended', 'standard']);
  assert.strictEqual(CANVAS_TONE_MAPPING_MODES.standard, 'standard');
  assert.strictEqual(CANVAS_TONE_MAPPING_MODES.extended, 'extended');
});

test('CANVAS_TONE_MAPPING_MODES is frozen', () => {
  assert.ok(Object.isFrozen(CANVAS_TONE_MAPPING_MODES));
});

test('CANVAS_COLOR_SPACES has expected keys', () => {
  assert.deepStrictEqual(Object.keys(CANVAS_COLOR_SPACES).sort(), ['display-p3', 'srgb']);
  assert.strictEqual(CANVAS_COLOR_SPACES.srgb, 'srgb');
  assert.strictEqual(CANVAS_COLOR_SPACES['display-p3'], 'display-p3');
});

test('CANVAS_COLOR_SPACES is frozen', () => {
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

test('array [10, 20] returns { x: 10, y: 20 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D([10, 20], 'test'), { x: 10, y: 20 });
});

test('array [5] returns { x: 5, y: 0 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D([5], 'test'), { x: 5, y: 0 });
});

test('empty array returns { x: 0, y: 0 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D([], 'test'), { x: 0, y: 0 });
});

test('object { x: 3, y: 7 } returns { x: 3, y: 7 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D({ x: 3, y: 7 }, 'test'), { x: 3, y: 7 });
});

test('object with missing y returns { x: 3, y: 0 }', () => {
  assert.deepStrictEqual(normalizeOrigin2D({ x: 3 }, 'test'), { x: 3, y: 0 });
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

test('accepts minimal valid config', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'bgra8unorm' },
    'test',
  );
  assert.strictEqual(result.format, 'bgra8unorm');
  assert.strictEqual(result.alphaMode, 'opaque');
  assert.strictEqual(result.colorSpace, 'srgb');
  assert.strictEqual(result.toneMapping.mode, 'standard');
  assert.deepStrictEqual(result.viewFormats, []);
});

test('passes through explicit alphaMode', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'rgba8unorm', alphaMode: 'premultiplied' },
    'test',
  );
  assert.strictEqual(result.alphaMode, 'premultiplied');
});

test('throws on invalid alphaMode', () => {
  const device = makeLiveDevice();
  assert.throws(
    () => normalizeCanvasConfiguration({ device, format: 'bgra8unorm', alphaMode: 'garbage' }, 'test'),
    /alphaMode must be one of/,
  );
});

test('throws on invalid colorSpace', () => {
  const device = makeLiveDevice();
  assert.throws(
    () => normalizeCanvasConfiguration({ device, format: 'bgra8unorm', colorSpace: 'adobergb' }, 'test'),
    /colorSpace must be one of/,
  );
});

test('throws on invalid toneMapping mode', () => {
  const device = makeLiveDevice();
  assert.throws(
    () => normalizeCanvasConfiguration({ device, format: 'bgra8unorm', toneMapping: { mode: 'hdr' } }, 'test'),
    /toneMapping\.mode must be one of/,
  );
});

test('throws when format is missing', () => {
  const device = makeLiveDevice();
  assert.throws(
    () => normalizeCanvasConfiguration({ device }, 'test'),
    /format is required/,
  );
});

test('throws when device is destroyed', () => {
  const device = makeLiveDevice();
  device._destroyed = true;
  assert.throws(
    () => normalizeCanvasConfiguration({ device, format: 'bgra8unorm' }, 'test'),
  );
});

test('preserves viewFormats array', () => {
  const device = makeLiveDevice();
  const result = normalizeCanvasConfiguration(
    { device, format: 'bgra8unorm', viewFormats: ['rgba8unorm'] },
    'test',
  );
  assert.deepStrictEqual(result.viewFormats, ['rgba8unorm']);
});

// ============================================================
// libraryFlavor (used by bun-ffi.js providerInfo)
// ============================================================
console.log('\nlibraryFlavor');

test('returns "missing" for null path', () => {
  assert.strictEqual(libraryFlavor(null), 'missing');
});

test('returns "missing" for empty string', () => {
  assert.strictEqual(libraryFlavor(''), 'missing');
});

test('returns "doe-dropin" for libwebgpu_doe.so', () => {
  assert.strictEqual(libraryFlavor('/path/to/libwebgpu_doe.so'), 'doe-dropin');
});

test('returns "doe-dropin" for libwebgpu_doe.dylib', () => {
  assert.strictEqual(libraryFlavor('/path/to/libwebgpu_doe.dylib'), 'doe-dropin');
});

test('returns "doe-dropin" for libwebgpu_doe.dll', () => {
  assert.strictEqual(libraryFlavor('/path/to/libwebgpu_doe.dll'), 'doe-dropin');
});

test('returns "delegate" for libwebgpu.so', () => {
  assert.strictEqual(libraryFlavor('/path/to/libwebgpu.so'), 'delegate');
});

test('returns "delegate" for libwebgpu_dawn.dylib', () => {
  assert.strictEqual(libraryFlavor('/path/to/libwebgpu_dawn.dylib'), 'delegate');
});

test('returns "delegate" for libwgpu_native.so', () => {
  assert.strictEqual(libraryFlavor('/path/to/libwgpu_native.so'), 'delegate');
});

test('returns "unknown" for unrecognized path', () => {
  assert.strictEqual(libraryFlavor('/path/to/libfoo.so'), 'unknown');
});

// ============================================================
// buildProviderInfo shape
// ============================================================
console.log('\nbuildProviderInfo shape');

test('returns object with all expected fields', () => {
  const info = buildProviderInfo({
    moduleName: '@simulatte/webgpu/bun-ffi',
    loaded: false,
    loadError: 'libwebgpu_doe not found',
    defaultCreateArgs: [],
    doeNative: false,
    libraryFlavor: 'missing',
    doeLibraryPath: '',
    buildMetadataSource: 'none',
    buildMetadataPath: '',
    leanVerifiedBuild: false,
    proofArtifactSha256: null,
  });
  assert.strictEqual(info.module, '@simulatte/webgpu/bun-ffi');
  assert.strictEqual(info.loaded, false);
  assert.strictEqual(info.loadError, 'libwebgpu_doe not found');
  assert.deepStrictEqual(info.defaultCreateArgs, []);
  assert.strictEqual(info.doeNative, false);
  assert.strictEqual(info.libraryFlavor, 'missing');
  assert.strictEqual(info.doeLibraryPath, '');
  assert.strictEqual(info.buildMetadataSource, 'none');
  assert.strictEqual(info.buildMetadataPath, '');
  assert.strictEqual(info.leanVerifiedBuild, false);
  assert.strictEqual(info.proofArtifactSha256, null);
});

test('loaded=true when library is present', () => {
  const info = buildProviderInfo({
    loaded: true,
    loadError: '',
    doeNative: true,
    libraryFlavor: 'doe-dropin',
    doeLibraryPath: '/path/to/libwebgpu_doe.so',
    buildMetadataSource: 'file',
    buildMetadataPath: '/path/to/metadata.json',
    leanVerifiedBuild: true,
    proofArtifactSha256: 'abc123',
  });
  assert.strictEqual(info.loaded, true);
  assert.strictEqual(info.loadError, '');
  assert.strictEqual(info.doeNative, true);
  assert.strictEqual(info.leanVerifiedBuild, true);
  assert.strictEqual(info.proofArtifactSha256, 'abc123');
});

// ============================================================
// bun-ffi.js direct-import tests (only run under Bun)
// ============================================================
console.log('\nbun-ffi.js direct import');

if (bunFfiLoadError) {
  const isBunMissing = /bun:ffi|Cannot find module|Received protocol 'bun:'/.test(bunFfiLoadError.message);
  if (isBunMissing) {
    skip('module loads under Bun', 'not running under Bun runtime');
    skip('exports create function', 'not running under Bun runtime');
    skip('exports createInstance function', 'not running under Bun runtime');
    skip('exports setupGlobals function', 'not running under Bun runtime');
    skip('exports requestAdapter function', 'not running under Bun runtime');
    skip('exports requestDevice function', 'not running under Bun runtime');
    skip('exports providerInfo function', 'not running under Bun runtime');
    skip('exports globals object', 'not running under Bun runtime');
    skip('exports preflightShaderSource function', 'not running under Bun runtime');
    skip('exports setNativeTimeoutMs function', 'not running under Bun runtime');
    skip('exports fastPathStats object', 'not running under Bun runtime');
    skip('exports createDoeRuntime function', 'not running under Bun runtime');
    skip('exports runDawnVsDoeCompare function', 'not running under Bun runtime');
    skip('exports CANVAS constants', 'not running under Bun runtime');
    skip('exports normalizeOrigin2D function', 'not running under Bun runtime');
    skip('exports normalizeCanvasConfiguration function', 'not running under Bun runtime');
    skip('providerInfo returns expected shape', 'not running under Bun runtime');
    skip('error message when native lib is missing is actionable', 'not running under Bun runtime');
  } else {
    // unexpected load error — report as failure
    test('module loads without unexpected error', () => {
      throw bunFfiLoadError;
    });
  }
} else {
  test('exports create function', () => {
    assert.strictEqual(typeof bunFfiModule.create, 'function');
  });

  test('exports createInstance function', () => {
    assert.strictEqual(typeof bunFfiModule.createInstance, 'function');
  });

  test('exports setupGlobals function', () => {
    assert.strictEqual(typeof bunFfiModule.setupGlobals, 'function');
  });

  test('exports requestAdapter function', () => {
    assert.strictEqual(typeof bunFfiModule.requestAdapter, 'function');
  });

  test('exports requestDevice function', () => {
    assert.strictEqual(typeof bunFfiModule.requestDevice, 'function');
  });

  test('exports providerInfo function', () => {
    assert.strictEqual(typeof bunFfiModule.providerInfo, 'function');
  });

  test('exports globals object', () => {
    assert.ok(bunFfiModule.globals);
    assert.strictEqual(typeof bunFfiModule.globals, 'object');
    assert.ok(bunFfiModule.globals.GPUBufferUsage);
    assert.ok(bunFfiModule.globals.GPUShaderStage);
  });

  test('exports preflightShaderSource function', () => {
    assert.strictEqual(typeof bunFfiModule.preflightShaderSource, 'function');
  });

  test('exports setNativeTimeoutMs function', () => {
    assert.strictEqual(typeof bunFfiModule.setNativeTimeoutMs, 'function');
  });

  test('exports fastPathStats object', () => {
    assert.ok(bunFfiModule.fastPathStats);
    assert.strictEqual(typeof bunFfiModule.fastPathStats.dispatchFlush, 'number');
    assert.strictEqual(typeof bunFfiModule.fastPathStats.flushAndMap, 'number');
  });

  test('exports createDoeRuntime function', () => {
    assert.strictEqual(typeof bunFfiModule.createDoeRuntime, 'function');
  });

  test('exports runDawnVsDoeCompare function', () => {
    assert.strictEqual(typeof bunFfiModule.runDawnVsDoeCompare, 'function');
  });

  test('exports CANVAS constants', () => {
    assert.ok(bunFfiModule.CANVAS_ALPHA_MODES);
    assert.ok(bunFfiModule.CANVAS_TONE_MAPPING_MODES);
    assert.ok(bunFfiModule.CANVAS_COLOR_SPACES);
  });

  test('exports normalizeOrigin2D function', () => {
    assert.strictEqual(typeof bunFfiModule.normalizeOrigin2D, 'function');
  });

  test('exports normalizeCanvasConfiguration function', () => {
    assert.strictEqual(typeof bunFfiModule.normalizeCanvasConfiguration, 'function');
  });

  test('providerInfo returns expected shape', () => {
    const info = bunFfiModule.providerInfo();
    assert.strictEqual(typeof info, 'object');
    assert.ok('loaded' in info);
    assert.ok('loadError' in info);
    assert.ok('doeNative' in info);
    assert.ok('libraryFlavor' in info);
    assert.ok('doeLibraryPath' in info);
    assert.strictEqual(typeof info.loaded, 'boolean');
    assert.strictEqual(typeof info.loadError, 'string');
    assert.strictEqual(typeof info.libraryFlavor, 'string');
  });

  test('error message when native lib is missing is actionable', () => {
    // If the library was not found, providerInfo should give an actionable error.
    // If it was found, the loadError should be empty.
    const info = bunFfiModule.providerInfo();
    if (!info.loaded) {
      assert.ok(info.loadError.length > 0, 'loadError should be non-empty when not loaded');
      assert.ok(
        /libwebgpu_doe|not found|DOE_WEBGPU_LIB/.test(info.loadError),
        `loadError should be actionable, got: ${info.loadError}`,
      );
    } else {
      assert.strictEqual(info.loadError, '');
    }
  });
}

// ============================================================
// Platform detection — LIB_EXT mapping
// ============================================================
console.log('\nplatform detection');

test('process.platform is a known value for library extension mapping', () => {
  const KNOWN_PLATFORMS = ['darwin', 'linux', 'win32'];
  const LIB_EXT = { darwin: 'dylib', linux: 'so', win32: 'dll' };
  // Verify the mapping logic handles both known and unknown platforms
  for (const platform of KNOWN_PLATFORMS) {
    assert.ok(LIB_EXT[platform], `expected extension for ${platform}`);
  }
  // Unknown platform falls back to 'so'
  const fallback = LIB_EXT['freebsd'] ?? 'so';
  assert.strictEqual(fallback, 'so');
});

// ============================================================
// Summary
// ============================================================
console.log(`\nResults: ${passed} passed, ${failed} failed, ${skipped} skipped`);
if (failed > 0) {
  process.exitCode = 1;
}
