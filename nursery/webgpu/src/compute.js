import * as full from './index.js';
import { createDoeNamespace } from './doe.js';

function unwrap(value) {
  return value && typeof value === 'object' && '_raw' in value ? value._raw : value;
}

function wrap_buffer(raw) {
  return {
    _raw: raw,
    size: raw.size,
    usage: raw.usage,
    /**
     * Map the wrapped compute-surface buffer for host access.
     *
     * This forwards the mapping request to the underlying Doe buffer while
     * keeping the narrower compute facade shape.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * await buffer.mapAsync(GPUMapMode.READ);
     * ```
     *
     * - This forwards directly to the underlying Doe buffer.
     * - The compute facade keeps the same mapping semantics as the full surface.
     */
    async mapAsync(mode, offset, size) {
      return raw.mapAsync(mode, offset, size);
    },
    /**
     * Return the currently mapped byte range.
     *
     * This exposes the mapped bytes from the wrapped buffer without changing
     * the compute-only facade.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const bytes = buffer.getMappedRange();
     * ```
     *
     * - Call this only while the buffer is mapped.
     * - The returned bytes come from the wrapped full-surface buffer object.
     */
    getMappedRange(offset, size) {
      return raw.getMappedRange(offset, size);
    },
    /**
     * Compare a mapped `f32` prefix against expected values.
     *
     * This is a small validation helper that mirrors the underlying Doe buffer
     * behavior on the compute surface.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * buffer.assertMappedPrefixF32([1, 2, 3, 4], 4);
     * ```
     *
     * - The buffer must already be mapped.
     * - This helper is most useful in tests and smoke checks.
     */
    assertMappedPrefixF32(expected, count) {
      return raw.assertMappedPrefixF32(expected, count);
    },
    /**
     * Release the current mapping.
     *
     * This forwards unmapping to the wrapped buffer so the resource can return
     * to normal GPU ownership.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * buffer.unmap();
     * ```
     *
     * - This forwards directly to the wrapped Doe buffer.
     */
    unmap() {
      return raw.unmap();
    },
    /**
     * Release the wrapped native buffer.
     *
     * This tears down the underlying Doe buffer owned by this facade object.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * buffer.destroy();
     * ```
     *
     * - Reusing the buffer after destruction is unsupported.
     */
    destroy() {
      return raw.destroy();
    },
  };
}

function wrap_bind_group_layout(raw) {
  return { _raw: raw };
}

function wrap_bind_group(raw) {
  return { _raw: raw };
}

function wrap_pipeline_layout(raw) {
  return { _raw: raw };
}

function wrap_compute_pipeline(raw) {
  return {
    _raw: raw,
    /**
     * Return the bind-group layout for a given group index.
     *
     * This forwards layout lookup to the underlying compute pipeline and wraps
     * the result back into the compute facade.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const layout = pipeline.getBindGroupLayout(0);
     * ```
     *
     * - This forwards to the underlying full-surface compute pipeline.
     * - The returned layout is wrapped back into the compute facade.
     */
    getBindGroupLayout(index) {
      return wrap_bind_group_layout(raw.getBindGroupLayout(index));
    },
  };
}

