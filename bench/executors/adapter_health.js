const NULL_BACKEND_TYPE = 1;
const NULL_BACKEND_DEVICE = 'null-backend';

function normalizeAdapterIdentifier(value) {
  return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

export function adapterInfoIsNullBackend(info) {
  if (!info || typeof info !== 'object' || Array.isArray(info)) {
    return false;
  }
  if (Number.isInteger(info.backendType) && info.backendType === NULL_BACKEND_TYPE) {
    return true;
  }
  return normalizeAdapterIdentifier(info.device) === NULL_BACKEND_DEVICE;
}

export function describeUnusableAdapterInfo(info, providerName = 'WebGPU provider') {
  if (!adapterInfoIsNullBackend(info)) {
    return '';
  }
  const backendType = Number.isInteger(info?.backendType) ? info.backendType : 'unknown';
  const device = normalizeAdapterIdentifier(info?.device) || 'unknown';
  return (
    `${providerName} returned a null-backend adapter `
    + `(backendType=${backendType}, device=${device})`
  );
}
