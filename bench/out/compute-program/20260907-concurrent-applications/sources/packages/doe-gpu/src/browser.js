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
} from './vendor/webgpu/browser.js';
import { createDoeNamespace } from './vendor/doe-namespace.js';

const BROWSER_RUNTIME_IDENTITY_VERSION = 1;
const BROWSER_RUNTIME_IDENTITY_KIND = 'browser_runtime_identity';
const BROWSER_SURFACE_ID = 'doe-gpu/browser';
const BROWSER_NATIVE_RUNTIME_ID = 'browser_navigator_gpu';

export const createGpuNamespace = createDoeNamespace;

export const gpu = createDoeNamespace({
  requestDevice,
});

function globalNavigatorGpu() {
  return globalThis.navigator?.gpu ?? null;
}

export function createBrowserRuntimeIdentity(options = {}) {
  const runtimeSelection = options.runtimeSelection ?? null;
  const selectedRuntime = runtimeSelection?.selectedRuntime
    ?? options.selectedRuntime
    ?? BROWSER_NATIVE_RUNTIME_ID;
  const hasRuntimeSelection = runtimeSelection != null;
  const gpuSurface = options.gpu ?? globalNavigatorGpu();

  return {
    schemaVersion: BROWSER_RUNTIME_IDENTITY_VERSION,
    artifactKind: BROWSER_RUNTIME_IDENTITY_KIND,
    surface: BROWSER_SURFACE_ID,
    evidenceSource: hasRuntimeSelection
      ? 'runtime_selection_artifact'
      : 'browser_wrapper_probe',
    selectedRuntime,
    executionOwner: hasRuntimeSelection ? 'chromium_runtime_selector' : 'browser',
    doeRuntimeActive:
      hasRuntimeSelection
      && selectedRuntime === 'doe'
      && runtimeSelection?.fallbackApplied === false
      && runtimeSelection?.hiddenFallbackAllowed === false,
    webgpuAvailable: Boolean(gpuSurface),
    provider: providerInfo(),
    runtimeSelection,
  };
}

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
export { createDoeNamespace } from './vendor/doe-namespace.js';

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
  createBrowserRuntimeIdentity,
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
