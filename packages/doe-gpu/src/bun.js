// doe-gpu — Bun entry

import {
  create,
  createInstance,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  nativeFastPathInfo,
  prewarmPreparedDispatches,
  nativeQueueSyncInfo,
  fastPathStats,
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
} from './vendor/webgpu/bun.js';
import { createDoeNamespace } from './vendor/doe-namespace.js';

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
  nativeFastPathInfo,
  prewarmPreparedDispatches,
  nativeQueueSyncInfo,
  fastPathStats,
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
export { createDoeNamespace } from './vendor/doe-namespace.js';
