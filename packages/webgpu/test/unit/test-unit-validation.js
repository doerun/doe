import assert from 'node:assert/strict';
import {
  ALL_BUFFER_USAGE_BITS,
  SAMPLER_BINDING_TYPES,
  FILTER_MODES,
  FRONT_FACES,
  INDEX_FORMATS,
  MIPMAP_FILTER_MODES,
  POWER_PREFERENCES,
  PRIMITIVE_TOPOLOGIES,
  QUERY_TYPES,
  STENCIL_OPERATIONS,
  TEXTURE_ASPECTS,
  TEXTURE_SAMPLE_TYPES,
  TEXTURE_DIMENSIONS,
  TEXTURE_VIEW_DIMENSIONS,
  STORAGE_TEXTURE_ACCESS,
  VERTEX_STEP_MODES,
  VERTEX_FORMATS,
  KNOWN_TEXTURE_FORMATS,
  KNOWN_FEATURE_NAMES,
  DEPTH_STENCIL_FORMATS_BASE,
  STORAGE_TEXTURE_FORMATS_BASE,
  FLOAT32_FORMATS,
  ALWAYS_BLENDABLE_FORMATS,
  BC_FORMATS,
  ASTC_FORMATS,
  ASTC_BLOCK_SIZES,
  ETC2_FORMATS,
  isBCFormat,
  isETC2Format,
  isDepthStencilFormat,
  hasStencilAspect,
  isStorageTextureFormat,
  float32SampleType,
  isFloat32Filterable,
  isFloat32Blendable,
  isBlendableFormat,
  isASTCFormat,
  astcBlockSize,
  assertBufferDescriptor,
  normalizeEnumKey,
  normalizeFeatureName,
  normalizePowerPreference,
  normalizeFrontFace,
  normalizeIndexFormat,
  normalizePrimitiveTopology,
  normalizeQueryType,
  normalizeMipmapFilterMode,
  normalizeStencilOperation,
  normalizeTextureAspect,
  normalizeTextureViewDimension,
  normalizeTextureSampleType,
  normalizeStorageTextureAccess,
  normalizeVertexFormat,
  normalizeVertexStepMode,
  normalizeTextureFormat,
  normalizeTextureDimension,
  normalizeRequestAdapterOptions,
  normalizeRequestDeviceDescriptor,
  normalizeSamplerDescriptor,
  normalizeTextureViewDescriptor,
  normalizeTextureDescriptor,
  normalizeQuerySetDescriptor,
  normalizePrimitiveState,
  normalizeDepthStencilState,
  normalizeVertexBufferLayouts,
  normalizeSamplerLayout,
  normalizeTextureLayout,
  normalizeStorageTextureLayout,
  assertTextureSize,
  assertBindGroupResource,
  normalizeBindGroupLayoutEntry,
  autoLayoutEntriesFromNativeBindings,
} from '../../src/shared/validation.js';

const GPUBufferUsage = {
  MAP_READ: 0x0001,
  MAP_WRITE: 0x0002,
  COPY_SRC: 0x0004,
  COPY_DST: 0x0008,
  INDEX: 0x0010,
  VERTEX: 0x0020,
  UNIFORM: 0x0040,
  STORAGE: 0x0080,
  INDIRECT: 0x0100,
  QUERY_RESOLVE: 0x0200,
};

const UINT32_MAX = 0xFFFF_FFFF;

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

function makeLiveResource(label = 'GPUBuffer') {
  return { _native: {}, _destroyed: false, _resourceLabel: label };
}

// ============================================================
// assertBufferDescriptor
// ============================================================
console.log('\nassertBufferDescriptor');

test('accepts valid buffer descriptor', () => {
  const result = assertBufferDescriptor(
    { size: 256, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST },
    'test',
  );
  assert.strictEqual(result.size, 256);
});

test('accepts mappedAtCreation=true with size multiple of 4', () => {
  assertBufferDescriptor(
    { size: 64, usage: GPUBufferUsage.STORAGE, mappedAtCreation: true },
    'test',
  );
});

test('throws when descriptor is not an object', () => {
  assert.throws(
    () => assertBufferDescriptor('not-an-object', 'test'),
    /must be an object/,
  );
});

test('throws when descriptor is null', () => {
  assert.throws(
    () => assertBufferDescriptor(null, 'test'),
    /must be an object/,
  );
});

test('throws when size is missing', () => {
  assert.throws(
    () => assertBufferDescriptor({ usage: GPUBufferUsage.STORAGE }, 'test'),
    /must be an integer/,
  );
});

test('throws when size is 0', () => {
  assert.throws(
    () => assertBufferDescriptor({ size: 0, usage: GPUBufferUsage.STORAGE }, 'test'),
    /must be an integer/,
  );
});

test('throws when size is negative', () => {
  assert.throws(
    () => assertBufferDescriptor({ size: -1, usage: GPUBufferUsage.STORAGE }, 'test'),
    /must be an integer/,
  );
});

test('throws when size is a string', () => {
  assert.throws(
    () => assertBufferDescriptor({ size: 'big', usage: GPUBufferUsage.STORAGE }, 'test'),
    /must be an integer/,
  );
});

test('throws when size is fractional', () => {
  assert.throws(
    () => assertBufferDescriptor({ size: 3.5, usage: GPUBufferUsage.STORAGE }, 'test'),
    /must be an integer/,
  );
});

test('throws when usage is 0', () => {
  assert.throws(
    () => assertBufferDescriptor({ size: 64, usage: 0 }, 'test'),
    /must be an integer/,
  );
});

test('throws when usage is missing', () => {
  assert.throws(
    () => assertBufferDescriptor({ size: 64 }, 'test'),
    /must be an integer/,
  );
});

test('throws when usage contains unknown flag bits', () => {
  assert.throws(
    () => assertBufferDescriptor({ size: 64, usage: 0x8000 }, 'test'),
    /unknown flag bits/,
  );
});

test('throws when mappedAtCreation is true but size not multiple of 4', () => {
  assert.throws(
    () => assertBufferDescriptor(
      { size: 3, usage: GPUBufferUsage.STORAGE, mappedAtCreation: true },
      'test',
    ),
    /multiple of 4/,
  );
});

test('throws when mappedAtCreation is not a boolean', () => {
  assert.throws(
    () => assertBufferDescriptor(
      { size: 64, usage: GPUBufferUsage.STORAGE, mappedAtCreation: 1 },
      'test',
    ),
    /must be a boolean/,
  );
});

// ============================================================
// normalizeEnumKey
// ============================================================
console.log('\nnormalizeEnumKey');

test('lowercases and trims', () => {
  assert.strictEqual(normalizeEnumKey('  Triangle_List  ', 'test', 'field'), 'triangle-list');
});

test('replaces underscores with hyphens', () => {
  assert.strictEqual(normalizeEnumKey('line_strip', 'test', 'field'), 'line-strip');
});

test('throws on non-string', () => {
  assert.throws(
    () => normalizeEnumKey(42, 'test', 'field'),
    /must be a string/,
  );
});

test('throws on empty string', () => {
  assert.throws(
    () => normalizeEnumKey('', 'test', 'field'),
    /must not be empty/,
  );
});

