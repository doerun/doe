import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globals } from './webgpu_constants.js';
import { loadDoeBuildMetadata } from './build_metadata.js';
import {
  setupGlobalsOnTarget,
  requestAdapterFromCreate,
  requestDeviceFromRequestAdapter,
  buildProviderInfo,
  libraryFlavor,
} from './shared/public-surface.js';
import {
  validatePositiveInteger,
} from './shared/resource-lifecycle.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const addon = loadAddon();
const DOE_LIB_PATH = resolveDoeLibraryPath();
const DOE_BUILD_METADATA = loadDoeBuildMetadata({
  packageRoot: resolve(__dirname, '..'),
  libraryPath: DOE_LIB_PATH ?? '',
});
let libraryLoaded = false;

function loadAddon() {
  const prebuildPath = resolve(__dirname, '..', 'prebuilds', `${process.platform}-${process.arch}`, 'doe_napi.node');
  try {
    return require('../build/Release/doe_napi.node');
  } catch {
    try {
      return require('../build/Debug/doe_napi.node');
    } catch {
      try {
        return require(prebuildPath);
      } catch {
        return null;
      }
    }
  }
}

function resolveDoeLibraryPath() {
  const ext = process.platform === 'darwin' ? 'dylib'
    : process.platform === 'win32' ? 'dll' : 'so';
  const candidates = [
    process.env.DOE_WEBGPU_LIB,
    process.env.FAWN_DOE_LIB,
    resolve(__dirname, '..', '..', '..', 'runtime', 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(__dirname, '..', '..', '..', 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(__dirname, '..', 'prebuilds', `${process.platform}-${process.arch}`, `libwebgpu_doe.${ext}`),
    resolve(process.cwd(), 'runtime', 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
    resolve(process.cwd(), 'zig', 'zig-out', 'lib', `libwebgpu_doe.${ext}`),
  ];
  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function ensureLibrary() {
  if (libraryLoaded) {
    return;
  }
  if (!addon) {
    throw new Error('@simulatte/webgpu/native-direct: native addon not found. Run `npm run build:addon` or `npm run prebuild`.');
  }
  if (!DOE_LIB_PATH) {
    throw new Error('@simulatte/webgpu/native-direct: libwebgpu_doe not found. Build it with `cd runtime/zig && zig build dropin` or set DOE_WEBGPU_LIB.');
  }
  addon.loadLibrary(DOE_LIB_PATH);
  libraryLoaded = true;
}

function buildCurrentProviderInfo() {
  return buildProviderInfo({
    moduleName: '@simulatte/webgpu/native-direct',
    loaded: Boolean(addon && DOE_LIB_PATH),
    loadError: addon && DOE_LIB_PATH ? '' : (!addon ? 'native addon not found' : 'libwebgpu_doe not found'),
    defaultCreateArgs: [],
    doeNative: Boolean(DOE_LIB_PATH),
    libraryFlavor: libraryFlavor(DOE_LIB_PATH),
    doeLibraryPath: DOE_LIB_PATH,
    buildMetadataSource: DOE_BUILD_METADATA?.source ?? 'missing',
    buildMetadataPath: DOE_BUILD_METADATA?.path ?? '',
    leanVerifiedBuild: DOE_BUILD_METADATA?.leanVerifiedBuild ?? false,
    proofArtifactSha256: DOE_BUILD_METADATA?.proofArtifactSha256 ?? null,
  });
}

export function create(createArgs = null) {
  void createArgs;
  ensureLibrary();
  if (typeof addon?.nativeDirectCreate !== 'function') {
    throw new Error('@simulatte/webgpu/native-direct: nativeDirectCreate is not available in the loaded addon.');
  }
  return addon.nativeDirectCreate();
}

export function createInstance(createArgs = null) {
  return create(createArgs);
}

export function setupGlobals(target = globalThis, createArgs = null) {
  return setupGlobalsOnTarget(target, create(createArgs), globals);
}

export async function requestAdapter(adapterOptions = undefined, createArgs = null) {
  return requestAdapterFromCreate(create, adapterOptions, createArgs);
}

export async function requestDevice(options = {}) {
  return requestDeviceFromRequestAdapter(requestAdapter, options);
}

export function providerInfo() {
  return buildCurrentProviderInfo();
}

export function preflightShaderSource(code) {
  ensureLibrary();
  if (typeof addon?.checkShaderSource !== 'function') {
    return { ok: true, stage: '', kind: '', message: '', reasons: [] };
  }
  const result = addon.checkShaderSource(code);
  if (!result || typeof result !== 'object') {
    return { ok: true, stage: '', kind: '', message: '', reasons: [] };
  }
  const out = {
    ok: result.ok !== false,
    stage: result.stage ?? '',
    kind: result.kind ?? '',
    message: result.message ?? '',
    reasons: result.ok === false && result.message ? [result.message] : [],
  };
  if (typeof result.line === 'number' && result.line > 0) out.line = result.line;
  if (typeof result.column === 'number' && result.column > 0) out.column = result.column;
  return out;
}

export function setNativeTimeoutMs(timeoutMs) {
  ensureLibrary();
  validatePositiveInteger(timeoutMs, 'native timeout');
  if (typeof addon.setTimeoutMs !== 'function') {
    throw new Error('setNativeTimeoutMs is not supported by the loaded addon.');
  }
  addon.setTimeoutMs(timeoutMs);
}

export { globals };

export default {
  create,
  createInstance,
  globals,
  setupGlobals,
  requestAdapter,
  requestDevice,
  providerInfo,
  preflightShaderSource,
  setNativeTimeoutMs,
};
