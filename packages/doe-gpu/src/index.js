// doe-gpu — full (default)
//
// Merged package surface combining @simulatte/webgpu and @simulatte/webgpu-doe.
// Primary export: gpu (not doe).

import * as full from '../../webgpu/src/index.js';
import { createDoeNamespace } from '../../webgpu-doe/src/index.js';

export const createGpuNamespace = createDoeNamespace;

export const gpu = createDoeNamespace({
  requestDevice: full.requestDevice,
});

export * from '../../webgpu/src/index.js';
export { createDoeNamespace } from '../../webgpu-doe/src/index.js';

export default {
  ...full,
  gpu,
  createGpuNamespace: createDoeNamespace,
};
