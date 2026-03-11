const DOE_GPU_BUFFER_USAGE = {
  MAP_READ: 0x0001,
  COPY_SRC: 0x0004,
  COPY_DST: 0x0008,
  UNIFORM: 0x0040,
  STORAGE: 0x0080,
};

const DOE_GPU_SHADER_STAGE = {
  COMPUTE: 0x4,
};

const DOE_GPU_MAP_MODE = {
  READ: 0x0001,
};

const DOE_BUFFER_META = new WeakMap();

function resolveBufferUsageToken(token, combined = false) {
  switch (token) {
    case 'upload':
      return DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'readback':
      return combined
        ? DOE_GPU_BUFFER_USAGE.COPY_SRC
        : DOE_GPU_BUFFER_USAGE.COPY_SRC | DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.MAP_READ;
    case 'uniform':
      return DOE_GPU_BUFFER_USAGE.UNIFORM | DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'storageRead':
      return DOE_GPU_BUFFER_USAGE.STORAGE | DOE_GPU_BUFFER_USAGE.COPY_DST;
    case 'storageReadWrite':
      return DOE_GPU_BUFFER_USAGE.STORAGE | DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.COPY_SRC;
    default:
      throw new Error(`Unknown Doe buffer usage token: ${token}`);
  }
}

function resolveBufferUsage(usage) {
  if (typeof usage === 'number') return usage;
  if (typeof usage === 'string') return resolveBufferUsageToken(usage);
  if (Array.isArray(usage)) {
    const combined = usage.length > 1;
    return usage.reduce((mask, token) => mask | resolveBufferUsageToken(token, combined), 0);
  }
  throw new Error('Doe buffer usage must be a number, string, or string array.');
}

function inferBindingAccessToken(token) {
  switch (token) {
    case 'uniform':
      return 'uniform';
    case 'storageRead':
      return 'storageRead';
    case 'storageReadWrite':
      return 'storageReadWrite';
    default:
      return null;
  }
}

function inferBindingAccess(usage) {
  if (typeof usage === 'number' || usage == null) return null;
  const tokens = typeof usage === 'string'
    ? [usage]
    : Array.isArray(usage)
      ? usage
      : null;
  if (!tokens) {
    throw new Error('Doe buffer usage must be a number, string, or string array.');
  }
  const inferred = [...new Set(tokens.map(inferBindingAccessToken).filter(Boolean))];
  if (inferred.length > 1) {
    throw new Error(`Doe buffer usage cannot imply multiple binding access modes: ${inferred.join(', ')}`);
  }
  return inferred[0] ?? null;
}

function rememberBufferUsage(buffer, usage) {
  DOE_BUFFER_META.set(buffer, {
    binding_access: inferBindingAccess(usage),
  });
  return buffer;
}

function inferredBindingAccessForBuffer(buffer) {
  return DOE_BUFFER_META.get(buffer)?.binding_access ?? null;
}

function normalizeWorkgroups(workgroups) {
  if (typeof workgroups === 'number') {
    return [workgroups, 1, 1];
  }
  if (Array.isArray(workgroups) && workgroups.length === 2) {
    return [workgroups[0], workgroups[1], 1];
  }
  if (Array.isArray(workgroups) && workgroups.length === 3) {
    return workgroups;
  }
  throw new Error('Doe workgroups must be a number, [x, y], or [x, y, z].');
}

function normalizeDataView(data) {
  if (ArrayBuffer.isView(data)) {
    return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  }
  if (data instanceof ArrayBuffer) {
    return new Uint8Array(data);
  }
  throw new Error('Doe buffer data must be an ArrayBuffer or ArrayBufferView.');
}

function resolveBufferSize(source) {
  if (source && typeof source === 'object' && typeof source.size === 'number') {
    return source.size;
  }
  if (ArrayBuffer.isView(source)) {
    return source.byteLength;
  }
  if (source instanceof ArrayBuffer) {
    return source.byteLength;
  }
  throw new Error('Doe buffer-like source must expose a byte size or be ArrayBuffer-backed data.');
}