function wrap_compute_pass(raw) {
  return {
    _raw: raw,
    /**
     * Set the compute pipeline used by later dispatch calls.
     *
     * This records the pipeline state that the wrapped compute pass should use
     * for subsequent dispatches.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * pass.setPipeline(pipeline);
     * ```
     *
     * - The pipeline must come from this compute facade or the same underlying device.
     */
    setPipeline(pipeline) {
      return raw.setPipeline(unwrap(pipeline));
    },
    /**
     * Bind a bind group for the compute pass.
     *
     * This records the resource bindings that the wrapped pass should expose to
     * the shader.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * pass.setBindGroup(0, bindGroup);
     * ```
     *
     * - The bind group is unwrapped before forwarding to the underlying pass.
     */
    setBindGroup(index, bindGroup) {
      return raw.setBindGroup(index, unwrap(bindGroup));
    },
    /**
     * Record a direct compute dispatch.
     *
     * This forwards an explicit workgroup dispatch to the wrapped pass encoder.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * pass.dispatchWorkgroups(4, 1, 1);
     * ```
     *
     * - Omitted `y` and `z` default to `1`.
     */
    dispatchWorkgroups(x, y = 1, z = 1) {
      return raw.dispatchWorkgroups(x, y, z);
    },
    /**
     * Dispatch workgroups using counts stored in a buffer.
     *
     * This forwards an indirect dispatch after unwrapping the buffer passed
     * through the compute facade.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * pass.dispatchWorkgroupsIndirect(indirectBuffer, 0);
     * ```
     *
     * - The indirect buffer is unwrapped before dispatch.
     */
    dispatchWorkgroupsIndirect(indirectBuffer, indirectOffset = 0) {
      return raw.dispatchWorkgroupsIndirect(unwrap(indirectBuffer), indirectOffset);
    },
    /**
     * Write a timestamp into a query set.
     *
     * This preserves the compute-facade API while forwarding timestamp writes
     * only when the underlying runtime supports them.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * pass.writeTimestamp(querySet, 0);
     * ```
     *
     * - This throws when the underlying runtime does not expose timestamp query writes.
     */
    writeTimestamp(querySet, queryIndex) {
      if (typeof raw.writeTimestamp !== 'function') {
        throw new Error('timestamp query writes are unsupported on the compute surface');
      }
      return raw.writeTimestamp(unwrap(querySet), queryIndex);
    },
    /**
     * Finish the compute pass.
     *
     * This closes the wrapped pass so the surrounding command encoder can be
     * finalized or continue recording.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * pass.end();
     * ```
     *
     * - This closes the wrapped pass but does not submit work by itself.
     */
    end() {
      return raw.end();
    },
  };
}

function wrap_command_encoder(raw) {
  return {
    _raw: raw,
    /**
     * Begin a compute pass on the compute facade.
     *
     * This creates a wrapped compute pass encoder that exposes only the
     * compute-surface contract.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const pass = encoder.beginComputePass();
     * ```
     *
     * - The returned pass is wrapped back into the compute facade.
     */
    beginComputePass(descriptor) {
      return wrap_compute_pass(raw.beginComputePass(descriptor));
    },
    /**
     * Record a buffer-to-buffer copy.
     *
     * This forwards the copy call after unwrapping the facade buffers to their
     * underlying Doe handles.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * encoder.copyBufferToBuffer(src, 0, dst, 0, src.size);
     * ```
     *
     * - Source and destination buffers are unwrapped before forwarding.
     */
    copyBufferToBuffer(source, sourceOffset, target, targetOffset, size) {
      return raw.copyBufferToBuffer(
        unwrap(source),
        sourceOffset,
        unwrap(target),
        targetOffset,
        size,
      );
    },
    /**
     * Resolve a query set into a destination buffer.
     *
     * This keeps the query-resolution API available on the facade only when
     * the underlying runtime exposes it.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * encoder.resolveQuerySet(querySet, 0, 1, dst, 0);
     * ```
     *
     * - This throws when query resolution is not supported by the underlying runtime.
     */
    resolveQuerySet(querySet, firstQuery, queryCount, destination, destinationOffset) {
      if (typeof raw.resolveQuerySet !== 'function') {
        throw new Error('query resolution is unsupported on the compute surface');
      }
      return raw.resolveQuerySet(
        unwrap(querySet),
        firstQuery,
        queryCount,
        unwrap(destination),
        destinationOffset,
      );
    },
    /**
     * Finish command recording and return a wrapped command buffer.
     *
     * This seals the wrapped encoder so the resulting command buffer can be
     * submitted through the compute-facade queue.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const commands = encoder.finish();
     * queue.submit([commands]);
     * ```
     *
     * - The command buffer is the same underlying object used by the full surface.
     */
    finish() {
      return raw.finish();
    },
  };
}

