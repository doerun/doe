import { parentPort, workerData } from "node:worker_threads";

const { inputBuffer, start, end, rounds } = workerData;

const input = new Float32Array(inputBuffer);
const output = new Float32Array(end - start);

for (let i = start; i < end; i += 1) {
  let a = Math.fround(input[i]);
  let b = Math.fround(input[i] + 1);
  let c = Math.fround(input[i] + 2);
  let d = Math.fround(input[i] + 3);

  for (let round = 0; round < rounds; round += 1) {
    a = Math.fround(Math.fround(a * 2) + 1);
    b = Math.fround(Math.fround(b * 2) + 1);
    c = Math.fround(Math.fround(c * 2) + 1);
    d = Math.fround(Math.fround(d * 2) + 1);
  }

  output[i - start] = Math.fround(Math.fround(a + b) + Math.fround(c + d));
}

parentPort.postMessage(
  {
    start,
    end,
    outputBuffer: output.buffer,
  },
  [output.buffer]
);