// ============================================================
// normalizeFeatureName
// ============================================================
console.log('\nnormalizeFeatureName');

test('accepts known feature names', () => {
  assert.strictEqual(normalizeFeatureName('timestamp-query', 'test', 'f'), 'timestamp-query');
  assert.strictEqual(normalizeFeatureName('shader-f16', 'test', 'f'), 'shader-f16');
});

test('normalizes underscore/case variant to known name', () => {
  assert.strictEqual(normalizeFeatureName('TIMESTAMP_QUERY', 'test', 'f'), 'timestamp-query');
});

test('throws on unknown feature name', () => {
  assert.throws(
    () => normalizeFeatureName('nonexistent-feature', 'test', 'f'),
    /must be one of/,
  );
});

// ============================================================
// enum normalizers (defaults and invalid values)
// ============================================================
console.log('\nenum normalizers');

test('normalizePowerPreference defaults to low-power', () => {
  assert.strictEqual(normalizePowerPreference(undefined, 'test'), 'low-power');
});

test('normalizePowerPreference accepts high-performance', () => {
  assert.strictEqual(normalizePowerPreference('high-performance', 'test'), 'high-performance');
});

test('normalizePowerPreference throws on invalid value', () => {
  assert.throws(
    () => normalizePowerPreference('turbo', 'test'),
    /must be one of/,
  );
});

test('normalizeFrontFace defaults to ccw', () => {
  assert.strictEqual(normalizeFrontFace(undefined, 'test'), 'ccw');
});

test('normalizeFrontFace accepts cw', () => {
  assert.strictEqual(normalizeFrontFace('cw', 'test'), 'cw');
});

test('normalizeIndexFormat defaults to uint16', () => {
  assert.strictEqual(normalizeIndexFormat(undefined, 'test', 'f'), 'uint16');
});

test('normalizePrimitiveTopology defaults to triangle-list', () => {
  assert.strictEqual(normalizePrimitiveTopology(undefined, 'test'), 'triangle-list');
});

test('normalizePrimitiveTopology accepts all valid topologies', () => {
  for (const topo of Object.keys(PRIMITIVE_TOPOLOGIES)) {
    assert.strictEqual(normalizePrimitiveTopology(topo, 'test'), topo);
  }
});

test('normalizePrimitiveTopology throws on invalid value', () => {
  assert.throws(
    () => normalizePrimitiveTopology('quad-list', 'test'),
    /must be one of/,
  );
});

test('normalizeQueryType defaults to timestamp', () => {
  assert.strictEqual(normalizeQueryType(undefined, 'test'), 'timestamp');
});

test('normalizeMipmapFilterMode defaults to nearest', () => {
  assert.strictEqual(normalizeMipmapFilterMode(undefined, 'test'), 'nearest');
});

test('normalizeStencilOperation defaults to keep', () => {
  assert.strictEqual(normalizeStencilOperation(undefined, 'test', 'f'), 'keep');
});

test('normalizeStencilOperation accepts all values', () => {
  for (const op of Object.keys(STENCIL_OPERATIONS)) {
    assert.strictEqual(normalizeStencilOperation(op, 'test', 'f'), op);
  }
});

test('normalizeTextureAspect defaults to all', () => {
  assert.strictEqual(normalizeTextureAspect(undefined, 'test'), 'all');
});

test('normalizeTextureViewDimension defaults to 2d', () => {
  assert.strictEqual(normalizeTextureViewDimension(undefined, 'test'), '2d');
});

test('normalizeTextureViewDimension accepts all values', () => {
  for (const dim of Object.keys(TEXTURE_VIEW_DIMENSIONS)) {
    assert.strictEqual(normalizeTextureViewDimension(dim, 'test'), dim);
  }
});

test('normalizeTextureSampleType defaults to float', () => {
  assert.strictEqual(normalizeTextureSampleType(undefined, 'test'), 'float');
});

test('normalizeStorageTextureAccess defaults to write-only', () => {
  assert.strictEqual(normalizeStorageTextureAccess(undefined, 'test'), 'write-only');
});

test('normalizeVertexFormat defaults to float32', () => {
  assert.strictEqual(normalizeVertexFormat(undefined, 'test', 'f'), 'float32');
});

test('normalizeVertexStepMode defaults to vertex', () => {
  assert.strictEqual(normalizeVertexStepMode(undefined, 'test'), 'vertex');
});

test('normalizeTextureDimension defaults to 2d', () => {
  assert.strictEqual(normalizeTextureDimension(undefined, 'test'), '2d');
});

test('normalizeTextureDimension accepts 1d and 3d', () => {
  assert.strictEqual(normalizeTextureDimension('1d', 'test'), '1d');
  assert.strictEqual(normalizeTextureDimension('3d', 'test'), '3d');
});

// ============================================================
// normalizeTextureFormat
// ============================================================
console.log('\nnormalizeTextureFormat');

test('accepts common formats without features', () => {
  assert.strictEqual(normalizeTextureFormat('rgba8unorm', 'test', 'fmt'), 'rgba8unorm');
  assert.strictEqual(normalizeTextureFormat('bgra8unorm', 'test', 'fmt'), 'bgra8unorm');
  assert.strictEqual(normalizeTextureFormat('depth32float', 'test', 'fmt'), 'depth32float');
});

test('normalizes case and underscores in format', () => {
  assert.strictEqual(normalizeTextureFormat('RGBA8UNORM', 'test', 'fmt'), 'rgba8unorm');
});

test('throws on unknown texture format', () => {
  assert.throws(
    () => normalizeTextureFormat('rgb565', 'test', 'fmt'),
    /known GPUTextureFormat/,
  );
});

test('throws on bc format without feature', () => {
  assert.throws(
    () => normalizeTextureFormat('bc1-rgba-unorm', 'test', 'fmt', null),
    /texture-compression-bc/,
  );
});

test('accepts bc format with bc feature', () => {
  const features = new Set(['texture-compression-bc']);
  assert.strictEqual(
    normalizeTextureFormat('bc1-rgba-unorm', 'test', 'fmt', features),
    'bc1-rgba-unorm',
  );
});

test('throws on etc2 format without feature', () => {
  assert.throws(
    () => normalizeTextureFormat('etc2-rgb8unorm', 'test', 'fmt', null),
    /texture-compression-etc2/,
  );
});

test('accepts etc2 format with etc2 feature', () => {
  const features = new Set(['texture-compression-etc2']);
  assert.strictEqual(
    normalizeTextureFormat('etc2-rgb8unorm', 'test', 'fmt', features),
    'etc2-rgb8unorm',
  );
});

test('throws on astc format without feature', () => {
  assert.throws(
    () => normalizeTextureFormat('astc-4x4-unorm', 'test', 'fmt', null),
    /texture-compression-astc/,
  );
});

test('accepts astc format with astc feature', () => {
  const features = new Set(['texture-compression-astc']);
  assert.strictEqual(
    normalizeTextureFormat('astc-4x4-unorm', 'test', 'fmt', features),
    'astc-4x4-unorm',
  );
});

