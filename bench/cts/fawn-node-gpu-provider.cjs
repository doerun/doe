const { resolve } = require('path');
const { pathToFileURL } = require('url');

const RUNTIME_MODULE_URL = pathToFileURL(
  resolve(__dirname, '../../packages/doe-gpu/src/index.js')
).href;

let runtimeModulePromise;
let gpuPromise;

function loadRuntimeModule() {
  if (!runtimeModulePromise) {
    runtimeModulePromise = import(RUNTIME_MODULE_URL);
  }
  return runtimeModulePromise;
}

async function getGpu() {
  if (!gpuPromise) {
    gpuPromise = loadRuntimeModule().then(mod => mod.create());
  }
  return gpuPromise;
}

function createLazyGpuFacade() {
  return {
    async requestAdapter(options) {
      const gpu = await getGpu();
      return gpu.requestAdapter(options);
    },
  };
}

module.exports = {
  create() {
    return createLazyGpuFacade();
  },
};
