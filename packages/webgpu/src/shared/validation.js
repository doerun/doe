import { globals } from '../webgpu_constants.js';
import {
  UINT32_MAX,
  failValidation,
  describeResourceLabel,
  assertObject,
  assertBoolean,
  assertNonEmptyString,
  assertIntegerInRange,
  assertOptionalIntegerInRange,
  assertLiveResource,
} from './resource-lifecycle.js';

const SAMPLER_BINDING_TYPES = Object.freeze({
  filtering: 'filtering',
  'non-filtering': 'non-filtering',
  comparison: 'comparison',
});

const TEXTURE_SAMPLE_TYPES = Object.freeze({
  float: 'float',
  'unfilterable-float': 'unfilterable-float',
  depth: 'depth',
  sint: 'sint',
  uint: 'uint',
});

const TEXTURE_VIEW_DIMENSIONS = Object.freeze({
  '1d': '1d',
  '2d': '2d',
  '2d-array': '2d-array',
  cube: 'cube',
  'cube-array': 'cube-array',
  '3d': '3d',
});

const TEXTURE_DIMENSIONS = Object.freeze({
  '1d': '1d',
  '2d': '2d',
  '3d': '3d',
});

const STORAGE_TEXTURE_ACCESS = Object.freeze({
  'write-only': 'write-only',
  'read-only': 'read-only',
  'read-write': 'read-write',
});

const ALL_BUFFER_USAGE_BITS = Object.values(globals.GPUBufferUsage)
  .reduce((mask, bit) => mask | bit, 0);

// ============================================================
// Texture format capability tables
// ============================================================

// Depth/stencil formats recognized without any feature gate
const DEPTH_STENCIL_FORMATS_BASE = Object.freeze(new Set([
  'stencil8',
  'depth16unorm',
  'depth24plus',
  'depth24plus-stencil8',
  'depth32float',
]));

// depth32float-stencil8 requires the depth32float-stencil8 feature
const DEPTH_STENCIL_FORMAT_DEPTH32FLOAT_STENCIL8 = 'depth32float-stencil8';

function isDepthStencilFormat(format, features) {
  if (DEPTH_STENCIL_FORMATS_BASE.has(format)) return true;
  if (format === DEPTH_STENCIL_FORMAT_DEPTH32FLOAT_STENCIL8) {
    return features != null && features.has('depth32float-stencil8');
  }
  return false;
}

// Formats that can have stencil aspect (stencilLoadOp / stencilStoreOp)
const STENCIL_FORMATS = Object.freeze(new Set([
  'stencil8',
  'depth24plus-stencil8',
  'depth32float-stencil8',
]));

function hasStencilAspect(format) {
  return STENCIL_FORMATS.has(format);
}

// Formats valid for STORAGE_BINDING usage (without any feature)
const STORAGE_TEXTURE_FORMATS_BASE = Object.freeze(new Set([
  'rgba8unorm',
  'rgba8snorm',
  'rgba8uint',
  'rgba8sint',
  'rgba16uint',
  'rgba16sint',
  'rgba16float',
  'r32float',
  'r32uint',
  'r32sint',
  'rg32float',
  'rg32uint',
  'rg32sint',
  'rgba32float',
  'rgba32uint',
  'rgba32sint',
]));

// bgra8unorm is valid for storage only with bgra8unorm-storage feature
function isStorageTextureFormat(format, features) {
  if (STORAGE_TEXTURE_FORMATS_BASE.has(format)) return true;
  if (format === 'bgra8unorm') {
    return features != null && features.has('bgra8unorm-storage');
  }
  return false;
}

// Float32 formats: default sample type is unfilterable-float.
// With float32-filterable feature, they become filterable (sample type = float).
const FLOAT32_FORMATS = Object.freeze(new Set([
  'r32float',
  'rg32float',
  'rgba32float',
]));