function normalizeBinding(binding, index) {
  const entry = binding && typeof binding === 'object' && 'buffer' in binding
    ? binding
    : { buffer: binding };
  const access = entry.access ?? inferredBindingAccessForBuffer(entry.buffer);
  if (!access) {
    throw new Error(
      'Doe binding access is required for buffers without Doe helper usage metadata. ' +
      'Pass { buffer, access } or create the buffer through doe.buffers.* with a bindable usage token.'
    );
  }
  return {
    binding: index,
    buffer: entry.buffer,
    access,
  };
}

function bindGroupLayoutEntry(binding) {
  const buffer_type = binding.access === 'uniform'
    ? 'uniform'
    : binding.access === 'storageRead'
      ? 'read-only-storage'
      : 'storage';
  return {
    binding: binding.binding,
    visibility: DOE_GPU_SHADER_STAGE.COMPUTE,
    buffer: { type: buffer_type },
  };
}

function bindGroupEntry(binding) {
  return {
    binding: binding.binding,
    resource: { buffer: binding.buffer },
  };
}

/**
 * Reusable compute kernel returned by `doe.compute.compile(...)`.
 *
 * This keeps the compiled pipeline and bind-group layout needed for repeated
 * dispatches of the same WGSL shape.
 *
 * - Instances are returned through the `Doe API` surface rather than exported directly.
 * - Dispatches still require bindings and workgroup counts for each run.
 */
class DoeKernel {
  constructor(device, pipeline, layout, entryPoint) {
    this.device = device;
    this.pipeline = pipeline;
    this.layout = layout;
    this.entryPoint = entryPoint;
  }

  /**
   * Dispatch the compiled kernel once.
   *
   * - `workgroups` may be `number`, `[x, y]`, or `[x, y, z]`.
   * - Bare buffers without Doe helper metadata still require `{ buffer, access }`.
   */
  async dispatch(options) {
    const bindings = (options.bindings ?? []).map(normalizeBinding);
    const workgroups = normalizeWorkgroups(options.workgroups);
    const bindGroup = this.device.createBindGroup({
      label: options.label ?? undefined,
      layout: this.layout,
      entries: bindings.map(bindGroupEntry),
    });
    const encoder = this.device.createCommandEncoder({ label: options.label ?? undefined });
    const pass = encoder.beginComputePass({ label: options.label ?? undefined });
    pass.setPipeline(this.pipeline);
    if (bindings.length > 0) {
      pass.setBindGroup(0, bindGroup);
    }
    pass.dispatchWorkgroups(workgroups[0], workgroups[1], workgroups[2]);
    pass.end();
    this.device.queue.submit([encoder.finish()]);
    if (typeof this.device.queue.onSubmittedWorkDone === 'function') {
      await this.device.queue.onSubmittedWorkDone();
    }
  }
}

function compileCompute(device, options) {
  const bindings = (options.bindings ?? []).map(normalizeBinding);
  const shader = device.createShaderModule({ code: options.code });
  const bindGroupLayout = device.createBindGroupLayout({
    entries: bindings.map(bindGroupLayoutEntry),
  });
  const pipelineLayout = device.createPipelineLayout({
    bindGroupLayouts: [bindGroupLayout],
  });
  const pipeline = device.createComputePipeline({
    layout: pipelineLayout,
    compute: {
      module: shader,
      entryPoint: options.entryPoint ?? 'main',
    },
  });
  return new DoeKernel(device, pipeline, bindGroupLayout, options.entryPoint ?? 'main');
}

function createBuffer(device, options) {
  return rememberBufferUsage(device.createBuffer({
    label: options.label ?? undefined,
    size: options.size,
    usage: resolveBufferUsage(options.usage),
    mappedAtCreation: options.mappedAtCreation ?? false,
  }), options.usage);
}

function createBufferFromData(device, data, options = {}) {
  const view = normalizeDataView(data);
  const usage = options.usage ?? 'storageRead';
  const buffer = rememberBufferUsage(device.createBuffer({
    label: options.label ?? undefined,
    size: view.byteLength,
    usage: resolveBufferUsage(usage),
  }), usage);
  device.queue.writeBuffer(buffer, 0, view);
  return buffer;
}

function createBufferLike(device, source, options = {}) {
  return createBuffer(device, {
    ...options,
    size: options.size ?? resolveBufferSize(source),
  });
}

