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
  encoder._native = addon.createCommandEncoder(assertLiveResource(encoder._device, 'GPUCommandEncoder', 'GPUDevice'));
  for (const cmd of encoder._commands) {
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
  computePassInit(pass) {
    pass._pipeline = null;
    pass._bindGroups = [];
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
    pass._pipeline = pipelineNative;
  },
  computePassSetBindGroup(pass, index, bindGroupNative) {
    pass._bindGroups[index] = bindGroupNative;
  },
  computePassDispatchWorkgroups(pass, x, y, z) {
    if (pass._pipeline == null) {
      failValidation('GPUComputePassEncoder.dispatchWorkgroups', 'setPipeline() must be called before dispatch');
    }
    pass._encoder._commands.push({ t: 0, p: pass._pipeline, bg: [...pass._bindGroups], x, y, z });
  },
  computePassDispatchWorkgroupsIndirect(pass, indirectBufferNative, indirectOffset) {
    if (pass._pipeline == null) {
      failValidation('GPUComputePassEncoder.dispatchWorkgroupsIndirect', 'setPipeline() must be called before dispatch');
    }
    ensureNodeCommandEncoderNative(pass._encoder);
    const nativePass = addon.beginComputePass(pass._encoder._native);
    addon.computePassSetPipeline(nativePass, pass._pipeline);
    for (let index = 0; index < pass._bindGroups.length; index += 1) {
      if (pass._bindGroups[index]) {
        addon.computePassSetBindGroup(nativePass, index, pass._bindGroups[index]);
      }
    }
    addon.computePassDispatchWorkgroupsIndirect(nativePass, indirectBufferNative, indirectOffset);
    addon.computePassEnd(nativePass);
    addon.computePassRelease(nativePass);
  },
  computePassEnd(pass) {
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
  renderPassEnd(pass) {
    addon.renderPassEnd(pass._native);
    pass._ended = true;
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
    return new classes.DoeGPUComputePassEncoder(null, encoder);
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
    if (encoder._native) {
      addon.commandEncoderCopyBufferToBuffer(encoder._native, srcNative, srcOffset, dstNative, dstOffset, size);
      return;
    }
    encoder._commands.push({ t: 1, s: srcNative, so: srcOffset, d: dstNative, do: dstOffset, sz: size });
  },
  commandEncoderFinish(encoder) {
    encoder._finished = true;
    if (encoder._native) {
      const cmd = addon.commandEncoderFinish(encoder._native);
      encoder._native = null;
      return { _native: cmd, _batched: false };
    }
    return { _commands: encoder._commands, _batched: true };
  },
};

const {
  DoeGPUComputePassEncoder,
  DoeGPUCommandEncoder,
  DoeGPURenderPassEncoder,
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
  initBufferState() {},
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
  },
  bufferGetMappedRange(_wrapper, native, offset, size) {
    return addon.bufferGetMappedRange(native, offset, size);
  },
  bufferAssertMappedPrefixF32(_wrapper, native, expected, count) {
    return addon.bufferAssertMappedPrefixF32(native, expected, count);
  },
  bufferUnmap(native) {
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
  async queueOnSubmittedWorkDone(queue, queueNative) {
    try {
      addon.queueFlush(queue._instance, queueNative);
    } catch (error) {
      if (error?.code === 'DOE_QUEUE_UNAVAILABLE') {
        return;
      }
      throw error;
    }
  },
  textureCreateView(_texture, native) {
    return addon.textureCreateView(native);
  },
  textureDestroy(native) {
    addon.textureRelease(native);
  },
  shaderModuleDestroy(native) {
    addon.shaderModuleRelease(native);
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
  deviceCreateShaderModule(device, code) {
    try {
      return addon.createShaderModule(assertLiveResource(device, 'GPUDevice.createShaderModule', 'GPUDevice'), code);
    } catch (error) {
      throw enrichNativeCompilerError(error, 'GPUDevice.createShaderModule');
    }
  },
  deviceCreateComputePipeline(device, shaderNative, entryPoint, layoutNative) {
    try {
      return addon.createComputePipeline(
        assertLiveResource(device, 'GPUDevice.createComputePipeline', 'GPUDevice'),
        shaderNative,
        entryPoint,
        layoutNative,
      );
    } catch (error) {
      throw enrichNativeCompilerError(error, 'GPUDevice.createComputePipeline');
    }
  },
  deviceCreateBindGroupLayout(device, entries) {
    return addon.createBindGroupLayout(assertLiveResource(device, 'GPUDevice.createBindGroupLayout', 'GPUDevice'), entries);
  },
  deviceCreateBindGroup(device, layoutNative, entries) {
    return addon.createBindGroup(
      assertLiveResource(device, 'GPUDevice.createBindGroup', 'GPUDevice'),
      layoutNative,
      entries,
    );
  },
  deviceCreatePipelineLayout(device, layouts) {
    return addon.createPipelineLayout(assertLiveResource(device, 'GPUDevice.createPipelineLayout', 'GPUDevice'), layouts);
  },
  deviceCreateTexture(device, textureDescriptor, size, usage) {
    return addon.createTexture(assertLiveResource(device, 'GPUDevice.createTexture', 'GPUDevice'), {
      format: textureDescriptor.format || 'rgba8unorm',
      width: size.width,
      height: size.height,
      depthOrArrayLayers: size.depthOrArrayLayers,
      usage,
      mipLevelCount: assertIntegerInRange(textureDescriptor.mipLevelCount ?? 1, 'GPUDevice.createTexture', 'descriptor.mipLevelCount', { min: 1, max: UINT32_MAX }),
    });
  },
  deviceCreateSampler(device, descriptor) {
    return addon.createSampler(assertLiveResource(device, 'GPUDevice.createSampler', 'GPUDevice'), descriptor);
  },
  deviceCreateRenderPipeline(device, descriptor) {
    return addon.createRenderPipeline(
      assertLiveResource(device, 'GPUDevice.createRenderPipeline', 'GPUDevice'),
      {
        layout: descriptor.layout,
        vertex: {
          module: descriptor.vertexModule,
          entryPoint: descriptor.vertexEntryPoint,
          buffers: descriptor.vertexBuffers ?? [],
        },
        fragment: {
          module: descriptor.fragmentModule,
          entryPoint: descriptor.fragmentEntryPoint,
          targets: [{ format: descriptor.colorFormat }],
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
  deviceCreateCommandEncoder(device) {
    return new DoeGPUCommandEncoder(null, device);
  },
  deviceDestroy(native) {
    addon.deviceRelease(native);
  },
  adapterRequestDevice(adapter, _descriptor, classes) {
    assertLiveResource(adapter, 'GPUAdapter.requestDevice', 'GPUAdapter');
    const device = addon.requestDevice(adapter._instance, adapter._native);
    return new classes.DoeGPUDevice(device, adapter._instance, deviceLimits(device));
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