function float32SampleType(format, features) {
  if (!FLOAT32_FORMATS.has(format)) return null;
  if (features != null && features.has('float32-filterable')) {
    return 'float';
  }
  return 'unfilterable-float';
}

function isFloat32Filterable(format, features) {
  return FLOAT32_FORMATS.has(format) && features != null && features.has('float32-filterable');
}

// Float32 formats: default is not blendable as render target.
// With float32-blendable feature, blend state is allowed on float32 color targets.
function isFloat32Blendable(format, features) {
  return FLOAT32_FORMATS.has(format) && features != null && features.has('float32-blendable');
}

// Formats that are always blendable (non-integer, non-depth, non-float32)
const ALWAYS_BLENDABLE_FORMATS = Object.freeze(new Set([
  'r8unorm', 'r8snorm',
  'r16float',
  'rg8unorm', 'rg8snorm',
  'rg16float',
  'rgba8unorm', 'rgba8unorm-srgb', 'rgba8snorm',
  'bgra8unorm', 'bgra8unorm-srgb',
  'rgb10a2unorm',
  'rgba16float',
]));

function isBlendableFormat(format, features) {
  if (ALWAYS_BLENDABLE_FORMATS.has(format)) return true;
  return isFloat32Blendable(format, features);
}

// BC (S3TC/DXT) compressed formats — require texture-compression-bc feature.
// Read-only compressed: valid for TEXTURE_BINDING and CopySrc/CopyDst,
// not valid for RENDER_ATTACHMENT or STORAGE_BINDING.
const BC_FORMATS = Object.freeze(new Set([
  'bc1-rgba-unorm', 'bc1-rgba-unorm-srgb',
  'bc2-rgba-unorm', 'bc2-rgba-unorm-srgb',
  'bc3-rgba-unorm', 'bc3-rgba-unorm-srgb',
  'bc4-r-unorm', 'bc4-r-snorm',
  'bc5-rg-unorm', 'bc5-rg-snorm',
  'bc6h-rgb-ufloat', 'bc6h-rgb-float',
  'bc7-rgba-unorm', 'bc7-rgba-unorm-srgb',
]));

function isBCFormat(format) {
  return BC_FORMATS.has(format);
}

// ASTC compressed formats — require texture-compression-astc feature.
// Read-only compressed: valid for TEXTURE_BINDING and CopySrc/CopyDst,
// not valid for RENDER_ATTACHMENT or STORAGE_BINDING.
const ASTC_FORMATS = Object.freeze(new Set([
  'astc-4x4-unorm', 'astc-4x4-unorm-srgb',
  'astc-5x4-unorm', 'astc-5x4-unorm-srgb',
  'astc-5x5-unorm', 'astc-5x5-unorm-srgb',
  'astc-6x5-unorm', 'astc-6x5-unorm-srgb',
  'astc-6x6-unorm', 'astc-6x6-unorm-srgb',
  'astc-8x5-unorm', 'astc-8x5-unorm-srgb',
  'astc-8x6-unorm', 'astc-8x6-unorm-srgb',
  'astc-8x8-unorm', 'astc-8x8-unorm-srgb',
  'astc-10x5-unorm', 'astc-10x5-unorm-srgb',
  'astc-10x6-unorm', 'astc-10x6-unorm-srgb',
  'astc-10x8-unorm', 'astc-10x8-unorm-srgb',
  'astc-10x10-unorm', 'astc-10x10-unorm-srgb',
  'astc-12x10-unorm', 'astc-12x10-unorm-srgb',
  'astc-12x12-unorm', 'astc-12x12-unorm-srgb',
]));

function isASTCFormat(format) {
  return ASTC_FORMATS.has(format);
}

