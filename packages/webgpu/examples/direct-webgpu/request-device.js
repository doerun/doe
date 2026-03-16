import { requestDevice } from "@simulatte/webgpu";

const device = await requestDevice();

console.log(JSON.stringify({
  createBuffer: typeof device.createBuffer === "function",
  createComputePipeline: typeof device.createComputePipeline === "function",
  createRenderPipeline: typeof device.createRenderPipeline === "function",
  writeBuffer: typeof device.queue?.writeBuffer === "function",
}));
