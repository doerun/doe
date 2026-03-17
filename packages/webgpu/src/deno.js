// Deno entry point for @simulatte/webgpu.
//
// Deno's Node compatibility layer supports createRequire and N-API addons,
// so this entry point re-exports the full Node surface through index.js.
// If a Deno-native FFI path is needed in the future, it can be added here
// without changing the public export shape.

import * as full from './index.js';
// Use relative path for Deno compatibility; bare specifier @simulatte/webgpu-doe
// requires Node-style node_modules resolution that Deno does not support without
// explicit import maps. This relative path resolves via the monorepo symlink in
// development and works as a direct path for all Deno contexts.
import { createDoeNamespace } from '../../webgpu-doe/src/index.js';

export const doe = createDoeNamespace({
  requestDevice: full.requestDevice,
});

export const create = full.create;
export const globals = full.globals;
export const setupGlobals = full.setupGlobals;
export const requestAdapter = full.requestAdapter;
export const requestDevice = full.requestDevice;
export const providerInfo = full.providerInfo;
export const preflightShaderSource = full.preflightShaderSource;
export const setNativeTimeoutMs = full.setNativeTimeoutMs;
export const createDoeRuntime = full.createDoeRuntime;
export const runDawnVsDoeCompare = full.runDawnVsDoeCompare;

export default {
  ...full,
  doe,
};