// ETC2/EAC compressed formats — require texture-compression-etc2 feature.
// Read-only compressed: valid for TEXTURE_BINDING and CopySrc/CopyDst,
// not valid for RENDER_ATTACHMENT or STORAGE_BINDING.
const ETC2_FORMATS = Object.freeze(new Set([
  'etc2-rgb8unorm', 'etc2-rgb8unorm-srgb',
  'etc2-rgb8a1unorm', 'etc2-rgb8a1unorm-srgb',
  'etc2-rgba8unorm', 'etc2-rgba8unorm-srgb',
  'eac-r11unorm', 'eac-r11snorm',
  'eac-rg11unorm', 'eac-rg11snorm',
]));

function isETC2Format(format) {
  return ETC2_FORMATS.has(format);
}

// ASTC block sizes for validation (width, height) keyed by format prefix
const ASTC_BLOCK_SIZES = Object.freeze({
  'astc-4x4': [4, 4], 'astc-5x4': [5, 4], 'astc-5x5': [5, 5],
  'astc-6x5': [6, 5], 'astc-6x6': [6, 6], 'astc-8x5': [8, 5],
  'astc-8x6': [8, 6], 'astc-8x8': [8, 8], 'astc-10x5': [10, 5],
  'astc-10x6': [10, 6], 'astc-10x8': [10, 8], 'astc-10x10': [10, 10],
  'astc-12x10': [12, 10], 'astc-12x12': [12, 12],
});

function astcBlockSize(format) {
  const prefix = format.replace(/-unorm(-srgb)?$/, '');
  return ASTC_BLOCK_SIZES[prefix] ?? null;
}

function assertBufferDescriptor(descriptor, path) {
  assertObject(descriptor, path, 'descriptor');
  assertIntegerInRange(descriptor.size, path, 'descriptor.size', { min: 1 });
  const usage = assertIntegerInRange(descriptor.usage, path, 'descriptor.usage', { min: 1 });
  if ((usage & ~ALL_BUFFER_USAGE_BITS) !== 0) {
    failValidation(path, `descriptor.usage contains unknown flag bits (0x${(usage & ~ALL_BUFFER_USAGE_BITS).toString(16)})`);
  }
  if (descriptor.mappedAtCreation !== undefined) {
    assertBoolean(descriptor.mappedAtCreation, path, 'descriptor.mappedAtCreation');
    if (descriptor.mappedAtCreation && (descriptor.size % 4) !== 0) {
      failValidation(path, 'descriptor.size must be a multiple of 4 when mappedAtCreation is true');
    }
  }
  return descriptor;
}

function normalizeEnumKey(value, path, label) {
  return assertNonEmptyString(value, path, label).trim().toLowerCase().replaceAll('_', '-');
}

function normalizeSamplerLayout(binding, path, label) {
  const sampler = assertObject(binding, path, label);
  const type = normalizeEnumKey(sampler.type ?? 'filtering', path, `${label}.type`);
  if (!(type in SAMPLER_BINDING_TYPES)) {
    failValidation(path, `${label}.type must be one of: ${Object.keys(SAMPLER_BINDING_TYPES).join(', ')}`);
  }
  return { type };
}

function normalizeTextureLayout(binding, path, label) {
  const texture = assertObject(binding, path, label);
  const sampleType = normalizeEnumKey(texture.sampleType ?? 'float', path, `${label}.sampleType`);
  const viewDimension = normalizeEnumKey(texture.viewDimension ?? '2d', path, `${label}.viewDimension`);
  if (!(sampleType in TEXTURE_SAMPLE_TYPES)) {
    failValidation(path, `${label}.sampleType must be one of: ${Object.keys(TEXTURE_SAMPLE_TYPES).join(', ')}`);
  }
  if (!(viewDimension in TEXTURE_VIEW_DIMENSIONS)) {
    failValidation(path, `${label}.viewDimension must be one of: ${Object.keys(TEXTURE_VIEW_DIMENSIONS).join(', ')}`);
  }
  return {
    sampleType,
    viewDimension,
    multisampled: texture.multisampled === undefined
      ? false
      : assertBoolean(texture.multisampled, path, `${label}.multisampled`),
  };
}