test('throws on depth32float-stencil8 without feature', () => {
  assert.throws(
    () => normalizeTextureFormat('depth32float-stencil8', 'test', 'fmt', null),
    /depth32float-stencil8/,
  );
});

test('accepts depth32float-stencil8 with feature', () => {
  const features = new Set(['depth32float-stencil8']);
  assert.strictEqual(
    normalizeTextureFormat('depth32float-stencil8', 'test', 'fmt', features),
    'depth32float-stencil8',
  );
});

// ============================================================
// Format capability predicates
// ============================================================
console.log('\nformat capability predicates');

test('isBCFormat returns true for bc formats', () => {
  assert.strictEqual(isBCFormat('bc1-rgba-unorm'), true);
  assert.strictEqual(isBCFormat('bc7-rgba-unorm-srgb'), true);
});

test('isBCFormat returns false for non-bc formats', () => {
  assert.strictEqual(isBCFormat('rgba8unorm'), false);
  assert.strictEqual(isBCFormat('etc2-rgb8unorm'), false);
});

test('isETC2Format identifies etc2 and eac formats', () => {
  assert.strictEqual(isETC2Format('etc2-rgb8unorm'), true);
  assert.strictEqual(isETC2Format('eac-r11unorm'), true);
  assert.strictEqual(isETC2Format('rgba8unorm'), false);
});

test('isASTCFormat identifies astc formats', () => {
  assert.strictEqual(isASTCFormat('astc-4x4-unorm'), true);
  assert.strictEqual(isASTCFormat('astc-12x12-unorm-srgb'), true);
  assert.strictEqual(isASTCFormat('rgba8unorm'), false);
});

test('isDepthStencilFormat recognizes base depth/stencil formats', () => {
  assert.strictEqual(isDepthStencilFormat('depth32float', null), true);
  assert.strictEqual(isDepthStencilFormat('depth24plus-stencil8', null), true);
  assert.strictEqual(isDepthStencilFormat('stencil8', null), true);
});

test('isDepthStencilFormat rejects depth32float-stencil8 without feature', () => {
  assert.strictEqual(isDepthStencilFormat('depth32float-stencil8', null), false);
});

test('isDepthStencilFormat accepts depth32float-stencil8 with feature', () => {
  assert.strictEqual(
    isDepthStencilFormat('depth32float-stencil8', new Set(['depth32float-stencil8'])),
    true,
  );
});

test('isDepthStencilFormat returns false for color formats', () => {
  assert.strictEqual(isDepthStencilFormat('rgba8unorm', null), false);
});

test('hasStencilAspect returns true for stencil formats', () => {
  assert.strictEqual(hasStencilAspect('stencil8'), true);
  assert.strictEqual(hasStencilAspect('depth24plus-stencil8'), true);
  assert.strictEqual(hasStencilAspect('depth32float-stencil8'), true);
});

test('hasStencilAspect returns false for depth-only formats', () => {
  assert.strictEqual(hasStencilAspect('depth32float'), false);
  assert.strictEqual(hasStencilAspect('depth16unorm'), false);
});

test('isStorageTextureFormat recognizes base storage formats', () => {
  assert.strictEqual(isStorageTextureFormat('rgba8unorm', null), true);
  assert.strictEqual(isStorageTextureFormat('r32float', null), true);
  assert.strictEqual(isStorageTextureFormat('rgba32sint', null), true);
});

test('isStorageTextureFormat rejects bgra8unorm without feature', () => {
  assert.strictEqual(isStorageTextureFormat('bgra8unorm', null), false);
});

test('isStorageTextureFormat accepts bgra8unorm with feature', () => {
  assert.strictEqual(
    isStorageTextureFormat('bgra8unorm', new Set(['bgra8unorm-storage'])),
    true,
  );
});

test('isStorageTextureFormat rejects non-storage formats', () => {
  assert.strictEqual(isStorageTextureFormat('r8unorm', null), false);
  assert.strictEqual(isStorageTextureFormat('depth32float', null), false);
});

test('float32SampleType returns unfilterable-float by default', () => {
  assert.strictEqual(float32SampleType('r32float', null), 'unfilterable-float');
  assert.strictEqual(float32SampleType('rg32float', null), 'unfilterable-float');
  assert.strictEqual(float32SampleType('rgba32float', null), 'unfilterable-float');
});

test('float32SampleType returns float with float32-filterable feature', () => {
  const features = new Set(['float32-filterable']);
  assert.strictEqual(float32SampleType('r32float', features), 'float');
});

test('float32SampleType returns null for non-float32 formats', () => {
  assert.strictEqual(float32SampleType('rgba8unorm', null), null);
});

test('isFloat32Filterable returns false without feature', () => {
  assert.strictEqual(isFloat32Filterable('r32float', null), false);
});

test('isFloat32Filterable returns true with feature', () => {
  assert.strictEqual(isFloat32Filterable('r32float', new Set(['float32-filterable'])), true);
});

test('isFloat32Blendable returns false without feature', () => {
  assert.strictEqual(isFloat32Blendable('r32float', null), false);
});

test('isFloat32Blendable returns true with feature', () => {
  assert.strictEqual(isFloat32Blendable('r32float', new Set(['float32-blendable'])), true);
});

test('isBlendableFormat recognizes always-blendable formats', () => {
  assert.strictEqual(isBlendableFormat('rgba8unorm', null), true);
  assert.strictEqual(isBlendableFormat('rgba16float', null), true);
  assert.strictEqual(isBlendableFormat('bgra8unorm-srgb', null), true);
});

test('isBlendableFormat rejects integer and depth formats', () => {
  assert.strictEqual(isBlendableFormat('rgba8uint', null), false);
  assert.strictEqual(isBlendableFormat('depth32float', null), false);
});

test('isBlendableFormat accepts float32 with float32-blendable', () => {
  assert.strictEqual(isBlendableFormat('r32float', new Set(['float32-blendable'])), true);
});

test('astcBlockSize returns correct block sizes', () => {
  assert.deepStrictEqual(astcBlockSize('astc-4x4-unorm'), [4, 4]);
  assert.deepStrictEqual(astcBlockSize('astc-12x12-unorm-srgb'), [12, 12]);
  assert.deepStrictEqual(astcBlockSize('astc-10x5-unorm'), [10, 5]);
});

test('astcBlockSize returns null for non-astc formats', () => {
  assert.strictEqual(astcBlockSize('rgba8unorm'), null);
});

// ============================================================
// assertTextureSize
// ============================================================
console.log('\nassertTextureSize');

test('accepts a number as width-only', () => {
  assert.deepStrictEqual(assertTextureSize(128, 'test'), {
    width: 128,
    height: 1,
    depthOrArrayLayers: 1,
  });
});

test('accepts [width] array', () => {
  assert.deepStrictEqual(assertTextureSize([256], 'test'), {
    width: 256,
    height: 1,
    depthOrArrayLayers: 1,
  });
});

test('accepts [width, height] array', () => {
  assert.deepStrictEqual(assertTextureSize([512, 256], 'test'), {
    width: 512,
    height: 256,
    depthOrArrayLayers: 1,
  });
});

test('accepts [width, height, depth] array', () => {
  assert.deepStrictEqual(assertTextureSize([64, 64, 6], 'test'), {
    width: 64,
    height: 64,
    depthOrArrayLayers: 6,
  });
});

