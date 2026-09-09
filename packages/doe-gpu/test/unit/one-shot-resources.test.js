import assert from 'node:assert/strict';
import { createDoeNamespace } from '../../src/vendor/doe-namespace.js';
import { initResource, releaseOwnedResource } from '../../src/vendor/webgpu/shared/resource-lifecycle.js';

const INPUT = new Float32Array([1, 2, 3, 4]);
const EXPECTED = [2, 4, 6, 8];
const WORKGROUP_LIMIT = 65535;

function fixture() {
  const state = { calls: 0, failAt: null, failReadbackEncoding: false, resources: [] };
  const failure = new Error('injected operation failure');
  function step() {
    state.calls += 1;
    if (state.calls === state.failAt) throw failure;
  }
  function resource(kind, fields = {}) {
    const value = { _native: {}, ...fields };
    initResource(value, kind, null, () => {
      assert.equal(value._destroyed, false, `duplicate release: ${kind}`);
    });
    value.destroy = () => releaseOwnedResource(value);
    state.resources.push(value);
    return value;
  }
  function live(value) {
    assert.equal(value._destroyed, false, `premature release: ${value._resourceLabel}`);
  }
  const device = {
    limits: { maxComputeWorkgroupsPerDimension: WORKGROUP_LIMIT },
    queue: {
      writeBuffer(buffer, offset, view) {
        step(); live(buffer);
        new Uint8Array(buffer.data).set(new Uint8Array(view.buffer, view.byteOffset, view.byteLength), offset);
      },
      submit(commands) {
        step();
        for (const command of commands) {
          live(command);
          for (const execute of command.operations) execute();
        }
      },
    },
    createBuffer(descriptor) {
      step();
      const buffer = resource('buffer', { ...descriptor, data: new ArrayBuffer(descriptor.size) });
      buffer.mapAsync = async () => { step(); live(buffer); };
      buffer.getMappedRange = () => { step(); live(buffer); return buffer.data; };
      buffer.unmap = () => { step(); live(buffer); };
      return buffer;
    },
    createShaderModule() { step(); return resource('shader'); },
    createComputePipeline({ compute }) {
      step(); live(compute.module);
      return resource('pipeline', {
        getBindGroupLayout() { step(); return resource('binding layout'); },
      });
    },
    createBindGroup({ entries, layout }) {
      step(); live(layout);
      return resource('binding group', { entries });
    },
    createCommandEncoder() {
      step();
      const operations = [];
      return {
        beginComputePass() {
          step();
          let group, pipeline;
          return {
            setPipeline(value) { step(); live(value); pipeline = value; },
            setBindGroup(_index, value) { step(); live(value); group = value; },
            dispatchWorkgroups() {
              step();
              operations.push(() => {
                live(group); live(pipeline);
                const [input, output] = group.entries.map(entry => entry.resource.buffer);
                live(input); live(output);
                const values = new Float32Array(input.data);
                new Float32Array(output.data).set(values.map(value => value * 2));
              });
            },
            end() { step(); },
          };
        },
        copyBufferToBuffer(source, offset, target, targetOffset, size) {
          step();
          if (state.failReadbackEncoding) {
            state.failReadbackEncoding = false;
            throw failure;
          }
          operations.push(() => {
            live(source); live(target);
            new Uint8Array(target.data, targetOffset, size).set(new Uint8Array(source.data, offset, size));
          });
        },
        finish() { step(); return resource('command buffer', { operations }); },
      };
    },
  };
  const gpu = createDoeNamespace({ requestDevice: async () => device }).bind(device);
  return { state, failure, device, gpu };
}

function options(inputs = [INPUT]) {
  return { code: 'fixed doubling fixture', inputs, output: { type: Float32Array, size: INPUT.byteLength }, workgroups: 1 };
}

const success = fixture();
assert.deepEqual(Array.from(await success.gpu.compute(options())), EXPECTED);
assert(success.state.resources.every(resource => resource._destroyed));
const operationCount = success.state.calls;
for (let failAt = 1; failAt <= operationCount; failAt += 1) {
  const { state, failure, gpu } = fixture();
  state.failAt = failAt;
  await assert.rejects(gpu.compute(options()), error => error === failure);
  assert(state.resources.every(resource => resource._destroyed), `unreleased resource after operation ${failAt}`);
  state.failAt = null;
  assert.deepEqual(Array.from(await gpu.compute(options())), EXPECTED);
  assert(state.resources.every(resource => resource._destroyed), `stale resource after recovery ${failAt}`);
}

for (const invalid of [
  { ...options(), inputs: [INPUT, null] },
  { ...options(), output: {} },
  { ...options(), workgroups: -1 },
]) {
  const { state, gpu } = fixture();
  await assert.rejects(gpu.compute(invalid));
  assert(state.resources.every(resource => resource._destroyed));
}

const borrowed = fixture();
const inputBuffer = borrowed.device.createBuffer({ size: INPUT.byteLength, usage: 0x88 });
borrowed.device.queue.writeBuffer(inputBuffer, 0, INPUT);
assert.deepEqual(Array.from(await borrowed.gpu.compute(options([{ buffer: inputBuffer, access: 'read' }]))), EXPECTED);
assert.equal(inputBuffer._destroyed, false);
assert(borrowed.state.resources.filter(resource => resource !== inputBuffer).every(resource => resource._destroyed));
inputBuffer.destroy();

const concurrent = fixture();
const doubledInput = INPUT.map(value => value * 2);
assert.deepEqual((await Promise.all([
  concurrent.gpu.compute(options()), concurrent.gpu.compute(options([doubledInput])),
])).map(value => Array.from(value)), [EXPECTED, EXPECTED.map(value => value * 2)]);
concurrent.state.failReadbackEncoding = true;
const outcomes = await Promise.allSettled([
  concurrent.gpu.compute(options()), concurrent.gpu.compute(options([doubledInput])),
]);
assert.equal(outcomes[0].status, 'rejected');
assert.equal(outcomes[0].reason, concurrent.failure);
assert.equal(outcomes[1].status, 'fulfilled');
assert.deepEqual(Array.from(outcomes[1].value), EXPECTED.map(value => value * 2));
assert(concurrent.state.resources.every(resource => resource._destroyed));
console.log('one-shot-resources.test: exact output, complete temporary release, injected failures, recovery, and borrowed input preservation');