function wrap_queue(raw) {
  return {
    _raw: raw,
    /**
     * Submit command buffers to the queue.
     *
     * This unwraps the supplied command buffers and forwards them to the
     * underlying Doe queue.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * queue.submit([encoder.finish()]);
     * ```
     *
     * - Command buffers are unwrapped before forwarding.
     */
    submit(commandBuffers) {
      return raw.submit(commandBuffers.map(unwrap));
    },
    /**
     * Write host data into a GPU buffer.
     *
     * This forwards queue-side uploads after unwrapping the facade buffer.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * queue.writeBuffer(buffer, 0, new Float32Array([1, 2, 3, 4]));
     * ```
     *
     * - The wrapped buffer is unwrapped before forwarding to the underlying queue.
     */
    writeBuffer(buffer, bufferOffset, data, dataOffset, size) {
      return raw.writeBuffer(unwrap(buffer), bufferOffset, data, dataOffset, size);
    },
    /**
     * Resolve after submitted work has drained.
     *
     * This keeps the queue waiting API available on the facade while treating
     * missing runtime support as an immediate resolution.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * await queue.onSubmittedWorkDone();
     * ```
     *
     * - If the underlying queue does not expose this method, the facade resolves immediately.
     */
    async onSubmittedWorkDone() {
      if (typeof raw.onSubmittedWorkDone === 'function') {
        return raw.onSubmittedWorkDone();
      }
    },
  };
}

function wrap_query_set(raw) {
  return {
    _raw: raw,
    /**
     * Release the wrapped query set.
     *
     * This forwards destruction to the underlying query set handle returned by
     * the full-surface runtime.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * querySet.destroy();
     * ```
     *
     * - Reusing the query set after destruction is unsupported.
     */
    destroy() {
      return raw.destroy();
    },
  };
}

function wrap_device(raw) {
  return {
    _raw: raw,
    queue: wrap_queue(raw.queue),
    limits: raw.limits,
    features: raw.features,
    /**
     * Create a buffer on the compute-only device facade.
     *
     * This forwards buffer creation to Doe and wraps the result back into the
     * narrower compute-only surface.
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
     * - The returned buffer is wrapped back into the compute facade.
     */
    createBuffer(descriptor) {
      return wrap_buffer(raw.createBuffer(descriptor));
    },
    /**
     * Create a shader module from WGSL source.
     *
     * This preserves the same shader-module behavior as the full package while
     * keeping the compute-only device shape.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const shader = device.createShaderModule({ code: WGSL });
     * ```
     *
     * - This forwards directly to the underlying Doe device.
     */
    createShaderModule(descriptor) {
      return raw.createShaderModule(descriptor);
    },
    /**
     * Create a compute pipeline.
     *
     * This builds the underlying Doe pipeline and wraps it back into the
     * compute facade for later dispatch use.
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
     * - The returned pipeline is wrapped back into the compute facade.
     */
    createComputePipeline(descriptor) {
      const compute = descriptor.compute ?? {};
      return wrap_compute_pipeline(raw.createComputePipeline({
        ...descriptor,
        layout: descriptor.layout === 'auto' ? 'auto' : unwrap(descriptor.layout),
        compute: {
          ...compute,
          module: unwrap(compute.module),
        },
      }));
    },
    /**
     * Create a compute pipeline through an async-shaped API.
     *
     * This preserves the async WebGPU shape while returning the wrapped
     * compute-only pipeline object.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const pipeline = await device.createComputePipelineAsync(descriptor);
     * ```
     *
     * - The returned pipeline is wrapped back into the compute facade.
     */
    async createComputePipelineAsync(descriptor) {
      return wrap_compute_pipeline(await raw.createComputePipelineAsync(descriptor));
    },
    /**
     * Create a bind-group layout.
     *
     * This forwards layout creation to Doe and returns the wrapped layout used
     * by the compute facade.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const layout = device.createBindGroupLayout({ entries });
     * ```
     *
     * - The returned layout is wrapped for compute-surface use.
     */
    createBindGroupLayout(descriptor) {
      return wrap_bind_group_layout(raw.createBindGroupLayout(descriptor));
    },
    /**
     * Create a bind group.
     *
     * This unwraps facade resources and creates the bind group on the
     * underlying Doe device.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const bindGroup = device.createBindGroup({ layout, entries });
     * ```
     *
     * - Wrapped layouts and buffers are unwrapped before forwarding.
     */
    createBindGroup(descriptor) {
      const entries = (descriptor.entries ?? []).map((entry) => ({
        ...entry,
        resource: entry.resource && typeof entry.resource === 'object' && 'buffer' in entry.resource
          ? { ...entry.resource, buffer: unwrap(entry.resource.buffer) }
          : entry.resource,
      }));
      return wrap_bind_group(raw.createBindGroup({
        ...descriptor,
        layout: unwrap(descriptor.layout),
        entries,
      }));
    },
    /**
     * Create a pipeline layout.
     *
     * This combines wrapped bind-group layouts into a pipeline layout on the
     * underlying Doe device.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const layout = device.createPipelineLayout({ bindGroupLayouts: [group0] });
     * ```
     *
     * - Wrapped bind-group layouts are unwrapped before creation.
     */
    createPipelineLayout(descriptor) {
      return wrap_pipeline_layout(raw.createPipelineLayout({
        ...descriptor,
        bindGroupLayouts: (descriptor.bindGroupLayouts ?? []).map(unwrap),
      }));
    },
    /**
     * Create a command encoder.
     *
     * This returns the compute-facade wrapper around Doe's command encoder so
     * callers stay inside the narrower device contract.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const encoder = device.createCommandEncoder();
     * ```
     *
     * - The returned encoder is wrapped back into the compute facade.
     */
    createCommandEncoder(descriptor) {
      return wrap_command_encoder(raw.createCommandEncoder(descriptor));
    },
    /**
     * Create a query set.
     *
     * This forwards query-set creation when the underlying runtime supports it
     * and otherwise fails explicitly.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const querySet = device.createQuerySet({ type: "timestamp", count: 2 });
     * ```
     *
     * - This throws when query sets are unsupported by the underlying runtime.
     */
    createQuerySet(descriptor) {
      if (typeof raw.createQuerySet !== 'function') {
        throw new Error('query sets are unsupported on the compute surface');
      }
      return wrap_query_set(raw.createQuerySet(descriptor));
    },
    /**
     * Release the wrapped device.
     *
     * This tears down the underlying Doe device associated with the compute
     * facade wrapper.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * device.destroy();
     * ```
     *
     * - Reusing the device after destruction is unsupported.
     */
    destroy() {
      return raw.destroy();
    },
  };
}