test('accepts object with width/height/depthOrArrayLayers', () => {
  assert.deepStrictEqual(
    assertTextureSize({ width: 100, height: 200, depthOrArrayLayers: 3 }, 'test'),
    { width: 100, height: 200, depthOrArrayLayers: 3 },
  );
});

test('object form defaults height and depth to 1', () => {
  assert.deepStrictEqual(
    assertTextureSize({ width: 100 }, 'test'),
    { width: 100, height: 1, depthOrArrayLayers: 1 },
  );
});

test('object form accepts depth alias', () => {
  const result = assertTextureSize({ width: 100, depth: 5 }, 'test');
  assert.strictEqual(result.depthOrArrayLayers, 5);
});

test('throws on empty array', () => {
  assert.throws(
    () => assertTextureSize([], 'test'),
    /1 to 3 entries/,
  );
});

test('throws on 4-element array', () => {
  assert.throws(
    () => assertTextureSize([1, 1, 1, 1], 'test'),
    /1 to 3 entries/,
  );
});

test('throws on zero width (number form)', () => {
  assert.throws(
    () => assertTextureSize(0, 'test'),
    /must be an integer/,
  );
});

test('throws on zero width (array form)', () => {
  assert.throws(
    () => assertTextureSize([0], 'test'),
    /must be an integer/,
  );
});

test('throws on negative dimension in array', () => {
  assert.throws(
    () => assertTextureSize([256, -1], 'test'),
    /must be an integer/,
  );
});

test('throws on non-integer dimension', () => {
  assert.throws(
    () => assertTextureSize([256, 1.5], 'test'),
    /must be an integer/,
  );
});

test('accepts UINT32_MAX as dimension', () => {
  const result = assertTextureSize([UINT32_MAX], 'test');
  assert.strictEqual(result.width, UINT32_MAX);
});

// ============================================================
// normalizeSamplerLayout
// ============================================================
console.log('\nnormalizeSamplerLayout');

test('accepts valid sampler layout with defaults', () => {
  const result = normalizeSamplerLayout({}, 'test', 'sampler');
  assert.deepStrictEqual(result, { type: 'filtering' });
});

test('accepts non-filtering sampler type', () => {
  const result = normalizeSamplerLayout({ type: 'non-filtering' }, 'test', 'sampler');
  assert.deepStrictEqual(result, { type: 'non-filtering' });
});

test('accepts comparison sampler type', () => {
  const result = normalizeSamplerLayout({ type: 'comparison' }, 'test', 'sampler');
  assert.deepStrictEqual(result, { type: 'comparison' });
});

test('throws on invalid sampler type', () => {
  assert.throws(
    () => normalizeSamplerLayout({ type: 'bilinear' }, 'test', 'sampler'),
    /must be one of/,
  );
});

test('throws when sampler is not an object', () => {
  assert.throws(
    () => normalizeSamplerLayout('filtering', 'test', 'sampler'),
    /must be an object/,
  );
});

// ============================================================
// normalizeTextureLayout
// ============================================================
console.log('\nnormalizeTextureLayout');

test('accepts defaults', () => {
  const result = normalizeTextureLayout({}, 'test', 'texture');
  assert.deepStrictEqual(result, {
    sampleType: 'float',
    viewDimension: '2d',
    multisampled: false,
  });
});

test('accepts explicit values', () => {
  const result = normalizeTextureLayout(
    { sampleType: 'depth', viewDimension: 'cube', multisampled: true },
    'test',
    'texture',
  );
  assert.deepStrictEqual(result, {
    sampleType: 'depth',
    viewDimension: 'cube',
    multisampled: true,
  });
});

test('throws when multisampled is not boolean', () => {
  assert.throws(
    () => normalizeTextureLayout({ multisampled: 1 }, 'test', 'texture'),
    /must be a boolean/,
  );
});

test('throws on invalid sampleType', () => {
  assert.throws(
    () => normalizeTextureLayout({ sampleType: 'rgb' }, 'test', 'texture'),
    /must be one of/,
  );
});

test('normalizes textureBindingViewDimension if present', () => {
  const result = normalizeTextureLayout(
    { textureBindingViewDimension: '3d' },
    'test',
    'texture',
  );
  assert.strictEqual(result.textureBindingViewDimension, '3d');
});

test('throws on invalid textureBindingViewDimension', () => {
  assert.throws(
    () => normalizeTextureLayout(
      { textureBindingViewDimension: '4d' },
      'test',
      'texture',
    ),
    /must be one of/,
  );
});

// ============================================================
// normalizeStorageTextureLayout
// ============================================================
console.log('\nnormalizeStorageTextureLayout');

test('accepts valid storage texture layout', () => {
  const result = normalizeStorageTextureLayout(
    { access: 'write-only', format: 'rgba8unorm', viewDimension: '2d' },
    'test',
    'st',
  );
  assert.deepStrictEqual(result, {
    access: 'write-only',
    format: 'rgba8unorm',
    viewDimension: '2d',
  });
});

test('uses defaults for access and viewDimension', () => {
  const result = normalizeStorageTextureLayout(
    { format: 'r32float' },
    'test',
    'st',
  );
  assert.strictEqual(result.access, 'write-only');
  assert.strictEqual(result.viewDimension, '2d');
});

test('throws when format is not a storage format', () => {
  assert.throws(
    () => normalizeStorageTextureLayout(
      { format: 'r8unorm' },
      'test',
      'st',
    ),
    /not valid for storageTexture/,
  );
});

test('throws on invalid access', () => {
  assert.throws(
    () => normalizeStorageTextureLayout(
      { format: 'rgba8unorm', access: 'readwrite' },
      'test',
      'st',
    ),
    /must be one of/,
  );
});

test('accepts read-only and read-write access', () => {
  const ro = normalizeStorageTextureLayout(
    { format: 'rgba8unorm', access: 'read-only' },
    'test', 'st',
  );
  assert.strictEqual(ro.access, 'read-only');
  const rw = normalizeStorageTextureLayout(
    { format: 'rgba8unorm', access: 'read-write' },
    'test', 'st',
  );
  assert.strictEqual(rw.access, 'read-write');
});

// ============================================================
// assertBindGroupResource
// ============================================================
console.log('\nassertBindGroupResource');

test('throws when resource is not an object', () => {
  assert.throws(
    () => assertBindGroupResource(null, 'test'),
    /must be an object/,
  );
});

test('throws when resource is a primitive', () => {
  assert.throws(
    () => assertBindGroupResource(42, 'test'),
    /must be an object/,
  );
});

test('throws when resource has no recognized keys', () => {
  assert.throws(
    () => assertBindGroupResource({ unknown: true }, 'test'),
    /must be a GPUBuffer/,
  );
});

test('accepts { buffer } resource with live buffer', () => {
  const buf = makeLiveResource('GPUBuffer');
  const result = assertBindGroupResource({ buffer: buf }, 'test');
  assert.strictEqual(result.buffer, buf._native);
  assert.strictEqual(result.offset, 0);
  assert.strictEqual(result.size, undefined);
});

