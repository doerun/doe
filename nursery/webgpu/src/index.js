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
  DOE_LIMITS,
  DOE_FEATURES,
  featureSet,
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

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

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
    resolve(__dirname, '..', 'prebuilds', `${process.platform}-${process.arch}`, `libwebgpu_doe.${ext}`),
    resolve(__dirname, '..', '..', '..', 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(process.cwd(), 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
  ];

  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate;
  }
  return null;
}

function libraryFlavor(libraryPath) {
  if (!libraryPath) return 'missing';
  if (libraryPath.endsWith('libwebgpu_doe.so') || libraryPath.endsWith('libwebgpu_doe.dylib') || libraryPath.endsWith('libwebgpu_doe.dll')) {
    return 'doe-dropin';
  }
  if (libraryPath.endsWith('libwebgpu.so') || libraryPath.endsWith('libwebgpu.dylib') || libraryPath.endsWith('libwebgpu_dawn.so') || libraryPath.endsWith('libwgpu_native.so') || libraryPath.endsWith('libwgpu_native.so.0')) {
    return 'delegate';
  }
  return 'unknown';
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
      '@simulatte/webgpu: libwebgpu_doe not found. Build it with `cd zig && zig build dropin` or set DOE_WEBGPU_LIB.'
    );
  }
  addon.loadLibrary(DOE_LIB_PATH);
  libraryLoaded = true;
}

function validateBufferDescriptor(descriptor) {
  return assertBufferDescriptor(descriptor, 'GPUDevice.createBuffer');
}

function adapterLimits(native) {
  if (typeof addon?.adapterGetLimits === 'function') {
    const queried = addon.adapterGetLimits(native);
    if (queried && typeof queried === 'object' && queried.maxBindGroups) {
      return Object.freeze({ ...DOE_LIMITS, ...queried });
    }
  }
  return DOE_LIMITS;
}

function deviceLimits(native) {
  void native;
  return DOE_LIMITS;
}

function adapterFeatures(native) {
  if (typeof addon?.adapterHasFeature === 'function') {
    return featureSet((feature) => addon.adapterHasFeature(native, feature));
  }
  return DOE_FEATURES;
}

function deviceFeatures(native) {
  if (typeof addon?.deviceHasFeature === 'function') {
    return featureSet((feature) => addon.deviceHasFeature(native, feature));
  }
  return DOE_FEATURES;
}

