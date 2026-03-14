const MAX_SAFE_U64 = Number.MAX_SAFE_INTEGER;
const UINT32_MAX = 0xFFFF_FFFF;

function failValidation(path, message) {
  throw new Error(`${path}: ${message}`);
}

function describeResourceLabel(value, fallback = 'resource') {
  return value?._resourceLabel ?? fallback;
}

function initResource(target, label, owner = null) {
  target._resourceLabel = label;
  target._resourceOwner = owner;
  target._destroyed = false;
  return target;
}

function assertObject(value, path, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    failValidation(path, `${label} must be an object`);
  }
  return value;
}

function assertArray(value, path, label) {
  if (!Array.isArray(value)) {
    failValidation(path, `${label} must be an array`);
  }
  return value;
}

function assertBoolean(value, path, label) {
  if (typeof value !== 'boolean') {
    failValidation(path, `${label} must be a boolean`);
  }
  return value;
}

function assertString(value, path, label) {
  if (typeof value !== 'string') {
    failValidation(path, `${label} must be a string`);
  }
  return value;
}

function assertNonEmptyString(value, path, label) {
  if (assertString(value, path, label).length === 0) {
    failValidation(path, `${label} must not be empty`);
  }
  return value;
}

function assertIntegerInRange(value, path, label, {
  min = 0,
  max = MAX_SAFE_U64,
} = {}) {
  if (!Number.isInteger(value) || value < min || value > max) {
    failValidation(path, `${label} must be an integer in [${min}, ${max}]`);
  }
  return value;
}

function assertOptionalIntegerInRange(value, path, label, options) {
  if (value === undefined) {
    return value;
  }
  return assertIntegerInRange(value, path, label, options);
}

function validatePositiveInteger(value, label) {
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${label} must be a positive integer.`);
  }
}

function assertLiveResource(resource, path, label = null) {
  const resourceLabel = label ?? describeResourceLabel(resource);
  if (!resource || typeof resource !== 'object' || !('_native' in resource)) {
    failValidation(path, `${resourceLabel} must be a Doe WebGPU object`);
  }
  const owner = resource._resourceOwner;
  if (owner?._destroyed) {
    failValidation(
      path,
      `${resourceLabel} cannot be used after ${describeResourceLabel(owner, 'owning resource')} was destroyed`,
    );
  }
  if (resource._destroyed || resource._native == null) {
    failValidation(path, `${resourceLabel} was destroyed`);
  }
  return resource._native;
}

function destroyResource(resource, release) {
  if (resource._destroyed || resource._native == null) {
    return;
  }
  release(resource._native);
  resource._native = null;
  resource._destroyed = true;
}

export {
  MAX_SAFE_U64,
  UINT32_MAX,
  failValidation,
  describeResourceLabel,
  initResource,
  assertObject,
  assertArray,
  assertBoolean,
  assertString,
  assertNonEmptyString,
  assertIntegerInRange,
  assertOptionalIntegerInRange,
  validatePositiveInteger,
  assertLiveResource,
  destroyResource,
};
