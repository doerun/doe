import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globals } from './webgpu-constants.js';
import {
  createDoeRuntime as createDoeRuntimeCli,
  runDawnVsDoeCompare as runDawnVsDoeCompareCli,
} from './runtime-cli.js';
import { loadDoeBuildMetadata } from './build-metadata.js';
import {
  UINT32_MAX,
  failValidation,
  describeResourceLabel,
  initResource,
  assertObject,
  assertArray,
  assertBoolean,
  assertNonEmptyString,
  assertIntegerInRange,
  assertOptionalIntegerInRange,
  validatePositiveInteger,
  assertLiveResource,
  destroyResource,
} from './shared/resource-lifecycle.js';
import {
  publishLimits,
  publishFeatures,
} from './shared/capabilities.js';
import {
  assertBufferDescriptor,
  assertTextureSize,
  assertBindGroupResource,
  normalizeSamplerLayout,
  normalizeTextureLayout,
  normalizeStorageTextureLayout,
  autoLayoutEntriesFromNativeBindings,
} from './shared/validation.js';
import {
  setupGlobalsOnTarget,
  requestAdapterFromCreate,
  requestDeviceFromRequestAdapter,
  buildProviderInfo,
  libraryFlavor,
} from './shared/public-surface.js';
import {
  enrichNativeCompilerError,
  compilerErrorFromMessage,
  pipelineErrorFromError,
} from './shared/compiler-errors.js';
import {
  createFullSurfaceClasses,
  dispatchDeviceEvent,
} from './shared/full-surface.js';
import {
  createEncoderClasses,
} from './shared/encoder-surface.js';
import {
  createBrowserSurfaceClasses,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
} from './shared/browser-surface.js';
import {
  createNativeBrowserCanvasBackend as createNativeBrowserCanvasBackendImpl,
} from './shared/browser-native-canvas-backend.js';
import {
  createNativeMetalCanvasBackend as createNativeMetalCanvasBackendImpl,
} from './shared/native-metal-canvas-backend.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = resolve(__dirname, '..', '..', '..');
const WORKSPACE_ROOT = resolve(PACKAGE_ROOT, '..', '..');
const require = createRequire(import.meta.url);
const TEXTURE_DIMENSION_MAP = Object.freeze({
  '1d': 1,
  '2d': 2,
  '3d': 3,
});
const TEXTURE_VIEW_DIMENSION_MAP = Object.freeze({
  '1d': 1,
  '2d': 2,
  '2d-array': 3,
  cube: 4,
  'cube-array': 5,
  '3d': 6,
});
const TEXTURE_ASPECT_MAP = Object.freeze({
  all: 1,
  'stencil-only': 2,
  'depth-only': 3,
});
const TEXTURE_SWIZZLE_COMPONENT_MAP = Object.freeze({
  '0': 1,
  '1': 2,
  r: 3,
  g: 4,
  b: 5,
  a: 6,
});
const NS_PER_MS = 1_000_000;
const WHOLE_SIZE_SENTINEL = -1;

const addon = loadAddon();
const DOE_LIB_PATH = resolveDoeLibraryPath();
const DOE_BUILD_METADATA = loadDoeBuildMetadata({
  packageRoot: PACKAGE_ROOT,
  libraryPath: DOE_LIB_PATH ?? '',
});
let libraryLoaded = false;
let nativeMetalCanvasBackend = null;

export {
  globals,
  preflightShaderSource,
  createNativeBrowserCanvasBackendImpl as createNativeBrowserCanvasBackend,
};


function loadAddon() {
  const candidates = [
    resolve(PACKAGE_ROOT, 'build', 'Release', 'doe_napi.node'),
    resolve(PACKAGE_ROOT, 'build', 'Debug', 'doe_napi.node'),
    resolve(__dirname, '..', 'build', 'Release', 'doe_napi.node'),
    resolve(__dirname, '..', 'build', 'Debug', 'doe_napi.node'),
    resolve(PACKAGE_ROOT, 'prebuilds', `${process.platform}-${process.arch}`, 'doe_napi.node'),
  ];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      // Keep searching. The common local failure is an incompatible stale binary.
    }
  }
  return null;
}