function preflightShaderSource(code) {
  ensureLibrary();
  if (typeof addon?.checkShaderSource === 'function') {
    const result = addon.checkShaderSource(code);
    if (result && typeof result === 'object') {
      if (result.ok !== false && /@(?:vertex|fragment)\b/.test(code)) {
        return {
          ok: false,
          stage: 'package_surface',
          kind: 'UnsupportedSurface',
          message: 'package_surface: vertex and fragment shaders are not fully supported on this package surface yet',
          reasons: ['package_surface: vertex and fragment shaders are not fully supported on this package surface yet'],
        };
      }
      return {
        ok: result.ok !== false,
        stage: result.stage ?? '',
        kind: result.kind ?? '',
        message: result.message ?? '',
        reasons: result.ok === false && result.message ? [result.message] : [],
      };
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
 * WebGPU buffer returned by the Doe full package surface.
 *
 * Instances come from `device.createBuffer(...)` and expose buffer metadata,
 * mapping, and destruction operations for headless workflows.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const buffer = device.createBuffer({
 *   size: 16,
 *   usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
 * });
 * ```
 *
 * - `size` and `usage` are copied onto the JS object for convenience.
 * - Destroying the buffer releases the native handle but does not remove the JS object itself.
 */
class DoeGPUBuffer {
  constructor(native, instance, size, usage, queue, owner) {
    this._native = native;
    this._instance = instance;
    this._queue = queue;
    this.size = size;
    this.usage = usage;
    initResource(this, 'GPUBuffer', owner);
  }

  /**
   * Map the buffer for host access.
   *
   * This resolves after Doe has flushed any pending queue work needed to make
   * the requested range readable or writable from JS.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * await buffer.mapAsync(GPUMapMode.READ);
   * ```
   *
   * - When `size` is omitted, Doe maps the remaining bytes from `offset` to the end of the buffer.
   * - When the queue still has pending submissions, Doe flushes them before mapping.
   */
  async mapAsync(mode, offset = 0, size = Math.max(0, this.size - offset)) {
    const native = assertLiveResource(this, 'GPUBuffer.mapAsync', 'GPUBuffer');
    assertIntegerInRange(mode, 'GPUBuffer.mapAsync', 'mode', { min: 0, max: UINT32_MAX });
    assertIntegerInRange(offset, 'GPUBuffer.mapAsync', 'offset', { min: 0 });
    assertIntegerInRange(size, 'GPUBuffer.mapAsync', 'size', { min: 0 });
    if (offset + size > this.size) {
      failValidation('GPUBuffer.mapAsync', `mapped range ${offset}+${size} exceeds buffer size ${this.size}`);
    }
    if (this._queue) {
      if (this._queue.hasPendingSubmissions()) {
        addon.flushAndMapSync(
          this._instance,
          assertLiveResource(this._queue, 'GPUBuffer.mapAsync', 'GPUQueue'),
          native,
          mode,
          offset,
          size
        );
        this._queue.markSubmittedWorkDone();
      } else {
        addon.bufferMapSync(this._instance, native, mode, offset, size);
      }
    } else {
      addon.bufferMapSync(this._instance, native, mode, offset, size);
    }
  }

  /**
   * Return the currently mapped byte range.
   *
   * This exposes the mapped bytes as an `ArrayBuffer`-backed view after a
   * successful `mapAsync(...)` call.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const bytes = buffer.getMappedRange();
   * ```
   *
   * - Call this only while the buffer is mapped.
   * - When `size` is omitted, Doe returns the remaining bytes from `offset` to the end of the buffer.
   */
  getMappedRange(offset = 0, size = Math.max(0, this.size - offset)) {
    const native = assertLiveResource(this, 'GPUBuffer.getMappedRange', 'GPUBuffer');
    assertIntegerInRange(offset, 'GPUBuffer.getMappedRange', 'offset', { min: 0 });
    assertIntegerInRange(size, 'GPUBuffer.getMappedRange', 'size', { min: 0 });
    if (offset + size > this.size) {
      failValidation('GPUBuffer.getMappedRange', `mapped range ${offset}+${size} exceeds buffer size ${this.size}`);
    }
    return addon.bufferGetMappedRange(native, offset, size);
  }

  /**
   * Compare a mapped `f32` prefix against expected values.
   *
   * This is a small assertion helper used by smoke tests and quick validation
   * flows after mapping a buffer for read.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * buffer.assertMappedPrefixF32([1, 2, 3, 4], 4);
   * ```
   *
   * - The buffer must already be mapped.
   * - This checks only the requested prefix rather than the whole buffer.
   */
  assertMappedPrefixF32(expected, count) {
    const native = assertLiveResource(this, 'GPUBuffer.assertMappedPrefixF32', 'GPUBuffer');
    assertIntegerInRange(count, 'GPUBuffer.assertMappedPrefixF32', 'count', { min: 0, max: UINT32_MAX });
    if (Array.isArray(expected)) {
      if (expected.length < count) {
        failValidation('GPUBuffer.assertMappedPrefixF32', `expected array must contain at least ${count} values`);
      }
      const actual = new Float32Array(this.getMappedRange(0, count * Float32Array.BYTES_PER_ELEMENT));
      for (let index = 0; index < count; index += 1) {
        if (actual[index] !== expected[index]) {
          failValidation(
            'GPUBuffer.assertMappedPrefixF32',
            `expected readback[${index}] === ${expected[index]}, got ${actual[index]}`
          );
        }
      }
      return;
    }
    if (typeof expected !== 'number') {
      failValidation('GPUBuffer.assertMappedPrefixF32', 'expected must be a number or array of numbers');
    }
    return addon.bufferAssertMappedPrefixF32(native, expected, count);
  }

  /**
   * Release the current mapping.
   *
   * This returns the buffer to normal GPU ownership after `mapAsync(...)`.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * buffer.unmap();
   * ```
   *
   * - Call this after reading or writing mapped bytes.
   * - `getMappedRange(...)` is not valid again until the buffer is remapped.
   */
  unmap() {
    addon.bufferUnmap(assertLiveResource(this, 'GPUBuffer.unmap', 'GPUBuffer'));
  }

  /**
   * Release the native buffer.
   *
   * This tears down the underlying Doe buffer and marks the JS wrapper as
   * released.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * buffer.destroy();
   * ```
   *
   * - Reusing a destroyed buffer is unsupported.
   * - The wrapper remains reachable in JS but no longer owns a live native handle.
   */
  destroy() {
    destroyResource(this, (native) => addon.bufferRelease(native));
  }
}

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
class DoeGPUComputePassEncoder {
  constructor(encoder) {
    this._encoder = encoder;
    this._pipeline = null;
    this._bindGroups = [];
    this._ended = false;
    initResource(this, 'GPUComputePassEncoder', encoder);
  }

  _assertOpen(path) {
    if (this._ended) {
      failValidation(path, 'compute pass is already ended');
    }
    if (this._encoder._finished) {
      failValidation(path, 'command encoder is already finished');
    }
  }

  /**
   * Set the compute pipeline used by later dispatch calls.
   *
   * This stores the pipeline handle on the pass so later dispatches use the
   * expected compiled shader and layout.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.setPipeline(pipeline);
   * ```
   *
   * - Call this before dispatching workgroups.
   * - The pipeline object must come from the same device.
   */
  setPipeline(pipeline) {
    this._assertOpen('GPUComputePassEncoder.setPipeline');
    this._pipeline = assertLiveResource(pipeline, 'GPUComputePassEncoder.setPipeline', 'GPUComputePipeline');
  }

  /**
   * Bind a bind group for the compute pass.
   *
   * This records the resource bindings that the next dispatches should see.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.setBindGroup(0, bindGroup);
   * ```
   *
   * - Later calls for the same index replace the previous bind group.
   * - Sparse indices are allowed, but the shader layout still has to match.
   */
  setBindGroup(index, bindGroup) {
    this._assertOpen('GPUComputePassEncoder.setBindGroup');
    assertIntegerInRange(index, 'GPUComputePassEncoder.setBindGroup', 'index', { min: 0, max: UINT32_MAX });
    this._bindGroups[index] = assertLiveResource(bindGroup, 'GPUComputePassEncoder.setBindGroup', 'GPUBindGroup');
  }

  /**
   * Record a direct compute dispatch.
   *
   * This queues an explicit workgroup dispatch on the current pass.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.dispatchWorkgroups(4, 1, 1);
   * ```
   *
   * - Omitted `y` and `z` default to `1`.
   * - The pipeline and required bind groups should already be set.
   */
  dispatchWorkgroups(x, y = 1, z = 1) {
    this._assertOpen('GPUComputePassEncoder.dispatchWorkgroups');
    if (this._pipeline == null) {
      failValidation('GPUComputePassEncoder.dispatchWorkgroups', 'setPipeline() must be called before dispatch');
    }
    assertIntegerInRange(x, 'GPUComputePassEncoder.dispatchWorkgroups', 'x', { min: 0, max: UINT32_MAX });
    assertIntegerInRange(y, 'GPUComputePassEncoder.dispatchWorkgroups', 'y', { min: 0, max: UINT32_MAX });
    assertIntegerInRange(z, 'GPUComputePassEncoder.dispatchWorkgroups', 'z', { min: 0, max: UINT32_MAX });
    this._encoder._commands.push({
      t: 0, p: this._pipeline, bg: [...this._bindGroups], x, y, z,
    });
  }

  /**
   * Dispatch compute workgroups using counts stored in a buffer.
   *
   * This switches to the native encoder path and forwards the indirect dispatch
   * parameters from the supplied buffer.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.dispatchWorkgroupsIndirect(indirectBuffer, 0);
   * ```
   *
   * - This forces the command encoder to materialize a native encoder immediately.
   * - The indirect buffer must contain the expected dispatch layout.
   */
  dispatchWorkgroupsIndirect(indirectBuffer, indirectOffset = 0) {
    this._assertOpen('GPUComputePassEncoder.dispatchWorkgroupsIndirect');
    if (this._pipeline == null) {
      failValidation('GPUComputePassEncoder.dispatchWorkgroupsIndirect', 'setPipeline() must be called before dispatch');
    }
    assertIntegerInRange(
      indirectOffset,
      'GPUComputePassEncoder.dispatchWorkgroupsIndirect',
      'indirectOffset',
      { min: 0 }
    );
    this._encoder._ensureNative();
    const pass = addon.beginComputePass(this._encoder._native);
    addon.computePassSetPipeline(pass, this._pipeline);
    for (let i = 0; i < this._bindGroups.length; i++) {
      if (this._bindGroups[i]) addon.computePassSetBindGroup(pass, i, this._bindGroups[i]);
    }
    addon.computePassDispatchWorkgroupsIndirect(
      pass,
      assertLiveResource(indirectBuffer, 'GPUComputePassEncoder.dispatchWorkgroupsIndirect', 'GPUBuffer'),
      indirectOffset
    );
    addon.computePassEnd(pass);
    addon.computePassRelease(pass);
  }

  /**
   * Finish the compute pass.
   *
   * This closes the pass so the surrounding command encoder can continue or
   * be finalized.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.end();
   * ```
   *
   * - Doe records most work on the surrounding command encoder, so this is lightweight.
   * - Finishing the pass does not submit it; submit the finished command buffer on the queue.
   */
  end() {
    this._assertOpen('GPUComputePassEncoder.end');
    this._ended = true;
  }
}

/**
 * Command encoder returned by `device.createCommandEncoder(...)`.
 *
 * This records compute, render, and buffer-copy commands before they are
 * turned into a command buffer for queue submission.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const encoder = device.createCommandEncoder();
 * ```
 *
 * - Doe may batch simple command sequences before a native encoder is required.
 * - Submission still happens through `device.queue.submit(...)`.
 */
class DoeGPUCommandEncoder {
  constructor(device) {
    this._device = device;
    this._commands = [];
    this._native = null;
    this._finished = false;
    initResource(this, 'GPUCommandEncoder', device);
  }

  _assertOpen(path) {
    assertLiveResource(this._device, path, 'GPUDevice');
    if (this._finished) {
      failValidation(path, 'command encoder is already finished');
    }
  }

  _ensureNative() {
    this._assertOpen('GPUCommandEncoder');
    if (this._native) return;
    this._native = addon.createCommandEncoder(assertLiveResource(this._device, 'GPUCommandEncoder', 'GPUDevice'));
    for (const cmd of this._commands) {
      if (cmd.t === 0) {
        const pass = addon.beginComputePass(this._native);
        addon.computePassSetPipeline(pass, cmd.p);
        for (let i = 0; i < cmd.bg.length; i++) {
          if (cmd.bg[i]) addon.computePassSetBindGroup(pass, i, cmd.bg[i]);
        }
        addon.computePassDispatchWorkgroups(pass, cmd.x, cmd.y, cmd.z);
        addon.computePassEnd(pass);
        addon.computePassRelease(pass);
      } else if (cmd.t === 1) {
        addon.commandEncoderCopyBufferToBuffer(this._native, cmd.s, cmd.so, cmd.d, cmd.do, cmd.sz);
      }
    }
    this._commands = [];
  }

  /**
   * Begin a compute pass.
   *
   * This creates a pass encoder that records compute state and dispatches on
   * this command encoder.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const pass = encoder.beginComputePass();
   * ```
   *
   * - The descriptor is accepted for WebGPU shape compatibility.
   * - The returned pass is valid until `pass.end()`.
   */
  beginComputePass(descriptor) {
    this._assertOpen('GPUCommandEncoder.beginComputePass');
    return new DoeGPUComputePassEncoder(this);
  }

  /**
   * Begin a render pass.
   *
   * This starts a headless render pass with the provided attachments on the
   * underlying native command encoder.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const pass = encoder.beginRenderPass({
   *   colorAttachments: [{ view }],
   * });
   * ```
   *
   * - Doe materializes the native encoder before starting the render pass.
   * - Color attachments default their clear color when one is not provided.
   */
  beginRenderPass(descriptor) {
    this._assertOpen('GPUCommandEncoder.beginRenderPass');
    const passDescriptor = assertObject(descriptor, 'GPUCommandEncoder.beginRenderPass', 'descriptor');
    const attachments = assertArray(passDescriptor.colorAttachments ?? [], 'GPUCommandEncoder.beginRenderPass', 'descriptor.colorAttachments');
    if (attachments.length === 0) {
      failValidation('GPUCommandEncoder.beginRenderPass', 'descriptor.colorAttachments must contain at least one attachment');
    }
    this._ensureNative();
    const colorAttachments = attachments.map((attachment, index) => {
      const entry = assertObject(attachment, 'GPUCommandEncoder.beginRenderPass', `descriptor.colorAttachments[${index}]`);
      return {
        view: assertLiveResource(entry.view, 'GPUCommandEncoder.beginRenderPass', 'GPUTextureView'),
        clearValue: entry.clearValue || { r: 0, g: 0, b: 0, a: 1 },
      };
    });
    const pass = addon.beginRenderPass(this._native, colorAttachments);
    return new DoeGPURenderPassEncoder(pass, this);
  }

  /**
   * Record a buffer-to-buffer copy.
   *
   * This schedules a transfer from one buffer range into another on the
   * command encoder.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * encoder.copyBufferToBuffer(src, 0, dst, 0, src.size);
   * ```
   *
   * - Copies can be batched until the encoder is finalized.
   * - Buffer ranges still need to be valid for the underlying WebGPU rules.
   */
  copyBufferToBuffer(src, srcOffset, dst, dstOffset, size) {
    this._assertOpen('GPUCommandEncoder.copyBufferToBuffer');
    const srcNative = assertLiveResource(src, 'GPUCommandEncoder.copyBufferToBuffer', 'GPUBuffer');
    const dstNative = assertLiveResource(dst, 'GPUCommandEncoder.copyBufferToBuffer', 'GPUBuffer');
    assertIntegerInRange(srcOffset, 'GPUCommandEncoder.copyBufferToBuffer', 'srcOffset', { min: 0 });
    assertIntegerInRange(dstOffset, 'GPUCommandEncoder.copyBufferToBuffer', 'dstOffset', { min: 0 });
    assertIntegerInRange(size, 'GPUCommandEncoder.copyBufferToBuffer', 'size', { min: 1 });
    if (this._native) {
      addon.commandEncoderCopyBufferToBuffer(this._native, srcNative, srcOffset, dstNative, dstOffset, size);
    } else {
      this._commands.push({ t: 1, s: srcNative, so: srcOffset, d: dstNative, do: dstOffset, sz: size });
    }
  }

  /**
   * Finish command recording and return a command buffer.
   *
   * This seals the recorded commands so they can be submitted on a queue.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const commands = encoder.finish();
   * device.queue.submit([commands]);
   * ```
   *
   * - Doe may return a lightweight batched command buffer representation.
   * - The returned object is meant for queue submission, not direct inspection.
   */
  finish() {
    this._assertOpen('GPUCommandEncoder.finish');
    this._finished = true;
    if (this._native) {
      const cmd = addon.commandEncoderFinish(this._native);
      this._native = null;
      return { _native: cmd, _batched: false };
    }
    return { _commands: this._commands, _batched: true };
  }
}

/**
 * Queue exposed on `device.queue`.
 *
 * This submits finished command buffers, uploads host data into buffers, and
 * lets callers wait for queued work to drain.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * device.queue.submit([encoder.finish()]);
 * ```
 *
 * - Queue writes and submissions stay package-local and headless.
 * - The queue also tracks lightweight submission state used by Doe's sync mapping path.
 */
class DoeGPUQueue {
  constructor(native, instance, device) {
    this._native = native;
    this._instance = instance;
    this._device = device;
    this._submittedSerial = 0;
    this._completedSerial = 0;
    initResource(this, 'GPUQueue', device);
  }

  /**
   * Report whether this queue still has unflushed submitted work.
   *
   * This exposes Doe's lightweight submission bookkeeping for callers that
   * need to understand queue state.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const busy = device.queue.hasPendingSubmissions();
   * ```
   *
   * - This is a Doe queue-state helper rather than a standard WebGPU method.
   * - It reflects Doe's tracked submission serials, not a browser event model.
   */
  hasPendingSubmissions() {
    assertLiveResource(this, 'GPUQueue.hasPendingSubmissions', 'GPUQueue');
    return this._completedSerial < this._submittedSerial;
  }

  /**
   * Mark the current tracked submissions as completed.
   *
   * This updates Doe's internal queue bookkeeping without waiting on any
   * external event source.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * device.queue.markSubmittedWorkDone();
   * ```
   *
   * - This is primarily useful for Doe's own queue bookkeeping.
   * - Most callers should prefer `await queue.onSubmittedWorkDone()`.
   */
  markSubmittedWorkDone() {
    assertLiveResource(this, 'GPUQueue.markSubmittedWorkDone', 'GPUQueue');
    this._completedSerial = this._submittedSerial;
  }

  /**
   * Submit command buffers to the queue.
   *
   * This forwards one or more finished command buffers to the Doe queue for
   * execution.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * device.queue.submit([encoder.finish()]);
   * ```
   *
   * - Empty submissions are ignored.
   * - Simple batched compute-copy sequences may take a Doe fast path.
   */
  submit(commandBuffers) {
    const queueNative = assertLiveResource(this, 'GPUQueue.submit', 'GPUQueue');
    const deviceNative = assertLiveResource(this._device, 'GPUQueue.submit', 'GPUDevice');
    const buffers = assertArray(commandBuffers, 'GPUQueue.submit', 'commandBuffers');
    if (buffers.length === 0) return;
    this._submittedSerial += 1;
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
        return;
      }
    }
    if (buffers.length > 0 && buffers.every((commandBuffer) => commandBuffer?._batched && Array.isArray(commandBuffer._commands))) {
      const allCommands = [];
      for (const cb of buffers) allCommands.push(...cb._commands);
      addon.submitBatched(deviceNative, queueNative, allCommands);
      if (
        allCommands.length === 2
        && allCommands[0]?.t === 0
        && allCommands[1]?.t === 1
      ) {
        this.markSubmittedWorkDone();
      }
    } else {
      const natives = buffers.map((commandBuffer, index) => {
        if (!commandBuffer || typeof commandBuffer !== 'object' || commandBuffer._native == null) {
          failValidation('GPUQueue.submit', `commandBuffers[${index}] must be a finished command buffer`);
        }
        return commandBuffer._native;
      });
      addon.queueSubmit(queueNative, natives);
    }
  }

  /**
   * Write host data into a GPU buffer.
   *
   * This copies bytes from JS-owned memory into the destination GPU buffer
   * range on the queue.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * device.queue.writeBuffer(buffer, 0, new Float32Array([1, 2, 3, 4]));
   * ```
   *
   * - `dataOffset` and `size` are interpreted in element units for typed arrays.
   * - Doe converts the requested range into bytes before writing it.
   */
  writeBuffer(buffer, bufferOffset, data, dataOffset = 0, size) {
    const queueNative = assertLiveResource(this, 'GPUQueue.writeBuffer', 'GPUQueue');
    const bufferNative = assertLiveResource(buffer, 'GPUQueue.writeBuffer', 'GPUBuffer');
    assertIntegerInRange(bufferOffset, 'GPUQueue.writeBuffer', 'bufferOffset', { min: 0 });
    assertIntegerInRange(dataOffset, 'GPUQueue.writeBuffer', 'dataOffset', { min: 0 });
    if (
      !ArrayBuffer.isView(data)
      && !(data instanceof ArrayBuffer)
      && !Buffer.isBuffer(data)
    ) {
      failValidation('GPUQueue.writeBuffer', 'data must be a TypedArray, DataView, ArrayBuffer, or Buffer');
    }
    let view = data;
    if (dataOffset > 0 || size !== undefined) {
      if (!ArrayBuffer.isView(data)) {
        failValidation('GPUQueue.writeBuffer', 'dataOffset and size slicing require a TypedArray or DataView input');
      }
      if (size !== undefined) {
        assertIntegerInRange(size, 'GPUQueue.writeBuffer', 'size', { min: 0 });
      }
      const byteOffset = data.byteOffset + dataOffset * (data.BYTES_PER_ELEMENT || 1);
      const byteLength = size !== undefined
        ? size * (data.BYTES_PER_ELEMENT || 1)
        : data.byteLength - dataOffset * (data.BYTES_PER_ELEMENT || 1);
      view = new Uint8Array(data.buffer, byteOffset, byteLength);
    }
    addon.queueWriteBuffer(queueNative, bufferNative, bufferOffset, view);
  }

  /**
   * Resolve after submitted work has been flushed.
   *
   * This gives callers a simple way to wait until Doe has drained the tracked
   * queue work relevant to this device.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * await device.queue.onSubmittedWorkDone();
   * ```
   *
   * - If no submissions are pending, this resolves immediately.
   * - Doe flushes the native queue before marking the tracked work complete.
   */
  async onSubmittedWorkDone() {
    const queueNative = assertLiveResource(this, 'GPUQueue.onSubmittedWorkDone', 'GPUQueue');
    if (!this.hasPendingSubmissions()) return;
    try {
      addon.queueFlush(this._instance, queueNative);
    } catch (error) {
      if (error?.code === 'DOE_QUEUE_UNAVAILABLE') {
        return;
      }
      throw error;
    }
    this.markSubmittedWorkDone();
  }
}