test('accepts { buffer } resource with explicit offset and size', () => {
  const buf = makeLiveResource('GPUBuffer');
  const result = assertBindGroupResource({ buffer: buf, offset: 16, size: 64 }, 'test');
  assert.strictEqual(result.offset, 16);
  assert.strictEqual(result.size, 64);
});

test('throws when buffer resource size is 0', () => {
  const buf = makeLiveResource('GPUBuffer');
  assert.throws(
    () => assertBindGroupResource({ buffer: buf, size: 0 }, 'test'),
    /must be an integer/,
  );
});

test('throws when buffer resource offset is negative', () => {
  const buf = makeLiveResource('GPUBuffer');
  assert.throws(
    () => assertBindGroupResource({ buffer: buf, offset: -1 }, 'test'),
    /must be an integer/,
  );
});

test('accepts { sampler } resource', () => {
  const smp = makeLiveResource('GPUSampler');
  const result = assertBindGroupResource({ sampler: smp }, 'test');
  assert.strictEqual(result.sampler, smp._native);
});

test('accepts { textureView } resource', () => {
  const tv = makeLiveResource('GPUTextureView');
  const result = assertBindGroupResource({ textureView: tv }, 'test');
  assert.strictEqual(result.textureView, tv._native);
});

test('accepts { externalTexture } resource', () => {
  const et = makeLiveResource('GPUExternalTexture');
  const result = assertBindGroupResource({ externalTexture: et }, 'test');
  assert.strictEqual(result.externalTexture, et._native);
});

test('accepts _native resource identified as GPUSampler', () => {
  const smp = makeLiveResource('GPUSampler');
  const result = assertBindGroupResource(smp, 'test');
  assert.strictEqual(result.sampler, smp._native);
});

test('accepts _native resource identified as GPUTextureView', () => {
  const tv = makeLiveResource('GPUTextureView');
  const result = assertBindGroupResource(tv, 'test');
  assert.strictEqual(result.textureView, tv._native);
});

test('accepts _native resource identified as GPUExternalTexture', () => {
  const et = makeLiveResource('GPUExternalTexture');
  const result = assertBindGroupResource(et, 'test');
  assert.strictEqual(result.externalTexture, et._native);
});

test('accepts _native resource as buffer fallback', () => {
  const buf = { _native: {}, _destroyed: false, _resourceLabel: 'GPUBufferCustom' };
  const result = assertBindGroupResource(buf, 'test');
  assert.strictEqual(result.buffer, buf._native);
  assert.strictEqual(result.offset, 0);
});

// ============================================================
// normalizeBindGroupLayoutEntry
// ============================================================
console.log('\nnormalizeBindGroupLayoutEntry');

test('normalizes a buffer binding entry', () => {
  const entry = {
    binding: 0,
    visibility: 0x4,
    buffer: { type: 'storage' },
  };
  const result = normalizeBindGroupLayoutEntry(entry, 0, 'test');
  assert.strictEqual(result.binding, 0);
  assert.strictEqual(result.visibility, 0x4);
  assert.strictEqual(result.buffer.type, 'storage');
  assert.strictEqual(result.buffer.hasDynamicOffset, false);
  assert.strictEqual(result.buffer.minBindingSize, 0);
});

test('buffer type defaults to uniform', () => {
  const entry = {
    binding: 1,
    visibility: 0x1,
    buffer: {},
  };
  const result = normalizeBindGroupLayoutEntry(entry, 0, 'test');
  assert.strictEqual(result.buffer.type, 'uniform');
});

test('normalizes a sampler binding entry', () => {
  const entry = {
    binding: 2,
    visibility: 0x2,
    sampler: { type: 'comparison' },
  };
  const result = normalizeBindGroupLayoutEntry(entry, 0, 'test');
  assert.deepStrictEqual(result.sampler, { type: 'comparison' });
});

test('normalizes a texture binding entry', () => {
  const entry = {
    binding: 3,
    visibility: 0x2,
    texture: { sampleType: 'depth', viewDimension: 'cube' },
  };
  const result = normalizeBindGroupLayoutEntry(entry, 0, 'test');
  assert.strictEqual(result.texture.sampleType, 'depth');
  assert.strictEqual(result.texture.viewDimension, 'cube');
  assert.strictEqual(result.texture.multisampled, false);
});

test('normalizes a storageTexture binding entry', () => {
  const entry = {
    binding: 4,
    visibility: 0x4,
    storageTexture: { format: 'rgba8unorm', access: 'read-write' },
  };
  const result = normalizeBindGroupLayoutEntry(entry, 0, 'test');
  assert.strictEqual(result.storageTexture.format, 'rgba8unorm');
  assert.strictEqual(result.storageTexture.access, 'read-write');
  assert.strictEqual(result.storageTexture.viewDimension, '2d');
});

test('normalizes an externalTexture binding entry', () => {
  const entry = {
    binding: 5,
    visibility: 0x2,
    externalTexture: {},
  };
  const result = normalizeBindGroupLayoutEntry(entry, 0, 'test');
  assert.deepStrictEqual(result.externalTexture, {});
});

test('throws when binding is negative', () => {
  assert.throws(
    () => normalizeBindGroupLayoutEntry({ binding: -1, visibility: 0x1 }, 0, 'test'),
    /must be an integer/,
  );
});

test('throws when entry is not an object', () => {
  assert.throws(
    () => normalizeBindGroupLayoutEntry('not-object', 0, 'test'),
    /must be an object/,
  );
});

// ============================================================
// normalizeRequestAdapterOptions
// ============================================================
console.log('\nnormalizeRequestAdapterOptions');

test('returns undefined for undefined input', () => {
  assert.strictEqual(normalizeRequestAdapterOptions(undefined), undefined);
});

test('normalizes powerPreference', () => {
  const result = normalizeRequestAdapterOptions({ powerPreference: 'high-performance' });
  assert.strictEqual(result.powerPreference, 'high-performance');
});

test('normalizes forceFallbackAdapter boolean', () => {
  const result = normalizeRequestAdapterOptions({ forceFallbackAdapter: true });
  assert.strictEqual(result.forceFallbackAdapter, true);
});

test('throws when forceFallbackAdapter is not boolean', () => {
  assert.throws(
    () => normalizeRequestAdapterOptions({ forceFallbackAdapter: 'yes' }),
    /must be a boolean/,
  );
});

test('throws when options is not an object', () => {
  assert.throws(
    () => normalizeRequestAdapterOptions(42),
    /must be an object/,
  );
});

// ============================================================
// normalizeRequestDeviceDescriptor
// ============================================================
console.log('\nnormalizeRequestDeviceDescriptor');

test('returns undefined for undefined input', () => {
  assert.strictEqual(normalizeRequestDeviceDescriptor(undefined), undefined);
});

test('normalizes requiredFeatures', () => {
  const result = normalizeRequestDeviceDescriptor({
    requiredFeatures: ['timestamp-query', 'shader-f16'],
  });
  assert.deepStrictEqual(result.requiredFeatures, ['timestamp-query', 'shader-f16']);
});

test('throws on unknown feature in requiredFeatures', () => {
  assert.throws(
    () => normalizeRequestDeviceDescriptor({
      requiredFeatures: ['nonexistent'],
    }),
    /must be one of/,
  );
});