async function readBuffer(device, buffer, type, options = {}) {
  const offset = options.offset ?? 0;
  const size = options.size ?? Math.max(0, (buffer.size ?? 0) - offset);
  if (((buffer.usage ?? 0) & DOE_GPU_BUFFER_USAGE.MAP_READ) !== 0) {
    await buffer.mapAsync(DOE_GPU_MAP_MODE.READ, offset, size);
    const copy = buffer.getMappedRange(offset, size).slice(0);
    buffer.unmap();
    return new type(copy);
  }
  const staging = device.createBuffer({
    label: options.label ?? undefined,
    size,
    usage: DOE_GPU_BUFFER_USAGE.COPY_DST | DOE_GPU_BUFFER_USAGE.MAP_READ,
  });
  const encoder = device.createCommandEncoder({ label: options.label ?? undefined });
  encoder.copyBufferToBuffer(buffer, offset, staging, 0, size);
  device.queue.submit([encoder.finish()]);
  await staging.mapAsync(DOE_GPU_MAP_MODE.READ);
  const copy = staging.getMappedRange().slice(0);
  staging.unmap();
  if (typeof staging.destroy === 'function') {
    staging.destroy();
  }
  return new type(copy);
}

async function runCompute(device, options) {
  const kernel = compileCompute(device, options);
  await kernel.dispatch({
    bindings: options.bindings ?? [],
    workgroups: options.workgroups,
    label: options.label,
  });
}

function assertLayer3Usage(usage, path) {
  if (typeof usage === 'number') {
    throw new Error(`Doe ${path} does not accept raw numeric usage flags. Use Doe usage tokens on compute.once(...) or drop to gpu.buffers.*.`);
  }
  if (Array.isArray(usage) && usage.some((token) => typeof token === 'number')) {
    throw new Error(`Doe ${path} does not accept raw numeric usage flags. Use Doe usage tokens on compute.once(...) or drop to gpu.buffers.*.`);
  }
}

function normalizeOnceInput(device, input, index) {
  if (ArrayBuffer.isView(input) || input instanceof ArrayBuffer) {
    const buffer = createBufferFromData(device, input, {});
    return {
      binding: buffer,
      buffer,
      byte_length: resolveBufferSize(input),
      owned: true,
    };
  }

  if (input && typeof input === 'object' && 'data' in input) {
    assertLayer3Usage(input.usage, `compute.once input ${index} usage`);
    const buffer = createBufferFromData(device, input.data, {
      usage: input.usage ?? 'storageRead',
      label: input.label,
    });
    return {
      binding: input.access ? { buffer, access: input.access } : buffer,
      buffer,
      byte_length: resolveBufferSize(input.data),
      owned: true,
    };
  }

  if (input && typeof input === 'object' && 'buffer' in input) {
    return {
      binding: input,
      buffer: input.buffer,
      byte_length: resolveBufferSize(input.buffer),
      owned: false,
    };
  }

  if (input && typeof input === 'object' && typeof input.size === 'number') {
    return {
      binding: input,
      buffer: input,
      byte_length: input.size,
      owned: false,
    };
  }

  throw new Error(`Doe compute.once input ${index} must be data, a Doe input spec, or a buffer.`);
}

function normalizeOnceOutput(device, output, inputs) {
  if (!output || typeof output !== 'object') {
    throw new Error('Doe compute.once output is required.');
  }
  if (typeof output.type !== 'function') {
    throw new Error('Doe compute.once output.type must be a typed-array constructor.');
  }

  const fallback_input_index = inputs.length > 0 ? 0 : null;
  const like_input_index = output.likeInput ?? fallback_input_index;
  const size = output.size ?? (
    like_input_index != null && inputs[like_input_index]
      ? inputs[like_input_index].byte_length
      : null
  );

  if (!(size > 0)) {
    throw new Error('Doe compute.once output size must be provided or derived from likeInput.');
  }

  assertLayer3Usage(output.usage, 'compute.once output usage');
  const buffer = createBuffer(device, {
    size,
    usage: output.usage ?? 'storageReadWrite',
    label: output.label,
  });
  return {
    binding: output.access ? { buffer, access: output.access } : buffer,
    buffer,
    type: output.type,
    read_options: output.read ?? {},
  };
}