/**
 * Render pass encoder returned by `commandEncoder.beginRenderPass(...)`.
 *
 * This provides the subset of render-pass methods currently surfaced by the
 * full headless package.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const pass = encoder.beginRenderPass({ colorAttachments: [{ view }] });
 * ```
 *
 * - The exposed render API is intentionally narrower than a browser implementation.
 * - Submission still happens through the command encoder and queue.
 */
class DoeGPURenderPassEncoder {
  constructor(native, encoder) {
    this._native = native;
    this._encoder = encoder;
    this._ended = false;
    initResource(this, 'GPURenderPassEncoder', encoder);
  }

  _assertOpen(path) {
    if (this._ended) {
      failValidation(path, 'render pass is already ended');
    }
    if (this._encoder._finished) {
      failValidation(path, 'command encoder is already finished');
    }
  }

  /**
   * Set the render pipeline used by later draw calls.
   *
   * This records the pipeline state that subsequent draw calls in the pass
   * should use.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.setPipeline(pipeline);
   * ```
   *
   * - The pipeline must come from the same device.
   * - Call this before `draw(...)`.
   */
  setPipeline(pipeline) {
    this._assertOpen('GPURenderPassEncoder.setPipeline');
    addon.renderPassSetPipeline(
      assertLiveResource(this, 'GPURenderPassEncoder.setPipeline', 'GPURenderPassEncoder'),
      assertLiveResource(pipeline, 'GPURenderPassEncoder.setPipeline', 'GPURenderPipeline')
    );
  }

