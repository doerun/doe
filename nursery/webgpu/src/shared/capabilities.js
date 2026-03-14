const SHADER_F16_FEATURE = 0x0000000B;

const KNOWN_FEATURES = Object.freeze([
  ['shader-f16', SHADER_F16_FEATURE],
]);

const DOE_LIMITS = Object.freeze({
  maxTextureDimension1D: 16384,
  maxTextureDimension2D: 16384,
  maxTextureDimension3D: 2048,
  maxTextureArrayLayers: 2048,
  maxBindGroups: 4,
  maxBindGroupsPlusVertexBuffers: 24,
  maxBindingsPerBindGroup: 1000,
  maxDynamicUniformBuffersPerPipelineLayout: 8,
  maxDynamicStorageBuffersPerPipelineLayout: 4,
  maxSampledTexturesPerShaderStage: 16,
  maxSamplersPerShaderStage: 16,
  maxStorageBuffersPerShaderStage: 8,
  maxStorageTexturesPerShaderStage: 4,
  maxUniformBuffersPerShaderStage: 12,
  maxUniformBufferBindingSize: 65536,
  maxStorageBufferBindingSize: 134217728,
  minUniformBufferOffsetAlignment: 256,
  minStorageBufferOffsetAlignment: 32,
  maxVertexBuffers: 8,
  maxBufferSize: 268435456,
  maxVertexAttributes: 16,
  maxVertexBufferArrayStride: 2048,
  maxInterStageShaderVariables: 16,
  maxColorAttachments: 8,
  maxColorAttachmentBytesPerSample: 32,
  maxComputeWorkgroupStorageSize: 32768,
  maxComputeInvocationsPerWorkgroup: 1024,
  maxComputeWorkgroupSizeX: 1024,
  maxComputeWorkgroupSizeY: 1024,
  maxComputeWorkgroupSizeZ: 64,
  maxComputeWorkgroupsPerDimension: 65535,
});

const DOE_LIMIT_NAMES = Object.freeze(Object.keys(DOE_LIMITS));
const DOE_FEATURES = Object.freeze(new Set());

function featureSet(hasFeature) {
  const supported = [];
  for (const [name, value] of KNOWN_FEATURES) {
    if (hasFeature(value)) supported.push(name);
  }
  return supported.length === 0 ? DOE_FEATURES : Object.freeze(new Set(supported));
}

function isPublishedLimitValue(value) {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function publishLimits(queried) {
  if (!queried || typeof queried !== 'object') {
    return DOE_LIMITS;
  }
  let sawNativeValue = false;
  const published = {};
  for (const name of DOE_LIMIT_NAMES) {
    const value = queried[name];
    if (isPublishedLimitValue(value)) {
      published[name] = value;
      sawNativeValue = true;
      continue;
    }
    published[name] = DOE_LIMITS[name];
  }
  return sawNativeValue ? Object.freeze(published) : DOE_LIMITS;
}

function publishFeatures(hasFeature) {
  if (typeof hasFeature !== 'function') {
    return DOE_FEATURES;
  }
  return featureSet(hasFeature);
}

export {
  SHADER_F16_FEATURE,
  KNOWN_FEATURES,
  DOE_LIMITS,
  DOE_LIMIT_NAMES,
  DOE_FEATURES,
  featureSet,
  publishLimits,
  publishFeatures,
};