function resolveDoeLibraryPath() {
  const ext = process.platform === 'darwin' ? 'dylib'
    : process.platform === 'win32' ? 'dll' : 'so';

  const candidates = [
    process.env.DOE_WEBGPU_LIB,
    process.env.DOE_LIB,
    resolve(WORKSPACE_ROOT, 'runtime', 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(WORKSPACE_ROOT, 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(PACKAGE_ROOT, 'prebuilds', `${process.platform}-${process.arch}`, `libwebgpu_doe.${ext}`),
    resolve(process.cwd(), 'runtime', 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(process.cwd(), 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
  ];

  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate;
  }
  return null;
}

function ensureLibrary() {
  if (libraryLoaded) return;
  if (!addon) {
    throw new Error(
      'doe-gpu: Native addon not found. Run `npm run build:addon` or `npx node-gyp rebuild`.'
    );
  }
  if (!DOE_LIB_PATH) {
    throw new Error(
      'doe-gpu: libwebgpu_doe not found. Build it with `cd runtime/zig && zig build dropin` or set DOE_WEBGPU_LIB.'
    );
  }
  addon.loadLibrary(DOE_LIB_PATH);
  libraryLoaded = true;
}

function validateBufferDescriptor(descriptor) {
  return assertBufferDescriptor(descriptor, 'GPUDevice.createBuffer');
}

function presentPendingCanvasContexts(queue) {
  if (nativeMetalCanvasBackend && typeof nativeMetalCanvasBackend.queuePresentPendingCanvasContexts === 'function') {
    nativeMetalCanvasBackend.queuePresentPendingCanvasContexts(queue);
  }
}

/**
 * Read structured error fields from the native N-API addon's last-error ABI.
 * Uses `addon.getLastErrorLine` / `addon.getLastErrorColumn` when available
 * (requires native build that exports `doeNativeGetLastErrorLine/Column`).
 * Returns null when the addon does not expose these functions.
 */
function readLastErrorFields() {
  if (typeof addon?.getLastErrorStage !== 'function' && typeof addon?.getLastErrorKind !== 'function') {
    return null;
  }
  const stage = typeof addon?.getLastErrorStage === 'function' ? (addon.getLastErrorStage() ?? '') : '';
  const kind = typeof addon?.getLastErrorKind === 'function' ? (addon.getLastErrorKind() ?? '') : '';
  const line = typeof addon?.getLastErrorLine === 'function' ? Number(addon.getLastErrorLine()) : 0;
  const column = typeof addon?.getLastErrorColumn === 'function' ? Number(addon.getLastErrorColumn()) : 0;
  return {
    stage: stage || undefined,
    kind: kind || undefined,
    line: line > 0 ? line : undefined,
    column: column > 0 ? column : undefined,
  };
}

function adapterLimits(native) {
  if (typeof addon?.adapterGetLimits !== 'function') {
    return publishLimits(null);
  }
  return publishLimits(addon.adapterGetLimits(native));
}

function deviceLimits(native) {
  if (typeof addon?.deviceGetLimits !== 'function') {
    return publishLimits(null);
  }
  return publishLimits(addon.deviceGetLimits(native));
}

function adapterFeatures(native) {
  return publishFeatures(
    typeof addon?.adapterHasFeature === 'function'
      ? (feature) => addon.adapterHasFeature(native, feature)
      : null,
  );
}

function deviceFeatures(native) {
  return publishFeatures(
    typeof addon?.deviceHasFeature === 'function'
      ? (feature) => addon.deviceHasFeature(native, feature)
      : null,
  );
}

function preflightShaderSource(code) {
  ensureLibrary();
  if (typeof addon?.checkShaderSource === 'function') {
    const result = addon.checkShaderSource(code);
    if (result && typeof result === 'object') {
      const out = {
        ok: result.ok !== false,
        stage: result.stage ?? '',
        kind: result.kind ?? '',
        message: result.message ?? '',
        reasons: result.ok === false && result.message ? [result.message] : [],
      };
      if (typeof result.line === 'number' && result.line > 0) out.line = result.line;
      if (typeof result.column === 'number' && result.column > 0) out.column = result.column;
      return out;
    }
  }
  return { ok: true, stage: '', kind: '', message: '', reasons: [] };
}

function requireAutoLayoutEntriesFromNative(shaderNative, visibility, path) {
  if (typeof addon?.shaderModuleGetBindings !== 'function') {
    failValidation(
      path,
      'layout: "auto" requires native shader binding metadata on this package surface'
    );
  }
  const bindings = addon.shaderModuleGetBindings(shaderNative);
  if (!Array.isArray(bindings)) {
    failValidation(
      path,
      'layout: "auto" could not read native shader binding metadata'
    );
  }
  return autoLayoutEntriesFromNativeBindings(bindings, visibility);
}

const ERROR_SCOPE_FILTERS = Object.freeze({
  validation: 0x00000001,
  'out-of-memory': 0x00000002,
  internal: 0x00000003,
});

function createGpuError(result) {
  if (!result || result.type === 'no-error') {
    return null;
  }
  const error = new Error(result.message ?? '');
  if (result.type === 'validation') {
    error.name = 'GPUValidationError';
  } else if (result.type === 'out-of-memory') {
    error.name = 'GPUOutOfMemoryError';
  } else if (result.type === 'internal') {
    error.name = 'GPUInternalError';
  } else {
    error.name = 'GPUError';
  }
  error.type = result.type ?? 'unknown';
  return error;
}

function emptyAdapterInfo() {
  return Object.freeze({
    vendor: '',
    architecture: '',
    device: '',
    description: '',
    subgroupMinSize: 0,
    subgroupMaxSize: 0,
  });
}

function dispatchNodeDeviceEvent(device, event) {
  if (!event || typeof event !== 'object') {
    return;
  }
  if (typeof event.type === 'string') {
    dispatchDeviceEvent(device, event.type, event);
  }
  if (event.type === 'uncapturederror' && typeof device._onuncapturederror === 'function') {
    device._onuncapturederror.call(device, event);
  }
}

function unsupportedNodeDeviceCapability(name) {
  return new Error(`${name} is not available in this Node package build`);
}

function ensureNodeDeviceLostRegistration(device) {
  if (device._lostRegistrationAttempted) {
    return device._lostSupported;
  }
  device._lostRegistrationAttempted = true;
  if (typeof addon?.deviceRegisterLostCallback !== 'function') {
    device._lostSupported = false;
    device._lost = null;
    return false;
  }
  let resolveLost;
  const lostPromise = new Promise((resolve) => {
    resolveLost = resolve;
  });
  try {
    const registered = addon.deviceRegisterLostCallback(device._native, resolveLost);
    if (registered !== false) {
      device._lost = lostPromise;
      device._lostSupported = true;
      return true;
    }
  } catch (error) {
    if (!String(error?.message ?? '').includes('not available')) {
      throw error;
    }
  }
  device._lostSupported = false;
  device._lost = null;
  return false;
}

function installNodeDeviceCallbacks(device) {
  device._lostSupported = false;
  device._lostRegistrationAttempted = false;
  device._lost = null;
  device._eventListeners = new Map();
  device._onuncapturederror = null;
  const lostDescriptor = {
      configurable: true,
      enumerable: true,
      get() {
        if (this._lost != null) {
          return this._lost;
        }
        if (this._lostRegistrationAttempted && !this._lostSupported) {
          throw unsupportedNodeDeviceCapability('GPUDevice.lost');
        }
        assertLiveResource(this, 'GPUDevice.lost', 'GPUDevice');
        if (!ensureNodeDeviceLostRegistration(this)) {
          throw unsupportedNodeDeviceCapability('GPUDevice.lost');
        }
        return this._lost;
      },
    };
  Object.defineProperties(device, {
    lost: lostDescriptor,
    adapterInfo: {
      configurable: true,
      enumerable: true,
      get() {
        return this._adapterInfo ?? Object.freeze({
          vendor: '',
          architecture: '',
          device: '',
          description: '',
          subgroupMinSize: 0,
          subgroupMaxSize: 0,
        });
      },
    },
    onuncapturederror: {
      configurable: true,
      enumerable: true,
      get() {
        return this._onuncapturederror ?? null;
      },
      set(handler) {
        assertLiveResource(this, 'GPUDevice.onuncapturederror', 'GPUDevice');
        if (handler !== null && handler !== undefined && typeof handler !== 'function') {
          failValidation('GPUDevice.onuncapturederror', 'handler must be a function or null');
        }
        this._onuncapturederror = handler ?? null;
        if (typeof addon?.deviceSetUncapturedErrorCallback !== 'function') {
          if (handler) {
            throw unsupportedNodeDeviceCapability('GPUDevice.onuncapturederror');
          }
          return;
        }
        try {
          const registered = addon.deviceSetUncapturedErrorCallback(
            this._native,
            handler
              ? (event) => dispatchNodeDeviceEvent(this, event)
              : null,
          );
          if (registered === false && handler) {
            throw unsupportedNodeDeviceCapability('GPUDevice.onuncapturederror');
          }
        } catch (error) {
          if (String(error?.message ?? '').includes('not available')) {
            if (handler) {
              throw unsupportedNodeDeviceCapability('GPUDevice.onuncapturederror');
            }
            return;
          }
          throw error;
        }
      },
    },
  });
  ensureNodeDeviceLostRegistration(device);
}

function nodeDevicePushErrorScope(filter) {
  assertLiveResource(this, 'GPUDevice.pushErrorScope', 'GPUDevice');
  if (!Object.hasOwn(ERROR_SCOPE_FILTERS, filter)) {
    failValidation('GPUDevice.pushErrorScope', `invalid filter "${filter}"; must be "validation", "out-of-memory", or "internal"`);
  }
  if (typeof addon?.devicePushErrorScope !== 'function') {
    throw unsupportedNodeDeviceCapability('GPUDevice.pushErrorScope');
  }
  try {
    addon.devicePushErrorScope(this._native, ERROR_SCOPE_FILTERS[filter]);
  } catch (error) {
    if (String(error?.message ?? '').includes('not available')) {
      throw unsupportedNodeDeviceCapability('GPUDevice.pushErrorScope');
    }
    throw error;
  }
}

async function nodeDevicePopErrorScope() {
  assertLiveResource(this, 'GPUDevice.popErrorScope', 'GPUDevice');
  if (typeof addon?.devicePopErrorScope !== 'function') {
    throw unsupportedNodeDeviceCapability('GPUDevice.popErrorScope');
  }
  try {
    return createGpuError(addon.devicePopErrorScope(this._native, this._instance ?? null));
  } catch (error) {
    if (String(error?.message ?? '').includes('not available')) {
      throw unsupportedNodeDeviceCapability('GPUDevice.popErrorScope');
    }
    throw error;
  }
}


/**
 * Standard WebGPU enum objects exposed by the Doe package runtime.
 *
 * These package-local shared enum tables are commonly needed by Node and Bun
 * callers that want WebGPU constants without relying on browser globals.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { globals } from "doe-gpu";
 *
 * const usage = globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST;
 * ```
 *
 * - These values mirror the standard WebGPU numeric constants.
 * - They do not install themselves on `globalThis`; use `setupGlobals(...)` if needed.
 * - `doe-gpu/compute` shares the same constants even though its device facade is narrower.
 */
/**
 * Compute pass encoder returned by `commandEncoder.beginComputePass(...)`.
 *
 * This records a compute pass on the full package surface.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const pass = encoder.beginComputePass();
 * pass.setPipeline(pipeline);
 * ```
 *
 * - Dispatches may be batched until the command encoder is finalized.
 * - The encoder only supports the compute commands exposed by Doe here.
 */
function ensureNodeCommandEncoderNative(encoder) {
  encoder._assertOpen('GPUCommandEncoder');
  if (encoder._native) {
    return;
  }
  encoder._native = addon.createCommandEncoder(assertLiveResource(encoder._device, 'GPUCommandEncoder', 'GPUDevice'), encoder.label || undefined);
  for (const cmd of encoder._commands ?? []) {
    if (cmd.t === 0) {
      const pass = addon.beginComputePass(encoder._native, cmd.d ?? undefined);
      addon.computePassSetPipeline(pass, cmd.p);
      for (let index = 0; index < cmd.bg.length; index += 1) {
        if (cmd.bg[index]) {
          addon.computePassSetBindGroup(pass, index, cmd.bg[index]);
        }
      }
      addon.computePassDispatchWorkgroups(pass, cmd.x, cmd.y, cmd.z);
      addon.computePassEnd(pass);
      addon.computePassRelease(pass);
    } else if (cmd.t === 1) {
      addon.commandEncoderCopyBufferToBuffer(encoder._native, cmd.s, cmd.so, cmd.d, cmd.do, cmd.sz);
    }
  }
  encoder._commands = [];
}

function materializeLazyComputePass(pass) {
  if (!pass._lazy) {
    return;
  }
  ensureNodeCommandEncoderNative(pass._encoder);
  pass._lazy = false;
  pass._native = addon.beginComputePass(pass._encoder._native, pass._descriptor ?? undefined);
  if (pass._pipeline != null) {
    addon.computePassSetPipeline(pass._native, pass._pipeline);
  }
  for (let index = 0; index < pass._bindGroups.length; index += 1) {
    if (pass._bindGroups[index]) {
      addon.computePassSetBindGroup(pass._native, index, pass._bindGroups[index]);
    }
  }
}

function failIfSubmittedCommandBuffer(commandBuffer, index) {
  if (commandBuffer?._submitted) {
    failValidation('GPUQueue.submit', `commandBuffers[${index}] was already submitted`);
  }
}

function consumeSubmittedCommandBuffers(commandBuffers) {
  for (const commandBuffer of commandBuffers) {
    if (!commandBuffer || typeof commandBuffer !== 'object') {
      continue;
    }
    commandBuffer._submitted = true;
    commandBuffer.destroy?.();
  }
}

function elapsedNsSince(startedAtMs) {
  return Math.max(0, Math.round((performance.now() - startedAtMs) * NS_PER_MS));
}

function zeroQueueSubmitBreakdown() {
  return {
    submitCommandPrepTotalNs: 0,
    submitAddonCallTotalNs: 0,
    submitAddonCommandReplayTotalNs: 0,
    submitAddonQueueSubmitTotalNs: 0,
    submitAddonFlushTotalNs: 0,
    submitPostSubmitBookkeepingTotalNs: 0,
    submitQueueFlushTotalNs: 0,
    submitQueueFlushWaitCompletedTotalNs: 0,
    submitQueueFlushDeferredCopyTotalNs: 0,
    submitQueueFlushDeferredResolveTotalNs: 0,
    submitQueueWaitBookkeepingTotalNs: 0,
  };
}

function accumulateQueueSubmitBreakdown(queue, field, startedAtMs) {
  queue._submitBreakdownNs[field] += elapsedNsSince(startedAtMs);
}

function accumulateAddonSubmitBreakdown(queue, addonBreakdown) {
  if (!addonBreakdown || typeof addonBreakdown !== 'object') {
    return;
  }
  queue._submitBreakdownNs.submitAddonCommandReplayTotalNs += Number(addonBreakdown.commandReplayNs ?? 0);
  queue._submitBreakdownNs.submitAddonQueueSubmitTotalNs += Number(addonBreakdown.queueSubmitNs ?? 0);
  queue._submitBreakdownNs.submitAddonFlushTotalNs += Number(addonBreakdown.flushNs ?? 0);
}

function accumulateQueueFlushBreakdown(queue, flushBreakdown) {
  if (!flushBreakdown || typeof flushBreakdown !== 'object') {
    return;
  }
  queue._submitBreakdownNs.submitQueueFlushWaitCompletedTotalNs += Number(flushBreakdown.waitCompletedNs ?? 0);
  queue._submitBreakdownNs.submitQueueFlushDeferredCopyTotalNs += Number(flushBreakdown.deferredCopyNs ?? 0);
  queue._submitBreakdownNs.submitQueueFlushDeferredResolveTotalNs += Number(flushBreakdown.deferredResolveNs ?? 0);
}

const nodeEncoderBackend = {
  computePassInit(pass, native) {
    if (native === null) {
      pass._native = null;
      pass._pipeline = null;
      pass._bindGroups = [];
      pass._lazy = true;
    } else {
      pass._native = native;
      pass._lazy = false;
    }
    pass._descriptor = undefined;
    pass._ended = false;
  },
  computePassAssertOpen(pass, path) {
    if (pass._ended) {
      failValidation(path, 'compute pass is already ended');
    }
    if (pass._encoder._finished) {
      failValidation(path, 'command encoder is already finished');
    }
  },
  computePassSetPipeline(pass, pipelineNative) {
    if (pass._lazy) {
      pass._pipeline = pipelineNative;
      return;
    }
    addon.computePassSetPipeline(
      assertLiveResource(pass, 'GPUComputePassEncoder.setPipeline', 'GPUComputePassEncoder'),
      pipelineNative,
    );
  },
  computePassSetBindGroup(pass, index, bindGroupNative) {
    if (pass._lazy) {
      pass._bindGroups[index] = bindGroupNative;
      return;
    }
    addon.computePassSetBindGroup(
      assertLiveResource(pass, 'GPUComputePassEncoder.setBindGroup', 'GPUComputePassEncoder'),
      index,
      bindGroupNative,
    );
  },
  computePassSetImmediates(pass, index, data) {
    materializeLazyComputePass(pass);
    addon.computePassSetImmediates(
      assertLiveResource(pass, 'GPUComputePassEncoder.setImmediates', 'GPUComputePassEncoder'),
      index,
      data,
    );
  },
  computePassDispatchWorkgroups(pass, x, y, z) {
    if (pass._lazy) {
      if (pass._pipeline == null) {
        failValidation('GPUComputePassEncoder.dispatchWorkgroups', 'setPipeline() must be called before dispatch');
      }
      pass._encoder._commands.push({ t: 0, p: pass._pipeline, bg: [...pass._bindGroups], x, y, z, d: pass._descriptor ?? undefined });
      return;
    }
    addon.computePassDispatchWorkgroups(
      assertLiveResource(
        pass,
        'GPUComputePassEncoder.dispatchWorkgroups',
        'GPUComputePassEncoder',
      ),
      x,
      y,
      z,
    );
  },
  computePassDispatchBound(pass, pipelineNative, bindGroupNative, x, y, z) {
    if (pass._lazy) {
      pass._pipeline = pipelineNative;
      pass._bindGroups[0] = bindGroupNative;
      pass._encoder._commands.push({ t: 0, p: pipelineNative, bg: [...pass._bindGroups], x, y, z, d: pass._descriptor ?? undefined });
      return;
    }
    const nativePass = assertLiveResource(
      pass,
      'GPUComputePassEncoder._dispatchBound',
      'GPUComputePassEncoder',
    );
    if (typeof addon.computePassDispatchBound === 'function') {
      addon.computePassDispatchBound(nativePass, pipelineNative, bindGroupNative, x, y, z);
      return;
    }
    addon.computePassSetPipeline(nativePass, pipelineNative);
    addon.computePassSetBindGroup(nativePass, 0, bindGroupNative);
    addon.computePassDispatchWorkgroups(nativePass, x, y, z);
  },
  computePassDispatchWorkgroupsIndirect(pass, indirectBufferNative, indirectOffset) {
    materializeLazyComputePass(pass);
    const nativePass = assertLiveResource(
      pass,
      'GPUComputePassEncoder.dispatchWorkgroupsIndirect',
      'GPUComputePassEncoder',
    );
    addon.computePassDispatchWorkgroupsIndirect(nativePass, indirectBufferNative, indirectOffset);
  },
  computePassEnd(pass) {
    if (pass._lazy) {
      pass._ended = true;
      return;
    }
    addon.computePassEnd(
      assertLiveResource(pass, 'GPUComputePassEncoder.end', 'GPUComputePassEncoder'),
    );
    addon.computePassRelease(pass._native);
    pass._native = null;
    pass._ended = true;
  },
  renderPassInit(pass, native) {
    pass._native = native;
    pass._ended = false;
  },
  renderPassAssertOpen(pass, path) {
    if (pass._ended) {
      failValidation(path, 'render pass is already ended');
    }
    if (pass._encoder._finished) {
      failValidation(path, 'command encoder is already finished');
    }
  },
  renderPassSetPipeline(pass, pipelineNative) {
    addon.renderPassSetPipeline(
      assertLiveResource(pass, 'GPURenderPassEncoder.setPipeline', 'GPURenderPassEncoder'),
      pipelineNative,
    );
  },
  renderPassSetBindGroup(pass, index, bindGroupNative) {
    addon.renderPassSetBindGroup(
      assertLiveResource(pass, 'GPURenderPassEncoder.setBindGroup', 'GPURenderPassEncoder'),
      index,
      bindGroupNative,
    );
  },
  renderPassSetImmediates(pass, index, data) {
    addon.renderPassSetImmediates(
      assertLiveResource(pass, 'GPURenderPassEncoder.setImmediates', 'GPURenderPassEncoder'),
      index,
      data,
    );
  },
  renderPassSetVertexBuffer(pass, slot, bufferNative, offset, size) {
    addon.renderPassSetVertexBuffer(
      assertLiveResource(pass, 'GPURenderPassEncoder.setVertexBuffer', 'GPURenderPassEncoder'),
      slot,
      bufferNative,
      offset,
      size ?? WHOLE_SIZE_SENTINEL,
    );
  },
  renderPassSetIndexBuffer(pass, bufferNative, format, offset, size) {
    addon.renderPassSetIndexBuffer(
      assertLiveResource(pass, 'GPURenderPassEncoder.setIndexBuffer', 'GPURenderPassEncoder'),
      bufferNative,
      format,
      offset,
      size ?? WHOLE_SIZE_SENTINEL,
    );
  },
  renderPassDraw(pass, vertexCount, instanceCount, firstVertex, firstInstance) {
    addon.renderPassDraw(pass._native, vertexCount, instanceCount, firstVertex, firstInstance);
  },
  renderPassDrawIndexed(pass, indexCount, instanceCount, firstIndex, baseVertex, firstInstance) {
    addon.renderPassDrawIndexed(pass._native, indexCount, instanceCount, firstIndex, baseVertex, firstInstance);
  },
  renderPassDrawIndirect(pass, indirectBufferNative, indirectOffset) {
    if (typeof addon.renderPassDrawIndirect !== 'function') {
      throw unsupportedNodeDeviceCapability('GPURenderPassEncoder.drawIndirect');
    }
    addon.renderPassDrawIndirect(pass._native, indirectBufferNative, indirectOffset);
  },
  renderPassDrawIndexedIndirect(pass, indirectBufferNative, indirectOffset) {
    if (typeof addon.renderPassDrawIndexedIndirect !== 'function') {
      throw unsupportedNodeDeviceCapability('GPURenderPassEncoder.drawIndexedIndirect');
    }
    addon.renderPassDrawIndexedIndirect(pass._native, indirectBufferNative, indirectOffset);
  },
  renderPassSetViewport(pass, x, y, width, height, minDepth, maxDepth) {
    addon.renderPassSetViewport(pass._native, x, y, width, height, minDepth, maxDepth);
  },
  renderPassSetScissorRect(pass, x, y, width, height) {
    addon.renderPassSetScissorRect(pass._native, x, y, width, height);
  },
  renderPassSetBlendConstant(pass, color) {
    addon.renderPassSetBlendConstant(pass._native, color);
  },
  renderPassSetStencilReference(pass, ref) {
    addon.renderPassSetStencilReference(pass._native, ref);
  },
  renderPassBeginOcclusionQuery(pass, queryIndex) {
    if (typeof addon.renderPassBeginOcclusionQuery === 'function') {
      addon.renderPassBeginOcclusionQuery(pass._native, queryIndex);
    }
  },
  renderPassEndOcclusionQuery(pass) {
    if (typeof addon.renderPassEndOcclusionQuery === 'function') {
      addon.renderPassEndOcclusionQuery(pass._native);
    }
  },
  renderPassExecuteBundles(pass, bundles) {
    if (typeof addon.renderPassExecuteBundles === 'function') {
      addon.renderPassExecuteBundles(pass._native, bundles.map((b) => b._native));
    }
  },
  renderPassPushDebugGroup(pass, label) {
    if (typeof addon.renderPassPushDebugGroup === 'function') {
      addon.renderPassPushDebugGroup(pass._native, label);
    }
  },
  renderPassPopDebugGroup(pass) {
    if (typeof addon.renderPassPopDebugGroup === 'function') {
      addon.renderPassPopDebugGroup(pass._native);
    }
  },
  renderPassInsertDebugMarker(pass, label) {
    if (typeof addon.renderPassInsertDebugMarker === 'function') {
      addon.renderPassInsertDebugMarker(pass._native, label);
    }
  },
  computePassPushDebugGroup(pass, label) {
    if (typeof addon.computePassPushDebugGroup === 'function') {
      addon.computePassPushDebugGroup(pass._native, label);
    }
  },
  computePassPopDebugGroup(pass) {
    if (typeof addon.computePassPopDebugGroup === 'function') {
      addon.computePassPopDebugGroup(pass._native);
    }
  },
  computePassInsertDebugMarker(pass, label) {
    if (typeof addon.computePassInsertDebugMarker === 'function') {
      addon.computePassInsertDebugMarker(pass._native, label);
    }
  },
  renderPassEnd(pass) {
    addon.renderPassEnd(pass._native);
    pass._ended = true;
  },
  renderBundleEncoderInit(enc, state) {
    enc._native = state;
    enc._ended = false;
  },
  renderBundleEncoderSetPipeline(enc, pipelineNative) {
    addon.renderBundleEncoderSetPipeline(enc._native, pipelineNative);
  },
  renderBundleEncoderSetBindGroup(enc, index, bindGroupNative) {
    addon.renderBundleEncoderSetBindGroup(enc._native, index, bindGroupNative);
  },
  renderBundleEncoderSetImmediates(enc, index, data) {
    addon.renderBundleEncoderSetImmediates(
      assertLiveResource(enc, 'GPURenderBundleEncoder.setImmediates', 'GPURenderBundleEncoder'),
      index,
      data,
    );
  },
  renderBundleEncoderSetVertexBuffer(enc, slot, bufferNative, offset, size) {
    addon.renderBundleEncoderSetVertexBuffer(enc._native, slot, bufferNative, offset, size ?? WHOLE_SIZE_SENTINEL);
  },
  renderBundleEncoderSetIndexBuffer(enc, bufferNative, format, offset, size) {
    addon.renderBundleEncoderSetIndexBuffer(enc._native, bufferNative, format, offset, size ?? WHOLE_SIZE_SENTINEL);
  },
  renderBundleEncoderDraw(enc, vertexCount, instanceCount, firstVertex, firstInstance) {
    addon.renderBundleEncoderDraw(enc._native, vertexCount, instanceCount, firstVertex, firstInstance);
  },
  renderBundleEncoderDrawIndexed(enc, indexCount, instanceCount, firstIndex, baseVertex, firstInstance) {
    addon.renderBundleEncoderDrawIndexed(enc._native, indexCount, instanceCount, firstIndex, baseVertex, firstInstance);
  },
  renderBundleEncoderDrawIndirect(enc, indirectBufferNative, indirectOffset) {
    if (typeof addon.renderBundleEncoderDrawIndirect !== 'function') {
      throw unsupportedNodeDeviceCapability('GPURenderBundleEncoder.drawIndirect');
    }
    addon.renderBundleEncoderDrawIndirect(enc._native, indirectBufferNative, indirectOffset);
  },
  renderBundleEncoderDrawIndexedIndirect(enc, indirectBufferNative, indirectOffset) {
    if (typeof addon.renderBundleEncoderDrawIndexedIndirect !== 'function') {
      throw unsupportedNodeDeviceCapability('GPURenderBundleEncoder.drawIndexedIndirect');
    }
    addon.renderBundleEncoderDrawIndexedIndirect(enc._native, indirectBufferNative, indirectOffset);
  },
  commandBufferDestroy(native) {
    if (typeof addon.commandBufferRelease === 'function') {
      addon.commandBufferRelease(native);
    }
  },
  renderBundleEncoderPushDebugGroup(enc, label) {
    if (typeof addon.renderBundleEncoderPushDebugGroup === 'function') {
      addon.renderBundleEncoderPushDebugGroup(enc._native, label);
    }
  },
  renderBundleEncoderPopDebugGroup(enc) {
    if (typeof addon.renderBundleEncoderPopDebugGroup === 'function') {
      addon.renderBundleEncoderPopDebugGroup(enc._native);
    }
  },
  renderBundleEncoderInsertDebugMarker(enc, label) {
    if (typeof addon.renderBundleEncoderInsertDebugMarker === 'function') {
      addon.renderBundleEncoderInsertDebugMarker(enc._native, label);
    }
  },
  renderBundleEncoderFinish(enc, _descriptor, classes) {
    const bundle = addon.renderBundleEncoderFinish(enc._native);
    enc._ended = true;
    return new classes.DoeGPURenderBundle(bundle, enc._encoder ?? enc);
  },
  renderBundleDestroy(native) {
    if (typeof addon.renderBundleRelease === 'function') {
      addon.renderBundleRelease(native);
    }
  },
  commandEncoderInit(encoder) {
    encoder._commands = [];
    encoder._native = addon.createCommandEncoder(
      assertLiveResource(encoder._device, 'GPUCommandEncoder', 'GPUDevice'),
      encoder.label || undefined,
    );
    encoder._finished = false;
  },
  commandEncoderAssertOpen(encoder, path) {
    if (encoder._finished) {
      failValidation(path, 'command encoder is already finished');
    }
  },
  commandEncoderBeginComputePass(encoder, _descriptor, classes) {
    let passDescriptor = undefined;
    if (_descriptor !== undefined && _descriptor !== null) {
      const descriptor = assertObject(_descriptor, 'GPUCommandEncoder.beginComputePass', 'descriptor');
      passDescriptor = {};
      if (descriptor.label !== undefined) {
        passDescriptor.label = descriptor.label;
      }
      if (descriptor.timestampWrites !== undefined && descriptor.timestampWrites !== null) {
        const writes = assertObject(descriptor.timestampWrites, 'GPUCommandEncoder.beginComputePass', 'descriptor.timestampWrites');
        passDescriptor.timestampWrites = {
          querySet: assertLiveResource(writes.querySet, 'GPUCommandEncoder.beginComputePass', 'GPUQuerySet'),
          beginningOfPassWriteIndex: writes.beginningOfPassWriteIndex ?? 0xFFFFFFFF,
          endOfPassWriteIndex: writes.endOfPassWriteIndex ?? 0xFFFFFFFF,
        };
      }
      if (Object.keys(passDescriptor).length === 0) {
        passDescriptor = undefined;
      }
    }
    if (encoder._native === null) {
      const pass = new classes.DoeGPUComputePassEncoder(null, encoder);
      pass._descriptor = passDescriptor;
      return pass;
    }
    const pass = new classes.DoeGPUComputePassEncoder(
      addon.beginComputePass(encoder._native, passDescriptor),
      encoder,
    );
    pass._descriptor = passDescriptor;
    return pass;
  },
  commandEncoderBeginRenderPass(encoder, passDescriptor, classes) {
    const attachments = assertArray(passDescriptor.colorAttachments ?? [], 'GPUCommandEncoder.beginRenderPass', 'descriptor.colorAttachments');
    if (attachments.length === 0) {
      failValidation('GPUCommandEncoder.beginRenderPass', 'descriptor.colorAttachments must contain at least one attachment');
    }
    ensureNodeCommandEncoderNative(encoder);
    const colorAttachments = attachments.map((attachment, index) => {
      const entry = assertObject(attachment, 'GPUCommandEncoder.beginRenderPass', `descriptor.colorAttachments[${index}]`);
      const normalized = {
        view: assertLiveResource(entry.view, 'GPUCommandEncoder.beginRenderPass', 'GPUTextureView'),
        clearValue: entry.clearValue || { r: 0, g: 0, b: 0, a: 1 },
        loadOp: entry.loadOp ?? 'clear',
        storeOp: entry.storeOp ?? 'store',
      };
      if (entry.resolveTarget !== undefined && entry.resolveTarget !== null) {
        normalized.resolveTarget = assertLiveResource(entry.resolveTarget, 'GPUCommandEncoder.beginRenderPass', 'GPUTextureView');
      }
      if (entry.depthSlice !== undefined) {
        normalized.depthSlice = entry.depthSlice;
      }
      return normalized;
    });
    let depthStencilAttachment = undefined;
    if (passDescriptor.depthStencilAttachment !== undefined) {
      const depthAttachment = assertObject(passDescriptor.depthStencilAttachment, 'GPUCommandEncoder.beginRenderPass', 'descriptor.depthStencilAttachment');
      depthStencilAttachment = {
        view: assertLiveResource(depthAttachment.view, 'GPUCommandEncoder.beginRenderPass', 'GPUTextureView'),
        depthLoadOp: depthAttachment.depthLoadOp ?? 'clear',
        depthStoreOp: depthAttachment.depthStoreOp ?? 'store',
        depthClearValue: depthAttachment.depthClearValue ?? 1,
        depthReadOnly: depthAttachment.depthReadOnly ?? false,
        stencilLoadOp: depthAttachment.stencilLoadOp ?? 'clear',
        stencilStoreOp: depthAttachment.stencilStoreOp ?? 'store',
        stencilClearValue: depthAttachment.stencilClearValue ?? 0,
        stencilReadOnly: depthAttachment.stencilReadOnly ?? false,
      };
    }
    let occlusionQuerySet = undefined;
    if (passDescriptor.occlusionQuerySet !== undefined && passDescriptor.occlusionQuerySet !== null) {
      occlusionQuerySet = assertLiveResource(passDescriptor.occlusionQuerySet, 'GPUCommandEncoder.beginRenderPass', 'GPUQuerySet');
    }
    let timestampWrites = undefined;
    if (passDescriptor.timestampWrites !== undefined && passDescriptor.timestampWrites !== null) {
      const writes = assertObject(passDescriptor.timestampWrites, 'GPUCommandEncoder.beginRenderPass', 'descriptor.timestampWrites');
      timestampWrites = {
        querySet: assertLiveResource(writes.querySet, 'GPUCommandEncoder.beginRenderPass', 'GPUQuerySet'),
        beginningOfPassWriteIndex: writes.beginningOfPassWriteIndex ?? 0xFFFFFFFF,
        endOfPassWriteIndex: writes.endOfPassWriteIndex ?? 0xFFFFFFFF,
      };
    }
    const normalizedDescriptor = {
      label: passDescriptor.label,
      colorAttachments,
      depthStencilAttachment,
      occlusionQuerySet,
      timestampWrites,
      maxDrawCount: passDescriptor.maxDrawCount ?? 50_000_000,
    };
    const pass = addon.beginRenderPass(encoder._native, normalizedDescriptor);
    return new classes.DoeGPURenderPassEncoder(pass, encoder);
  },
  commandEncoderCopyBufferToBuffer(encoder, srcNative, srcOffset, dstNative, dstOffset, size) {
    if (encoder._native === null) {
      encoder._commands.push({ t: 1, s: srcNative, so: srcOffset, d: dstNative, do: dstOffset, sz: size });
      return;
    }
    addon.commandEncoderCopyBufferToBuffer(encoder._native, srcNative, srcOffset, dstNative, dstOffset, size);
  },
  commandEncoderWriteTimestamp(encoder, querySetNative, queryIndex) {
    ensureNodeCommandEncoderNative(encoder);
    addon.commandEncoderWriteTimestamp(encoder._native, querySetNative, queryIndex);
  },
  commandEncoderResolveQuerySet(encoder, querySetNative, firstQuery, queryCount, destinationNative, destinationOffset) {
    ensureNodeCommandEncoderNative(encoder);
    addon.commandEncoderResolveQuerySet(encoder._native, querySetNative, firstQuery, queryCount, destinationNative, destinationOffset);
  },
  commandEncoderCopyBufferToTexture(encoder, source, destination, copySize) {
    ensureNodeCommandEncoderNative(encoder);
    addon.commandEncoderCopyBufferToTexture(
      encoder._native,
      source.buffer,
      source.offset ?? 0,
      source.bytesPerRow ?? 0,
      source.rowsPerImage ?? 0,
      destination.texture,
      destination.mipLevel ?? 0,
      destination.origin?.x ?? 0,
      destination.origin?.y ?? 0,
      destination.origin?.z ?? 0,
      destination.aspect ?? 1,
      copySize.width,
      copySize.height,
      copySize.depthOrArrayLayers ?? 1,
    );
  },
  commandEncoderCopyTextureToBuffer(encoder, source, destination, copySize) {
    ensureNodeCommandEncoderNative(encoder);
    addon.commandEncoderCopyTextureToBuffer(
      encoder._native,
      source.texture,
      source.mipLevel ?? 0,
      source.origin?.x ?? 0,
      source.origin?.y ?? 0,
      source.origin?.z ?? 0,
      source.aspect ?? 1,
      destination.buffer,
      destination.offset ?? 0,
      destination.bytesPerRow ?? 0,
      destination.rowsPerImage ?? 0,
      copySize.width,
      copySize.height,
      copySize.depthOrArrayLayers ?? 1,
    );
  },
  commandEncoderClearBuffer(encoder, bufferNative, offset, size) {
    ensureNodeCommandEncoderNative(encoder);
    addon.commandEncoderClearBuffer(
      encoder._native,
      bufferNative,
      offset,
      size,
    );
  },
  commandEncoderPushDebugGroup(encoder, label) {
    if (typeof addon.commandEncoderPushDebugGroup === 'function') {
      addon.commandEncoderPushDebugGroup(encoder._native, label);
    }
  },
  commandEncoderPopDebugGroup(encoder) {
    if (typeof addon.commandEncoderPopDebugGroup === 'function') {
      addon.commandEncoderPopDebugGroup(encoder._native);
    }
  },
  commandEncoderInsertDebugMarker(encoder, label) {
    if (typeof addon.commandEncoderInsertDebugMarker === 'function') {
      addon.commandEncoderInsertDebugMarker(encoder._native, label);
    }
  },
  commandEncoderCopyTextureToTexture(encoder, source, destination, copySize) {
    ensureNodeCommandEncoderNative(encoder);
    addon.commandEncoderCopyTextureToTexture(
      encoder._native,
      source.texture,
      source.mipLevel ?? 0,
      source.origin?.x ?? 0,
      source.origin?.y ?? 0,
      source.origin?.z ?? 0,
      source.aspect ?? 1,
      destination.texture,
      destination.mipLevel ?? 0,
      destination.origin?.x ?? 0,
      destination.origin?.y ?? 0,
      destination.origin?.z ?? 0,
      copySize.width,
      copySize.height,
      copySize.depthOrArrayLayers ?? 1,
    );
  },
  commandEncoderFinish(encoder) {
    const cmds = encoder._commands;
    if (encoder._native === null) {
      encoder._finished = true;
      return { _commands: cmds, _batched: true };
    }
    encoder._finished = true;
    const cmd = addon.commandEncoderFinish(encoder._native);
    encoder._native = null;
    return { _native: cmd, _batched: false };
  },
};

const {
  DoeGPUComputePassEncoder,
  DoeGPUCommandEncoder,
  DoeGPURenderPassEncoder,
  DoeGPURenderBundleEncoder,
  DoeGPURenderBundle,
} = createEncoderClasses(nodeEncoderBackend);

/**
 * Texture returned by `device.createTexture(...)`.
 *
 * This represents a headless Doe texture resource and can create default views
 * for render or sampling usage.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const texture = device.createTexture({
 *   size: [64, 64, 1],
 *   format: "rgba8unorm",
 *   usage: GPUTextureUsage.RENDER_ATTACHMENT,
 * });
 * ```
 *
 * - The package currently exposes the texture operations needed by its headless surface.
 * - Texture views are created through `createView(...)`.
 */
const fullSurfaceBackend = {
  initBufferState(buffer) {
    buffer._mapMode = 0;
    buffer._mappedWriteRanges = [];
  },
  bufferMarkMappedAtCreation(buffer) {
    buffer._mapMode = globals.GPUMapMode.WRITE;
    buffer._mappedWriteRanges = [];
  },
  bufferMapAsync(wrapper, native, mode, offset, size) {
    if (wrapper._queue) {
      if (wrapper._queue.hasPendingSubmissions()) {
        addon.flushAndMapSync(
          wrapper._instance,
          assertLiveResource(wrapper._queue, 'GPUBuffer.mapAsync', 'GPUQueue'),
          native,
          mode,
          offset,
          size,
        );
        wrapper._queue.markSubmittedWorkDone();
      } else {
        addon.bufferMapSync(wrapper._instance, native, mode, offset, size);
      }
    } else {
      addon.bufferMapSync(wrapper._instance, native, mode, offset, size);
    }
    wrapper._mapMode = mode;
    if (mode === globals.GPUMapMode.WRITE) {
      wrapper._mappedWriteRanges = [];
    }
  },
  bufferGetMappedRange(wrapper, native, offset, size) {
    if (wrapper._mapMode === globals.GPUMapMode.WRITE) {
      const staged = addon.bufferGetStagedRange(native, offset, size);
      wrapper._mappedWriteRanges.push({ buf: staged, native, offset, size });
      return staged;
    }
    return addon.bufferGetMappedRange(native, offset, size);
  },
  bufferReadCopy(_wrapper, native, offset, size) {
    if (typeof addon.bufferReadCopy === 'function') {
      return addon.bufferReadCopy(native, offset, size);
    }
    return addon.bufferGetMappedRange(native, offset, size).slice(0);
  },
  bufferGetMapState(_wrapper, native) {
    if (_wrapper?._mapState === 'pending') {
      return 'pending';
    }
    if (typeof addon.bufferGetMapState !== 'function') {
      return null;
    }
    return addon.bufferGetMapState(native);
  },
  bufferAssertMappedPrefixF32(_wrapper, native, expected, count) {
    return addon.bufferAssertMappedPrefixF32(native, expected, count);
  },
  bufferUnmap(native, wrapper) {
    for (const range of wrapper._mappedWriteRanges ?? []) {
      addon.bufferFlushStagedRange(range.native, range.buf, range.offset, range.size);
    }
    wrapper._mappedWriteRanges = [];
    wrapper._mapMode = 0;
    addon.bufferUnmap(native);
  },
  bufferDestroy(native) {
    addon.bufferRelease(native);
  },
  initQueueState(queue) {
    queue._submittedSerial = 0;
    queue._completedSerial = 0;
    queue._submitBreakdownNs = zeroQueueSubmitBreakdown();
  },
  queueHasPendingSubmissions(queue) {
    return queue._completedSerial < queue._submittedSerial;
  },
  queueMarkSubmittedWorkDone(queue) {
    queue._completedSerial = queue._submittedSerial;
  },
  queueSubmit(queue, queueNative, buffers) {
    const deviceNative = assertLiveResource(queue._device, 'GPUQueue.submit', 'GPUDevice');
    queue._submittedSerial += 1;
    if (buffers.length === 1 && buffers[0]?._batched && Array.isArray(buffers[0]._commands)) {
      const prepStartedAt = performance.now();
      failIfSubmittedCommandBuffer(buffers[0], 0);
      const cmds = buffers[0]._commands;
      accumulateQueueSubmitBreakdown(queue, 'submitCommandPrepTotalNs', prepStartedAt);
      if (cmds.length === 0) {
        const bookkeepingStartedAt = performance.now();
        queue.markSubmittedWorkDone();
        consumeSubmittedCommandBuffers(buffers);
        presentPendingCanvasContexts(queue);
        accumulateQueueSubmitBreakdown(queue, 'submitPostSubmitBookkeepingTotalNs', bookkeepingStartedAt);
        return;
      }
      if (
        cmds.length === 2
        && cmds[0]?.t === 0
        && cmds[1]?.t === 1
        && typeof addon.submitComputeDispatchCopy === 'function'
      ) {
        const addonStartedAt = performance.now();
        addon.submitComputeDispatchCopy(
          deviceNative,
          queueNative,
          cmds[0].p,
          cmds[0].bg,
          cmds[0].x,
          cmds[0].y,
          cmds[0].z,
          cmds[1].s,
          cmds[1].so,
          cmds[1].d,
          cmds[1].do,
          cmds[1].sz,
        );
        accumulateQueueSubmitBreakdown(queue, 'submitAddonCallTotalNs', addonStartedAt);
        // submitComputeDispatchCopy is synchronous: spin-polls until GPU signals.
        // Mark done so onSubmittedWorkDone() short-circuits rather than calling queueFlush.
        const bookkeepingStartedAt = performance.now();
        queue.markSubmittedWorkDone();
        consumeSubmittedCommandBuffers(buffers);
        presentPendingCanvasContexts(queue);
        accumulateQueueSubmitBreakdown(queue, 'submitPostSubmitBookkeepingTotalNs', bookkeepingStartedAt);
        return;
      }
      const addonStartedAt = performance.now();
      const addonBreakdown = addon.submitBatched(deviceNative, queueNative, cmds);
      accumulateQueueSubmitBreakdown(queue, 'submitAddonCallTotalNs', addonStartedAt);
      accumulateAddonSubmitBreakdown(queue, addonBreakdown);
      const bookkeepingStartedAt = performance.now();
      if (
        cmds.length === 2
        && cmds[0]?.t === 0
        && cmds[1]?.t === 1
      ) {
        queue.markSubmittedWorkDone();
      }
      consumeSubmittedCommandBuffers(buffers);
      presentPendingCanvasContexts(queue);
      accumulateQueueSubmitBreakdown(queue, 'submitPostSubmitBookkeepingTotalNs', bookkeepingStartedAt);
      return;
    }
    if (buffers.every((commandBuffer) => commandBuffer?._batched && Array.isArray(commandBuffer._commands))) {
      const prepStartedAt = performance.now();
      for (let index = 0; index < buffers.length; index += 1) {
        failIfSubmittedCommandBuffer(buffers[index], index);
      }
      const allCommands = [];
      for (const cb of buffers) {
        allCommands.push(...cb._commands);
      }
      accumulateQueueSubmitBreakdown(queue, 'submitCommandPrepTotalNs', prepStartedAt);
      if (allCommands.length === 0) {
        const bookkeepingStartedAt = performance.now();
        queue.markSubmittedWorkDone();
        consumeSubmittedCommandBuffers(buffers);
        presentPendingCanvasContexts(queue);
        accumulateQueueSubmitBreakdown(queue, 'submitPostSubmitBookkeepingTotalNs', bookkeepingStartedAt);
        return;
      }
      const addonStartedAt = performance.now();
      const addonBreakdown = addon.submitBatched(deviceNative, queueNative, allCommands);
      accumulateQueueSubmitBreakdown(queue, 'submitAddonCallTotalNs', addonStartedAt);
      accumulateAddonSubmitBreakdown(queue, addonBreakdown);
      const bookkeepingStartedAt = performance.now();
      if (
        allCommands.length === 2
        && allCommands[0]?.t === 0
        && allCommands[1]?.t === 1
      ) {
        queue.markSubmittedWorkDone();
      }
      consumeSubmittedCommandBuffers(buffers);
      presentPendingCanvasContexts(queue);
      accumulateQueueSubmitBreakdown(queue, 'submitPostSubmitBookkeepingTotalNs', bookkeepingStartedAt);
      return;
    }
    const prepStartedAt = performance.now();
    const natives = buffers.map((commandBuffer, index) => {
      failIfSubmittedCommandBuffer(commandBuffer, index);
      if (!commandBuffer || typeof commandBuffer !== 'object' || commandBuffer._native == null) {
        failValidation('GPUQueue.submit', `commandBuffers[${index}] must be a finished command buffer`);
      }
      return commandBuffer._native;
    });
    accumulateQueueSubmitBreakdown(queue, 'submitCommandPrepTotalNs', prepStartedAt);
    const addonStartedAt = performance.now();
    const addonBreakdown = addon.queueSubmit(queueNative, natives);
    accumulateQueueSubmitBreakdown(queue, 'submitAddonCallTotalNs', addonStartedAt);
    accumulateAddonSubmitBreakdown(queue, addonBreakdown);
    const bookkeepingStartedAt = performance.now();
    consumeSubmittedCommandBuffers(buffers);
    presentPendingCanvasContexts(queue);
    accumulateQueueSubmitBreakdown(queue, 'submitPostSubmitBookkeepingTotalNs', bookkeepingStartedAt);
  },
  queueWriteBuffer(_queue, queueNative, bufferNative, bufferOffset, view) {
    addon.queueWriteBuffer(queueNative, bufferNative, bufferOffset, view);
  },
  queueWriteTexture(_queue, queueNative, destination, data, dataLayout, size) {
    addon.queueWriteTexture(
      queueNative,
      destination.texture,
      data,
      dataLayout.offset ?? 0,
      dataLayout.bytesPerRow ?? 0,
      dataLayout.rowsPerImage ?? 0,
      destination.mipLevel ?? 0,
      destination.origin?.x ?? 0,
      destination.origin?.y ?? 0,
      destination.origin?.z ?? 0,
      size.width,
      size.height,
      size.depthOrArrayLayers ?? 1,
    );
  },
  async queueOnSubmittedWorkDone(queue, queueNative) {
    if (!queue.hasPendingSubmissions()) {
      return;
    }
    try {
      const flushStartedAt = performance.now();
      const flushBreakdown = addon.queueFlush(queue._instance, queueNative);
      accumulateQueueSubmitBreakdown(queue, 'submitQueueFlushTotalNs', flushStartedAt);
      accumulateQueueFlushBreakdown(queue, flushBreakdown);
      const bookkeepingStartedAt = performance.now();
      queue.markSubmittedWorkDone();
      accumulateQueueSubmitBreakdown(queue, 'submitQueueWaitBookkeepingTotalNs', bookkeepingStartedAt);
    } catch (error) {
      if (error?.code === 'DOE_QUEUE_UNAVAILABLE') {
        return;
      }
      throw error;
    }
  },
  textureCreateView(_texture, native, descriptor) {
    if (!descriptor) {
      return addon.textureCreateView(native);
    }
    const viewDescriptor = { ...descriptor };
    if (descriptor.dimension !== undefined) {
      viewDescriptor.dimension = typeof descriptor.dimension === 'number'
        ? descriptor.dimension
        : (TEXTURE_VIEW_DIMENSION_MAP[descriptor.dimension] ?? 0);
    }
    if (descriptor.aspect !== undefined) {
      viewDescriptor.aspect = typeof descriptor.aspect === 'number'
        ? descriptor.aspect
        : (TEXTURE_ASPECT_MAP[descriptor.aspect] ?? 0);
    }
    if (typeof descriptor.swizzle === 'string' && descriptor.swizzle.length === 4) {
      viewDescriptor.swizzle = descriptor.swizzle;
      viewDescriptor.swizzleR = TEXTURE_SWIZZLE_COMPONENT_MAP[descriptor.swizzle[0]] ?? 0;
      viewDescriptor.swizzleG = TEXTURE_SWIZZLE_COMPONENT_MAP[descriptor.swizzle[1]] ?? 0;
      viewDescriptor.swizzleB = TEXTURE_SWIZZLE_COMPONENT_MAP[descriptor.swizzle[2]] ?? 0;
      viewDescriptor.swizzleA = TEXTURE_SWIZZLE_COMPONENT_MAP[descriptor.swizzle[3]] ?? 0;
    }
    return addon.textureCreateView(native, viewDescriptor);
  },
  textureDestroy(native, texture) {
    if (texture?._externallyOwned) {
      if (typeof texture?._nativeCanvasRelease === 'function') {
        texture._nativeCanvasRelease(native, texture);
      }
      return;
    }
    addon.textureRelease(native);
  },
  shaderModuleDestroy(native) {
    addon.shaderModuleRelease(native);
  },
  shaderModuleGetCompilationInfo(_shaderModule, native) {
    return addon.shaderModuleGetCompilationInfo(native);
  },
  computePipelineGetBindGroupLayout(pipeline, index, classes) {
    if (pipeline._autoLayoutEntriesByGroup) {
      const entries = pipeline._autoLayoutEntriesByGroup.get(index) ?? [];
      return pipeline._device.createBindGroupLayout({ entries });
    }
    if (typeof addon.computePipelineGetBindGroupLayout === 'function') {
      return new classes.DoeGPUBindGroupLayout(
        addon.computePipelineGetBindGroupLayout(pipeline._native, index),
        pipeline._device,
      );
    }
    if (pipeline._autoLayoutEntriesByGroup) {
      const entries = pipeline._autoLayoutEntriesByGroup.get(index) ?? [];
      return pipeline._device.createBindGroupLayout({ entries });
    }
    return pipeline._device.createBindGroupLayout({ entries: [] });
  },
  renderPipelineGetBindGroupLayout(pipeline, index, classes) {
    if (typeof addon.renderPipelineGetBindGroupLayout === 'function') {
      return new classes.DoeGPUBindGroupLayout(
        addon.renderPipelineGetBindGroupLayout(pipeline._native, index),
        pipeline,
      );
    }
    return new classes.DoeGPUBindGroupLayout(null, pipeline);
  },
  deviceCreateRenderBundleEncoder(device, descriptor, encoderClasses) {
    const colorFormats = Array.isArray(descriptor.colorFormats) ? descriptor.colorFormats : [];
    const native = addon.createRenderBundleEncoder(
      assertLiveResource(device, 'GPUDevice.createRenderBundleEncoder', 'GPUDevice'),
      colorFormats,
      descriptor.depthStencilFormat ?? null,
      descriptor.sampleCount ?? 1,
      descriptor.depthReadOnly ?? false,
      descriptor.stencilReadOnly ?? false,
      descriptor.label ?? null,
    );
    return new encoderClasses.DoeGPURenderBundleEncoder(native, device);
  },
  deviceLimits,
  deviceFeatures,
  adapterLimits,
  adapterFeatures,
  preflightShaderSource,
  preflightShaderSourceOnCreate: false,
  requireAutoLayoutEntriesFromNative(shader, visibility, path) {
    return requireAutoLayoutEntriesFromNative(
      assertLiveResource(shader, path, 'GPUShaderModule'),
      visibility,
      path,
    );
  },
  deviceGetQueue(native) {
    return addon.deviceGetQueue(native);
  },
  deviceCreateBuffer(device, validated) {
    return addon.createBuffer(assertLiveResource(device, 'GPUDevice.createBuffer', 'GPUDevice'), validated);
  },
  deviceCreateShaderModule(device, code, compilationHints, label = null) {
    try {
      return addon.createShaderModule(
        assertLiveResource(device, 'GPUDevice.createShaderModule', 'GPUDevice'),
        code,
        compilationHints ?? null,
        label,
      );
    } catch (error) {
      throw enrichNativeCompilerError(error, 'GPUDevice.createShaderModule', readLastErrorFields());
    }
  },
  deviceCreateComputePipeline(device, shaderNative, entryPoint, layoutNative, constants, label) {
    try {
      return addon.createComputePipeline(
        assertLiveResource(device, 'GPUDevice.createComputePipeline', 'GPUDevice'),
        shaderNative,
        entryPoint,
        layoutNative,
        constants,
        label,
      );
    } catch (error) {
      throw pipelineErrorFromError(error, 'GPUDevice.createComputePipeline', readLastErrorFields());
    }
  },
  deviceCreateBindGroupLayout(device, entries, label) {
    if (entries.some((entry) => entry.externalTexture)) {
      failValidation(
        'GPUDevice.createBindGroupLayout',
        'externalTexture bindings require a browser canvas backend provider, not the headless Doe runtime package surface',
      );
    }
    return addon.createBindGroupLayout(assertLiveResource(device, 'GPUDevice.createBindGroupLayout', 'GPUDevice'), entries, label);
  },
  deviceCreateBindGroup(device, layoutNative, entries, label) {
    if (entries.some((entry) => entry.externalTexture)) {
      failValidation(
        'GPUDevice.createBindGroup',
        'externalTexture resources require a browser canvas backend provider, not the headless Doe runtime package surface',
      );
    }
    return addon.createBindGroup(
      assertLiveResource(device, 'GPUDevice.createBindGroup', 'GPUDevice'),
      layoutNative,
      entries,
      label,
    );
  },
  deviceCreatePipelineLayout(device, layouts, label, immediateSize = 0) {
    return addon.createPipelineLayout(
      assertLiveResource(device, 'GPUDevice.createPipelineLayout', 'GPUDevice'),
      layouts,
      label,
      immediateSize,
    );
  },
  deviceCreateTexture(device, textureDescriptor, size, usage) {
    const desc = {
      label: textureDescriptor.label ?? '',
      format: textureDescriptor.format || 'rgba8unorm',
      width: size.width,
      height: size.height,
      depthOrArrayLayers: size.depthOrArrayLayers,
      dimension: TEXTURE_DIMENSION_MAP[textureDescriptor.dimension ?? '2d'] ?? 2,
      usage,
      mipLevelCount: assertIntegerInRange(textureDescriptor.mipLevelCount ?? 1, 'GPUDevice.createTexture', 'descriptor.mipLevelCount', { min: 1, max: UINT32_MAX }),
      sampleCount: assertIntegerInRange(textureDescriptor.sampleCount ?? 1, 'GPUDevice.createTexture', 'descriptor.sampleCount', { min: 1, max: UINT32_MAX }),
      viewFormats: Array.isArray(textureDescriptor.viewFormats) ? textureDescriptor.viewFormats : [],
    };
    if (textureDescriptor.textureBindingViewDimension) {
      desc.textureBindingViewDimension = textureDescriptor.textureBindingViewDimension;
    }
    return addon.createTexture(assertLiveResource(device, 'GPUDevice.createTexture', 'GPUDevice'), desc);
  },
  deviceCreateSampler(device, descriptor) {
    return addon.createSampler(assertLiveResource(device, 'GPUDevice.createSampler', 'GPUDevice'), descriptor);
  },
  deviceCreateRenderPipeline(device, descriptor) {
    try {
      const fragmentTarget = descriptor.fragmentTarget ?? { format: descriptor.colorFormat ?? 'rgba8unorm' };
      return addon.createRenderPipeline(
        assertLiveResource(device, 'GPUDevice.createRenderPipeline', 'GPUDevice'),
        {
          layout: descriptor.layout,
          vertex: {
            module: descriptor.vertexModule,
            entryPoint: descriptor.vertexEntryPoint,
            buffers: descriptor.vertexBuffers ?? [],
            constants: descriptor.vertexConstants ?? null,
          },
          fragment: {
            module: descriptor.fragmentModule,
            entryPoint: descriptor.fragmentEntryPoint,
            constants: descriptor.fragmentConstants ?? null,
            targets: [{
              format: fragmentTarget.format,
              writeMask: fragmentTarget.writeMask,
              blend: fragmentTarget.blend ?? undefined,
            }],
          },
          primitive: descriptor.primitive ? {
            topology: descriptor.primitive.topology ?? 'triangle-list',
            frontFace: descriptor.primitive.frontFace ?? 'ccw',
            cullMode: descriptor.primitive.cullMode ?? 'none',
            unclippedDepth: descriptor.primitive.unclippedDepth ?? false,
          } : undefined,
          multisample: descriptor.multisample ? {
            count: descriptor.multisample.count ?? 1,
            mask: descriptor.multisample.mask ?? 0xFFFF_FFFF,
            alphaToCoverageEnabled: descriptor.multisample.alphaToCoverageEnabled ?? false,
          } : undefined,
          depthStencil: descriptor.depthStencil ? {
            format: descriptor.depthStencil.format,
            depthWriteEnabled: descriptor.depthStencil.depthWriteEnabled ?? false,
            depthCompare: descriptor.depthStencil.depthCompare ?? 'always',
            stencilFront: descriptor.depthStencil.stencilFront ?? undefined,
            stencilBack: descriptor.depthStencil.stencilBack ?? undefined,
            stencilReadMask: descriptor.depthStencil.stencilReadMask ?? 0xFFFF_FFFF,
            stencilWriteMask: descriptor.depthStencil.stencilWriteMask ?? 0xFFFF_FFFF,
            depthBias: descriptor.depthStencil.depthBias ?? 0,
            depthBiasSlopeScale: descriptor.depthStencil.depthBiasSlopeScale ?? 0,
            depthBiasClamp: descriptor.depthStencil.depthBiasClamp ?? 0,
          } : undefined,
        },
      );
    } catch (error) {
      throw pipelineErrorFromError(error, 'GPUDevice.createRenderPipeline', readLastErrorFields());
    }
  },
  deviceCreateQuerySet(device, descriptor) {
    const QUERY_TYPE_OCCLUSION = 1;
    const QUERY_TYPE_TIMESTAMP = 2;
    const querySet = addon.createQuerySet(
      assertLiveResource(device, 'GPUDevice.createQuerySet', 'GPUDevice'),
      descriptor.type === 'occlusion' ? QUERY_TYPE_OCCLUSION : QUERY_TYPE_TIMESTAMP,
      descriptor.count,
    );
    if (descriptor.label && typeof addon.objectSetLabel === 'function') {
      addon.objectSetLabel(querySet, descriptor.label);
    }
    return querySet;
  },
  querySetDestroy(native) {
    addon.querySetDestroy(native);
  },
  deviceCreateCommandEncoder(device) {
    return new DoeGPUCommandEncoder(null, device);
  },
  deviceDestroy(native) {
    addon.deviceRelease(native);
  },
  adapterGetInfo(_adapter, native) {
    if (typeof addon.adapterGetInfo !== 'function') {
      return emptyAdapterInfo();
    }
    return Object.freeze(addon.adapterGetInfo(native));
  },
  adapterRequestDevice(adapter, _descriptor, classes) {
    assertLiveResource(adapter, 'GPUAdapter.requestDevice', 'GPUAdapter');
    const descriptor = _descriptor ?? undefined;
    let native;
    try {
      native = addon.requestDevice(adapter._instance, adapter._native, descriptor);
    } catch (error) {
      const message = String(error?.message ?? '');
      if (!message.includes('adapter is "consumed"')) {
        throw error;
      }
      adapter._native = addon.requestAdapter(adapter._instance, adapter._requestOptions ?? null);
      native = addon.requestDevice(adapter._instance, adapter._native, descriptor);
    }
    const device = new classes.DoeGPUDevice(
      native,
      adapter._instance,
      deviceLimits(native),
      deviceFeatures(native),
    );
    device.label = descriptor?.label ?? '';
    if (device.queue) {
      device.queue.label = descriptor?.defaultQueue?.label ?? '';
    }
    device._adapterInfo = adapter.info;
    installNodeDeviceCallbacks(device);
    return device;
  },
  adapterDestroy(native) {
    addon.adapterRelease(native);
  },
  gpuRequestAdapter(gpu, options, classes) {
    const adapter = addon.requestAdapter(gpu._instance, options);
    return new classes.DoeGPUAdapter(adapter, gpu._instance, options);
  },
};

nativeMetalCanvasBackend = process.platform === 'darwin'
  ? createNativeMetalCanvasBackendImpl({ addon })
  : null;

const {
  DoeGPUBuffer,
  DoeGPUQueue,
  DoeGPUTexture,
  DoeGPUTextureView,
  DoeGPUSampler,
  DoeGPURenderPipeline,
  DoeGPUShaderModule,
  DoeGPUComputePipeline,
  DoeGPUBindGroupLayout,
  DoeGPUBindGroup,
  DoeGPUPipelineLayout,
  DoeGPUDevice,
  DoeGPUAdapter,
  DoeGPU,
  DoeGPUCanvasContext,
} = (nativeMetalCanvasBackend
  ? createBrowserSurfaceClasses({
    canvasBackend: nativeMetalCanvasBackend,
    fullClasses: createFullSurfaceClasses({
      globals,
      backend: fullSurfaceBackend,
      encoderClasses: { DoeGPURenderBundleEncoder, DoeGPURenderBundle },
    }),
  })
  : createFullSurfaceClasses({
    globals,
    backend: fullSurfaceBackend,
    encoderClasses: { DoeGPURenderBundleEncoder, DoeGPURenderBundle },
  }));

/**
 * Create a package-local `GPU` object backed by the Doe native runtime.
 *
 * This loads the addon/runtime if needed, creates a fresh GPU instance, and
 * returns an object with `requestAdapter(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { create } from "doe-gpu";
 *
 * const gpu = create();
 * const adapter = await gpu.requestAdapter();
 * ```
 *
 * - Throws if the native addon or `libwebgpu_doe` cannot be found.
 * - `createArgs` are currently accepted for API stability but ignored by the default Doe-native provider path.
 */
export function create(createArgs = null) {
  ensureLibrary();
  const instance = addon.createInstance();
  return new DoeGPU(instance);
}

export function createInstance(createArgs = null) {
  return create(createArgs);
}

export function createCanvasContext(canvas) {
  if (!nativeMetalCanvasBackend || typeof DoeGPUCanvasContext !== 'function') {
    failValidation(
      'createCanvasContext',
      'native Metal GPUCanvasContext is unavailable on this host/runtime',
    );
  }
  return new DoeGPUCanvasContext(canvas);
}

export function setNativeTimeoutMs(timeoutMs) {
  ensureLibrary();
  validatePositiveInteger(timeoutMs, 'native timeout');
  if (typeof addon.setTimeoutMs !== 'function') {
    throw new Error('setNativeTimeoutMs is not supported by the loaded addon.');
  }
  addon.setTimeoutMs(timeoutMs);
}

/**
 * Install the package WebGPU globals onto a target object and return its GPU.
 *
 * This adds missing enum globals plus `navigator.gpu` to `target`, then
 * returns the created package-local GPU object.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { setupGlobals } from "doe-gpu";
 *
 * setupGlobals(globalThis);
 * const adapter = await navigator.gpu.requestAdapter();
 * ```
 *
 * - Existing properties are preserved; this only fills in missing globals.
 * - If `target.navigator` exists without `gpu`, only `navigator.gpu` is added.
 * - The returned GPU is still headless/package-owned, not browser DOM ownership or browser-process parity.
 */
export function setupGlobals(target = globalThis, createArgs = null) {
  const gpu = create(createArgs);
  return setupGlobalsOnTarget(target, gpu, globals);
}

/**
 * Request a Doe-backed adapter from the full package surface.
 *
 * This is a convenience wrapper over `create(...).requestAdapter(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { requestAdapter } from "doe-gpu";
 *
 * const adapter = await requestAdapter();
 * ```
 *
 * - Returns `null` if no adapter is available.
 * - `adapterOptions` are accepted for WebGPU shape compatibility; the current Doe package path does not use them for adapter filtering.
 */
export async function requestAdapter(adapterOptions = undefined, createArgs = null) {
  return requestAdapterFromCreate(create, adapterOptions, createArgs);
}

/**
 * Request a Doe-backed device from the full package surface.
 *
 * This creates a package-local GPU, requests an adapter, then requests a
 * device from that adapter.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { requestDevice } from "doe-gpu";
 *
 * const device = await requestDevice();
 * const buffer = device.createBuffer({
 *   size: 16,
 *   usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
 * });
 * ```
 *
 * - On the full package surface, the returned device includes render, texture, sampler, and surface APIs when the runtime supports them.
 * - Missing runtime prerequisites still fail at request time through the same addon/library checks as `create()`.
 */
export async function requestDevice(options = {}) {
  return requestDeviceFromRequestAdapter(requestAdapter, options);
}

/**
 * Report how the package resolved and loaded the Doe runtime.
 *
 * This returns package/runtime provenance such as whether the native path is
 * loaded, which library flavor was chosen, and whether build metadata says the
 * runtime was built with Lean-verified mode.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { providerInfo } from "doe-gpu";
 *
 * console.log(providerInfo());
 * ```
 *
 * - If metadata is unavailable, `leanVerifiedBuild` is `null` rather than a guess.
 * - `loaded: false` is still diagnostically useful before attempting `requestDevice()`.
 */
export function providerInfo() {
  const flavor = libraryFlavor(DOE_LIB_PATH);
  return buildProviderInfo({
    loaded: !!addon && !!DOE_LIB_PATH,
    loadError: !addon ? 'native addon not found' : !DOE_LIB_PATH ? 'libwebgpu_doe not found' : '',
    defaultCreateArgs: [],
    doeNative: flavor === 'doe-dropin',
    libraryFlavor: flavor,
    doeLibraryPath: DOE_LIB_PATH ?? '',
    buildMetadataSource: DOE_BUILD_METADATA.source,
    buildMetadataPath: DOE_BUILD_METADATA.path,
    leanVerifiedBuild: DOE_BUILD_METADATA.leanVerifiedBuild,
    proofArtifactSha256: DOE_BUILD_METADATA.proofArtifactSha256,
  });
}

/**
 * Create a Node or Bun runtime wrapper for Doe CLI execution.
 *
 * This exposes the package-side CLI bridge used for benchmark and command
 * stream execution workflows.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { createDoeRuntime } from "doe-gpu";
 *
 * const runtime = createDoeRuntime();
 * ```
 *
 * - This is package/runtime orchestration, not the in-process WebGPU device path.
 */
export const createDoeRuntime = createDoeRuntimeCli;

/**
 * Run the Dawn-vs-Doe compare harness from the full package surface.
 *
 * This forwards into the artifact-backed compare wrapper used by benchmark and
 * verification tooling.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { runDawnVsDoeCompare } from "doe-gpu";
 *
 * const result = runDawnVsDoeCompare({ configPath: "bench/config.json" });
 * ```
 *
 * - Requires an explicit compare config path either in options or forwarded CLI args.
 * - This is a tooling entrypoint, not the in-process `device` or `doe` helper path.
 */
export const runDawnVsDoeCompare = runDawnVsDoeCompareCli;
export {
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
};

export default {
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  create,
  createCanvasContext,
  createInstance,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend: createNativeBrowserCanvasBackendImpl,
  globals,
  normalizeCanvasConfiguration,
  normalizeOrigin2D,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  createDoeRuntime,
  runDawnVsDoeCompare,
};