  /**
   * Record a non-indexed draw.
   *
   * This queues a draw call using the current render pipeline and bound
   * attachments.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.draw(3);
   * ```
   *
   * - Omitted instance and offset arguments default to the WebGPU-style values.
   * - Draw calls only become visible after the command buffer is submitted.
   */
  draw(vertexCount, instanceCount = 1, firstVertex = 0, firstInstance = 0) {
    this._assertOpen('GPURenderPassEncoder.draw');
    assertIntegerInRange(vertexCount, 'GPURenderPassEncoder.draw', 'vertexCount', { min: 0, max: UINT32_MAX });
    assertIntegerInRange(instanceCount, 'GPURenderPassEncoder.draw', 'instanceCount', { min: 0, max: UINT32_MAX });
    assertIntegerInRange(firstVertex, 'GPURenderPassEncoder.draw', 'firstVertex', { min: 0, max: UINT32_MAX });
    assertIntegerInRange(firstInstance, 'GPURenderPassEncoder.draw', 'firstInstance', { min: 0, max: UINT32_MAX });
    addon.renderPassDraw(this._native, vertexCount, instanceCount, firstVertex, firstInstance);
  }

  /**
   * Finish the render pass.
   *
   * This closes the native render-pass encoder so the command encoder can
   * continue recording.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * pass.end();
   * ```
   *
   * - This closes the native render pass encoder.
   * - It does not submit work by itself.
   */
  end() {
    this._assertOpen('GPURenderPassEncoder.end');
    addon.renderPassEnd(this._native);
    this._ended = true;
  }
}

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
class DoeGPUTexture {
  constructor(native, owner) {
    this._native = native;
    initResource(this, 'GPUTexture', owner);
  }

