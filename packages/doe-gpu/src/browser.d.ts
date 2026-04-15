import type { DoeNamespace } from "./vendor/doe-namespace.js";
import type { ProviderInfo } from "./index.js";

export type {
  DoeDeterminismProofLink,
  DoeMatmulLogitsSliceOptions,
  DoeMatmulLogitsSliceResult,
  DoeNumericStabilityCandidateInput,
  DoeNumericStabilityFirstDivergence,
  DoeNumericStabilityReceipt,
  DoeNumericStabilityReceiptCandidate,
  DoeNumericStabilityRouteDecision,
  DoeReviewedChoiceOptions,
  DoeReviewedChoiceReceipt,
  DoeReviewedChoiceResult,
  DoeStableChoiceOptions,
  DoeStableChoiceReceipt,
  DoeStableChoiceResult,
  DoeStableTokenOptions,
  DoeStableTokenReceipt,
  DoeStableTokenResult,
  DoeStableTokenTieBreakRule,
} from "./vendor/doe-namespace.js";

export interface NativeBrowserCanvasBackend {
  canvasContextConfigure(context: unknown, configuration: GPUCanvasConfiguration): void;
  canvasContextGetCurrentTexture(
    context: unknown,
    configuration: GPUCanvasConfiguration,
    fullClasses: Record<string, unknown>
  ): GPUTexture;
  canvasContextUnconfigure(context: unknown): void;
  externalTextureDestroy(native: unknown): void;
  deviceImportExternalTexture(
    device: GPUDevice,
    native: unknown,
    descriptor: GPUExternalTextureDescriptor,
    classes: Record<string, unknown>
  ): GPUExternalTexture;
  queueCopyExternalImageToTexture(
    queue: GPUQueue,
    native: unknown,
    source: GPUImageCopyExternalImage,
    destination: GPUImageCopyTextureTagged,
    copySize: GPUExtent3DStrict
  ): void;
}

export interface BrowserSurfaceFactoryOptions {
  canvasBackend: NativeBrowserCanvasBackend;
  fullClasses: Record<string, unknown>;
}

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

export const globals: Record<string, unknown>;
export const CANVAS_ALPHA_MODES: Readonly<Record<string, GPUCanvasAlphaMode>>;
export const CANVAS_TONE_MAPPING_MODES: Readonly<Record<string, GPUCanvasToneMappingMode>>;
export const CANVAS_COLOR_SPACES: Readonly<Record<string, PredefinedColorSpace>>;
export function normalizeOrigin2D(origin: GPUOrigin2D | null | undefined, path: string): { x: number; y: number };
export function normalizeCanvasConfiguration(
  config: GPUCanvasConfiguration,
  path: string
): {
  device: GPUDevice;
  format: GPUTextureFormat;
  usage: number;
  alphaMode: GPUCanvasAlphaMode;
  colorSpace: PredefinedColorSpace;
  toneMapping: { mode: GPUCanvasToneMappingMode };
  viewFormats: GPUTextureFormat[];
};
export function createBrowserSurfaceClasses(
  options: BrowserSurfaceFactoryOptions
): Record<string, unknown>;
export function createNativeBrowserCanvasBackend(options?: {
  contextFactory?: (canvas: unknown, context: unknown) => unknown;
}): NativeBrowserCanvasBackend;

export const gpu: DoeNamespace<GPUDevice, unknown, BrowserRequestDeviceOptions>;
export const createGpuNamespace: typeof import("./vendor/doe-namespace.js").createDoeNamespace;
export { createGpuNamespace as createDoeNamespace };

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
  gpu: typeof gpu;
  createGpuNamespace: typeof createGpuNamespace;
  CANVAS_ALPHA_MODES: typeof CANVAS_ALPHA_MODES;
  CANVAS_TONE_MAPPING_MODES: typeof CANVAS_TONE_MAPPING_MODES;
  CANVAS_COLOR_SPACES: typeof CANVAS_COLOR_SPACES;
  normalizeOrigin2D: typeof normalizeOrigin2D;
  normalizeCanvasConfiguration: typeof normalizeCanvasConfiguration;
  createBrowserSurfaceClasses: typeof createBrowserSurfaceClasses;
  createNativeBrowserCanvasBackend: typeof createNativeBrowserCanvasBackend;
};

export default _default;