// ============================================================
// normalizeSamplerDescriptor
// ============================================================
console.log('\nnormalizeSamplerDescriptor');

test('accepts empty sampler descriptor', () => {
  const result = normalizeSamplerDescriptor({});
  assert.strictEqual(typeof result, 'object');
});

test('normalizes all address modes', () => {
  const result = normalizeSamplerDescriptor({
    addressModeU: 'repeat',
    addressModeV: 'mirror-repeat',
    addressModeW: 'clamp-to-edge',
  });
  assert.strictEqual(result.addressModeU, 'repeat');
  assert.strictEqual(result.addressModeV, 'mirror-repeat');
  assert.strictEqual(result.addressModeW, 'clamp-to-edge');
});

test('normalizes filter modes', () => {
  const result = normalizeSamplerDescriptor({
    magFilter: 'linear',
    minFilter: 'nearest',
    mipmapFilter: 'linear',
  });
  assert.strictEqual(result.magFilter, 'linear');
  assert.strictEqual(result.minFilter, 'nearest');
  assert.strictEqual(result.mipmapFilter, 'linear');
});

test('throws on invalid address mode', () => {
  assert.throws(
    () => normalizeSamplerDescriptor({ addressModeU: 'wrap' }),
    /must be one of/,
  );
});

test('throws on invalid filter mode', () => {
  assert.throws(
    () => normalizeSamplerDescriptor({ magFilter: 'bilinear' }),
    /must be one of/,
  );
});

test('normalizes lodMinClamp and lodMaxClamp', () => {
  const result = normalizeSamplerDescriptor({
    lodMinClamp: 0,
    lodMaxClamp: 10,
  });
  assert.strictEqual(result.lodMinClamp, 0);
  assert.strictEqual(result.lodMaxClamp, 10);
});

test('throws when lodMinClamp > lodMaxClamp', () => {
  assert.throws(
    () => normalizeSamplerDescriptor({ lodMinClamp: 5, lodMaxClamp: 2 }),
    /lodMinClamp must be less than or equal/,
  );
});

test('throws when lodMinClamp is Infinity', () => {
  assert.throws(
    () => normalizeSamplerDescriptor({ lodMinClamp: Infinity }),
    /must be a finite number/,
  );
});

test('throws when lodMaxClamp is NaN', () => {
  assert.throws(
    () => normalizeSamplerDescriptor({ lodMaxClamp: NaN }),
    /must be a finite number/,
  );
});

test('normalizes compare function', () => {
  const result = normalizeSamplerDescriptor({ compare: 'less-equal' });
  assert.strictEqual(result.compare, 'less-equal');
});

test('validates maxAnisotropy range', () => {
  const result = normalizeSamplerDescriptor({ maxAnisotropy: 16 });
  assert.strictEqual(result.maxAnisotropy, 16);
});

test('throws when maxAnisotropy is 0', () => {
  assert.throws(
    () => normalizeSamplerDescriptor({ maxAnisotropy: 0 }),
    /must be an integer/,
  );
});

test('throws when maxAnisotropy is negative', () => {
  assert.throws(
    () => normalizeSamplerDescriptor({ maxAnisotropy: -1 }),
    /must be an integer/,
  );
});

test('throws when sampler descriptor is not an object', () => {
  assert.throws(
    () => normalizeSamplerDescriptor(null),
    /must be an object/,
  );
});

// ============================================================
// normalizeTextureViewDescriptor
// ============================================================
console.log('\nnormalizeTextureViewDescriptor');

test('accepts undefined descriptor', () => {
  const result = normalizeTextureViewDescriptor(undefined, { format: 'rgba8unorm' }, null);
  assert.strictEqual(result.format, 'rgba8unorm');
});

test('normalizes dimension and aspect', () => {
  const result = normalizeTextureViewDescriptor(
    { dimension: 'cube', aspect: 'depth-only' },
    { format: 'depth32float' },
    null,
  );
  assert.strictEqual(result.dimension, 'cube');
  assert.strictEqual(result.aspect, 'depth-only');
});

test('throws on swizzle without feature', () => {
  assert.throws(
    () => normalizeTextureViewDescriptor(
      { swizzle: 'rgba' },
      { format: 'rgba8unorm' },
      null,
    ),
    /texture-component-swizzle/,
  );
});

test('accepts swizzle with feature', () => {
  const result = normalizeTextureViewDescriptor(
    { swizzle: 'rgba' },
    { format: 'rgba8unorm' },
    new Set(['texture-component-swizzle']),
  );
  assert.strictEqual(result.swizzle, 'rgba');
});

// ============================================================
// normalizeTextureDescriptor
// ============================================================
console.log('\nnormalizeTextureDescriptor');

test('normalizes texture descriptor with all fields', () => {
  const result = normalizeTextureDescriptor(
    { format: 'rgba8unorm', dimension: '2d' },
    { width: 256, height: 256, depthOrArrayLayers: 1 },
    0x04,
    null,
  );
  assert.strictEqual(result.format, 'rgba8unorm');
  assert.strictEqual(result.dimension, '2d');
  assert.strictEqual(result.size.width, 256);
  assert.strictEqual(result.usage, 0x04);
});

test('defaults format to rgba8unorm', () => {
  const result = normalizeTextureDescriptor(
    {},
    { width: 64, height: 64, depthOrArrayLayers: 1 },
    0x04,
    null,
  );
  assert.strictEqual(result.format, 'rgba8unorm');
});

test('normalizes viewFormats array', () => {
  const result = normalizeTextureDescriptor(
    { format: 'rgba8unorm', viewFormats: ['rgba8unorm-srgb'] },
    { width: 64, height: 64, depthOrArrayLayers: 1 },
    0x04,
    null,
  );
  assert.deepStrictEqual(result.viewFormats, ['rgba8unorm-srgb']);
});

test('throws on invalid viewFormat', () => {
  assert.throws(
    () => normalizeTextureDescriptor(
      { format: 'rgba8unorm', viewFormats: ['invalid-format'] },
      { width: 64, height: 64, depthOrArrayLayers: 1 },
      0x04,
      null,
    ),
    /known GPUTextureFormat/,
  );
});

// ============================================================
// normalizeQuerySetDescriptor
// ============================================================
console.log('\nnormalizeQuerySetDescriptor');

test('normalizes query type', () => {
  const result = normalizeQuerySetDescriptor({ type: 'occlusion', count: 16 });
  assert.strictEqual(result.type, 'occlusion');
  assert.strictEqual(result.count, 16);
});

test('defaults query type to timestamp', () => {
  const result = normalizeQuerySetDescriptor({ count: 8 });
  assert.strictEqual(result.type, 'timestamp');
});

test('throws on invalid query type', () => {
  assert.throws(
    () => normalizeQuerySetDescriptor({ type: 'pipeline-statistics' }),
    /must be one of/,
  );
});

// ============================================================
// normalizePrimitiveState
// ============================================================
console.log('\nnormalizePrimitiveState');

test('returns null for null input', () => {
  assert.strictEqual(normalizePrimitiveState(null), null);
});