  /**
   * Create a texture view.
   *
   * This returns a default texture view wrapper for the texture so it can be
   * used in render or sampling APIs.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const view = texture.createView();
   * ```
   *
   * - Doe currently ignores most descriptor variation here and creates a default view.
   * - The returned view is suitable for the package's headless render paths.
   */
  createView(descriptor) {
    const view = addon.textureCreateView(assertLiveResource(this, 'GPUTexture.createView', 'GPUTexture'));
    return new DoeGPUTextureView(view, this);
  }

  /**
   * Release the native texture.
   *
   * This tears down the underlying Doe texture allocation associated with the
   * wrapper.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * texture.destroy();
   * ```
   *
   * - Reusing the texture after destruction is unsupported.
   * - Views already created are plain JS wrappers and do not keep the texture alive.
   */
  destroy() {
    destroyResource(this, (native) => addon.textureRelease(native));
  }
}

/**
 * Texture view wrapper returned by `texture.createView()`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const view = texture.createView();
 * ```
 *
 * - This package currently treats the view as a lightweight opaque handle.
 */
class DoeGPUTextureView {
  constructor(native, owner) {
    this._native = native;
    initResource(this, 'GPUTextureView', owner);
  }
}

/**
 * Sampler wrapper returned by `device.createSampler(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const sampler = device.createSampler();
 * ```
 *
 * - The sampler is currently an opaque handle on the JS side.
 */
class DoeGPUSampler {
  constructor(native, owner) {
    this._native = native;
    initResource(this, 'GPUSampler', owner);
  }
}

/**
 * Render pipeline returned by `device.createRenderPipeline(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const pipeline = device.createRenderPipeline(descriptor);
 * ```
 *
 * - The JS wrapper is currently an opaque handle used by render passes.
 */
class DoeGPURenderPipeline {
  constructor(native, owner) {
    this._native = native;
    initResource(this, 'GPURenderPipeline', owner);
  }
}

/**
 * Shader module returned by `device.createShaderModule(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const shader = device.createShaderModule({ code: WGSL });
 * ```
 *
 * - Doe keeps the WGSL source on the wrapper for pipeline creation and auto-layout work.
 */
class DoeGPUShaderModule {
  constructor(native, code, owner) {
    this._native = native;
    this._code = code;
    initResource(this, 'GPUShaderModule', owner);
  }

  destroy() {
    destroyResource(this, (native) => addon.shaderModuleRelease(native));
  }
}

/**
 * Compute pipeline returned by `device.createComputePipeline(...)`.
 *
 * This wrapper exposes pipeline layout lookup for bind-group creation and
 * dispatch setup.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const pipeline = device.createComputePipeline({
 *   layout: "auto",
 *   compute: { module: shader, entryPoint: "main" },
 * });
 * ```
 *
 * - Auto-layout pipelines derive bind-group layouts from the shader source.
 * - Explicit-layout pipelines return the layout they were created with.
 */
class DoeGPUComputePipeline {
  constructor(native, device, explicitLayout, autoLayoutEntriesByGroup) {
    this._native = native;
    this._device = device;
    this._explicitLayout = explicitLayout;
    this._autoLayoutEntriesByGroup = autoLayoutEntriesByGroup;
    this._cachedLayouts = new Map();
    initResource(this, 'GPUComputePipeline', device);
  }

  /**
   * Return the bind-group layout for a given group index.
   *
   * This gives callers the layout object needed to construct compatible bind
   * groups for the pipeline.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const layout = pipeline.getBindGroupLayout(0);
   * ```
   *
   * - Auto-layout pipelines lazily build and cache layouts by group index.
   * - Explicit-layout pipelines return their original layout for any requested index.
   */
  getBindGroupLayout(index) {
    assertLiveResource(this, 'GPUComputePipeline.getBindGroupLayout', 'GPUComputePipeline');
    assertIntegerInRange(index, 'GPUComputePipeline.getBindGroupLayout', 'index', { min: 0, max: UINT32_MAX });
    if (this._explicitLayout) return this._explicitLayout;
    if (this._cachedLayouts.has(index)) return this._cachedLayouts.get(index);
    let layout;
    if (this._autoLayoutEntriesByGroup && process.platform === 'darwin') {
      const entries = this._autoLayoutEntriesByGroup.get(index) ?? [];
      layout = this._device.createBindGroupLayout({ entries });
    } else if (typeof addon.computePipelineGetBindGroupLayout === 'function') {
      layout = new DoeGPUBindGroupLayout(
        addon.computePipelineGetBindGroupLayout(this._native, index),
        this._device,
      );
    } else if (this._autoLayoutEntriesByGroup) {
      const entries = this._autoLayoutEntriesByGroup.get(index) ?? [];
      layout = this._device.createBindGroupLayout({ entries });
    } else {
      layout = this._device.createBindGroupLayout({ entries: [] });
    }
    this._cachedLayouts.set(index, layout);
    return layout;
  }
}

