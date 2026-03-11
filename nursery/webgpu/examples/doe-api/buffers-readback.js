import { doe } from "@simulatte/webgpu/compute";

const gpu = await doe.requestDevice();
const src = gpu.buffers.fromData(new Float32Array([1, 2, 3, 4]), {
  usage: ["storageRead", "readback"],
});

const result = await gpu.buffers.read(src, Float32Array);
console.log(JSON.stringify(Array.from(result)));