async function computeOnce(device, options) {
  const inputs = (options.inputs ?? []).map((input, index) => normalizeOnceInput(device, input, index));
  const output = normalizeOnceOutput(device, options.output, inputs);
  try {
    await runCompute(device, {
      code: options.code,
      entryPoint: options.entryPoint,
      bindings: [...inputs.map((input) => input.binding), output.binding],
      workgroups: options.workgroups,
      label: options.label,
    });
    return await readBuffer(device, output.buffer, output.type, output.read_options);
  } finally {
    if (typeof output.buffer.destroy === 'function') {
      output.buffer.destroy();
    }
    for (const input of inputs) {
      if (input.owned && typeof input.buffer.destroy === 'function') {
        input.buffer.destroy();
      }
    }
  }
}

function createBoundDoe(device) {
  return {
    device,
    buffers: {
      /**
       * Create a buffer with explicit size and Doe usage tokens.
       *
       * This is part of the `Doe API` surface over `device.createBuffer(...)`.
       * It accepts Doe usage tokens and remembers bindability metadata for
       * later Doe API calls.
       *
       * - Raw numeric usage flags are allowed here for explicit control.
       * - If you later pass a raw-usage buffer to `compute.run(...)`, you may still need `{ buffer, access }` because Doe can only infer access from Doe usage tokens, not arbitrary bitmasks.
       */
      create(options) {
        return createBuffer(device, options);
      },
      /**
       * Create a buffer from typed-array or ArrayBuffer data and upload it immediately.
       *
       * This allocates a buffer, writes the provided data into it, and
       * remembers Doe usage metadata for later helper inference.
       *
       * - Defaults to `storageRead` usage when none is provided.
       * - Raw numeric usage flags are allowed, but that may disable later access inference if the bitmask does not map cleanly to one Doe access mode.
       */
      fromData(data, options = {}) {
        return createBufferFromData(device, data, options);
      },
      /**
       * Create a buffer whose size is derived from another buffer or typed-array source.
       *
       * This copies the byte size from `source` unless an explicit
       * `options.size` is provided, which removes common `size: src.size`
       * boilerplate.
       *
       * - `source` may be a Doe buffer, a raw buffer exposing `.size`, a typed array, or an `ArrayBuffer`.
       * - If the source has no byte size, this throws instead of guessing.
       */
      like(source, options = {}) {
        return createBufferLike(device, source, options);
      },
      /**
       * Read a buffer back into a typed array.
       *
       * This copies the source buffer into a staging buffer, maps it for read,
       * and returns a new typed array instance created from the copied bytes.
       *
       * - `options.offset` and `options.size` let you read a subrange.
       * - The returned typed array constructor must accept a plain `ArrayBuffer`.
       */
      read(buffer, type, options = {}) {
        return readBuffer(device, buffer, type, options);
      },
    },
    compute: {
      /**
       * Compile and dispatch a one-off compute job.
       *
       * This builds a compute pipeline for the provided WGSL, dispatches it
       * once with the supplied bindings and workgroups, and waits for submitted
       * work to finish as part of the explicit `Doe API` surface.
       *
       * - `workgroups` may be `number`, `[x, y]`, or `[x, y, z]`.
       * - Bare buffers without Doe helper metadata require `{ buffer, access }`.
       * - This recompiles per call; use `compute.compile(...)` when reusing the kernel.
       */
      run(options) {
        return runCompute(device, options);
      },
      /**
       * Compile a reusable compute kernel.
       *
       * This creates the shader, bind-group layout, and compute pipeline once
       * and returns a kernel object with `.dispatch(...)`.
       *
       * - Binding access is inferred from the bindings passed at compile time.
       * - Reuse this path when you are dispatching the same WGSL shape repeatedly.
       */
      compile(options) {
        return compileCompute(device, options);
      },
      /**
       * Run a narrow Doe routines typed-array workflow.
       *
       * This is the first `Doe routines` path. It accepts typed-array or Doe input specs, allocates temporary
       * buffers, dispatches the compute job once, reads the output back, and
       * returns the requested typed array result.
       *
       * - This is intentionally opinionated: it rejects raw numeric WebGPU usage flags and expects Doe usage tokens when usage is specified.
       * - Output size defaults from `likeInput` or the first input when possible; if no size can be derived, it throws instead of guessing.
       * - Temporary buffers created internally are destroyed before the call returns.
       */
      once(options) {
        return computeOnce(device, options);
      },
    },
  };
}

