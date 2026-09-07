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
} from './vendor/webgpu/compute.js';
import { createDoeNamespace } from './vendor/doe-namespace.js';

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
export { createDoeNamespace } from './vendor/doe-namespace.js';

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