function normalizeStorageTextureLayout(binding, path, label) {
  const storageTexture = assertObject(binding, path, label);
  const access = normalizeEnumKey(storageTexture.access ?? 'write-only', path, `${label}.access`);
  const viewDimension = normalizeEnumKey(storageTexture.viewDimension ?? '2d', path, `${label}.viewDimension`);
  if (!(access in STORAGE_TEXTURE_ACCESS)) {
    failValidation(path, `${label}.access must be one of: ${Object.keys(STORAGE_TEXTURE_ACCESS).join(', ')}`);
  }
  if (!(viewDimension in TEXTURE_VIEW_DIMENSIONS)) {
    failValidation(path, `${label}.viewDimension must be one of: ${Object.keys(TEXTURE_VIEW_DIMENSIONS).join(', ')}`);
  }
  return {
    access,
    format: assertNonEmptyString(storageTexture.format, path, `${label}.format`),
    viewDimension,
  };
}

function normalizeTextureDimension(value, path, label = 'descriptor.dimension') {
  const dimension = normalizeEnumKey(value ?? '2d', path, label);
  if (!(dimension in TEXTURE_DIMENSIONS)) {
    failValidation(path, `${label} must be one of: ${Object.keys(TEXTURE_DIMENSIONS).join(', ')}`);
  }
  return dimension;
}

function assertTextureSize(size, path) {
  if (typeof size === 'number') {
    return {
      width: assertIntegerInRange(size, path, 'descriptor.size', { min: 1 }),
      height: 1,
      depthOrArrayLayers: 1,
    };
  }
  if (Array.isArray(size)) {
    if (size.length < 1 || size.length > 3) {
      failValidation(path, 'descriptor.size array must have 1 to 3 entries');
    }
    return {
      width: assertIntegerInRange(size[0], path, 'descriptor.size[0]', { min: 1, max: UINT32_MAX }),
      height: assertIntegerInRange(size[1] ?? 1, path, 'descriptor.size[1]', { min: 1, max: UINT32_MAX }),
      depthOrArrayLayers: assertIntegerInRange(size[2] ?? 1, path, 'descriptor.size[2]', { min: 1, max: UINT32_MAX }),
    };
  }
  const objectSize = assertObject(size, path, 'descriptor.size');
  return {
    width: assertIntegerInRange(objectSize.width ?? 1, path, 'descriptor.size.width', { min: 1, max: UINT32_MAX }),
    height: assertIntegerInRange(objectSize.height ?? 1, path, 'descriptor.size.height', { min: 1, max: UINT32_MAX }),
    depthOrArrayLayers: assertIntegerInRange(
      objectSize.depthOrArrayLayers ?? 1,
      path,
      'descriptor.size.depthOrArrayLayers',
      { min: 1, max: UINT32_MAX },
    ),
  };
}

function assertBindGroupResource(resource, path) {
  if (!resource || typeof resource !== 'object') {
    failValidation(path, 'entry.resource must be an object');
  }
  if ('buffer' in resource) {
    return {
      buffer: assertLiveResource(resource.buffer, path, 'GPUBuffer'),
      offset: assertOptionalIntegerInRange(resource.offset ?? 0, path, 'entry.resource.offset', { min: 0 }),
      size: resource.size === undefined
        ? undefined
        : assertIntegerInRange(resource.size, path, 'entry.resource.size', { min: 1 }),
    };
  }
  if ('_native' in resource) {
    if (describeResourceLabel(resource) === 'GPUSampler') {
      return { sampler: assertLiveResource(resource, path, 'GPUSampler') };
    }
    if (describeResourceLabel(resource) === 'GPUTextureView') {
      return { textureView: assertLiveResource(resource, path, 'GPUTextureView') };
    }
    return {
      buffer: assertLiveResource(resource, path, 'GPUBuffer'),
      offset: 0,
      size: undefined,
    };
  }
  if ('sampler' in resource) {
    return { sampler: assertLiveResource(resource.sampler, path, 'GPUSampler') };
  }
  if ('textureView' in resource) {
    return { textureView: assertLiveResource(resource.textureView, path, 'GPUTextureView') };
  }
  failValidation(path, 'entry.resource must be a GPUBuffer, GPUTextureView, GPUSampler, or { buffer|textureView|sampler, ... }');
}