test('returns null for undefined input', () => {
  assert.strictEqual(normalizePrimitiveState(undefined), null);
});

test('normalizes topology and frontFace with defaults', () => {
  const result = normalizePrimitiveState({});
  assert.strictEqual(result.topology, 'triangle-list');
  assert.strictEqual(result.frontFace, 'ccw');
});

test('normalizes explicit topology and frontFace', () => {
  const result = normalizePrimitiveState({
    topology: 'line-strip',
    frontFace: 'cw',
  });
  assert.strictEqual(result.topology, 'line-strip');
  assert.strictEqual(result.frontFace, 'cw');
});

test('normalizes stripIndexFormat when provided', () => {
  const result = normalizePrimitiveState({
    topology: 'triangle-strip',
    stripIndexFormat: 'uint32',
  });
  assert.strictEqual(result.stripIndexFormat, 'uint32');
});

test('throws on invalid topology', () => {
  assert.throws(
    () => normalizePrimitiveState({ topology: 'patch-list' }),
    /must be one of/,
  );
});

// ============================================================
// normalizeDepthStencilState
// ============================================================
console.log('\nnormalizeDepthStencilState');

test('returns null for null input', () => {
  assert.strictEqual(normalizeDepthStencilState(null, null), null);
});

test('normalizes depth stencil format', () => {
  const result = normalizeDepthStencilState(
    { format: 'depth32float' },
    null,
  );
  assert.strictEqual(result.format, 'depth32float');
});

test('normalizes depthCompare function', () => {
  const result = normalizeDepthStencilState(
    { format: 'depth32float', depthCompare: 'less' },
    null,
  );
  assert.strictEqual(result.depthCompare, 'less');
});

test('validates stencilReadMask range', () => {
  const result = normalizeDepthStencilState(
    { format: 'depth24plus-stencil8', stencilReadMask: 0xFF },
    null,
  );
  assert.strictEqual(result.stencilReadMask, 0xFF);
});

test('throws on negative stencilWriteMask', () => {
  assert.throws(
    () => normalizeDepthStencilState(
      { format: 'depth24plus-stencil8', stencilWriteMask: -1 },
      null,
    ),
    /must be an integer/,
  );
});

test('throws on stencilReadMask exceeding UINT32_MAX', () => {
  assert.throws(
    () => normalizeDepthStencilState(
      { format: 'depth24plus-stencil8', stencilReadMask: UINT32_MAX + 1 },
      null,
    ),
    /must be an integer/,
  );
});

test('normalizes depthBias', () => {
  const result = normalizeDepthStencilState(
    { format: 'depth32float', depthBias: -100 },
    null,
  );
  assert.strictEqual(result.depthBias, -100);
});

test('normalizes depthBiasSlopeScale and depthBiasClamp', () => {
  const result = normalizeDepthStencilState(
    { format: 'depth32float', depthBiasSlopeScale: 1.5, depthBiasClamp: 0.01 },
    null,
  );
  assert.strictEqual(result.depthBiasSlopeScale, 1.5);
  assert.strictEqual(result.depthBiasClamp, 0.01);
});

test('throws when depthBiasSlopeScale is Infinity', () => {
  assert.throws(
    () => normalizeDepthStencilState(
      { format: 'depth32float', depthBiasSlopeScale: Infinity },
      null,
    ),
    /must be a finite number/,
  );
});

test('normalizes stencilFront and stencilBack', () => {
  const result = normalizeDepthStencilState(
    {
      format: 'depth24plus-stencil8',
      stencilFront: { compare: 'always', failOp: 'zero', passOp: 'replace' },
      stencilBack: { depthFailOp: 'invert' },
    },
    null,
  );
  assert.strictEqual(result.stencilFront.compare, 'always');
  assert.strictEqual(result.stencilFront.failOp, 'zero');
  assert.strictEqual(result.stencilFront.passOp, 'replace');
  assert.strictEqual(result.stencilBack.depthFailOp, 'invert');
});

// ============================================================
// normalizeVertexBufferLayouts
// ============================================================
console.log('\nnormalizeVertexBufferLayouts');

test('normalizes a single buffer layout with attributes', () => {
  const result = normalizeVertexBufferLayouts([
    {
      arrayStride: 16,
      attributes: [
        { format: 'float32x4', shaderLocation: 0 },
      ],
    },
  ]);
  assert.strictEqual(result.length, 1);
  assert.strictEqual(result[0].arrayStride, 16);
  assert.strictEqual(result[0].stepMode, 'vertex');
  assert.strictEqual(result[0].attributes.length, 1);
  assert.strictEqual(result[0].attributes[0].format, 'float32x4');
  assert.strictEqual(result[0].attributes[0].offset, 0);
  assert.strictEqual(result[0].attributes[0].shaderLocation, 0);
});

test('normalizes multiple buffer layouts', () => {
  const result = normalizeVertexBufferLayouts([
    {
      arrayStride: 12,
      stepMode: 'instance',
      attributes: [
        { format: 'float32x3', shaderLocation: 0 },
      ],
    },
    {
      arrayStride: 8,
      attributes: [
        { format: 'float32x2', shaderLocation: 1, offset: 0 },
      ],
    },
  ]);
  assert.strictEqual(result.length, 2);
  assert.strictEqual(result[0].stepMode, 'instance');
  assert.strictEqual(result[1].stepMode, 'vertex');
});

test('defaults arrayStride to 0', () => {
  const result = normalizeVertexBufferLayouts([
    { attributes: [{ format: 'float32', shaderLocation: 0 }] },
  ]);
  assert.strictEqual(result[0].arrayStride, 0);
});

test('throws when shaderLocation is missing', () => {
  assert.throws(
    () => normalizeVertexBufferLayouts([
      { arrayStride: 16, attributes: [{ format: 'float32x4' }] },
    ]),
    /must be an integer/,
  );
});

test('throws when attributes is not an array', () => {
  assert.throws(
    () => normalizeVertexBufferLayouts([
      { arrayStride: 16, attributes: 'not-array' },
    ]),
    /must be an array/,
  );
});

test('throws when layouts is not an array', () => {
  assert.throws(
    () => normalizeVertexBufferLayouts('not-array'),
    /must be an array/,
  );
});

test('throws on invalid vertex format', () => {
  assert.throws(
    () => normalizeVertexBufferLayouts([
      { arrayStride: 16, attributes: [{ format: 'vec4', shaderLocation: 0 }] },
    ]),
    /must be one of/,
  );
});

test('throws on negative shaderLocation', () => {
  assert.throws(
    () => normalizeVertexBufferLayouts([
      { arrayStride: 16, attributes: [{ format: 'float32', shaderLocation: -1 }] },
    ]),
    /must be an integer/,
  );
});

// ============================================================
// autoLayoutEntriesFromNativeBindings
// ============================================================
console.log('\nautoLayoutEntriesFromNativeBindings');

test('returns empty map for null input', () => {
  const result = autoLayoutEntriesFromNativeBindings(null, 0x4);
  assert.strictEqual(result.size, 0);
});

test('returns empty map for empty array', () => {
  const result = autoLayoutEntriesFromNativeBindings([], 0x4);
  assert.strictEqual(result.size, 0);
});

