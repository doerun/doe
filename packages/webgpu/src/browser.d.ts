import type {
  NativeBrowserCanvasBackend,
  ProviderInfo,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  globals,
} from './full.js';

export interface BrowserCreateOptions {
  gpu?: GPU;
  canvasBackend?: NativeBrowserCanvasBackend;
  contextFactory?: (canvas: HTMLCanvasElement | OffscreenCanvas) => GPUCanvasContext | null;
}

export interface BrowserRequestDeviceOptions extends BrowserCreateOptions {
  adapterOptions?: GPURequestAdapterOptions;
  deviceDescriptor?: GPUDeviceDescriptor;
}

export interface BrowserRuntime {
  readonly nativeGpu: GPU | null;
  readonly gpu: GPU | null;
  readonly canvasBackend: NativeBrowserCanvasBackend;
  readonly classes: Record<string, unknown> & {
    DoeGPUCanvasContext: new (canvas: HTMLCanvasElement | OffscreenCanvas) => GPUCanvasContext;
    DoeGPUAdapter: new (native: GPUAdapter, instance?: GPU | null) => GPUAdapter;
    DoeGPUDevice: new (native: GPUDevice, instance?: GPU | null) => GPUDevice;
  };
  createCanvasContext(canvas: HTMLCanvasElement | OffscreenCanvas): GPUCanvasContext;
  bindAdapter(adapter: GPUAdapter): GPUAdapter;
  bindDevice(device: GPUDevice): GPUDevice;
}

export function createBrowserRuntime(options?: BrowserCreateOptions): BrowserRuntime;
export function create(options?: BrowserCreateOptions): GPU;
export function createInstance(options?: BrowserCreateOptions): GPU;
export function setupGlobals(target?: object, options?: BrowserCreateOptions): GPU;
export function requestAdapter(
  adapterOptions?: GPURequestAdapterOptions,
  options?: BrowserCreateOptions,
): Promise<GPUAdapter | null>;
export function requestDevice(options?: BrowserRequestDeviceOptions): Promise<GPUDevice>;
export function bindAdapter(adapter: GPUAdapter, options?: BrowserCreateOptions): GPUAdapter;
export function bindDevice(device: GPUDevice, options?: BrowserCreateOptions): GPUDevice;
export function createCanvasContext(
  canvas: HTMLCanvasElement | OffscreenCanvas,
  options?: BrowserCreateOptions,
): GPUCanvasContext;
export function providerInfo(): ProviderInfo;

export {
  globals,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
};

declare const _default: {
  createBrowserRuntime: typeof createBrowserRuntime;
  create: typeof create;
  createInstance: typeof createInstance;
  setupGlobals: typeof setupGlobals;
  requestAdapter: typeof requestAdapter;
  requestDevice: typeof requestDevice;
  bindAdapter: typeof bindAdapter;
  bindDevice: typeof bindDevice;
  createCanvasContext: typeof createCanvasContext;
  providerInfo: typeof providerInfo;
  globals: typeof globals;
  CANVAS_ALPHA_MODES: typeof CANVAS_ALPHA_MODES;
  CANVAS_TONE_MAPPING_MODES: typeof CANVAS_TONE_MAPPING_MODES;
  CANVAS_COLOR_SPACES: typeof CANVAS_COLOR_SPACES;
  normalizeOrigin2D: typeof normalizeOrigin2D;
  normalizeCanvasConfiguration: typeof normalizeCanvasConfiguration;
  createBrowserSurfaceClasses: typeof createBrowserSurfaceClasses;
  createNativeBrowserCanvasBackend: typeof createNativeBrowserCanvasBackend;
};

export default _default;
