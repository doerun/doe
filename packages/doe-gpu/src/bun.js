// doe-gpu — Bun entry

import {
  create,
  createInstance,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  preflightShaderSource,
  setNativeTimeoutMs,
  createDoeRuntime,
  runDawnVsDoeCompare,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
} from '../../webgpu/src/bun.js';
import { createDoeNamespace } from '../../webgpu-doe/src/index.js';

export const createGpuNamespace = createDoeNamespace;

export const gpu = createDoeNamespace({
  requestDevice,
});

export {
  create,
  createInstance,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  preflightShaderSource,
  setNativeTimeoutMs,
  createDoeRuntime,
  runDawnVsDoeCompare,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
};
export { createDoeNamespace } from '../../webgpu-doe/src/index.js';