/**
 * Bind-group layout returned by `device.createBindGroupLayout(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const layout = device.createBindGroupLayout({ entries });
 * ```
 *
 * - The JS wrapper is an opaque handle used when creating bind groups and pipelines.
 */
class DoeGPUBindGroupLayout {
  constructor(native, owner) {
    this._native = native;
    initResource(this, 'GPUBindGroupLayout', owner);
  }
}

/**
 * Bind group returned by `device.createBindGroup(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const bindGroup = device.createBindGroup({ layout, entries });
 * ```
 *
 * - The JS wrapper is an opaque handle consumed by pass encoders.
 */
class DoeGPUBindGroup {
  constructor(native, owner) {
    this._native = native;
    initResource(this, 'GPUBindGroup', owner);
  }
}

/**
 * Pipeline layout returned by `device.createPipelineLayout(...)`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const layout = device.createPipelineLayout({ bindGroupLayouts: [group0] });
 * ```
 *
 * - The JS wrapper is an opaque handle passed into pipeline creation.
 */
class DoeGPUPipelineLayout {
  constructor(native, owner) {
    this._native = native;
    initResource(this, 'GPUPipelineLayout', owner);
  }
}

const DOE_LIMITS = Object.freeze({
  maxTextureDimension1D: 16384,
  maxTextureDimension2D: 16384,
  maxTextureDimension3D: 2048,
  maxTextureArrayLayers: 2048,
  maxBindGroups: 4,
  maxBindGroupsPlusVertexBuffers: 24,
  maxBindingsPerBindGroup: 1000,
  maxDynamicUniformBuffersPerPipelineLayout: 8,
  maxDynamicStorageBuffersPerPipelineLayout: 4,
  maxSampledTexturesPerShaderStage: 16,
  maxSamplersPerShaderStage: 16,
  maxStorageBuffersPerShaderStage: 8,
  maxStorageTexturesPerShaderStage: 4,
  maxUniformBuffersPerShaderStage: 12,
  maxUniformBufferBindingSize: 65536,
  maxStorageBufferBindingSize: 134217728,
  minUniformBufferOffsetAlignment: 256,
  minStorageBufferOffsetAlignment: 32,
  maxVertexBuffers: 8,
  maxBufferSize: 268435456,
  maxVertexAttributes: 16,
  maxVertexBufferArrayStride: 2048,
  maxInterStageShaderVariables: 16,
  maxColorAttachments: 8,
  maxColorAttachmentBytesPerSample: 32,
  maxComputeWorkgroupStorageSize: 32768,
  maxComputeInvocationsPerWorkgroup: 1024,
  maxComputeWorkgroupSizeX: 1024,
  maxComputeWorkgroupSizeY: 1024,
  maxComputeWorkgroupSizeZ: 64,
  maxComputeWorkgroupsPerDimension: 65535,
});

const DOE_FEATURES = Object.freeze(new Set());

/**
 * Device returned by `adapter.requestDevice()`.
 *
 * This is the main full-surface headless WebGPU object exposed by the package.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const device = await adapter.requestDevice();
 * ```
 *
 * - `queue`, `limits`, and `features` are available as data properties.
 * - The full package keeps render, texture, sampler, and command APIs on this object.
 */
class DoeGPUDevice {
  constructor(native, instance, inheritedLimits = null) {
    this._native = native;
    this._instance = instance;
    initResource(this, 'GPUDevice');
    const q = addon.deviceGetQueue(native);
    this.queue = new DoeGPUQueue(q, instance, this);
    this.limits = inheritedLimits ?? deviceLimits(native);
    this.features = deviceFeatures(native);
  }

  /**
   * Create a buffer.
   *
   * This allocates a Doe buffer using the supplied WebGPU-shaped descriptor and
   * returns the package wrapper for it.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const buffer = device.createBuffer({
   *   size: 16,
   *   usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST,
   * });
   * ```
   *
   * - The descriptor follows the standard WebGPU buffer shape.
   * - The returned wrapper exposes `size`, `usage`, mapping, and destruction helpers.
   */
  createBuffer(descriptor) {
    const validated = validateBufferDescriptor(descriptor);
    const buf = addon.createBuffer(assertLiveResource(this, 'GPUDevice.createBuffer', 'GPUDevice'), validated);
    return new DoeGPUBuffer(buf, this._instance, validated.size, validated.usage, this.queue, this);
  }

  /**
   * Create a shader module from WGSL source.
   *
   * This compiles WGSL into a shader module wrapper that can be used by
   * compute or render pipeline creation.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const shader = device.createShaderModule({ code: WGSL });
   * ```
   *
   * - `descriptor.code` is required on this surface.
   * - The package also accepts `descriptor.source` as a convenience alias.
   */
  createShaderModule(descriptor) {
    const objectDescriptor = assertObject(descriptor, 'GPUDevice.createShaderModule', 'descriptor');
    const code = objectDescriptor.code ?? objectDescriptor.source;
    assertNonEmptyString(code, 'GPUDevice.createShaderModule', 'descriptor.code');
    const preflight = preflightShaderSource(code);
    if (!preflight.ok) {
      shaderCheckFailure('GPUDevice.createShaderModule', preflight);
    }
    let mod;
    try {
      mod = addon.createShaderModule(assertLiveResource(this, 'GPUDevice.createShaderModule', 'GPUDevice'), code);
    } catch (error) {
      throw enrichNativeCompilerError(error, 'GPUDevice.createShaderModule');
    }
    return new DoeGPUShaderModule(mod, code, this);
  }

  /**
   * Create a compute pipeline.
   *
   * This builds a pipeline wrapper from a shader module, entry point, and
   * optional explicit layout information.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const pipeline = device.createComputePipeline({
   *   layout: "auto",
   *   compute: { module: shader, entryPoint: "main" },
   * });
   * ```
   *
   * - `layout: "auto"` derives bind-group layouts from the WGSL.
   * - Explicit pipeline layouts are passed through directly.
   */
  createComputePipeline(descriptor) {
    const pipelineDescriptor = assertObject(descriptor, 'GPUDevice.createComputePipeline', 'descriptor');
    const compute = assertObject(pipelineDescriptor.compute, 'GPUDevice.createComputePipeline', 'descriptor.compute');
    const shader = compute.module;
    const shaderNative = assertLiveResource(shader, 'GPUDevice.createComputePipeline', 'GPUShaderModule');
    const entryPoint = compute.entryPoint ?? 'main';
    assertNonEmptyString(entryPoint, 'GPUDevice.createComputePipeline', 'descriptor.compute.entryPoint');
    const layout = pipelineDescriptor.layout === 'auto' || pipelineDescriptor.layout === undefined
      ? null
      : pipelineDescriptor.layout;
    if (layout !== null) {
      assertLiveResource(layout, 'GPUDevice.createComputePipeline', 'GPUPipelineLayout');
    }
    const autoLayoutEntriesByGroup = layout
      ? null
      : requireAutoLayoutEntriesFromNative(
        shaderNative,
        globals.GPUShaderStage.COMPUTE,
        'GPUDevice.createComputePipeline'
      );
    let native;
    try {
      native = addon.createComputePipeline(
        assertLiveResource(this, 'GPUDevice.createComputePipeline', 'GPUDevice'),
        shaderNative,
        entryPoint,
        layout?._native ?? null
      );
    } catch (error) {
      throw enrichNativeCompilerError(error, 'GPUDevice.createComputePipeline');
    }
    return new DoeGPUComputePipeline(native, this, layout, autoLayoutEntriesByGroup);
  }