/**
 * Build the shared Doe namespace for a package surface.
 *
 * This creates the public `doe` object used by both `@simulatte/webgpu` and
 * `@simulatte/webgpu/compute` for the `Doe API` and `Doe routines` surface.
 *
 * - If no `requestDevice` implementation is supplied, `doe.requestDevice()` throws, but `doe.bind(device)` and the static helper groups still work.
 * - Both package surfaces share this helper shape; only the underlying raw device contract differs.
 */
export function createDoeNamespace({ requestDevice } = {}) {
  return {
    /**
     * Request a device and return the bound Doe helper object in one step.
     *
     * This calls the package-local `requestDevice(...)` implementation, then
     * wraps the resulting device into the `Doe API` surface.
     *
     * - Throws if this Doe namespace was created without a `requestDevice` implementation.
     * - The returned `gpu.device` is full-surface or compute-only depending on which package created the namespace.
     */
    async requestDevice(options = {}) {
      if (typeof requestDevice !== 'function') {
        throw new Error('Doe requestDevice() is unavailable in this context.');
      }
      return createBoundDoe(await requestDevice(options));
    },

    /**
     * Wrap an existing device in the Doe API surface.
     *
     * This turns a previously requested device into the same bound helper
     * object returned by `await doe.requestDevice()`.
     *
     * - Use this when you need the raw device first for non-helper setup.
     * - No async work happens here; it only wraps the device you already have.
     */
    bind(device) {
      return createBoundDoe(device);
    },

    buffers: {
      /**
       * Static Doe API buffer creation call for an explicit device.
       *
       * This lets callers use the Doe API buffer surface without first binding
       * a device into a `gpu` helper object.
       *
       * - This is the unbound form of `gpu.buffers.create(...)`.
       */
      create(device, options) {
        return createBuffer(device, options);
      },
      /**
       * Static data-upload helper for an explicit device.
       *
       * This provides the unbound form of the same upload flow exposed on
       * `gpu.buffers.fromData(...)`.
       *
       * - This is the unbound form of `gpu.buffers.fromData(...)`.
       */
      fromData(device, data, options = {}) {
        return createBufferFromData(device, data, options);
      },
      /**
       * Static size-copy helper for an explicit device.
       *
       * This keeps the `createBufferLike` convenience available when callers
       * are working with a raw device rather than a bound helper object.
       *
       * - This is the unbound form of `gpu.buffers.like(...)`.
       */
      like(device, source, options = {}) {
        return createBufferLike(device, source, options);
      },
      /**
       * Static readback helper for an explicit device.
       *
       * This exposes the same staging-copy readback path as
       * `gpu.buffers.read(...)` without requiring a bound helper.
       *
       * - This is the unbound form of `gpu.buffers.read(...)`.
       */
      read(device, buffer, type, options = {}) {
        return readBuffer(device, buffer, type, options);
      },
    },

    compute: {
      /**
       * Static compute dispatch helper for an explicit device.
       *
       * This gives raw-device callers the same one-off compute dispatch helper
       * that bound helpers expose on `gpu.compute.run(...)`.
       *
       * - This is the unbound form of `gpu.compute.run(...)`.
       */
      run(device, options) {
        return runCompute(device, options);
      },
      /**
       * Static reusable-kernel compiler for an explicit device.
       *
       * This exposes the reusable kernel path without requiring a previously
       * bound `gpu` helper object.
       *
       * - This is the unbound form of `gpu.compute.compile(...)`.
       */
      compile(device, options) {
        return compileCompute(device, options);
      },
      /**
       * Static Doe routines typed-array compute call for an explicit device.
       *
       * This keeps the narrow `Doe routines` `compute.once(...)` workflow available to
       * callers that are still holding a raw device.
       *
       * - This is the unbound form of `gpu.compute.once(...)`.
       */
      once(device, options) {
        return computeOnce(device, options);
      },
    },
  };
}

/**
 * Unbound Doe namespace without a package-local `requestDevice(...)`.
 *
 * This export is primarily for internal composition and advanced consumers who
 * want the shared Doe API and Doe routines groups without choosing the full or compute package entry.
 *
 * - `doe.requestDevice()` throws here because no package-local request function is attached.
 * - Most package consumers should prefer the `doe` export from `@simulatte/webgpu` or `@simulatte/webgpu/compute`.
 */
export const doe = createDoeNamespace();

export default doe;
