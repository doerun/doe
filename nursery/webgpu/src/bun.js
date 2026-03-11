import * as ffi from "./bun-ffi.js";
import * as full from "./full.js";
import { createDoeNamespace } from "./doe.js";

const runtime = process.platform === "linux" ? ffi : full;

export const doe = createDoeNamespace({
  requestDevice: runtime.requestDevice,
});

export const create = runtime.create;
export const globals = runtime.globals;
export const setupGlobals = runtime.setupGlobals;
export const requestAdapter = runtime.requestAdapter;
export const requestDevice = runtime.requestDevice;
export const providerInfo = runtime.providerInfo;
export const createDoeRuntime = runtime.createDoeRuntime;
export const runDawnVsDoeCompare = runtime.runDawnVsDoeCompare;

export default {
  ...runtime,
  doe,
};
