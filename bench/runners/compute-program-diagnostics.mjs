// Bounded, opt-in host diagnostics; no file writes during application measurement.
import { performance, PerformanceObserver } from 'node:perf_hooks';
import { setImmediate } from 'node:timers/promises';
import { writeFileSync } from 'node:fs';

const METHODS = Object.freeze({
  device: ['createCommandEncoder', 'createBuffer', 'pushErrorScope', 'popErrorScope'],
  encoder: ['clearBuffer', 'beginComputePass', 'resolveQuerySet', 'copyBufferToBuffer', 'finish'],
  pass: ['setPipeline', 'setBindGroup', 'dispatchWorkgroups', 'end'],
  queue: ['writeBuffer', 'submit', 'onSubmittedWorkDone'],
  buffer: ['mapAsync', 'getMappedRange', 'unmap'],
});
const EVENT_WIDTH = 5;
const INVOCATION_FIELDS = Object.freeze(['ordinal', 'invocationId', 'startMs', 'endMs',
  'heapUsedBefore', 'heapUsedAfter', 'voluntaryContextSwitches', 'involuntaryContextSwitches']);

export function createDiagnostics(device, maxEvents) {
  if (!Number.isSafeInteger(maxEvents) || maxEvents < 1) throw new Error('Invalid diagnostic event bound');
  const records = new Float64Array(maxEvents * EVENT_WIDTH);
  const names = ['gc', 'invocation'];
  const restores = [];
  const seen = new WeakSet();
  const invocations = [];
  let count = 0;
  let dropped = 0;
  let active = 0;
  let ordinal = 0;
  let started = 0;
  let beforeHeap = 0;
  let beforeUsage;

  function record(method, invocation, start, end, kind) {
    if (count === maxEvents) { dropped += 1; return; }
    const offset = count * EVENT_WIDTH;
    records[offset] = method;
    records[offset + 1] = invocation;
    records[offset + 2] = start;
    records[offset + 3] = end;
    records[offset + 4] = kind;
    count += 1;
  }

  function wrap(object, category) {
    const prototype = Object.getPrototypeOf(object);
    if (seen.has(prototype)) return;
    seen.add(prototype);
    for (const method of METHODS[category]) {
      const original = prototype[method];
      if (typeof original !== 'function') throw new Error(`Missing diagnostic method ${category}.${method}`);
      const id = names.push(`${category}.${method}`) - 1;
      const descriptor = Object.getOwnPropertyDescriptor(prototype, method);
      prototype[method] = function (...args) {
        const invocation = active;
        const start = performance.now();
        let result;
        try { result = Reflect.apply(original, this, args); }
        finally { if (invocation) record(id, invocation, start, performance.now(), 0); }
        if (method === 'createCommandEncoder') wrap(result, 'encoder');
        if (method === 'beginComputePass') wrap(result, 'pass');
        if (method === 'createBuffer') wrap(result, 'buffer');
        if (invocation && result instanceof Promise) {
          // Observe settlement without replacing the caller's promise.
          result.then(() => record(id, invocation, start, performance.now(), 1),
            () => record(id, invocation, start, performance.now(), 2));
        }
        return result;
      };
      restores.push(() => {
        if (descriptor) Object.defineProperty(prototype, method, descriptor);
        else delete prototype[method];
      });
    }
  }
  const observer = new PerformanceObserver((list) => {
    for (const event of list.getEntries()) {
      record(0, 0, event.startTime, event.startTime + event.duration, event.detail.kind);
    }
  });
  observer.observe({ entryTypes: ['gc'] });
  wrap(device, 'device');
  wrap(device.queue, 'queue');

  return {
    begin() {
      if (active) throw new Error('Diagnostic invocation overlaps its predecessor');
      active = ++ordinal;
      beforeHeap = process.memoryUsage().heapUsed;
      beforeUsage = process.resourceUsage();
      started = performance.now();
    },
    end(receipt) {
      const end = performance.now();
      record(1, active, started, end, 0);
      const afterUsage = process.resourceUsage();
      const invocation = { ordinal: active, invocationId: `${receipt.programInstance}:${receipt.run}`,
        startMs: started, endMs: end, heapUsedBefore: beforeHeap,
        heapUsedAfter: process.memoryUsage().heapUsed,
        voluntaryContextSwitches: afterUsage.voluntaryContextSwitches - beforeUsage.voluntaryContextSwitches,
        involuntaryContextSwitches: afterUsage.involuntaryContextSwitches - beforeUsage.involuntaryContextSwitches };
      if (invocations.length < maxEvents) invocations.push(invocation);
      else dropped += 1;
      active = 0;
    },
    async finish(path) {
      await setImmediate();
      await setImmediate();
      observer.disconnect();
      for (const restore of restores.reverse()) restore();
      const rows = ['event\tinvocationOrdinal\tstartMs\tendMs\tkind'];
      for (let i = 0; i < count; i += 1) {
        const offset = i * EVENT_WIDTH;
        rows.push([names[records[offset]], ...records.subarray(offset + 1, offset + EVENT_WIDTH)].join('\t'));
      }
      writeFileSync(`${path}.events.tsv`, `${rows.join('\n')}\n`);
      const fields = INVOCATION_FIELDS;
      writeFileSync(`${path}.invocations.tsv`, `${fields.join('\t')}\n${invocations.map((row) => fields.map((field) => row[field]).join('\t')).join('\n')}\n`);
      writeFileSync(`${path}.limits.txt`, `schemaVersion=1\nmaxEvents=${maxEvents}\ndroppedEvents=${dropped}\nHeap values are net live-heap observations, not allocation counts. GC intervals use the performance clock. Native allocations, reusable capacity, and lock waits are unmeasured. Method timing includes host, addon, and native work; async settlement rows overlap synchronous rows. Instrumented timings are diagnostic only.\n`);
      if (dropped) throw new Error(`Diagnostic buffer overflow: ${dropped} events dropped`);
    },
  };
}