function wrap_adapter(raw) {
  return {
    _raw: raw,
    features: raw.features,
    limits: raw.limits,
    /**
     * Request a compute-only device facade from this adapter.
     *
     * This asks the underlying adapter for a Doe device and then narrows it to
     * the compute-only JS surface.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const device = await adapter.requestDevice();
     * ```
     *
     * - The wrapped device intentionally omits render and surface APIs.
     */
    async requestDevice(descriptor) {
      return wrap_device(await raw.requestDevice(descriptor));
    },
    /**
     * Release the wrapped adapter.
     *
     * This tears down the underlying Doe adapter associated with this facade.
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
      return raw.destroy();
    },
  };
}

function wrap_gpu(raw) {
  return {
    _raw: raw,
    /**
     * Request a compute-only adapter facade.
     *
     * This asks the underlying GPU object for an adapter and wraps it into the
     * compute-surface contract.
     *
     * This example shows the API in its basic form.
     *
     * ```js
     * const adapter = await gpu.requestAdapter();
     * ```
     *
     * - The wrapped adapter later produces compute-only devices.
     */
    async requestAdapter(options) {
      return wrap_adapter(await raw.requestAdapter(options));
    },
  };
}

/**
 * Standard WebGPU enum objects for the compute package surface.
 *
 * This exposes the same package-local enum tables as the full surface so
 * compute-only consumers can build usage flags without browser globals.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { globals } from "@simulatte/webgpu/compute";
 *
 * const usage = globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST;
 * ```
 *
 * - The enum values are shared with the full package.
 * - The difference between package surfaces is the device facade, not the constants.
 */
export const globals = full.globals;

/**
 * Create a compute-only `GPU` facade backed by the Doe runtime.
 *
 * This wraps the full package GPU object and narrows the exposed adapter and
 * device methods to the compute-focused contract.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { create } from "@simulatte/webgpu/compute";
 *
 * const gpu = create();
 * const adapter = await gpu.requestAdapter();
 * ```
 *
 * - The underlying runtime is still Doe; this is a JS facade restriction, not a separate backend.
 * - The returned device intentionally omits render, sampler, and surface methods.
 */
export function create(createArgs = null) {
  return wrap_gpu(full.create(createArgs));
}

