import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createDiagnostics } from '../runners/compute-program-diagnostics.mjs';

class Buffer {
  mapAsync() { return Promise.resolve(); }
  getMappedRange() { return new ArrayBuffer(0); }
  unmap() {}
}
class Pass {
  setPipeline() {}
  setBindGroup() {}
  dispatchWorkgroups() {}
  end() {}
}
class Encoder {
  clearBuffer() {}
  beginComputePass() { return new Pass(); }
  resolveQuerySet() {}
  copyBufferToBuffer() {}
  finish() { return {}; }
}
class Queue {
  writeBuffer() {}
  submit() {}
  onSubmittedWorkDone() { return this.completion; }
}
class Device {
  constructor() { this.queue = new Queue(); }
  createCommandEncoder() { return new Encoder(); }
  createBuffer() { return new Buffer(); }
  pushErrorScope() {}
  popErrorScope() { return Promise.resolve(null); }
}

const directory = mkdtempSync(join(tmpdir(), 'doe-program-diagnostics-'));
try {
  const device = new Device();
  const submit = Queue.prototype.submit;
  const diagnostics = createDiagnostics(device, 1000);
  const buffer = device.createBuffer();
  diagnostics.begin();
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  pass.dispatchWorkgroups();
  pass.end();
  device.queue.submit([encoder.finish()]);
  const failure = new Error('completion rejected');
  device.queue.completion = Promise.reject(failure);
  assert.equal(device.queue.onSubmittedWorkDone(), device.queue.completion);
  await assert.rejects(device.queue.completion, (error) => error === failure);
  await buffer.mapAsync();
  diagnostics.end({ programInstance: 'instance', run: 7 });
  const path = join(directory, 'run');
  await diagnostics.finish(path);
  assert.equal(Queue.prototype.submit, submit);
  assert.match(readFileSync(`${path}.invocations.tsv`, 'utf8'), /instance:7/);
  assert.match(readFileSync(`${path}.events.tsv`, 'utf8'), /queue.onSubmittedWorkDone\t1\t[^\n]+\t2/);
  assert.match(readFileSync(`${path}.events.tsv`, 'utf8'), /pass.dispatchWorkgroups\t1/);
  const bounded = createDiagnostics(device, 1);
  bounded.begin();
  device.queue.submit([]);
  device.queue.submit([]);
  bounded.end({ programInstance: 'instance', run: 8 });
  bounded.begin();
  bounded.end({ programInstance: 'instance', run: 9 });
  await assert.rejects(bounded.finish(join(directory, 'overflow')), /buffer overflow/);
  assert.equal(Queue.prototype.submit, submit);
  assert.doesNotMatch(readFileSync(join(directory, 'overflow.invocations.tsv'), 'utf8'), /instance:9/);
  const empty = createDiagnostics(device, 1);
  await empty.finish(join(directory, 'empty'));
  assert.equal(Queue.prototype.submit, submit);
  assert.match(readFileSync(join(directory, 'empty.invocations.tsv'), 'utf8'), /^ordinal\tinvocationId/);
  console.log('diagnostic identity, promise semantics, restoration, and overflow passed');
} finally {
  rmSync(directory, { recursive: true, force: true });
}