function normalizeBindGroupLayoutEntry(entry, index, path) {
  const binding = assertObject(entry, path, `descriptor.entries[${index}]`);
  const normalized = {
    binding: assertIntegerInRange(binding.binding, path, `descriptor.entries[${index}].binding`, { min: 0, max: UINT32_MAX }),
    visibility: assertIntegerInRange(binding.visibility, path, `descriptor.entries[${index}].visibility`, { min: 0 }),
  };
  if (binding.buffer) {
    const buffer = assertObject(binding.buffer, path, `descriptor.entries[${index}].buffer`);
    normalized.buffer = {
      type: buffer.type || 'uniform',
      hasDynamicOffset: buffer.hasDynamicOffset === undefined
        ? false
        : assertBoolean(buffer.hasDynamicOffset, path, `descriptor.entries[${index}].buffer.hasDynamicOffset`),
      minBindingSize: assertOptionalIntegerInRange(
        buffer.minBindingSize ?? 0,
        path,
        `descriptor.entries[${index}].buffer.minBindingSize`,
        { min: 0 },
      ) ?? 0,
    };
  }
  if (binding.sampler) {
    normalized.sampler = normalizeSamplerLayout(binding.sampler, path, `descriptor.entries[${index}].sampler`);
  }
  if (binding.texture) {
    normalized.texture = normalizeTextureLayout(binding.texture, path, `descriptor.entries[${index}].texture`);
  }
  if (binding.storageTexture) {
    normalized.storageTexture = normalizeStorageTextureLayout(
      binding.storageTexture,
      path,
      `descriptor.entries[${index}].storageTexture`,
    );
  }
  return normalized;
}

function autoLayoutEntriesFromNativeBindings(bindings, visibility) {
  const groups = new Map();
  for (const binding of bindings ?? []) {
    const entry = (() => {
      if (binding.type === 'buffer') {
        const type = binding.space === 'uniform'
          ? 'uniform'
          : binding.access === 'read'
            ? 'read-only-storage'
            : 'storage';
        return {
          binding: binding.binding,
          visibility,
          buffer: { type },
        };
      }
      if (binding.type === 'sampler') {
        return {
          binding: binding.binding,
          visibility,
          sampler: { type: 'filtering' },
        };
      }
      if (binding.type === 'texture') {
        return {
          binding: binding.binding,
          visibility,
          texture: { sampleType: 'float', viewDimension: '2d', multisampled: false },
        };
      }
      if (binding.type === 'storage_texture') {
        return {
          binding: binding.binding,
          visibility,
          storageTexture: {
            access: binding.access === 'read' ? 'read-only' : 'write-only',
            format: 'rgba8unorm',
            viewDimension: '2d',
          },
        };
      }
      return null;
    })();
    if (!entry) continue;
    const entries = groups.get(binding.group) ?? [];
    entries.push(entry);
    groups.set(binding.group, entries);
  }
  for (const entries of groups.values()) {
    entries.sort((left, right) => left.binding - right.binding);
  }
  return groups;
}

export {
  ALL_BUFFER_USAGE_BITS,
  SAMPLER_BINDING_TYPES,
  TEXTURE_SAMPLE_TYPES,
  TEXTURE_DIMENSIONS,
  TEXTURE_VIEW_DIMENSIONS,
  STORAGE_TEXTURE_ACCESS,
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
  normalizeTextureDimension,
  normalizeSamplerLayout,
  normalizeTextureLayout,
  normalizeStorageTextureLayout,
  assertTextureSize,
  assertBindGroupResource,
  normalizeBindGroupLayoutEntry,
  autoLayoutEntriesFromNativeBindings,
};
