// Scoped API observations; nested durations never become additive GPU timing.
export function observeDevicePhases(device, events, phase) {
  const instrument = (owner, method, detail = () => ({})) => {
    if (typeof owner[method] !== 'function') return;
    const original = owner[method].bind(owner);
    owner[method] = (...args) => {
      const start = performance.now();
      const scope = phase();
      const metadata = detail(args);
      const result = original(...args);
      if (result && typeof result.then === 'function') {
        return result.then((value) => {
          events.push({ phase: scope, method, startedMs: start, endedMs: performance.now(), durationMs: performance.now() - start, ...metadata });return value;
        }, (error) => {
          events.push({ phase: scope, method, startedMs: start, endedMs: performance.now(), durationMs: performance.now() - start, failure: error.message, ...metadata });throw error;
        });
      }
      events.push({ phase: scope, method, startedMs: start, endedMs: performance.now(), durationMs: performance.now() - start, ...metadata });
      return result;
    };
  };
  for (const method of ['createShaderModule', 'createComputePipeline', 'createComputePipelineAsync',
    'createBindGroup', 'createBindGroupLayout', 'createPipelineLayout', 'createCommandEncoder']) {
    instrument(device, method, ([descriptor]) => ({ label: descriptor?.label ?? '' }));
  }
  const createBuffer = device.createBuffer.bind(device);
  device.createBuffer = (descriptor) => {
    const start = performance.now();
    const buffer = createBuffer(descriptor);
    events.push({ phase: phase(), method: 'createBuffer', startedMs: start, endedMs: performance.now(), durationMs: performance.now() - start,
      bytes: descriptor.size, label: descriptor.label ?? '' });
    instrument(buffer, 'mapAsync', () => ({ label: buffer.label ?? '' }));
    instrument(buffer, 'getMappedRange', () => ({ label: buffer.label ?? '' }));
    return buffer;
  };
  for (const method of ['submit', 'onSubmittedWorkDone', 'writeBuffer']) instrument(device.queue, method);
}
