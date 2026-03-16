import { parentPort, workerData } from "node:worker_threads";

const { leftBuffer, rightBuffer, size, startRow, endRow } = workerData;

const left = new Float32Array(leftBuffer);
const right = new Float32Array(rightBuffer);
const output = new Float32Array((endRow - startRow) * size);

for (let row = startRow; row < endRow; row += 1) {
  for (let col = 0; col < size; col += 1) {
    let sum = 0;
    for (let k = 0; k < size; k += 1) {
      const product = Math.fround(left[row * size + k] * right[k * size + col]);
      sum = Math.fround(sum + product);
    }
    output[(row - startRow) * size + col] = sum;
  }
}

parentPort.postMessage(
  {
    startRow,
    endRow,
    outputBuffer: output.buffer,
  },
  [output.buffer]
);
