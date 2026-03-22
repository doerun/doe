// doe-gpu/browser — browser shim

import {
  createBrowserRuntime,
  create,
  createInstance,
  setupGlobals,
  requestAdapter,
  requestDevice,
  bindAdapter,
  bindDevice,
  createCanvasContext,
  providerInfo,
  globals,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
} from '../../webgpu/src/browser.js';
import { createDoeNamespace } from '../../webgpu-doe/src/index.js';

export const createGpuNamespace = createDoeNamespace;

export const gpu = createDoeNamespace({
  requestDevice,
});

export {
  createBrowserRuntime,
  create,
  createInstance,
  setupGlobals,
  requestAdapter,
  requestDevice,
  bindAdapter,
  bindDevice,
  createCanvasContext,
  providerInfo,
  globals,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
};
export { createDoeNamespace } from '../../webgpu-doe/src/index.js';

export default {
  createBrowserRuntime,
  create,
  createInstance,
  setupGlobals,
  requestAdapter,
  requestDevice,
  bindAdapter,
  bindDevice,
  createCanvasContext,
  providerInfo,
  globals,
  gpu,
  createGpuNamespace: createDoeNamespace,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
};
