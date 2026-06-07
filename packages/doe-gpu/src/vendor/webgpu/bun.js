import * as ffi from "./bun-ffi.js";
import * as full from "./full.js";
import { createDoeNamespace } from '../doe-namespace.js';

const ffiDefaultPlatforms = new Set(["darwin", "linux"]);
const requestedBackend = process.env.DOE_BUN_WEBGPU_BACKEND ?? "";
const ffiLoaded = ffi.providerInfo().loaded;
const runtime = requestedBackend === "full"
  ? full
  : (requestedBackend === "ffi" || ffiDefaultPlatforms.has(process.platform)) && ffiLoaded
    ? ffi
    : full;
const runtimeProvider = runtime === ffi ? "doe-ffi" : "doe-full";

export const doe = createDoeNamespace({
  requestDevice: runtime.requestDevice,
});

export const create = runtime.create;
export const createCanvasContext = runtime.createCanvasContext ?? full.createCanvasContext;
export const createInstance = runtime.createInstance;
export const globals = runtime.globals;
export const setupGlobals = runtime.setupGlobals;
export const requestAdapter = runtime.requestAdapter;
export const requestDevice = runtime.requestDevice;
export const providerInfo = () => ({
  ...runtime.providerInfo(),
  bunRuntimeProvider: runtimeProvider,
});
export const nativeFastPathInfo = runtime.nativeFastPathInfo ?? full.nativeFastPathInfo;
export const nativeQueueSyncInfo = runtime.nativeQueueSyncInfo ?? full.nativeQueueSyncInfo;
export const fastPathStats = runtime.fastPathStats;
export const preflightShaderSource = runtime.preflightShaderSource ?? full.preflightShaderSource;
export const setNativeTimeoutMs = runtime.setNativeTimeoutMs ?? full.setNativeTimeoutMs;
export const createDoeRuntime = runtime.createDoeRuntime;
export const runDawnVsDoeCompare = runtime.runDawnVsDoeCompare;
export const CANVAS_ALPHA_MODES = runtime.CANVAS_ALPHA_MODES ?? full.CANVAS_ALPHA_MODES;
export const CANVAS_TONE_MAPPING_MODES = runtime.CANVAS_TONE_MAPPING_MODES ?? full.CANVAS_TONE_MAPPING_MODES;
export const CANVAS_COLOR_SPACES = runtime.CANVAS_COLOR_SPACES ?? full.CANVAS_COLOR_SPACES;
export const normalizeOrigin2D = runtime.normalizeOrigin2D ?? full.normalizeOrigin2D;
export const normalizeCanvasConfiguration = runtime.normalizeCanvasConfiguration ?? full.normalizeCanvasConfiguration;
export const createBrowserSurfaceClasses = runtime.createBrowserSurfaceClasses ?? full.createBrowserSurfaceClasses;
export const createNativeBrowserCanvasBackend = runtime.createNativeBrowserCanvasBackend ?? full.createNativeBrowserCanvasBackend;

export default {
  ...runtime,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createCanvasContext,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
  nativeFastPathInfo,
  nativeQueueSyncInfo,
  fastPathStats,
  preflightShaderSource,
  setNativeTimeoutMs,
  doe,
};
