import { Worker } from 'node:worker_threads';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WORKER_PATH = resolve(__dirname, '../../examples/direct-webgpu/worker-compute.js');

let passed = 0, failed = 0;

function assert(condition, msg) {
  if (condition) { passed++; }
  else { failed++; console.error(`  FAIL: ${msg}`); }
}

function spawnWorker() {
  return new Worker(WORKER_PATH);
}

function dispatch(worker, data) {
  return new Promise((res, rej) => {
    worker.once('message', res);
    worker.once('error', rej);
    worker.postMessage({ data });
  });
}

// ---------------------------------------------------------------------------
// a. Single dispatch — verify ×2 transform
// ---------------------------------------------------------------------------

console.log('\n--- a. Single dispatch to worker thread ---');
{
  const worker = spawnWorker();
  try {
    const input = new Float32Array([1, 2, 3, 4]);
    const { result } = await dispatch(worker, input);
    const output = new Float32Array(result);
    assert(output[0] === 2, 'single dispatch: result[0] = 1*2 = 2');
    assert(output[1] === 4, 'single dispatch: result[1] = 2*2 = 4');
    assert(output[2] === 6, 'single dispatch: result[2] = 3*2 = 6');
    assert(output[3] === 8, 'single dispatch: result[3] = 4*2 = 8');
  } catch (err) {
    failed++;
    console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
  } finally {
    await worker.terminate();
  }
}

// ---------------------------------------------------------------------------
// b. Multiple sequential dispatches to same worker (device reuse)
// ---------------------------------------------------------------------------

console.log('\n--- b. Multiple sequential dispatches (device reuse) ---');
{
  const worker = spawnWorker();
  try {
    const inputs = [
      new Float32Array([10, 20, 30, 40]),
      new Float32Array([1, 1, 1, 1]),
      new Float32Array([0, 5, 10, 15]),
    ];
    const expected = [
      [20, 40, 60, 80],
      [2, 2, 2, 2],
      [0, 10, 20, 30],
    ];

    for (let i = 0; i < inputs.length; i++) {
      const { result } = await dispatch(worker, inputs[i]);
      const output = new Float32Array(result);
      const ok = expected[i].every((v, j) => output[j] === v);
      assert(ok, `sequential dispatch ${i + 1}: result = [${Array.from(output).slice(0, 4).join(', ')}]`);
    }
  } catch (err) {
    failed++;
    console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
  } finally {
    await worker.terminate();
  }
}

// ---------------------------------------------------------------------------
// c. Larger buffer — 1024 floats
// ---------------------------------------------------------------------------

console.log('\n--- c. Larger buffer (1024 floats) ---');
{
  const worker = spawnWorker();
  try {
    const COUNT = 1024;
    const input = Float32Array.from({ length: COUNT }, (_, i) => i);
    const { result } = await dispatch(worker, input);
    const output = new Float32Array(result);
    assert(output.length === COUNT, `large buffer: result length = ${COUNT}`);
    assert(output[0] === 0, 'large buffer: result[0] = 0*2 = 0');
    assert(output[1] === 2, 'large buffer: result[1] = 1*2 = 2');
    assert(output[COUNT - 1] === (COUNT - 1) * 2, `large buffer: result[${COUNT - 1}] = ${(COUNT - 1) * 2}`);
  } catch (err) {
    failed++;
    console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
  } finally {
    await worker.terminate();
  }
}

// ---------------------------------------------------------------------------
// d. Concurrent workers — two workers dispatching simultaneously
// ---------------------------------------------------------------------------

console.log('\n--- d. Concurrent workers ---');
{
  const w1 = spawnWorker();
  const w2 = spawnWorker();
  try {
    const input1 = new Float32Array([1, 2, 3, 4]);
    const input2 = new Float32Array([100, 200, 300, 400]);

    const [r1, r2] = await Promise.all([
      dispatch(w1, input1),
      dispatch(w2, input2),
    ]);

    const out1 = new Float32Array(r1.result);
    const out2 = new Float32Array(r2.result);

    assert(out1[0] === 2 && out1[3] === 8, `concurrent: worker1 result = [${Array.from(out1).join(', ')}]`);
    assert(out2[0] === 200 && out2[3] === 800, `concurrent: worker2 result = [${Array.from(out2).join(', ')}]`);
  } catch (err) {
    failed++;
    console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
  } finally {
    await Promise.all([w1.terminate(), w2.terminate()]);
  }
}

// ---------------------------------------------------------------------------
// e. Result is a transferable ArrayBuffer (not copied)
// ---------------------------------------------------------------------------

console.log('\n--- e. Result is transferable ArrayBuffer ---');
{
  const worker = spawnWorker();
  try {
    const input = new Float32Array([3, 6, 9]);
    const { result } = await dispatch(worker, input);
    assert(result instanceof ArrayBuffer, 'transferable: result is an ArrayBuffer');
    assert(result.byteLength === input.byteLength, `transferable: result.byteLength = ${result.byteLength}`);
    const output = new Float32Array(result);
    assert(output[0] === 6 && output[1] === 12 && output[2] === 18, 'transferable: values correct after wrapping');
  } catch (err) {
    failed++;
    console.error(`  FAIL (unexpected error): ${err?.message ?? err}`);
  } finally {
    await worker.terminate();
  }
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\nWorker thread: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
