// Scoped API observations; nested durations never become additive GPU timing.
export function observeDevicePhases(device, events, phase) {
  const instrument = (owner, method, detail = () => ({})) => {
    if (typeof owner[method] !== 'function') return;
    const original = owner[method].bind(owner);
    owner[method] = (...args) => {
      const start = performance.now();
      const scope = phase();
      const metadata = detail(args);
      const record = (failed = false, error) => {
        const end = performance.now();
        events.push({ phase: scope, method, startedMs: start, endedMs: end, durationMs: end - start,
          ...metadata, ...(failed ? { failure: error?.stack ?? String(error) } : {}) });
      };
      let result;
      try { result = original(...args); }
      catch (error) { record(true, error);throw error; }
      if (result && typeof result.then === 'function') {
        return result.then((value) => { record();return value; },
          (error) => { record(true, error);throw error; });
      }
      record();
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
    instrument(buffer, 'destroy', () => ({ bytes: descriptor.size, label: buffer.label ?? '' }));
    return buffer;
  };
  for (const method of ['submit', 'onSubmittedWorkDone', 'writeBuffer']) instrument(device.queue, method);
}