test('generates buffer entries with correct types', () => {
  const bindings = [
    { type: 'buffer', group: 0, binding: 0, space: 'uniform' },
    { type: 'buffer', group: 0, binding: 1, space: 'storage', access: 'read' },
    { type: 'buffer', group: 0, binding: 2, space: 'storage', access: 'write' },
  ];
  const result = autoLayoutEntriesFromNativeBindings(bindings, 0x4);
  const entries = result.get(0);
  assert.strictEqual(entries.length, 3);
  assert.strictEqual(entries[0].buffer.type, 'uniform');
  assert.strictEqual(entries[1].buffer.type, 'read-only-storage');
  assert.strictEqual(entries[2].buffer.type, 'storage');
});

test('generates sampler entry', () => {
  const bindings = [{ type: 'sampler', group: 0, binding: 0 }];
  const result = autoLayoutEntriesFromNativeBindings(bindings, 0x2);
  const entries = result.get(0);
  assert.strictEqual(entries.length, 1);
  assert.deepStrictEqual(entries[0].sampler, { type: 'filtering' });
  assert.strictEqual(entries[0].visibility, 0x2);
});

test('generates texture entry', () => {
  const bindings = [{ type: 'texture', group: 1, binding: 3 }];
  const result = autoLayoutEntriesFromNativeBindings(bindings, 0x2);
  const entries = result.get(1);
  assert.strictEqual(entries.length, 1);
  assert.strictEqual(entries[0].texture.sampleType, 'float');
  assert.strictEqual(entries[0].texture.viewDimension, '2d');
  assert.strictEqual(entries[0].texture.multisampled, false);
});

test('generates storage_texture entry', () => {
  const bindings = [
    { type: 'storage_texture', group: 0, binding: 0, access: 'read' },
    { type: 'storage_texture', group: 0, binding: 1, access: 'write' },
  ];
  const result = autoLayoutEntriesFromNativeBindings(bindings, 0x4);
  const entries = result.get(0);
  assert.strictEqual(entries[0].storageTexture.access, 'read-only');
  assert.strictEqual(entries[1].storageTexture.access, 'write-only');
});

test('sorts entries by binding within a group', () => {
  const bindings = [
    { type: 'buffer', group: 0, binding: 2, space: 'uniform' },
    { type: 'buffer', group: 0, binding: 0, space: 'uniform' },
    { type: 'buffer', group: 0, binding: 1, space: 'uniform' },
  ];
  const result = autoLayoutEntriesFromNativeBindings(bindings, 0x4);
  const entries = result.get(0);
  assert.strictEqual(entries[0].binding, 0);
  assert.strictEqual(entries[1].binding, 1);
  assert.strictEqual(entries[2].binding, 2);
});

test('separates entries into groups', () => {
  const bindings = [
    { type: 'buffer', group: 0, binding: 0, space: 'uniform' },
    { type: 'buffer', group: 1, binding: 0, space: 'storage', access: 'write' },
  ];
  const result = autoLayoutEntriesFromNativeBindings(bindings, 0x4);
  assert.strictEqual(result.size, 2);
  assert.strictEqual(result.get(0).length, 1);
  assert.strictEqual(result.get(1).length, 1);
});

test('skips unknown binding types', () => {
  const bindings = [
    { type: 'unknown_thing', group: 0, binding: 0 },
  ];
  const result = autoLayoutEntriesFromNativeBindings(bindings, 0x4);
  assert.strictEqual(result.size, 0);
});

// ============================================================
// Exported constant sets integrity checks
// ============================================================
console.log('\nexported constant sets');

test('ALL_BUFFER_USAGE_BITS covers all GPUBufferUsage values', () => {
  let expected = 0;
  for (const v of Object.values(GPUBufferUsage)) {
    expected |= v;
  }
  assert.strictEqual(ALL_BUFFER_USAGE_BITS, expected);
});

test('KNOWN_TEXTURE_FORMATS is a non-empty Set', () => {
  assert.ok(KNOWN_TEXTURE_FORMATS instanceof Set);
  assert.ok(KNOWN_TEXTURE_FORMATS.size > 50);
});

test('KNOWN_FEATURE_NAMES is a non-empty Set', () => {
  assert.ok(KNOWN_FEATURE_NAMES instanceof Set);
  assert.ok(KNOWN_FEATURE_NAMES.size > 10);
  assert.ok(KNOWN_FEATURE_NAMES.has('timestamp-query'));
});

test('DEPTH_STENCIL_FORMATS_BASE contains expected formats', () => {
  assert.ok(DEPTH_STENCIL_FORMATS_BASE.has('depth32float'));
  assert.ok(DEPTH_STENCIL_FORMATS_BASE.has('depth24plus'));
  assert.ok(DEPTH_STENCIL_FORMATS_BASE.has('stencil8'));
  assert.ok(!DEPTH_STENCIL_FORMATS_BASE.has('depth32float-stencil8'));
});

test('STORAGE_TEXTURE_FORMATS_BASE contains expected formats', () => {
  assert.ok(STORAGE_TEXTURE_FORMATS_BASE.has('rgba8unorm'));
  assert.ok(STORAGE_TEXTURE_FORMATS_BASE.has('r32float'));
  assert.ok(!STORAGE_TEXTURE_FORMATS_BASE.has('bgra8unorm'));
});

test('FLOAT32_FORMATS contains exactly r32float, rg32float, rgba32float', () => {
  assert.strictEqual(FLOAT32_FORMATS.size, 3);
  assert.ok(FLOAT32_FORMATS.has('r32float'));
  assert.ok(FLOAT32_FORMATS.has('rg32float'));
  assert.ok(FLOAT32_FORMATS.has('rgba32float'));
});

test('ASTC_BLOCK_SIZES has an entry for each ASTC block size prefix', () => {
  assert.deepStrictEqual(ASTC_BLOCK_SIZES['astc-4x4'], [4, 4]);
  assert.deepStrictEqual(ASTC_BLOCK_SIZES['astc-8x8'], [8, 8]);
  assert.strictEqual(Object.keys(ASTC_BLOCK_SIZES).length, 14);
});

test('BC_FORMATS contains expected bc formats', () => {
  assert.ok(BC_FORMATS.has('bc1-rgba-unorm'));
  assert.ok(BC_FORMATS.has('bc7-rgba-unorm-srgb'));
  assert.ok(!BC_FORMATS.has('rgba8unorm'));
});

test('ETC2_FORMATS contains expected etc2/eac formats', () => {
  assert.ok(ETC2_FORMATS.has('etc2-rgb8unorm'));
  assert.ok(ETC2_FORMATS.has('eac-r11unorm'));
  assert.ok(!ETC2_FORMATS.has('bc1-rgba-unorm'));
});

test('ALWAYS_BLENDABLE_FORMATS does not include integer formats', () => {
  assert.ok(!ALWAYS_BLENDABLE_FORMATS.has('rgba8uint'));
  assert.ok(!ALWAYS_BLENDABLE_FORMATS.has('r32uint'));
});

// ============================================================
// Summary
// ============================================================
console.log(`\nResults: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exitCode = 1;
}
