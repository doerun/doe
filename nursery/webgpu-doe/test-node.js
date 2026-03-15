import assert from 'node:assert/strict';
import doe, { createDoeNamespace } from './src/index.js';

const DOE_GPU_BUFFER_USAGE = {
  MAP_READ: 0x0001,
  COPY_DST: 0x0008,
  UNIFORM: 0x0040,
  STORAGE: 0x0080,
};

function createFakeBuffer(descriptor) {
  const byte_length = descriptor.size;
  const buffer = {
    label: descriptor.label,
    size: descriptor.size,
    usage: descriptor.usage ?? 0,
    mappedAtCreation: descriptor.mappedAtCreation ?? false,
    destroyed: false,
    _data: new Uint8Array(byte_length),
    async mapAsync() {},
    getMappedRange(offset = 0, size = byte_length - offset) {
      return this._data.slice(offset, offset + size).buffer;
    },
    unmap() {},
    destroy() {
      this.destroyed = true;
    },
  };
  return buffer;
}

function createFakeDevice() {
  const state = {
    submitted: 0,
    writes: 0,
  };

  const device = {
    limits: {
      maxComputeWorkgroupsPerDimension: 65535,
      maxComputeWorkgroupSizeX: 256,
      maxComputeWorkgroupSizeY: 256,
      maxComputeWorkgroupSizeZ: 64,
      maxComputeInvocationsPerWorkgroup: 256,
    },
    queue: {
      writeBuffer(buffer, offset, view) {
        const bytes = view instanceof Uint8Array
          ? view
          : new Uint8Array(view.buffer, view.byteOffset, view.byteLength);
        buffer._data.set(bytes, offset);
        state.writes += 1;
      },
      submit(commands) {
        state.submitted += commands.length;
      },
      async onSubmittedWorkDone() {},
    },
    createBuffer(descriptor) {
      return createFakeBuffer(descriptor);
    },
    createShaderModule(descriptor) {
      return { code: descriptor.code };
    },
    createBindGroupLayout(descriptor) {
      return { entries: descriptor.entries };
    },
    createPipelineLayout(descriptor) {
      return { bindGroupLayouts: descriptor.bindGroupLayouts };
    },
    createComputePipeline(descriptor) {
      return {
        descriptor,
        getBindGroupLayout(index) {
          return descriptor.layout.bindGroupLayouts[index];
        },
      };
    },
    createBindGroup(descriptor) {
      return descriptor;
    },
    createCommandEncoder() {
      return {
        beginComputePass() {
          return {
            setPipeline() {},
            setBindGroup() {},
            dispatchWorkgroups() {},
            end() {},
          };
        },
        copyBufferToBuffer(source, source_offset, destination, destination_offset, size) {
          destination._data.set(
            source._data.slice(source_offset, source_offset + size),
            destination_offset,
          );
        },
        finish() {
          return {};
        },
      };
    },
    _state: state,
  };

  return device;
}

async function main() {
  await assert.rejects(
    () => doe.requestDevice(),
    /unavailable/,
  );

  const fake_device = createFakeDevice();
  const bound = doe.bind(fake_device);

  assert.equal(bound.device, fake_device);
  assert.equal(typeof bound.buffer.create, 'function');
  assert.equal(typeof bound.buffer.read, 'function');
  assert.equal(typeof bound.kernel.run, 'function');
  assert.equal(typeof bound.kernel.create, 'function');
  assert.equal(typeof bound.compute, 'function');

  const uploaded = bound.buffer.create({
    data: Float32Array.of(1, 2, 3, 4),
    usage: 'storageRead',
  });
  assert.equal(uploaded.size, 16);
  assert.equal(fake_device._state.writes, 1);

  const readable = bound.buffer.create({
    size: 16,
    usage: DOE_GPU_BUFFER_USAGE.MAP_READ | DOE_GPU_BUFFER_USAGE.COPY_DST,
  });
  readable._data.set(new Uint8Array(Float32Array.of(5, 6, 7, 8).buffer));

  const readback = await bound.buffer.read({
    buffer: readable,
    type: Float32Array,
  });
  assert.deepEqual(Array.from(readback), [5, 6, 7, 8]);

  const kernel = bound.kernel.create({
    code: `
      @group(0) @binding(0) var<storage, read> src: array<f32>;

      @compute @workgroup_size(1)
      fn main() {}
    `,
    bindings: [{ buffer: uploaded, access: 'storageRead' }],
    workgroups: 1,
  });

  await kernel.dispatch({
    bindings: [{ buffer: uploaded, access: 'storageRead' }],
    workgroups: 1,
  });

  assert.equal(fake_device._state.submitted, 1);

  const injected_namespace = createDoeNamespace({
    async requestDevice() {
      return fake_device;
    },
  });
  const requested = await injected_namespace.requestDevice();
  assert.equal(requested.device, fake_device);

  const uniform = bound.buffer.create({
    size: 16,
    usage: DOE_GPU_BUFFER_USAGE.UNIFORM | DOE_GPU_BUFFER_USAGE.COPY_DST,
  });
  assert.equal(uniform.size, 16);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
