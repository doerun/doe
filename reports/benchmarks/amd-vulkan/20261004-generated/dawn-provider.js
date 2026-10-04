import { create, globals } from '/home/x/deco/doe/bench/out/external-projects/umap-gpu/upstream/node_modules/webgpu/index.js';
export function setupGlobals() {
  for (const [name,value] of Object.entries(globals)) Object.defineProperty(globalThis,name,{value,writable:true,configurable:true});
  Object.defineProperty(globalThis,'navigator',{value:{gpu:create(['backend=vulkan'])},configurable:true});
}
export function providerInfo() { return {provider:'pinned-dawn',module:'/home/x/deco/doe/bench/out/external-projects/umap-gpu/upstream/node_modules/webgpu/index.js'}; }
