import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globals } from './webgpu_constants.js';
import {
  createDoeRuntime as createDoeRuntimeCli,
  runDawnVsDoeCompare as runDawnVsDoeCompareCli,
} from './runtime_cli.js';
import { loadDoeBuildMetadata } from './build_metadata.js';
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
  shaderCheckFailure,
  enrichNativeCompilerError,
  compilerErrorFromMessage,
} from './shared/compiler-errors.js';
import {
  createFullSurfaceClasses,
} from './shared/full-surface.js';
import {
  createEncoderClasses,
} from './shared/encoder-surface.js';
import {
  createNativeBrowserCanvasBackend,
  createBrowserSurfaceClasses,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
} from './shared/browser-surface.js';
import {
  createNativeBrowserCanvasBackend,
} from './shared/browser-native-canvas-backend.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
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

const addon = loadAddon();
const DOE_LIB_PATH = resolveDoeLibraryPath();
const DOE_BUILD_METADATA = loadDoeBuildMetadata({
  packageRoot: resolve(__dirname, '..'),
  libraryPath: DOE_LIB_PATH ?? '',
});
let libraryLoaded = false;

export { globals, preflightShaderSource };


function loadAddon() {
  const prebuildPath = resolve(__dirname, '..', 'prebuilds', `${process.platform}-${process.arch}`, 'doe_napi.node');
  try {
    return require('../build/Release/doe_napi.node');
  } catch {
    try {
      return require('../build/Debug/doe_napi.node');
    } catch {
      try {
        return require(prebuildPath);
      } catch {
        return null;
      }
    }
  }
}

