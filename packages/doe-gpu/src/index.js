// doe-gpu — full (default)
//
// Merged package surface combining @simulatte/webgpu and @simulatte/webgpu-doe.
// Primary export: gpu (not doe).

import * as full from './vendor/webgpu/index.js';
import { createDoeNamespace } from './vendor/doe-namespace.js';

export const createGpuNamespace = createDoeNamespace;

export const gpu = createDoeNamespace({
  requestDevice: full.requestDevice,
});

export * from './vendor/webgpu/index.js';
export { createDoeNamespace } from './vendor/doe-namespace.js';

export default {
  ...full,
  gpu,
  createGpuNamespace: createDoeNamespace,
};
