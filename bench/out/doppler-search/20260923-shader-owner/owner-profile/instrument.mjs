import assert from 'node:assert/strict';
import inspector from 'node:inspector';

export function instrument(device) {
  assert(device.features.has('timestamp-query'));
  const originalCreate = device.createCommandEncoder.bind(device);
  const pending = [];
  let active = false;
  const cpu = new inspector.Session();
  cpu.connect();
  const post = (method, params = {}) => new Promise((resolve, reject) =>
    cpu.post(method, params, (error, result) => error ? reject(error) : resolve(result)));
  device.createCommandEncoder = function (descriptor) {
    const encoder = originalCreate(descriptor);
    if (!active) return encoder;
    const count = 2048;
    const query = device.createQuerySet({ type: 'timestamp', count });
    const resolved = device.createBuffer({ size: count * 8, usage: GPUBufferUsage.QUERY_RESOLVE | GPUBufferUsage.COPY_SRC });
    const readback = device.createBuffer({ size: count * 8, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
    const record = { label: descriptor?.label, query, resolved, readback, passes: [] };
    const originalBegin = encoder.beginComputePass.bind(encoder);
    const originalFinish = encoder.finish.bind(encoder);
    encoder.beginComputePass = function (desc = {}) {
      assert(!desc.timestampWrites, 'Do not replace existing timestamp observations');
      let pipeline;
      const groups = new Map();
      let ended = false;
      function dispatch(method, args) {
        assert(!ended && pipeline);
        const index = record.passes.length * 2;
        assert(index + 1 < count);
        const passRecord = { label: desc.label, dispatches: [{ pipeline: pipeline.label,
          ...(method === 'dispatchWorkgroups' ? { workgroups: args } : { indirect: true }) }] };
        record.passes.push(passRecord);
        const pass = originalBegin({ ...desc, timestampWrites: {
          querySet: query, beginningOfPassWriteIndex: index, endOfPassWriteIndex: index + 1,
        } });
        pass.setPipeline(pipeline);
        for (const [slot, values] of groups) pass.setBindGroup(slot, ...values);
        pass[method](...args);
        pass.end();
      }
      return {
        setPipeline(value) { assert(!ended); pipeline = value; },
        setBindGroup(slot, value, ...offsetArgs) {
          assert(!ended);
          if (offsetArgs[0]) offsetArgs[0] = offsetArgs[0].slice();
          groups.set(slot, [value, ...offsetArgs]);
        },
        dispatchWorkgroups(...args) { dispatch('dispatchWorkgroups', args); },
        dispatchWorkgroupsIndirect(...args) { dispatch('dispatchWorkgroupsIndirect', args); },
        end() { assert(!ended); ended = true; },
      };
    };
    encoder.finish = function (...args) {
      const used = record.passes.length * 2;
      if (used) {
        encoder.resolveQuerySet(query, 0, used, resolved, 0);
        encoder.copyBufferToBuffer(resolved, 0, readback, 0, used * 8);
      }
      const command = originalFinish(...args);
      pending.push(record);
      return command;
    };
    return encoder;
  };
  return {
    async start() {

      active = true;
      this.cpuStart = process.cpuUsage();
    },
    async stop() {
      active = false;
      const usage = process.cpuUsage(this.cpuStart);
      const profile = null;
      const records = [];
      for (const item of pending.splice(0)) {
        const used = item.passes.length * 2;
        if (used) {
          await item.readback.mapAsync(GPUMapMode.READ, 0, used * 8);
          const values = new BigUint64Array(item.readback.getMappedRange(0, used * 8));
          records.push({ label: item.label, passes: item.passes.map((pass, index) => {
            const begin = values[index * 2], end = values[index * 2 + 1];
            assert(end >= begin && begin > 0n);
            return { ...pass, beginNs: String(begin), endNs: String(end), gpuMs: Number(end - begin) / 1e6 };
          }) });
          item.readback.unmap();
        }
        item.query.destroy(); item.resolved.destroy(); item.readback.destroy();
      }
      return { usage, records, profile };
    },
    close() { cpu.disconnect(); device.createCommandEncoder = originalCreate; },
  };
}