function resolveDoeLibraryPath() {
  const ext = process.platform === 'darwin' ? 'dylib'
    : process.platform === 'win32' ? 'dll' : 'so';

  const candidates = [
    process.env.DOE_WEBGPU_LIB,
    process.env.FAWN_DOE_LIB,
    resolve(__dirname, '..', '..', '..', 'runtime', 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(__dirname, '..', '..', '..', 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(__dirname, '..', 'prebuilds', `${process.platform}-${process.arch}`, `libwebgpu_doe.${ext}`),
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
      '@simulatte/webgpu: Native addon not found. Run `npm run build:addon` or `npx node-gyp rebuild`.'
    );
  }
  if (!DOE_LIB_PATH) {
    throw new Error(
      '@simulatte/webgpu: libwebgpu_doe not found. Build it with `cd runtime/zig && zig build dropin` or set DOE_WEBGPU_LIB.'
    );
  }
  addon.loadLibrary(DOE_LIB_PATH);
  libraryLoaded = true;
}

function validateBufferDescriptor(descriptor) {
  return assertBufferDescriptor(descriptor, 'GPUDevice.createBuffer');
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
  device._onuncapturederror = null;
  device._onuncapturederrorDispatch = null;
  const lostDescriptor = {
      configurable: true,
      enumerable: true,
      get() {
        assertLiveResource(this, 'GPUDevice.lost', 'GPUDevice');
        if (!ensureNodeDeviceLostRegistration(this)) {
          throw unsupportedNodeDeviceCapability('GPUDevice.lost');
        }
        return this._lost;
      },
    };
  Object.defineProperties(device, {
    lost: lostDescriptor,
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
        const dispatch = handler
          ? (event) => handler.call(this, event)
          : null;
        this._onuncapturederrorDispatch = dispatch;
        if (typeof addon?.deviceSetUncapturedErrorCallback !== 'function') {
          if (dispatch) {
            throw unsupportedNodeDeviceCapability('GPUDevice.onuncapturederror');
          }
          return;
        }
        try {
          const registered = addon.deviceSetUncapturedErrorCallback(this._native, dispatch);
          if (registered === false && dispatch) {
            throw unsupportedNodeDeviceCapability('GPUDevice.onuncapturederror');
          }
        } catch (error) {
          if (String(error?.message ?? '').includes('not available')) {
            if (dispatch) {
              throw unsupportedNodeDeviceCapability('GPUDevice.onuncapturederror');
            }
            return;
          }
          throw error;
        }
      },
    },
  });
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
    return addon.devicePopErrorScope(this._native, this._instance ?? null);
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
 * import { globals } from "@simulatte/webgpu";
 *
 * const usage = globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST;
 * ```
 *
 * - These values mirror the standard WebGPU numeric constants.
 * - They do not install themselves on `globalThis`; use `setupGlobals(...)` if needed.
 * - `@simulatte/webgpu/compute` shares the same constants even though its device facade is narrower.
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
      const pass = addon.beginComputePass(encoder._native);
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
    if (pass._lazy) {
      ensureNodeCommandEncoderNative(pass._encoder);
      pass._lazy = false;
      pass._native = addon.beginComputePass(pass._encoder._native);
      if (pass._pipeline != null) {
        addon.computePassSetPipeline(pass._native, pass._pipeline);
      }
      for (let i = 0; i < pass._bindGroups.length; i += 1) {
        if (pass._bindGroups[i]) {
          addon.computePassSetBindGroup(pass._native, i, pass._bindGroups[i]);
        }
      }
    }
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
      pass._encoder._commands.push({ t: 0, p: pass._pipeline, bg: [...pass._bindGroups], x, y, z });
      return;
    }
    addon.computePassDispatchWorkgroups(
      assertLiveResource(pass, 'GPUComputePassEncoder.dispatchWorkgroups', 'GPUComputePassEncoder'),
      x,
      y,
      z,
    );
  },
  computePassDispatchWorkgroupsIndirect(pass, indirectBufferNative, indirectOffset) {
    if (pass._lazy) {
      ensureNodeCommandEncoderNative(pass._encoder);
      pass._lazy = false;
      pass._native = addon.beginComputePass(pass._encoder._native);
      if (pass._pipeline != null) {
        addon.computePassSetPipeline(pass._native, pass._pipeline);
      }
      for (let i = 0; i < pass._bindGroups.length; i += 1) {
        if (pass._bindGroups[i]) {
          addon.computePassSetBindGroup(pass._native, i, pass._bindGroups[i]);
        }
      }
    }
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
      size ?? 0,
    );
  },
  renderPassSetIndexBuffer(pass, bufferNative, format, offset, size) {
    addon.renderPassSetIndexBuffer(
      assertLiveResource(pass, 'GPURenderPassEncoder.setIndexBuffer', 'GPURenderPassEncoder'),
      bufferNative,
      format,
      offset,
      size ?? 0,
    );
  },
  renderPassDraw(pass, vertexCount, instanceCount, firstVertex, firstInstance) {
    addon.renderPassDraw(pass._native, vertexCount, instanceCount, firstVertex, firstInstance);
  },
  renderPassDrawIndexed(pass, indexCount, instanceCount, firstIndex, baseVertex, firstInstance) {
    addon.renderPassDrawIndexed(pass._native, indexCount, instanceCount, firstIndex, baseVertex, firstInstance);
  },
  renderPassDrawIndirect(pass, indirectBufferNative, indirectOffset) {
    if (typeof addon.renderPassDrawIndirect === 'function') {
      addon.renderPassDrawIndirect(pass._native, indirectBufferNative, indirectOffset);
    }
  },
  renderPassDrawIndexedIndirect(pass, indirectBufferNative, indirectOffset) {
    if (typeof addon.renderPassDrawIndexedIndirect === 'function') {
      addon.renderPassDrawIndexedIndirect(pass._native, indirectBufferNative, indirectOffset);
    }
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
    addon.renderBundleEncoderSetVertexBuffer(enc._native, slot, bufferNative, offset, size ?? 0);
  },
  renderBundleEncoderSetIndexBuffer(enc, bufferNative, format, offset, size) {
    addon.renderBundleEncoderSetIndexBuffer(enc._native, bufferNative, format, offset, size ?? 0);
  },
  renderBundleEncoderDraw(enc, vertexCount, instanceCount, firstVertex, firstInstance) {
    addon.renderBundleEncoderDraw(enc._native, vertexCount, instanceCount, firstVertex, firstInstance);
  },
  renderBundleEncoderDrawIndexed(enc, indexCount, instanceCount, firstIndex, baseVertex, firstInstance) {
    addon.renderBundleEncoderDrawIndexed(enc._native, indexCount, instanceCount, firstIndex, baseVertex, firstInstance);
  },
  renderBundleEncoderDrawIndirect(enc, indirectBufferNative, indirectOffset) {
    if (typeof addon.renderBundleEncoderDrawIndirect === 'function') {
      addon.renderBundleEncoderDrawIndirect(enc._native, indirectBufferNative, indirectOffset);
    }
  },
  renderBundleEncoderDrawIndexedIndirect(enc, indirectBufferNative, indirectOffset) {
    if (typeof addon.renderBundleEncoderDrawIndexedIndirect === 'function') {
      addon.renderBundleEncoderDrawIndexedIndirect(enc._native, indirectBufferNative, indirectOffset);
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
  renderBundleSetLabel(bundle, label) {
    if (typeof addon.objectSetLabel === 'function') {
      addon.objectSetLabel(bundle._native, label);
    }
  },
  commandEncoderInit(encoder) {
    encoder._commands = [];
    encoder._native = null;
    encoder._finished = false;
  },
  commandEncoderAssertOpen(encoder, path) {
    if (encoder._finished) {
      failValidation(path, 'command encoder is already finished');
    }
  },
  commandEncoderBeginComputePass(encoder, _descriptor, classes) {
    if (encoder._native === null) {
      return new classes.DoeGPUComputePassEncoder(null, encoder);
    }
    return new classes.DoeGPUComputePassEncoder(
      addon.beginComputePass(encoder._native),
      encoder,
    );
  },
  commandEncoderBeginRenderPass(encoder, passDescriptor, classes) {
    const attachments = assertArray(passDescriptor.colorAttachments ?? [], 'GPUCommandEncoder.beginRenderPass', 'descriptor.colorAttachments');
    if (attachments.length === 0) {
      failValidation('GPUCommandEncoder.beginRenderPass', 'descriptor.colorAttachments must contain at least one attachment');
    }
    ensureNodeCommandEncoderNative(encoder);
    const colorAttachments = attachments.map((attachment, index) => {
      const entry = assertObject(attachment, 'GPUCommandEncoder.beginRenderPass', `descriptor.colorAttachments[${index}]`);
      return {
        view: assertLiveResource(entry.view, 'GPUCommandEncoder.beginRenderPass', 'GPUTextureView'),
        clearValue: entry.clearValue || { r: 0, g: 0, b: 0, a: 1 },
      };
    });
    let depthStencilAttachment = undefined;
    if (passDescriptor.depthStencilAttachment !== undefined) {
      const depthAttachment = assertObject(passDescriptor.depthStencilAttachment, 'GPUCommandEncoder.beginRenderPass', 'descriptor.depthStencilAttachment');
      depthStencilAttachment = {
        view: assertLiveResource(depthAttachment.view, 'GPUCommandEncoder.beginRenderPass', 'GPUTextureView'),
        depthClearValue: depthAttachment.depthClearValue ?? 1,
        depthReadOnly: depthAttachment.depthReadOnly ?? false,
        stencilClearValue: depthAttachment.stencilClearValue ?? 0,
        stencilReadOnly: depthAttachment.stencilReadOnly ?? false,
      };
    }
    const pass = addon.beginRenderPass(encoder._native, {
      colorAttachments,
      depthStencilAttachment,
    });
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
    if (
      encoder._native === null
      && cmds.length === 2
      && cmds[0].t === 0
      && cmds[1].t === 1
    ) {
      encoder._finished = true;
      return { _commands: cmds, _batched: true };
    }
    ensureNodeCommandEncoderNative(encoder);
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
  },
  bufferMarkMappedAtCreation(buffer) {
    buffer._mapMode = globals.GPUMapMode.WRITE;
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
  },
  bufferGetMappedRange(wrapper, native, offset, size) {
    if (wrapper._mapMode === globals.GPUMapMode.WRITE) {
      const staged = addon.bufferGetStagedRange(native, offset, size);
      wrapper._staged = { buf: staged, native, offset, size };
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
  bufferAssertMappedPrefixF32(_wrapper, native, expected, count) {
    return addon.bufferAssertMappedPrefixF32(native, expected, count);
  },
  bufferUnmap(native, wrapper) {
    if (wrapper._staged) {
      const { buf, offset, size } = wrapper._staged;
      addon.bufferFlushStagedRange(native, buf, offset, size);
      wrapper._staged = null;
    }
    wrapper._mapMode = 0;
    addon.bufferUnmap(native);
  },
  bufferDestroy(native) {
    addon.bufferRelease(native);
  },
  initQueueState(queue) {
    queue._submittedSerial = 0;
    queue._completedSerial = 0;
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
    if (buffers.length === 1 && buffers[0]?._batched) {
      const cmds = buffers[0]._commands;
      if (
        cmds.length === 2
        && cmds[0]?.t === 0
        && cmds[1]?.t === 1
        && typeof addon.submitComputeDispatchCopy === 'function'
      ) {
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
        // submitComputeDispatchCopy is synchronous: spin-polls until GPU signals.
        // Mark done so onSubmittedWorkDone() short-circuits rather than calling queueFlush.
        queue.markSubmittedWorkDone();
        return;
      }
    }
    if (buffers.every((commandBuffer) => commandBuffer?._batched && Array.isArray(commandBuffer._commands))) {
      const allCommands = [];
      for (const cb of buffers) {
        allCommands.push(...cb._commands);
      }
      addon.submitBatched(deviceNative, queueNative, allCommands);
      if (
        allCommands.length === 2
        && allCommands[0]?.t === 0
        && allCommands[1]?.t === 1
      ) {
        queue.markSubmittedWorkDone();
      }
      return;
    }
    const natives = buffers.map((commandBuffer, index) => {
      if (!commandBuffer || typeof commandBuffer !== 'object' || commandBuffer._native == null) {
        failValidation('GPUQueue.submit', `commandBuffers[${index}] must be a finished command buffer`);
      }
      return commandBuffer._native;
    });
    addon.queueSubmit(queueNative, natives);
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
    try {
      addon.queueFlush(queue._instance, queueNative);
      queue.markSubmittedWorkDone();
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
  textureDestroy(native) {
    addon.textureRelease(native);
  },
  shaderModuleDestroy(native) {
    addon.shaderModuleRelease(native);
  },
  shaderModuleGetCompilationInfo(_shaderModule, native) {
    return addon.shaderModuleGetCompilationInfo(native);
  },
  computePipelineGetBindGroupLayout(pipeline, index, classes) {
    if (pipeline._autoLayoutEntriesByGroup && process.platform === 'darwin') {
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
    );
    return new encoderClasses.DoeGPURenderBundleEncoder(native, device);
  },
  deviceLimits,
  deviceFeatures,
  adapterLimits,
  adapterFeatures,
  preflightShaderSource,
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
  deviceCreateShaderModule(device, code, compilationHints) {
    try {
      return addon.createShaderModule(assertLiveResource(device, 'GPUDevice.createShaderModule', 'GPUDevice'), code, compilationHints ?? null);
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
      throw enrichNativeCompilerError(error, 'GPUDevice.createComputePipeline', readLastErrorFields());
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
    const fragmentTarget = descriptor.fragmentTarget ?? { format: 'rgba8unorm' };
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
        } : undefined,
      },
    );
  },
  deviceCreateQuerySet(device, descriptor) {
    const QUERY_TYPE_TIMESTAMP = 2;
    return addon.createQuerySet(
      assertLiveResource(device, 'GPUDevice.createQuerySet', 'GPUDevice'),
      QUERY_TYPE_TIMESTAMP,
      descriptor.count,
    );
  },
  querySetDestroy(native) {
    addon.querySetDestroy(native);
  },
  querySetSetLabel(querySet, label) {
    if (typeof addon.objectSetLabel === 'function') {
      addon.objectSetLabel(querySet._native, label);
    }
  },
  deviceCreateCommandEncoder(device) {
    return new DoeGPUCommandEncoder(null, device);
  },
  deviceDestroy(native) {
    addon.deviceRelease(native);
  },
  adapterGetInfo(_adapter, native) {
    return Object.freeze(addon.adapterGetInfo(native));
  },
  adapterRequestDevice(adapter, _descriptor, classes) {
    assertLiveResource(adapter, 'GPUAdapter.requestDevice', 'GPUAdapter');
    const native = addon.requestDevice(adapter._instance, adapter._native);
    const device = {
      _destroyed: false,
      _resourceLabel: 'GPUDevice',
      _resourceOwner: null,
      createBuffer: classes.DoeGPUDevice.prototype.createBuffer,
      createShaderModule: classes.DoeGPUDevice.prototype.createShaderModule,
      createComputePipeline: classes.DoeGPUDevice.prototype.createComputePipeline,
      createComputePipelineAsync: classes.DoeGPUDevice.prototype.createComputePipelineAsync,
      createBindGroupLayout: classes.DoeGPUDevice.prototype.createBindGroupLayout,
      createBindGroup: classes.DoeGPUDevice.prototype.createBindGroup,
      createPipelineLayout: classes.DoeGPUDevice.prototype.createPipelineLayout,
      createTexture: classes.DoeGPUDevice.prototype.createTexture,
      createSampler: classes.DoeGPUDevice.prototype.createSampler,
      createRenderPipeline: classes.DoeGPUDevice.prototype.createRenderPipeline,
      createRenderPipelineAsync: classes.DoeGPUDevice.prototype.createRenderPipelineAsync,
      createRenderBundleEncoder: classes.DoeGPUDevice.prototype.createRenderBundleEncoder,
      createQuerySet: classes.DoeGPUDevice.prototype.createQuerySet,
      createCommandEncoder: classes.DoeGPUDevice.prototype.createCommandEncoder,
      importExternalTexture: classes.DoeGPUDevice.prototype.importExternalTexture,
      pushErrorScope: nodeDevicePushErrorScope,
      popErrorScope: nodeDevicePopErrorScope,
      destroy: classes.DoeGPUDevice.prototype.destroy,
    };
    device._native = native;
    device._instance = adapter._instance;
    device.limits = deviceLimits(native);
    device.features = deviceFeatures(native);
    installNodeDeviceCallbacks(device);
    const queue = {
      _destroyed: false,
      _resourceLabel: 'GPUQueue',
      _resourceOwner: device,
      hasPendingSubmissions: classes.DoeGPUQueue.prototype.hasPendingSubmissions,
      markSubmittedWorkDone: classes.DoeGPUQueue.prototype.markSubmittedWorkDone,
      submit: classes.DoeGPUQueue.prototype.submit,
      writeBuffer: classes.DoeGPUQueue.prototype.writeBuffer,
      writeTexture: classes.DoeGPUQueue.prototype.writeTexture,
      copyExternalImageToTexture: classes.DoeGPUQueue.prototype.copyExternalImageToTexture,
      onSubmittedWorkDone: classes.DoeGPUQueue.prototype.onSubmittedWorkDone,
    };
    queue._native = addon.deviceGetQueue(native);
    queue._instance = adapter._instance;
    queue._device = device;
    this.initQueueState(queue);
    device.queue = queue;
    return device;
  },
  adapterDestroy(native) {
    addon.adapterRelease(native);
  },
  gpuRequestAdapter(gpu, _options, classes) {
    const adapter = addon.requestAdapter(gpu._instance);
    return new classes.DoeGPUAdapter(adapter, gpu._instance);
  },
};

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
} = createFullSurfaceClasses({
  globals,
  backend: fullSurfaceBackend,
  encoderClasses: { DoeGPURenderBundleEncoder, DoeGPURenderBundle },
});

/**
 * Create a package-local `GPU` object backed by the Doe native runtime.
 *
 * This loads the addon/runtime if needed, creates a fresh GPU instance, and
 * returns an object with `requestAdapter(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { create } from "@simulatte/webgpu";
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
 * import { setupGlobals } from "@simulatte/webgpu";
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
 * import { requestAdapter } from "@simulatte/webgpu";
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
 * import { requestDevice } from "@simulatte/webgpu";
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
 * import { providerInfo } from "@simulatte/webgpu";
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
 * import { createDoeRuntime } from "@simulatte/webgpu";
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
 * import { runDawnVsDoeCompare } from "@simulatte/webgpu";
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
  createNativeBrowserCanvasBackend,
};

export default {
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  create,
  createInstance,
  createBrowserSurfaceClasses,
  createNativeBrowserCanvasBackend,
  globals,
  normalizeCanvasConfiguration,
  normalizeOrigin2D,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  createDoeRuntime,
  runDawnVsDoeCompare,
  createBrowserSurfaceClasses,
};
