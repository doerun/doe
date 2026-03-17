// spawn-compute-worker.js — Dispatch WebGPU compute to a Node.js worker thread.
//
// Spawns worker-compute.js, sends a 256-element input, and reads the result
// back via postMessage. The worker keeps the GPU device alive across messages;
// dispatch multiple jobs before terminating to amortize init cost.
import { Worker } from 'node:worker_threads';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const worker = new Worker(resolve(__dirname, 'worker-compute.js'));

function dispatch(data) {
  return new Promise((res, rej) => {
    worker.once('message', res);
    worker.once('error', rej);
    worker.postMessage({ data });
  });
}

const COUNT = 256;
const input = Float32Array.from({ length: COUNT }, (_, i) => i);

const { result } = await dispatch(input);
const output = new Float32Array(result);

console.log('input[0..3] :', Array.from(input.slice(0, 4)));
console.log('result[0..3]:', Array.from(output.slice(0, 4)));
// expected: [0, 2, 4, 6]

await worker.terminate();