  /**
   * Create a compute pipeline through an async-shaped API.
   *
   * This preserves the async WebGPU API shape while using Doe's current
   * synchronous pipeline creation underneath.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const pipeline = await device.createComputePipelineAsync(descriptor);
   * ```
   *
   * - Doe currently resolves this by calling the synchronous pipeline creation path.
   * - The async shape exists for WebGPU API compatibility.
   */
  async createComputePipelineAsync(descriptor) {
    return this.createComputePipeline(descriptor);
  }

  /**
   * Create a bind-group layout.
   *
   * This normalizes the descriptor into the shape expected by Doe and returns
   * a layout wrapper for later resource binding.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const layout = device.createBindGroupLayout({ entries });
   * ```
   *
   * - Missing buffer entry fields are normalized to WebGPU-style defaults.
   * - Sampler, texture, and storage-texture entries are forwarded when present.
   */
  createBindGroupLayout(descriptor) {
    const layoutDescriptor = assertObject(descriptor, 'GPUDevice.createBindGroupLayout', 'descriptor');
    const entries = assertArray(layoutDescriptor.entries ?? [], 'GPUDevice.createBindGroupLayout', 'descriptor.entries').map((entry, index) => {
      const binding = assertObject(entry, 'GPUDevice.createBindGroupLayout', `descriptor.entries[${index}]`);
      return {
        binding: assertIntegerInRange(binding.binding, 'GPUDevice.createBindGroupLayout', `descriptor.entries[${index}].binding`, { min: 0, max: UINT32_MAX }),
        visibility: assertIntegerInRange(binding.visibility, 'GPUDevice.createBindGroupLayout', `descriptor.entries[${index}].visibility`, { min: 0 }),
        buffer: binding.buffer ? {
          type: binding.buffer.type || 'uniform',
          hasDynamicOffset: binding.buffer.hasDynamicOffset || false,
          minBindingSize: binding.buffer.minBindingSize || 0,
        } : undefined,
        sampler: binding.sampler
          ? normalizeSamplerLayout(binding.sampler, 'GPUDevice.createBindGroupLayout', `descriptor.entries[${index}].sampler`)
          : undefined,
        texture: binding.texture
          ? normalizeTextureLayout(binding.texture, 'GPUDevice.createBindGroupLayout', `descriptor.entries[${index}].texture`)
          : undefined,
        storageTexture: binding.storageTexture
          ? normalizeStorageTextureLayout(binding.storageTexture, 'GPUDevice.createBindGroupLayout', `descriptor.entries[${index}].storageTexture`)
          : undefined,
      };
    });
    const native = addon.createBindGroupLayout(assertLiveResource(this, 'GPUDevice.createBindGroupLayout', 'GPUDevice'), entries);
    return new DoeGPUBindGroupLayout(native, this);
  }

  /**
   * Create a bind group.
   *
   * This binds resources to a previously created layout and returns the bind
   * group wrapper used by pass encoders.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const bindGroup = device.createBindGroup({ layout, entries });
   * ```
   *
   * - Resource buffers may be passed either as `{ buffer, offset, size }` or as bare buffer wrappers.
   * - Layout and buffer wrappers must come from the same device.
   */
  createBindGroup(descriptor) {
    const bindGroupDescriptor = assertObject(descriptor, 'GPUDevice.createBindGroup', 'descriptor');
    const layoutNative = assertLiveResource(bindGroupDescriptor.layout, 'GPUDevice.createBindGroup', 'GPUBindGroupLayout');
    const entries = assertArray(bindGroupDescriptor.entries ?? [], 'GPUDevice.createBindGroup', 'descriptor.entries').map((entry, index) => {
      const binding = assertObject(entry, 'GPUDevice.createBindGroup', `descriptor.entries[${index}]`);
      const resource = assertBindGroupResource(binding.resource, 'GPUDevice.createBindGroup');
      const normalized = {
        binding: assertIntegerInRange(binding.binding, 'GPUDevice.createBindGroup', `descriptor.entries[${index}].binding`, { min: 0, max: UINT32_MAX }),
        buffer: resource.buffer,
        sampler: resource.sampler,
        textureView: resource.textureView,
        offset: resource.offset ?? 0,
      };
      if (resource.size !== undefined) normalized.size = resource.size;
      return normalized;
    });
    const native = addon.createBindGroup(
      assertLiveResource(this, 'GPUDevice.createBindGroup', 'GPUDevice'),
      layoutNative,
      entries
    );
    return new DoeGPUBindGroup(native, this);
  }

  /**
   * Create a pipeline layout.
   *
   * This combines one or more bind-group layouts into the pipeline layout
   * wrapper used during pipeline creation.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const layout = device.createPipelineLayout({ bindGroupLayouts: [group0] });
   * ```
   *
   * - Bind-group layouts are unwrapped to their native handles before creation.
   * - The returned wrapper is opaque on the JS side.
   */
  createPipelineLayout(descriptor) {
    const layoutDescriptor = assertObject(descriptor, 'GPUDevice.createPipelineLayout', 'descriptor');
    const layouts = assertArray(layoutDescriptor.bindGroupLayouts ?? [], 'GPUDevice.createPipelineLayout', 'descriptor.bindGroupLayouts')
      .map((layout, index) => assertLiveResource(layout, 'GPUDevice.createPipelineLayout', `descriptor.bindGroupLayouts[${index}]`));
    const native = addon.createPipelineLayout(assertLiveResource(this, 'GPUDevice.createPipelineLayout', 'GPUDevice'), layouts);
    return new DoeGPUPipelineLayout(native, this);
  }