/**
 * Install compute-surface globals and `navigator.gpu` onto a target object.
 *
 * This adds missing enum globals and installs a compute-only GPU facade at
 * `target.navigator.gpu`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { setupGlobals } from "@simulatte/webgpu/compute";
 *
 * setupGlobals(globalThis);
 * const device = await navigator.gpu.requestAdapter().then((a) => a.requestDevice());
 * ```
 *
 * - Existing globals are preserved.
 * - The installed `navigator.gpu` still yields the compute-only facade, so render APIs remain intentionally absent.
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
 * Request a compute-surface adapter.
 *
 * This is a convenience wrapper over `create(...).requestAdapter(...)` for the
 * compute package surface.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { requestAdapter } from "@simulatte/webgpu/compute";
 *
 * const adapter = await requestAdapter();
 * ```
 *
 * - Returns `null` if no adapter is available.
 * - The adapter later produces a compute-only device facade.
 */
export async function requestAdapter(adapterOptions = undefined, createArgs = null) {
  return create(createArgs).requestAdapter(adapterOptions);
}

/**
 * Request a compute-only device facade from the Doe runtime.
 *
 * This requests an adapter, then wraps the resulting device so only the
 * compute-side JS surface is exposed.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { requestDevice } from "@simulatte/webgpu/compute";
 *
 * const device = await requestDevice();
 * console.log(typeof device.createRenderPipeline); // "undefined"
 * ```
 *
 * - The facade hides render, sampler, and surface methods even if the underlying runtime has them.
 * - Buffer and queue operations remain available for upload, dispatch, copy, and readback workflows.
 */
export async function requestDevice(options = {}) {
  const adapter = await requestAdapter(options?.adapterOptions, options?.createArgs ?? null);
  return adapter.requestDevice(options?.deviceDescriptor);
}

/**
 * Shared Doe namespace for the compute package surface.
 *
 * This exposes `await doe.requestDevice()` for the one-line Doe API entry,
 * `doe.bind(device)` when you already have a device, `doe.buffers.*` and
 * `doe.compute.run(...)` / `doe.compute.compile(...)` for the `Doe API`
 * surface, and `doe.compute.once(...)` for `Doe routines`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { doe } from "@simulatte/webgpu/compute";
 *
 * const gpu = await doe.requestDevice();
 * const src = gpu.buffers.fromData(new Float32Array([1, 2, 3, 4]));
 * const dst = gpu.buffers.like(src, { usage: "storageReadWrite" });
 * ```
 *
 * - This Doe API and Doe routines shape is shared with the full package surface; the difference is the raw device returned underneath.
 * - `gpu.compute.once(...)` is intentionally narrow and rejects raw numeric usage flags; drop to `gpu.buffers.*` if you need explicit raw control.
 */
export const doe = createDoeNamespace({
  requestDevice,
});

/**
 * Report how the compute package surface resolved the Doe runtime.
 *
 * This re-exports the same provenance report as the full package.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { providerInfo } from "@simulatte/webgpu/compute";
 *
 * console.log(providerInfo().loaded);
 * ```
 *
 * - The report describes the shared package/runtime load path, not the compute facade wrapper itself.
 */
export const providerInfo = full.providerInfo;
/**
 * Create a Node/Bun runtime wrapper for Doe CLI execution from the compute package.
 *
 * This re-exports the same runtime CLI helper as the full package for
 * benchmark and command-stream execution workflows.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { createDoeRuntime } from "@simulatte/webgpu/compute";
 *
 * const runtime = createDoeRuntime();
 * ```
 *
 * - This is package/runtime orchestration, not the in-process compute facade.
 */
export const createDoeRuntime = full.createDoeRuntime;
/**
 * Run the Dawn-vs-Doe compare harness from the compute package surface.
 *
 * This re-exports the compare wrapper used for artifact-backed benchmark runs.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { runDawnVsDoeCompare } from "@simulatte/webgpu/compute";
 *
 * const result = runDawnVsDoeCompare({ configPath: "bench/config.json" });
 * ```
 *
 * - Requires an explicit compare config path either in options or forwarded CLI args.
 * - This is a tooling entrypoint, not the in-process `doe.compute.*` helper path.
 */
export const runDawnVsDoeCompare = full.runDawnVsDoeCompare;

export default {
  create,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  createDoeRuntime,
  runDawnVsDoeCompare,
  doe,
};
