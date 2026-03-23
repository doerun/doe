// doe-gpu — Deno entry

import * as full from './vendor/webgpu/index.js';
import { createDoeNamespace } from './vendor/doe-namespace.js';

export const createGpuNamespace = createDoeNamespace;

export const gpu = createDoeNamespace({
  requestDevice: full.requestDevice,
});

export const create = full.create;
export const createCanvasContext = full.createCanvasContext;
export const globals = full.globals;
export const setupGlobals = full.setupGlobals;
export const requestAdapter = full.requestAdapter;
export const requestDevice = full.requestDevice;
export const providerInfo = full.providerInfo;
export const preflightShaderSource = full.preflightShaderSource;
export const setNativeTimeoutMs = full.setNativeTimeoutMs;
export const createDoeRuntime = full.createDoeRuntime;
export const runDawnVsDoeCompare = full.runDawnVsDoeCompare;