  /**
   * Create a texture.
   *
   * This allocates a Doe texture resource from a WebGPU-shaped descriptor and
   * returns the package wrapper for it.
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
   * - `descriptor.size` may be a scalar, tuple, or width/height object.
   * - Omitted format and mip-count fields fall back to package defaults.
   */
  createTexture(descriptor) {
    const textureDescriptor = assertObject(descriptor, 'GPUDevice.createTexture', 'descriptor');
    const size = assertTextureSize(textureDescriptor.size, 'GPUDevice.createTexture');
    const usage = assertIntegerInRange(textureDescriptor.usage, 'GPUDevice.createTexture', 'descriptor.usage', { min: 1 });
    const native = addon.createTexture(assertLiveResource(this, 'GPUDevice.createTexture', 'GPUDevice'), {
      format: textureDescriptor.format || 'rgba8unorm',
      width: size.width,
      height: size.height,
      depthOrArrayLayers: size.depthOrArrayLayers,
      usage,
      mipLevelCount: assertIntegerInRange(textureDescriptor.mipLevelCount ?? 1, 'GPUDevice.createTexture', 'descriptor.mipLevelCount', { min: 1, max: UINT32_MAX }),
    });
    return new DoeGPUTexture(native, this);
  }

  /**
   * Create a sampler.
   *
   * This allocates a sampler wrapper that can be used by the package's render
   * and texture-binding paths.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const sampler = device.createSampler();
   * ```
   *
   * - An empty descriptor is allowed.
   * - The returned wrapper is currently an opaque handle on the JS side.
   */
  createSampler(descriptor = {}) {
    assertObject(descriptor, 'GPUDevice.createSampler', 'descriptor');
    const native = addon.createSampler(assertLiveResource(this, 'GPUDevice.createSampler', 'GPUDevice'), descriptor);
    return new DoeGPUSampler(native, this);
  }

  /**
   * Create a render pipeline.
   *
   * This builds the package's render-pipeline wrapper for use with render-pass
   * encoders on the full surface.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const pipeline = device.createRenderPipeline(descriptor);
   * ```
   *
   * - The returned wrapper is consumed by render-pass encoders.
   * - Descriptor handling on this package surface is intentionally narrower than browser engines.
   */
  createRenderPipeline(descriptor) {
    if (descriptor !== undefined) {
      assertObject(descriptor, 'GPUDevice.createRenderPipeline', 'descriptor');
    }
    assertLiveResource(this, 'GPUDevice.createRenderPipeline', 'GPUDevice');
    const error = new Error(
      'GPUDevice.createRenderPipeline: render pipelines are not supported on this package surface yet; use the lower-level Doe runtime or browser surface for render work'
    );
    error.code = 'UnsupportedSurface';
    error.stage = 'package_surface';
    throw error;
  }

  /**
   * Create a command encoder.
   *
   * This creates the object that records compute, render, and copy commands
   * before queue submission.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const encoder = device.createCommandEncoder();
   * ```
   *
   * - The descriptor is accepted for API shape compatibility.
   * - The returned encoder records work until `finish()` is called.
   */
  createCommandEncoder(descriptor) {
    if (descriptor !== undefined) {
      assertObject(descriptor, 'GPUDevice.createCommandEncoder', 'descriptor');
    }
    assertLiveResource(this, 'GPUDevice.createCommandEncoder', 'GPUDevice');
    return new DoeGPUCommandEncoder(this);
  }

  /**
   * Release the native device.
   *
   * This tears down the underlying Doe device associated with the wrapper.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * device.destroy();
   * ```
   *
   * - Reusing the device after destruction is unsupported.
   * - Existing wrappers created from the device do not regain validity afterward.
   */
  destroy() {
    destroyResource(this, (native) => addon.deviceRelease(native));
  }
}

/**
 * Adapter returned by `gpu.requestAdapter()`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const adapter = await gpu.requestAdapter();
 * ```
 *
 * - `features` and `limits` are exposed as data properties.
 * - The adapter produces full-surface devices on this package entrypoint.
 */
class DoeGPUAdapter {
  constructor(native, instance) {
    this._native = native;
    this._instance = instance;
    this.features = adapterFeatures(native);
    this.limits = adapterLimits(native);
    initResource(this, 'GPUAdapter');
  }

  /**
   * Request a device from this adapter.
   *
   * This creates the full-surface Doe device associated with the adapter.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const device = await adapter.requestDevice();
   * ```
   *
   * - The descriptor is accepted for WebGPU API shape compatibility.
   * - The returned device includes the full package surface.
   */
  async requestDevice(descriptor) {
    assertLiveResource(this, 'GPUAdapter.requestDevice', 'GPUAdapter');
    const device = addon.requestDevice(this._instance, this._native);
    return new DoeGPUDevice(device, this._instance, this.limits);
  }

  /**
   * Release the native adapter.
   *
   * This tears down the adapter handle that was returned by Doe for this GPU.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * adapter.destroy();
   * ```
   *
   * - Reusing the adapter after destruction is unsupported.
   */
  destroy() {
    destroyResource(this, (native) => addon.adapterRelease(native));
  }
}

/**
 * GPU root object returned by `create()` or installed at `navigator.gpu`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * const gpu = create();
 * ```
 *
 * - This is a headless package-owned GPU object, not a browser-owned DOM object.
 */
class DoeGPU {
  constructor(instance) {
    this._instance = instance;
  }

  /**
   * Request an adapter from the Doe runtime.
   *
   * This asks the package-owned GPU object for an adapter wrapper that can
   * later create full-surface devices.
   *
   * This example shows the API in its basic form.
   *
   * ```js
   * const adapter = await gpu.requestAdapter();
   * ```
   *
   * - The current Doe package path ignores adapter filtering options.
   * - The returned adapter exposes full-surface device creation.
   */
  async requestAdapter(options) {
    const adapter = addon.requestAdapter(this._instance);
    return new DoeGPUAdapter(adapter, this._instance);
  }
}

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
  for (const [name, value] of Object.entries(globals)) {
    if (target[name] === undefined) {
      Object.defineProperty(target, name, {
        value,
        writable: true,
        configurable: true,
        enumerable: false,
      });
    }
  }
  const gpu = create(createArgs);
  if (typeof target.navigator === 'undefined') {
    Object.defineProperty(target, 'navigator', {
      value: { gpu },
      writable: true,
      configurable: true,
      enumerable: false,
    });
  } else if (!target.navigator.gpu) {
    Object.defineProperty(target.navigator, 'gpu', {
      value: gpu,
      writable: true,
      configurable: true,
      enumerable: false,
    });
  }
  return gpu;
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
  const gpu = create(createArgs);
  return gpu.requestAdapter(adapterOptions);
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
  const createArgs = options?.createArgs ?? null;
  const adapter = await requestAdapter(options?.adapterOptions, createArgs);
  return adapter.requestDevice(options?.deviceDescriptor);
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
  return {
    module: '@simulatte/webgpu',
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
  };
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

export default {
  create,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  createDoeRuntime,
  runDawnVsDoeCompare,
};
