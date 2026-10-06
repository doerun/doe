// Exercise the real provider with delayed retirement and terminal device loss.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const [providerPath, poolPath, schemaPath, nativePath, output] = process.argv.slice(2);
process.env.DOE_WEBGPU_LIB = nativePath;
const provider = await import(pathToFileURL(providerPath).href);
Object.assign(globalThis, provider.globals);
const { BufferPool, BufferUsage } = await import(pathToFileURL(poolPath).href);
const { DEFAULT_BUFFER_POOL_CONFIG } = await import(pathToFileURL(schemaPath).href);
const adapter = await provider.create(['backend=vulkan']).requestAdapter();
const device = await adapter.requestDevice();
const pool = new BufferPool(false, structuredClone(DEFAULT_BUFFER_POOL_CONFIG), device);
pool.configure({ enablePooling: false });
const first = pool.acquire(64, BufferUsage.STORAGE, 'completed-retirement');
const second = pool.acquire(64, BufferUsage.STORAGE, 'retirement-after-boundary');
const counts = [0, 0];
for (const [index, buffer] of [first, second].entries()) {
  const destroy = buffer.destroy.bind(buffer);
  buffer.destroy = () => { counts[index]++; destroy(); };
}
const originalWait = device.queue.onSubmittedWorkDone.bind(device.queue);
let waits = 0;
device.queue.onSubmittedWorkDone = () => { waits++; return originalWait(); };
device.queue.writeBuffer(first, 0, new Uint32Array([1, 2, 3, 4]));
pool.release(first);
device.queue.writeBuffer(second, 0, new Uint32Array([5, 6, 7, 8]));
pool.release(second);
await new Promise(resolve => setImmediate(resolve));
device.destroy();
await device.lost;
await new Promise(resolve => setImmediate(resolve));
pool.destroy();
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(counts, [1, 1]);
assert.equal(pool.getStats().resources.deferredCleanup.count, 0);
const hash = async p => createHash('sha256').update(await readFile(p)).digest('hex');
await writeFile(output, JSON.stringify({ schemaVersion: 1, passed: true,
  destructionCalls: counts, completionRequests: waits, resources: pool.getStats().resources,
  poolSha256: await hash(poolPath), nativeSha256: await hash(nativePath) }, null, 2) + '\n');
