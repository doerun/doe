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

const STORAGE_TEXTURE_ACCESS = Object.freeze({
  'write-only': 'write-only',
  'read-only': 'read-only',
  'read-write': 'read-write',
});

const ALL_BUFFER_USAGE_BITS = Object.values(globals.GPUBufferUsage)
  .reduce((mask, bit) => mask | bit, 0);

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
  TEXTURE_VIEW_DIMENSIONS,
  STORAGE_TEXTURE_ACCESS,
  assertBufferDescriptor,
  normalizeEnumKey,
  normalizeSamplerLayout,
  normalizeTextureLayout,
  normalizeStorageTextureLayout,
  assertTextureSize,
  assertBindGroupResource,
  normalizeBindGroupLayoutEntry,
  autoLayoutEntriesFromNativeBindings,
};
