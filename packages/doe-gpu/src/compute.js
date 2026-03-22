// doe-gpu/compute — compute-only surface

import {
  create,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  createDoeRuntime,
  runDawnVsDoeCompare,
} from '../../webgpu/src/compute.js';
import { createDoeNamespace } from '../../webgpu-doe/src/index.js';

export const createGpuNamespace = createDoeNamespace;

export const gpu = createDoeNamespace({
  requestDevice,
});

export {
  create,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  createDoeRuntime,
  runDawnVsDoeCompare,
};
export { createDoeNamespace } from '../../webgpu-doe/src/index.js';

export default {
  create,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  createDoeRuntime,
  runDawnVsDoeCompare,
  gpu,
  createGpuNamespace: createDoeNamespace,
};
