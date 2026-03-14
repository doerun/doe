import { dlopen, FFIType, JSCallback, ptr as bunPtr, toArrayBuffer } from "bun:ffi";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createDoeRuntime, runDawnVsDoeCompare } from "./runtime_cli.js";
import { loadDoeBuildMetadata } from "./build_metadata.js";
import { globals } from "./webgpu_constants.js";
import {
  UINT32_MAX,
  failValidation,
  describeResourceLabel,
  initResource,
  assertObject,
  assertArray,
  assertBoolean,
  assertNonEmptyString,
  assertIntegerInRange,
  assertOptionalIntegerInRange,
  assertLiveResource,
  destroyResource,
} from "./shared/resource-lifecycle.js";
import {
  publishLimits,
  publishFeatures,
} from "./shared/capabilities.js";
import {
  ALL_BUFFER_USAGE_BITS,
  assertBufferDescriptor,
  assertTextureSize,
  assertBindGroupResource as normalizeBindGroupResource,
  normalizeBindGroupLayoutEntry,
  autoLayoutEntriesFromNativeBindings,
} from "./shared/validation.js";
import {
  setupGlobalsOnTarget,
  requestAdapterFromCreate,
  requestDeviceFromRequestAdapter,
  buildProviderInfo,
  libraryFlavor,
} from "./shared/public-surface.js";
import {
  shaderCheckFailure,
  enrichNativeCompilerError,
  compilerErrorFromMessage,
} from "./shared/compiler-errors.js";
import {
  createFullSurfaceClasses,
} from "./shared/full-surface.js";
import {
  createEncoderClasses,
} from "./shared/encoder-surface.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = resolve(__dirname, "..");

export { globals };

const CALLBACK_MODE_ALLOW_PROCESS_EVENTS = 2;
const WGPU_STATUS_SUCCESS = 1;
const REQUEST_ADAPTER_STATUS_SUCCESS = 1;
const REQUEST_DEVICE_STATUS_SUCCESS = 1;
const MAP_ASYNC_STATUS_SUCCESS = 1;
const STYPE_SHADER_SOURCE_WGSL = 0x00000002;
const PROCESS_EVENTS_TIMEOUT_NS = 5_000_000_000;
let processEventsTimeoutNs = PROCESS_EVENTS_TIMEOUT_NS;
const SAMPLER_BINDING_TYPE = Object.freeze({
    filtering: 2,
    "non-filtering": 3,
    comparison: 4,
});
const TEXTURE_SAMPLE_TYPE = Object.freeze({
    float: 2,
    "unfilterable-float": 3,
    depth: 4,
    sint: 5,
    uint: 6,
});
const TEXTURE_VIEW_DIMENSION = Object.freeze({
    "1d": 1,
    "2d": 2,
    "2d-array": 3,
    cube: 4,
    "cube-array": 5,
    "3d": 6,
});
const STORAGE_TEXTURE_ACCESS = Object.freeze({
    "write-only": 2,
    "read-only": 3,
    "read-write": 4,
});

// Struct layout constants for 64-bit platforms (LP64 / LLP64).
const PTR_SIZE = 8;
const SIZE_T_SIZE = 8;
const WGPU_BUFFER_DESCRIPTOR_SIZE = 48;
const WGPU_SHADER_SOURCE_WGSL_SIZE = 32;
const WGPU_SHADER_MODULE_DESCRIPTOR_SIZE = 24;
const WGPU_COMPUTE_PIPELINE_DESCRIPTOR_SIZE = 80;
const WGPU_RENDER_PIPELINE_DESCRIPTOR_SIZE = 168;
const WGPU_BIND_GROUP_LAYOUT_DESCRIPTOR_SIZE = 40;
const WGPU_BIND_GROUP_DESCRIPTOR_SIZE = 48;
const WGPU_PIPELINE_LAYOUT_DESCRIPTOR_SIZE = 48;
const WGPU_RENDER_PASS_DESCRIPTOR_SIZE = 64;
const WGPU_LIMITS_SIZE = 152;
const WGPU_RENDER_VERTEX_STATE_SIZE = 64;
const WGPU_RENDER_COLOR_TARGET_STATE_SIZE = 32;
const WGPU_RENDER_FRAGMENT_STATE_SIZE = 64;
const WGPU_VERTEX_ATTRIBUTE_SIZE = 32;
const WGPU_VERTEX_BUFFER_LAYOUT_SIZE = 40;
const WGPU_DEPTH_STENCIL_STATE_SIZE = 72;
const WGPU_RENDER_PASS_DEPTH_STENCIL_ATTACHMENT_SIZE = 48;

// ---------------------------------------------------------------------------
// Library resolution
// ---------------------------------------------------------------------------

const LIB_EXT = { darwin: "dylib", linux: "so", win32: "dll" };

function resolveDoeLibraryPath() {
    const ext = LIB_EXT[process.platform] ?? "so";
    const candidates = [
        process.env.DOE_WEBGPU_LIB,
        resolve(PACKAGE_ROOT, "prebuilds", `${process.platform}-${process.arch}`, `libwebgpu_doe.${ext}`),
        resolve(PACKAGE_ROOT, "..", "..", "zig", "zig-out", "lib", `libwebgpu_doe.${ext}`),
        resolve(process.cwd(), "zig", "zig-out", "lib", `libwebgpu_doe.${ext}`),
    ];
    for (const c of candidates) {
        if (c && existsSync(c)) return c;
    }
    return null;
}

const DOE_LIB_PATH = resolveDoeLibraryPath();
const DOE_LIBRARY_FLAVOR = libraryFlavor(DOE_LIB_PATH);
const DOE_BUILD_METADATA = loadDoeBuildMetadata({
    packageRoot: PACKAGE_ROOT,
    libraryPath: DOE_LIB_PATH ?? "",
});
let wgpu = null;

// ---------------------------------------------------------------------------
// FFI symbol bindings
// ---------------------------------------------------------------------------

function openLibrary(path) {
    const symbols = {
        // Instance
        wgpuCreateInstance:       { args: [FFIType.ptr], returns: FFIType.ptr },
        wgpuInstanceRelease:      { args: [FFIType.ptr], returns: FFIType.void },
        wgpuInstanceWaitAny:      { args: [FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.u64], returns: FFIType.u32 },
        wgpuInstanceProcessEvents: { args: [FFIType.ptr], returns: FFIType.void },

        // Adapter/Device (flat helpers)
        doeRequestAdapterFlat:    { args: [FFIType.ptr, FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr], returns: FFIType.u64 },
        doeRequestDeviceFlat:     { args: [FFIType.ptr, FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr], returns: FFIType.u64 },
        wgpuAdapterRelease:       { args: [FFIType.ptr], returns: FFIType.void },
        wgpuAdapterHasFeature:    { args: [FFIType.ptr, FFIType.u32], returns: FFIType.u32 },
        wgpuAdapterGetLimits:     { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.u32 },
        wgpuDeviceRelease:        { args: [FFIType.ptr], returns: FFIType.void },
        wgpuDeviceHasFeature:     { args: [FFIType.ptr, FFIType.u32], returns: FFIType.u32 },
        wgpuDeviceGetLimits:      { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.u32 },
        wgpuDeviceGetQueue:       { args: [FFIType.ptr], returns: FFIType.ptr },

        // Buffer
        wgpuDeviceCreateBuffer:   { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuBufferRelease:        { args: [FFIType.ptr], returns: FFIType.void },
        wgpuBufferUnmap:          { args: [FFIType.ptr], returns: FFIType.void },
        wgpuBufferGetConstMappedRange: { args: [FFIType.ptr, FFIType.u64, FFIType.u64], returns: FFIType.ptr },
        wgpuBufferGetMappedRange: { args: [FFIType.ptr, FFIType.u64, FFIType.u64], returns: FFIType.ptr },
        doeBufferMapAsyncFlat:    { args: [FFIType.ptr, FFIType.u64, FFIType.u64, FFIType.u64, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr], returns: FFIType.u64 },
        doeBufferMapSyncFlat:     { args: [FFIType.ptr, FFIType.ptr, FFIType.u64, FFIType.u64, FFIType.u64], returns: FFIType.u32 },

        // Queue
        wgpuQueueSubmit:          { args: [FFIType.ptr, FFIType.u64, FFIType.ptr], returns: FFIType.void },
        wgpuQueueWriteBuffer:     { args: [FFIType.ptr, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.u64], returns: FFIType.void },
        wgpuQueueRelease:         { args: [FFIType.ptr], returns: FFIType.void },
        doeQueueOnSubmittedWorkDoneFlat: { args: [FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr], returns: FFIType.u64 },

        // Shader
        wgpuDeviceCreateShaderModule: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuShaderModuleRelease:  { args: [FFIType.ptr], returns: FFIType.void },
        doeNativeShaderModuleGetBindings: { args: [FFIType.ptr, FFIType.ptr, FFIType.u64], returns: FFIType.u64 },

        // Compute pipeline
        wgpuDeviceCreateComputePipeline: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuComputePipelineRelease: { args: [FFIType.ptr], returns: FFIType.void },
        wgpuComputePipelineGetBindGroupLayout: { args: [FFIType.ptr, FFIType.u32], returns: FFIType.ptr },

        // Bind group layout / bind group / pipeline layout
        wgpuDeviceCreateBindGroupLayout: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuBindGroupLayoutRelease: { args: [FFIType.ptr], returns: FFIType.void },
        wgpuDeviceCreateBindGroup: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuBindGroupRelease:     { args: [FFIType.ptr], returns: FFIType.void },
        wgpuDeviceCreatePipelineLayout: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuPipelineLayoutRelease: { args: [FFIType.ptr], returns: FFIType.void },

        // Command encoder
        wgpuDeviceCreateCommandEncoder: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuCommandEncoderRelease: { args: [FFIType.ptr], returns: FFIType.void },
        wgpuCommandEncoderBeginComputePass: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuCommandEncoderCopyBufferToBuffer: { args: [FFIType.ptr, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.u64, FFIType.u64], returns: FFIType.void },
        wgpuCommandEncoderFinish: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuCommandBufferRelease: { args: [FFIType.ptr], returns: FFIType.void },

        // Compute pass
        wgpuComputePassEncoderSetPipeline: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.void },
        wgpuComputePassEncoderSetBindGroup: { args: [FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.u64, FFIType.ptr], returns: FFIType.void },
        wgpuComputePassEncoderDispatchWorkgroups: { args: [FFIType.ptr, FFIType.u32, FFIType.u32, FFIType.u32], returns: FFIType.void },
        wgpuComputePassEncoderDispatchWorkgroupsIndirect: { args: [FFIType.ptr, FFIType.ptr, FFIType.u64], returns: FFIType.void },
        wgpuComputePassEncoderEnd: { args: [FFIType.ptr], returns: FFIType.void },
        wgpuComputePassEncoderRelease: { args: [FFIType.ptr], returns: FFIType.void },

        // Texture
        wgpuDeviceCreateTexture:  { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuTextureCreateView:    { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuTextureRelease:       { args: [FFIType.ptr], returns: FFIType.void },
        wgpuTextureViewRelease:   { args: [FFIType.ptr], returns: FFIType.void },

        // Sampler
        wgpuDeviceCreateSampler:  { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuSamplerRelease:       { args: [FFIType.ptr], returns: FFIType.void },

        // Render pipeline
        wgpuDeviceCreateRenderPipeline: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuRenderPipelineRelease: { args: [FFIType.ptr], returns: FFIType.void },

        // Render pass
        wgpuCommandEncoderBeginRenderPass: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuRenderPassEncoderSetPipeline: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.void },
        wgpuRenderPassEncoderSetBindGroup: { args: [FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.u64, FFIType.ptr], returns: FFIType.void },
        wgpuRenderPassEncoderSetVertexBuffer: { args: [FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.u64, FFIType.u64], returns: FFIType.void },
        wgpuRenderPassEncoderSetIndexBuffer: { args: [FFIType.ptr, FFIType.ptr, FFIType.u32, FFIType.u64, FFIType.u64], returns: FFIType.void },
        wgpuRenderPassEncoderDraw: { args: [FFIType.ptr, FFIType.u32, FFIType.u32, FFIType.u32, FFIType.u32], returns: FFIType.void },
        wgpuRenderPassEncoderDrawIndexed: { args: [FFIType.ptr, FFIType.u32, FFIType.u32, FFIType.u32, FFIType.i32, FFIType.u32], returns: FFIType.void },
        wgpuRenderPassEncoderEnd: { args: [FFIType.ptr], returns: FFIType.void },
        wgpuRenderPassEncoderRelease: { args: [FFIType.ptr], returns: FFIType.void },
    };
    if (process.platform === "darwin") {
        symbols.doeNativeComputePipelineGetBindGroupLayout = {
            args: [FFIType.ptr, FFIType.u32],
            returns: FFIType.ptr,
        };
        symbols.doeNativeCheckShaderSource = {
            args: [FFIType.ptr, FFIType.u64],
            returns: FFIType.u32,
        };
        symbols.doeNativeCopyLastErrorMessage = {
            args: [FFIType.ptr, FFIType.u64],
            returns: FFIType.u64,
        };
        symbols.doeNativeCopyLastErrorStage = {
            args: [FFIType.ptr, FFIType.u64],
            returns: FFIType.u64,
        };
        symbols.doeNativeCopyLastErrorKind = {
            args: [FFIType.ptr, FFIType.u64],
            returns: FFIType.u64,
        };
    }
    return dlopen(path, symbols);
}

// ---------------------------------------------------------------------------
// Struct marshaling helpers
//
// All layouts assume 64-bit LP64/LLP64: ptr=8, size_t=8, u64=8, u32=4.
// WGPUStringView = { data: ptr@0, length: size_t@8 } = 16 bytes.
// ---------------------------------------------------------------------------

const encoder = new TextEncoder();
const decoder = new TextDecoder();

const LIMIT_OFFSETS = Object.freeze({
    maxTextureDimension1D: 8,
    maxTextureDimension2D: 12,
    maxTextureDimension3D: 16,
    maxTextureArrayLayers: 20,
    maxBindGroups: 24,
    maxBindGroupsPlusVertexBuffers: 28,
    maxBindingsPerBindGroup: 32,
    maxDynamicUniformBuffersPerPipelineLayout: 36,
    maxDynamicStorageBuffersPerPipelineLayout: 40,
    maxSampledTexturesPerShaderStage: 44,
    maxSamplersPerShaderStage: 48,
    maxStorageBuffersPerShaderStage: 52,
    maxStorageTexturesPerShaderStage: 56,
    maxUniformBuffersPerShaderStage: 60,
    maxUniformBufferBindingSize: 64,
    maxStorageBufferBindingSize: 72,
    minUniformBufferOffsetAlignment: 80,
    minStorageBufferOffsetAlignment: 84,
    maxVertexBuffers: 88,
    maxBufferSize: 96,
    maxVertexAttributes: 104,
    maxVertexBufferArrayStride: 108,
    maxInterStageShaderVariables: 112,
    maxColorAttachments: 116,
    maxColorAttachmentBytesPerSample: 120,
    maxComputeWorkgroupStorageSize: 124,
    maxComputeInvocationsPerWorkgroup: 128,
    maxComputeWorkgroupSizeX: 132,
    maxComputeWorkgroupSizeY: 136,
    maxComputeWorkgroupSizeZ: 140,
    maxComputeWorkgroupsPerDimension: 144,
});

function copyLastErrorMessage() {
    const fn = wgpu?.symbols?.doeNativeCopyLastErrorMessage;
    if (typeof fn !== "function") return "";
    const buf = new Uint8Array(4096);
    const len = Number(fn(buf, BigInt(buf.length)));
    if (len <= 1) return "";
    return decoder.decode(buf.subarray(0, Math.max(0, len - 1)));
}

function decodeLimits(raw) {
    const view = new DataView(raw);
    return Object.freeze({
        maxTextureDimension1D: view.getUint32(LIMIT_OFFSETS.maxTextureDimension1D, true),
        maxTextureDimension2D: view.getUint32(LIMIT_OFFSETS.maxTextureDimension2D, true),
        maxTextureDimension3D: view.getUint32(LIMIT_OFFSETS.maxTextureDimension3D, true),
        maxTextureArrayLayers: view.getUint32(LIMIT_OFFSETS.maxTextureArrayLayers, true),
        maxBindGroups: view.getUint32(LIMIT_OFFSETS.maxBindGroups, true),
        maxBindGroupsPlusVertexBuffers: view.getUint32(LIMIT_OFFSETS.maxBindGroupsPlusVertexBuffers, true),
        maxBindingsPerBindGroup: view.getUint32(LIMIT_OFFSETS.maxBindingsPerBindGroup, true),
        maxDynamicUniformBuffersPerPipelineLayout: view.getUint32(LIMIT_OFFSETS.maxDynamicUniformBuffersPerPipelineLayout, true),
        maxDynamicStorageBuffersPerPipelineLayout: view.getUint32(LIMIT_OFFSETS.maxDynamicStorageBuffersPerPipelineLayout, true),
        maxSampledTexturesPerShaderStage: view.getUint32(LIMIT_OFFSETS.maxSampledTexturesPerShaderStage, true),
        maxSamplersPerShaderStage: view.getUint32(LIMIT_OFFSETS.maxSamplersPerShaderStage, true),
        maxStorageBuffersPerShaderStage: view.getUint32(LIMIT_OFFSETS.maxStorageBuffersPerShaderStage, true),
        maxStorageTexturesPerShaderStage: view.getUint32(LIMIT_OFFSETS.maxStorageTexturesPerShaderStage, true),
        maxUniformBuffersPerShaderStage: view.getUint32(LIMIT_OFFSETS.maxUniformBuffersPerShaderStage, true),
        maxUniformBufferBindingSize: Number(view.getBigUint64(LIMIT_OFFSETS.maxUniformBufferBindingSize, true)),
        maxStorageBufferBindingSize: Number(view.getBigUint64(LIMIT_OFFSETS.maxStorageBufferBindingSize, true)),
        minUniformBufferOffsetAlignment: view.getUint32(LIMIT_OFFSETS.minUniformBufferOffsetAlignment, true),
        minStorageBufferOffsetAlignment: view.getUint32(LIMIT_OFFSETS.minStorageBufferOffsetAlignment, true),
        maxVertexBuffers: view.getUint32(LIMIT_OFFSETS.maxVertexBuffers, true),
        maxBufferSize: Number(view.getBigUint64(LIMIT_OFFSETS.maxBufferSize, true)),
        maxVertexAttributes: view.getUint32(LIMIT_OFFSETS.maxVertexAttributes, true),
        maxVertexBufferArrayStride: view.getUint32(LIMIT_OFFSETS.maxVertexBufferArrayStride, true),
        maxInterStageShaderVariables: view.getUint32(LIMIT_OFFSETS.maxInterStageShaderVariables, true),
        maxColorAttachments: view.getUint32(LIMIT_OFFSETS.maxColorAttachments, true),
        maxColorAttachmentBytesPerSample: view.getUint32(LIMIT_OFFSETS.maxColorAttachmentBytesPerSample, true),
        maxComputeWorkgroupStorageSize: view.getUint32(LIMIT_OFFSETS.maxComputeWorkgroupStorageSize, true),
        maxComputeInvocationsPerWorkgroup: view.getUint32(LIMIT_OFFSETS.maxComputeInvocationsPerWorkgroup, true),
        maxComputeWorkgroupSizeX: view.getUint32(LIMIT_OFFSETS.maxComputeWorkgroupSizeX, true),
        maxComputeWorkgroupSizeY: view.getUint32(LIMIT_OFFSETS.maxComputeWorkgroupSizeY, true),
        maxComputeWorkgroupSizeZ: view.getUint32(LIMIT_OFFSETS.maxComputeWorkgroupSizeZ, true),
        maxComputeWorkgroupsPerDimension: view.getUint32(LIMIT_OFFSETS.maxComputeWorkgroupsPerDimension, true),
    });
}

function queryLimits(handle, fnName) {
    const fn = wgpu?.symbols?.[fnName];
    if (typeof fn !== "function" || !handle) return publishLimits(null);
    const raw = new ArrayBuffer(WGPU_LIMITS_SIZE);
    const status = Number(fn(handle, new Uint8Array(raw)));
    if (status !== WGPU_STATUS_SUCCESS) return publishLimits(null);
    return publishLimits(decodeLimits(raw));
}

function adapterLimits(handle) {
    return queryLimits(handle, "wgpuAdapterGetLimits");
}

function deviceLimits(handle) {
    return queryLimits(handle, "wgpuDeviceGetLimits");
}

function adapterFeatures(handle) {
    const fn = wgpu?.symbols?.wgpuAdapterHasFeature;
    return publishFeatures(
        typeof fn === "function" && handle
            ? (feature) => Number(fn(handle, feature)) !== 0
            : null,
    );
}

function deviceFeatures(handle) {
    const fn = wgpu?.symbols?.wgpuDeviceHasFeature;
    return publishFeatures(
        typeof fn === "function" && handle
            ? (feature) => Number(fn(handle, feature)) !== 0
            : null,
    );
}

function copyNativeErrorMeta(symbolName) {
    const fn = wgpu?.symbols?.[symbolName];
    if (typeof fn !== "function") return "";
    const scratch = new Uint8Array(256);
    const len = Number(fn(scratch, scratch.length));
    if (!len) return "";
    return decoder.decode(scratch.subarray(0, Math.min(len, scratch.length - 1)));
}

function preflightShaderSource(code) {
    const fn = wgpu?.symbols?.doeNativeCheckShaderSource;
    if (typeof fn !== "function") {
        return { ok: true, stage: "", kind: "", message: "", reasons: [] };
    }
    const codeBytes = encoder.encode(code);
    const ok = Number(fn(codeBytes, codeBytes.length)) !== 0;
    if (ok) return { ok: true, stage: "", kind: "", message: "", reasons: [] };
    const message = copyNativeErrorMeta("doeNativeCopyLastErrorMessage");
    return {
        ok: false,
        stage: copyNativeErrorMeta("doeNativeCopyLastErrorStage"),
        kind: copyNativeErrorMeta("doeNativeCopyLastErrorKind"),
        message,
        reasons: message ? [message] : [],
    };
}

function writeStringView(view, offset, strBytes) {
    if (strBytes) {
        view.setBigUint64(offset, BigInt(bunPtr(strBytes)), true);
        view.setBigUint64(offset + 8, BigInt(strBytes.length), true);
    } else {
        view.setBigUint64(offset, 0n, true);
        view.setBigUint64(offset + 8, 0n, true);
    }
}

function writePtr(view, offset, ptr) {
    view.setBigUint64(offset, ptr ? BigInt(ptr) : 0n, true);
}

// WGPUBufferDescriptor: { nextInChain:ptr@0, label:sv@8, usage:u64@24, size:u64@32, mappedAtCreation:u32@40 } = 48
function buildBufferDescriptor(descriptor) {
    const buf = new ArrayBuffer(WGPU_BUFFER_DESCRIPTOR_SIZE);
    const v = new DataView(buf);
    // nextInChain = null
    writePtr(v, 0, null);
    // label = empty
    writeStringView(v, 8, null);
    // usage
    v.setBigUint64(24, BigInt(descriptor.usage || 0), true);
    // size
    v.setBigUint64(32, BigInt(descriptor.size || 0), true);
    // mappedAtCreation
    v.setUint32(40, descriptor.mappedAtCreation ? 1 : 0, true);
    return new Uint8Array(buf);
}

// WGPUShaderSourceWGSL: { chain:{next:ptr@0, sType:u32@8, pad@12}, code:sv@16 } = 32
// WGPUShaderModuleDescriptor: { nextInChain:ptr@0, label:sv@8 } = 24
function buildShaderModuleDescriptor(code) {
    const codeBytes = encoder.encode(code);

    const wgslBuf = new ArrayBuffer(WGPU_SHADER_SOURCE_WGSL_SIZE);
    const wgslView = new DataView(wgslBuf);
    writePtr(wgslView, 0, null);
    wgslView.setUint32(8, STYPE_SHADER_SOURCE_WGSL, true);
    writeStringView(wgslView, 16, codeBytes);
    const wgslArr = new Uint8Array(wgslBuf);

    const descBuf = new ArrayBuffer(WGPU_SHADER_MODULE_DESCRIPTOR_SIZE);
    const descView = new DataView(descBuf);
    writePtr(descView, 0, bunPtr(wgslArr));
    writeStringView(descView, 8, null);

    return { desc: new Uint8Array(descBuf), _refs: [codeBytes, wgslArr] };
}

// WGPUComputePipelineDescriptor:
// { nextInChain:ptr@0, label:sv@8, layout:ptr@24, compute:WGPUProgrammableStageDescriptor@32 }
// WGPUProgrammableStageDescriptor: { nextInChain:ptr@0, module:ptr@8, entryPoint:sv@16, constantCount:size_t@32, constants:ptr@40 } = 48
// Total descriptor: 24 + 8 (layout) + 48 (compute) = 80
function buildComputePipelineDescriptor(shaderModulePtr, entryPoint, layoutPtr) {
    const epBytes = encoder.encode(entryPoint);
    const buf = new ArrayBuffer(WGPU_COMPUTE_PIPELINE_DESCRIPTOR_SIZE);
    const v = new DataView(buf);
    // nextInChain
    writePtr(v, 0, null);
    // label
    writeStringView(v, 8, null);
    // layout
    writePtr(v, 24, layoutPtr);
    // compute.nextInChain
    writePtr(v, 32, null);
    // compute.module
    writePtr(v, 40, shaderModulePtr);
    // compute.entryPoint
    writeStringView(v, 48, epBytes);
    // compute.constantCount
    v.setBigUint64(64, 0n, true);
    // compute.constants
    writePtr(v, 72, null);
    return { desc: new Uint8Array(buf), _refs: [epBytes] };
}

function buildRenderPipelineDescriptor(descriptor) {
    const vertexEntryBytes = encoder.encode(descriptor.vertexEntryPoint);
    const fragmentEntryBytes = encoder.encode(descriptor.fragmentEntryPoint);
    const vertexBuffers = descriptor.vertexBuffers ?? [];

    const colorTargetBuf = new ArrayBuffer(WGPU_RENDER_COLOR_TARGET_STATE_SIZE);
    const colorTargetView = new DataView(colorTargetBuf);
    writePtr(colorTargetView, 0, null);
    colorTargetView.setUint32(8, TEXTURE_FORMAT_MAP[descriptor.colorFormat] ?? 0x00000016, true);
    writePtr(colorTargetView, 16, null);
    colorTargetView.setBigUint64(24, 0xFn, true);
    const colorTargetArr = new Uint8Array(colorTargetBuf);

    const fragmentBuf = new ArrayBuffer(WGPU_RENDER_FRAGMENT_STATE_SIZE);
    const fragmentView = new DataView(fragmentBuf);
    writePtr(fragmentView, 0, null);
    writePtr(fragmentView, 8, descriptor.fragmentModule);
    writeStringView(fragmentView, 16, fragmentEntryBytes);
    fragmentView.setBigUint64(32, 0n, true);
    writePtr(fragmentView, 40, null);
    fragmentView.setBigUint64(48, 1n, true);
    writePtr(fragmentView, 56, bunPtr(colorTargetArr));
    const fragmentArr = new Uint8Array(fragmentBuf);

    let vertexAttributeArr = null;
    let vertexBufferArr = null;
    if (vertexBuffers.length > 0) {
        let totalAttributeCount = 0;
        for (const buffer of vertexBuffers) {
            totalAttributeCount += (buffer.attributes ?? []).length;
        }
        vertexAttributeArr = new Uint8Array(totalAttributeCount * WGPU_VERTEX_ATTRIBUTE_SIZE);
        vertexBufferArr = new Uint8Array(vertexBuffers.length * WGPU_VERTEX_BUFFER_LAYOUT_SIZE);
        const attrView = new DataView(vertexAttributeArr.buffer);
        const layoutView = new DataView(vertexBufferArr.buffer);
        let attrIndex = 0;
        for (let bufferIndex = 0; bufferIndex < vertexBuffers.length; bufferIndex += 1) {
            const buffer = vertexBuffers[bufferIndex] ?? {};
            const attributes = buffer.attributes ?? [];
            const layoutOffset = bufferIndex * WGPU_VERTEX_BUFFER_LAYOUT_SIZE;
            writePtr(layoutView, layoutOffset + 0, null);
            layoutView.setUint32(layoutOffset + 8, VERTEX_STEP_MODE_MAP[buffer.stepMode ?? "vertex"] ?? VERTEX_STEP_MODE_MAP.vertex, true);
            layoutView.setBigUint64(layoutOffset + 16, BigInt(buffer.arrayStride ?? 0), true);
            layoutView.setBigUint64(layoutOffset + 24, BigInt(attributes.length), true);
            writePtr(layoutView, layoutOffset + 32, attributes.length > 0 ? bunPtr(vertexAttributeArr) + BigInt(attrIndex * WGPU_VERTEX_ATTRIBUTE_SIZE) : null);
            for (const attribute of attributes) {
                const attrOffset = attrIndex * WGPU_VERTEX_ATTRIBUTE_SIZE;
                writePtr(attrView, attrOffset + 0, null);
                attrView.setUint32(attrOffset + 8, VERTEX_FORMAT_MAP[attribute.format] ?? 0, true);
                attrView.setBigUint64(attrOffset + 16, BigInt(attribute.offset ?? 0), true);
                attrView.setUint32(attrOffset + 24, attribute.shaderLocation ?? 0, true);
                attrIndex += 1;
            }
        }
    }

    let depthStencilArr = null;
    if (descriptor.depthStencil) {
        const depthStencilBuf = new ArrayBuffer(WGPU_DEPTH_STENCIL_STATE_SIZE);
        const depthStencilView = new DataView(depthStencilBuf);
        writePtr(depthStencilView, 0, null);
        depthStencilView.setUint32(8, TEXTURE_FORMAT_MAP[descriptor.depthStencil.format] ?? TEXTURE_FORMAT_MAP.depth32float, true);
        depthStencilView.setUint32(12, descriptor.depthStencil.depthWriteEnabled ? 1 : 0, true);
        depthStencilView.setUint32(16, COMPARE_FUNC_MAP[descriptor.depthStencil.depthCompare ?? "always"] ?? COMPARE_FUNC_MAP.always, true);
        depthStencilView.setUint32(48, 0xFFFFFFFF, true);
        depthStencilView.setUint32(52, 0xFFFFFFFF, true);
        depthStencilArr = new Uint8Array(depthStencilBuf);
    }

    const primitive = descriptor.primitive ?? {};
    const multisample = descriptor.multisample ?? {};
    const buf = new ArrayBuffer(WGPU_RENDER_PIPELINE_DESCRIPTOR_SIZE);
    const view = new DataView(buf);
    writePtr(view, 0, null);
    writeStringView(view, 8, null);
    writePtr(view, 24, descriptor.layout);
    writePtr(view, 32, null);
    writePtr(view, 40, descriptor.vertexModule);
    writeStringView(view, 48, vertexEntryBytes);
    view.setBigUint64(64, 0n, true);
    writePtr(view, 72, null);
    view.setBigUint64(80, BigInt(vertexBuffers.length), true);
    writePtr(view, 88, vertexBuffers.length > 0 ? bunPtr(vertexBufferArr) : null);
    writePtr(view, 96, null);
    view.setUint32(104, {
        "point-list": 0x00000001,
        "line-list": 0x00000002,
        "line-strip": 0x00000003,
        "triangle-list": 0x00000004,
        "triangle-strip": 0x00000005,
    }[primitive.topology ?? "triangle-list"] ?? 0x00000004, true);
    view.setUint32(108, 0, true);
    view.setUint32(112, { ccw: 0x00000001, cw: 0x00000002 }[primitive.frontFace ?? "ccw"] ?? 0x00000001, true);
    view.setUint32(116, { none: 0x00000001, front: 0x00000002, back: 0x00000003 }[primitive.cullMode ?? "none"] ?? 0x00000001, true);
    view.setUint32(120, primitive.unclippedDepth ? 1 : 0, true);
    writePtr(view, 128, depthStencilArr ? bunPtr(depthStencilArr) : null);
    writePtr(view, 136, null);
    view.setUint32(144, multisample.count ?? 1, true);
    view.setUint32(148, multisample.mask ?? 0xFFFF_FFFF, true);
    view.setUint32(152, multisample.alphaToCoverageEnabled ? 1 : 0, true);
    writePtr(view, 160, bunPtr(fragmentArr));
    return {
        desc: new Uint8Array(buf),
        _refs: [vertexEntryBytes, fragmentEntryBytes, colorTargetArr, fragmentArr, vertexAttributeArr, vertexBufferArr, depthStencilArr].filter(Boolean),
    };
}

// WGPUBindGroupLayoutEntry: { nextInChain:ptr@0, binding:u32@8, visibility:u64@12(actually u32@12 + pad), ...complex }
// The full entry is large. We build a minimal version matching what doe_napi.c marshals.
// For simplicity, we build the entry array matching the C struct layout.
//
// WGPUBindGroupLayoutEntry (simplified layout for buffer-only bindings):
// { nextInChain:ptr@0, binding:u32@8, pad@12, visibility:u64@16,
//   buffer:{nextInChain:ptr@24, type:u32@32, pad@36, hasDynamicOffset:u32@40, pad@44, minBindingSize:u64@48},
//   sampler:{...@56}, texture:{...}, storageTexture:{...} }
// Full size per entry: 128 bytes (varies by ABI — we use a generous allocation)
//
// NOTE: The exact layout is ABI-dependent. We use the wgpu.h canonical layout.
// BindGroupLayoutEntry total = 136 bytes on 64-bit.
const BIND_GROUP_LAYOUT_ENTRY_SIZE = 120;

function buildBindGroupLayoutDescriptor(entries) {
    const entryBufs = new Uint8Array(entries.length * BIND_GROUP_LAYOUT_ENTRY_SIZE);
    const entryView = new DataView(entryBufs.buffer);

    for (let i = 0; i < entries.length; i++) {
        const e = entries[i];
        const off = i * BIND_GROUP_LAYOUT_ENTRY_SIZE;
        // nextInChain: ptr@0
        writePtr(entryView, off + 0, null);
        // binding: u32@8
        entryView.setUint32(off + 8, e.binding, true);
        // visibility: u64@16 (WGPUShaderStageFlags, after 4-byte pad at @12)
        entryView.setBigUint64(off + 16, BigInt(e.visibility || 0), true);
        // bindingArraySize: u32@24
        entryView.setUint32(off + 24, 0, true);
        // buffer sub-struct starts at @32:
        //   buffer.nextInChain: ptr@32
        writePtr(entryView, off + 32, null);
        if (e.buffer) {
            // WGPUBufferBindingType: Undefined=1, Uniform=2, Storage=3, ReadOnlyStorage=4
            const typeMap = { uniform: 2, storage: 3, "read-only-storage": 4 };
            //   buffer.type: u32@40
            entryView.setUint32(off + 40, typeMap[e.buffer.type || "uniform"] || 2, true);
            //   buffer.hasDynamicOffset: u32@44
            entryView.setUint32(off + 44, e.buffer.hasDynamicOffset ? 1 : 0, true);
            //   buffer.minBindingSize: u64@48
            entryView.setBigUint64(off + 48, BigInt(e.buffer.minBindingSize || 0), true);
        }
        if (e.sampler) {
            writePtr(entryView, off + 56, null);
            entryView.setUint32(off + 64, SAMPLER_BINDING_TYPE[e.sampler.type] || 2, true);
        }
        if (e.texture) {
            writePtr(entryView, off + 72, null);
            entryView.setUint32(off + 80, TEXTURE_SAMPLE_TYPE[e.texture.sampleType] || 2, true);
            entryView.setUint32(off + 84, TEXTURE_VIEW_DIMENSION[e.texture.viewDimension] || 2, true);
            entryView.setUint32(off + 88, e.texture.multisampled ? 1 : 0, true);
        }
        if (e.storageTexture) {
            writePtr(entryView, off + 96, null);
            entryView.setUint32(off + 104, STORAGE_TEXTURE_ACCESS[e.storageTexture.access] || 2, true);
            entryView.setUint32(off + 108, TEXTURE_FORMATS[e.storageTexture.format] || 18, true);
            entryView.setUint32(off + 112, TEXTURE_VIEW_DIMENSION[e.storageTexture.viewDimension] || 2, true);
        }
    }

    // WGPUBindGroupLayoutDescriptor: { nextInChain:ptr@0, label:sv@8, entryCount:size_t@24, entries:ptr@32 } = 40
    const descBuf = new ArrayBuffer(WGPU_BIND_GROUP_LAYOUT_DESCRIPTOR_SIZE);
    const descView = new DataView(descBuf);
    writePtr(descView, 0, null);
    writeStringView(descView, 8, null);
    descView.setBigUint64(24, BigInt(entries.length), true);
    writePtr(descView, 32, entries.length > 0 ? bunPtr(entryBufs) : null);

    return { desc: new Uint8Array(descBuf), _refs: [entryBufs] };
}

// WGPUBindGroupEntry: { nextInChain:ptr@0, binding:u32@8, pad@12, buffer:ptr@16, offset:u64@24, size:u64@32,
//   sampler:ptr@40, textureView:ptr@48 } = 56
const BIND_GROUP_ENTRY_SIZE = 56;
const WHOLE_SIZE = 0xFFFFFFFFFFFFFFFFn;

function buildBindGroupDescriptor(layoutPtr, entries) {
    const entryBufs = new Uint8Array(entries.length * BIND_GROUP_ENTRY_SIZE);
    const entryView = new DataView(entryBufs.buffer);

    for (let i = 0; i < entries.length; i++) {
        const e = entries[i];
        const off = i * BIND_GROUP_ENTRY_SIZE;
        writePtr(entryView, off + 0, null);
        entryView.setUint32(off + 8, e.binding, true);
        const bufferPtr = e.resource?.buffer ?? null;
        writePtr(entryView, off + 16, bufferPtr);
        entryView.setBigUint64(off + 24, BigInt(e.resource?.offset ?? 0), true);
        entryView.setBigUint64(off + 32, e.resource?.size !== undefined ? BigInt(e.resource.size) : WHOLE_SIZE, true);
        writePtr(entryView, off + 40, e.resource?.sampler ?? null);
        writePtr(entryView, off + 48, e.resource?.textureView ?? null);
    }

    // WGPUBindGroupDescriptor: { nextInChain:ptr@0, label:sv@8, layout:ptr@24, entryCount:size_t@32, entries:ptr@40 } = 48
    const descBuf = new ArrayBuffer(WGPU_BIND_GROUP_DESCRIPTOR_SIZE);
    const descView = new DataView(descBuf);
    writePtr(descView, 0, null);
    writeStringView(descView, 8, null);
    writePtr(descView, 24, layoutPtr);
    descView.setBigUint64(32, BigInt(entries.length), true);
    writePtr(descView, 40, entries.length > 0 ? bunPtr(entryBufs) : null);

    return { desc: new Uint8Array(descBuf), _refs: [entryBufs] };
}

// WGPUPipelineLayoutDescriptor: { nextInChain:ptr@0, label:sv@8, bindGroupLayoutCount:size_t@24,
//   bindGroupLayouts:ptr@32, immediateSize:u32@40, pad@44 } = 48
function buildPipelineLayoutDescriptor(layouts) {
    const ptrs = new BigUint64Array(layouts.length);
    for (let i = 0; i < layouts.length; i++) {
        ptrs[i] = BigInt(layouts[i]);
    }

    const descBuf = new ArrayBuffer(WGPU_PIPELINE_LAYOUT_DESCRIPTOR_SIZE);
    const descView = new DataView(descBuf);
    writePtr(descView, 0, null);
    writeStringView(descView, 8, null);
    descView.setBigUint64(24, BigInt(layouts.length), true);
    writePtr(descView, 32, layouts.length > 0 ? bunPtr(ptrs) : null);
    descView.setUint32(40, 0, true); // immediateSize

    return { desc: new Uint8Array(descBuf), _refs: [ptrs] };
}

// WGPUTextureDescriptor: { nextInChain:ptr@0, label:sv@8, usage:u64@24, dimension:u32@32,
//   size:{width:u32@36, height:u32@40, depthOrArrayLayers:u32@44}, format:u32@48,
//   mipLevelCount:u32@52, sampleCount:u32@56, viewFormatCount:size_t@60(pad to 64), viewFormats:ptr@72 }
// Actual: nextInChain@0(8) label@8(16) usage@24(8) dimension@32(4) pad@36(4)
// size@40 {w:u32@40 h:u32@44 d:u32@48} pad@52(4) format@56(4) mipLevelCount@60(4) sampleCount@64(4)
// viewFormatCount@68(8) viewFormats@76(8) = 84 → round to 88
// NOTE: Exact layout depends on struct packing. Let me match the C definition carefully.
// From doe_napi.c:
// { nextInChain:ptr, label:WGPUStringView, usage:u64, dimension:u32, size:WGPUExtent3D, format:u32,
//   mipLevelCount:u32, sampleCount:u32, viewFormatCount:size_t, viewFormats:ptr }
// WGPUExtent3D = { width:u32, height:u32, depthOrArrayLayers:u32 } = 12 bytes
//
// Layout (64-bit, packed):
// nextInChain: ptr@0 (8)
// label.data: ptr@8 (8)
// label.length: size_t@16 (8)
// usage: u64@24 (8)
// dimension: u32@32 (4)
// size.width: u32@36 (4)  ← follows u32, natural alignment
// size.height: u32@40 (4)
// size.depthOrArrayLayers: u32@44 (4)
// format: u32@48 (4)
// mipLevelCount: u32@52 (4)
// sampleCount: u32@56 (4)
// pad: 4@60
// viewFormatCount: size_t@64 (8)
// viewFormats: ptr@72 (8)
// Total: 80
const TEXTURE_DESC_SIZE = 80;

const TEXTURE_FORMAT_MAP = {
    rgba8unorm: 18, "rgba8unorm-srgb": 19, bgra8unorm: 23, "bgra8unorm-srgb": 24,
    r32float: 33, rg32float: 43, rgba32float: 52, depth24plus: 55, depth32float: 55,
};

const VERTEX_FORMAT_MAP = {
    float32: 0x00000019,
    float32x2: 0x0000001A,
    float32x3: 0x0000001B,
    float32x4: 0x0000001C,
    uint32: 0x00000021,
    uint32x2: 0x00000022,
    uint32x3: 0x00000023,
    uint32x4: 0x00000024,
    sint32: 0x00000025,
    sint32x2: 0x00000026,
    sint32x3: 0x00000027,
    sint32x4: 0x00000028,
};

const VERTEX_STEP_MODE_MAP = {
    vertex: 0x00000001,
    instance: 0x00000002,
};

const COMPARE_FUNC_MAP = {
    never: 0x00000001,
    less: 0x00000002,
    equal: 0x00000003,
    "less-equal": 0x00000004,
    greater: 0x00000005,
    "not-equal": 0x00000006,
    "greater-equal": 0x00000007,
    always: 0x00000008,
};

const INDEX_FORMAT_MAP = {
    uint16: 0x00000001,
    uint32: 0x00000002,
};

function buildTextureDescriptor(descriptor) {
    const buf = new ArrayBuffer(TEXTURE_DESC_SIZE);
    const v = new DataView(buf);
    writePtr(v, 0, null);
    writeStringView(v, 8, null);
    v.setBigUint64(24, BigInt(descriptor.usage || 0), true);
    v.setUint32(32, 1, true); // dimension = 2D (WGPUTextureDimension_2D = 1... actually 0x00000002)
    // WGPUTextureDimension: 1D=1, 2D=2, 3D=3 in standard. Let's use 2.
    v.setUint32(32, 2, true);
    const w = descriptor.size?.[0] ?? descriptor.size?.width ?? descriptor.size ?? 1;
    const h = descriptor.size?.[1] ?? descriptor.size?.height ?? 1;
    const d = descriptor.size?.[2] ?? descriptor.size?.depthOrArrayLayers ?? 1;
    v.setUint32(36, w, true);
    v.setUint32(40, h, true);
    v.setUint32(44, d, true);
    const fmt = descriptor.format || "rgba8unorm";
    v.setUint32(48, TEXTURE_FORMAT_MAP[fmt] ?? 18, true);
    v.setUint32(52, descriptor.mipLevelCount || 1, true);
    v.setUint32(56, 1, true); // sampleCount
    v.setBigUint64(64, 0n, true); // viewFormatCount
    writePtr(v, 72, null); // viewFormats
    return new Uint8Array(buf);
}

// WGPUSamplerDescriptor: { nextInChain:ptr@0, label:sv@8, addressModeU:u32@24, V:u32@28, W:u32@32,
//   magFilter:u32@36, minFilter:u32@40, mipmapFilter:u32@44, lodMinClamp:f32@48, lodMaxClamp:f32@52,
//   compare:u32@56, maxAnisotropy:u16@60 } = 64 (with padding)
const SAMPLER_DESC_SIZE = 64;

function buildSamplerDescriptor(descriptor) {
    const buf = new ArrayBuffer(SAMPLER_DESC_SIZE);
    const v = new DataView(buf);
    writePtr(v, 0, null);
    writeStringView(v, 8, null);
    // defaults: clamp-to-edge=2, nearest=0
    v.setUint32(24, 2, true); // addressModeU
    v.setUint32(28, 2, true); // addressModeV
    v.setUint32(32, 2, true); // addressModeW
    v.setUint32(36, 0, true); // magFilter = nearest
    v.setUint32(40, 0, true); // minFilter = nearest
    v.setUint32(44, 0, true); // mipmapFilter = nearest
    v.setFloat32(48, 0.0, true);
    v.setFloat32(52, 32.0, true);
    v.setUint32(56, 0, true); // compare = undefined
    v.setUint16(60, 1, true); // maxAnisotropy
    return new Uint8Array(buf);
}

// WGPURenderPassColorAttachment:
// { nextInChain:ptr@0, view:ptr@8, depthSlice:u32@16, pad@20, resolveTarget:ptr@24,
//   loadOp:u32@32, storeOp:u32@36, clearValue:{r:f64@40, g:f64@48, b:f64@56, a:f64@64} } = 72
const RENDER_PASS_COLOR_ATTACHMENT_SIZE = 72;

// WGPURenderPassDescriptor:
// { nextInChain:ptr@0, label:sv@8, colorAttachmentCount:size_t@24, colorAttachments:ptr@32,
//   depthStencilAttachment:ptr@40, occlusionQuerySet:ptr@48, timestampWrites:ptr@56 } = 64
function buildRenderPassDescriptor(descriptor) {
    const colorAttachments = descriptor.colorAttachments || [];
    const attBuf = new Uint8Array(colorAttachments.length * RENDER_PASS_COLOR_ATTACHMENT_SIZE);
    const attView = new DataView(attBuf.buffer);

    for (let i = 0; i < colorAttachments.length; i++) {
        const a = colorAttachments[i];
        const off = i * RENDER_PASS_COLOR_ATTACHMENT_SIZE;
        writePtr(attView, off + 0, null);
        writePtr(attView, off + 8, a.view._native);
        attView.setUint32(off + 16, 0xFFFFFFFF, true); // depthSlice = WGPU_DEPTH_SLICE_UNDEFINED
        writePtr(attView, off + 24, null); // resolveTarget
        attView.setUint32(off + 32, 1, true); // loadOp = clear (1)
        attView.setUint32(off + 36, 1, true); // storeOp = store (1)
        const cv = a.clearValue || { r: 0, g: 0, b: 0, a: 1 };
        attView.setFloat64(off + 40, cv.r ?? 0, true);
        attView.setFloat64(off + 48, cv.g ?? 0, true);
        attView.setFloat64(off + 56, cv.b ?? 0, true);
        attView.setFloat64(off + 64, cv.a ?? 1, true);
    }

    let depthStencilAttachmentArr = null;
    if (descriptor.depthStencilAttachment?.view) {
        const depthBuf = new ArrayBuffer(WGPU_RENDER_PASS_DEPTH_STENCIL_ATTACHMENT_SIZE);
        const depthView = new DataView(depthBuf);
        writePtr(depthView, 0, descriptor.depthStencilAttachment.view._native);
        depthView.setUint32(8, 1, true); // clear
        depthView.setUint32(12, 1, true); // store
        depthView.setFloat32(16, descriptor.depthStencilAttachment.depthClearValue ?? 1.0, true);
        depthView.setUint32(20, descriptor.depthStencilAttachment.depthReadOnly ? 1 : 0, true);
        depthView.setUint32(24, 1, true); // clear
        depthView.setUint32(28, 1, true); // store
        depthView.setUint32(32, descriptor.depthStencilAttachment.stencilClearValue ?? 0, true);
        depthView.setUint32(36, descriptor.depthStencilAttachment.stencilReadOnly ? 1 : 0, true);
        depthStencilAttachmentArr = new Uint8Array(depthBuf);
    }

    const descBuf = new ArrayBuffer(WGPU_RENDER_PASS_DESCRIPTOR_SIZE);
    const descView = new DataView(descBuf);
    writePtr(descView, 0, null);
    writeStringView(descView, 8, null);
    descView.setBigUint64(24, BigInt(colorAttachments.length), true);
    writePtr(descView, 32, colorAttachments.length > 0 ? bunPtr(attBuf) : null);
    writePtr(descView, 40, depthStencilAttachmentArr ? bunPtr(depthStencilAttachmentArr) : null);
    writePtr(descView, 48, null); // occlusionQuerySet
    writePtr(descView, 56, null); // timestampWrites

    return { desc: new Uint8Array(descBuf), _refs: [attBuf, depthStencilAttachmentArr].filter(Boolean) };
}

// ---------------------------------------------------------------------------
// Callback trampolines for async-to-sync bridging
//
// Uses CALLBACK_MODE_ALLOW_PROCESS_EVENTS + wgpuInstanceProcessEvents polling,
// matching the N-API addon strategy. wgpuInstanceWaitAny with timed waits is
// not supported on all backends (e.g. Vulkan/Dawn).
// ---------------------------------------------------------------------------

function processEventsUntilDone(instancePtr, isDone, timeoutNs = processEventsTimeoutNs) {
    const start = Number(process.hrtime.bigint());
    while (!isDone()) {
        wgpu.symbols.wgpuInstanceProcessEvents(instancePtr);
        if (Number(process.hrtime.bigint()) - start >= timeoutNs) {
            throw new Error("[fawn-webgpu] processEvents timeout");
        }
    }
}

function shaderModuleBindings(shaderModule) {
    const fn = wgpu?.symbols?.doeNativeShaderModuleGetBindings;
    if (typeof fn !== "function" || !shaderModule?._native) return null;
    const count = Number(fn(shaderModule._native, null, 0n));
    if (count <= 0) return [];
    const raw = new ArrayBuffer(count * 20);
    fn(shaderModule._native, new Uint8Array(raw), BigInt(count));
    const view = new DataView(raw);
    const bindings = [];
    for (let index = 0; index < count; index += 1) {
        const offset = index * 20;
        const group = view.getUint32(offset + 0, true);
        const binding = view.getUint32(offset + 4, true);
        const kind = view.getUint32(offset + 8, true);
        const addrSpace = view.getUint32(offset + 12, true);
        const access = view.getUint32(offset + 16, true);
        bindings.push({
            group,
            binding,
            type: ["buffer", "sampler", "texture", "storage_texture"][kind] ?? "unknown",
            space: ["function", "private", "workgroup", "uniform", "storage", "handle"][addrSpace] ?? "unknown",
            access: ["read", "write", "read_write"][access] ?? "unknown",
        });
    }
    return bindings;
}

function requireAutoLayoutEntriesFromNative(shaderModule, visibility, path) {
    const bindings = shaderModuleBindings(shaderModule);
    if (!Array.isArray(bindings)) {
        throw new Error(`${path}: layout: "auto" requires native shader binding metadata on this package surface`);
    }
    return autoLayoutEntriesFromNativeBindings(bindings, visibility);
}

function nativeFailureMessage(prefix) {
    const detail = copyLastErrorMessage();
    return detail ? `${prefix}: ${detail}` : prefix;
}

function requestAdapterSync(instancePtr) {
    let resolvedAdapter = null;
    let resolvedStatus = null;
    let done = false;
    const cb = new JSCallback(
        (status, adapter, _msgData, _msgLen, _ud1, _ud2) => {
            resolvedStatus = status;
            resolvedAdapter = adapter;
            done = true;
        },
        { args: [FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.ptr], returns: FFIType.void },
    );
    try {
        const futureId = wgpu.symbols.doeRequestAdapterFlat(
            instancePtr, null, CALLBACK_MODE_ALLOW_PROCESS_EVENTS, cb.ptr, null, null);
        if (futureId === 0 || futureId === 0n) throw new Error("[fawn-webgpu] requestAdapter future unavailable");
        processEventsUntilDone(instancePtr, () => done);
        if (resolvedStatus !== REQUEST_ADAPTER_STATUS_SUCCESS || !resolvedAdapter) {
            throw new Error(nativeFailureMessage(`[fawn-webgpu] requestAdapter failed (status=${resolvedStatus})`));
        }
        return resolvedAdapter;
    } finally {
        cb.close();
    }
}

function requestDeviceSync(instancePtr, adapterPtr) {
    let resolvedDevice = null;
    let resolvedStatus = null;
    let done = false;
    const cb = new JSCallback(
        (status, device, _msgData, _msgLen, _ud1, _ud2) => {
            resolvedStatus = status;
            resolvedDevice = device;
            done = true;
        },
        { args: [FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.ptr], returns: FFIType.void },
    );
    try {
        const futureId = wgpu.symbols.doeRequestDeviceFlat(
            adapterPtr, null, CALLBACK_MODE_ALLOW_PROCESS_EVENTS, cb.ptr, null, null);
        if (futureId === 0 || futureId === 0n) throw new Error("[fawn-webgpu] requestDevice future unavailable");
        processEventsUntilDone(instancePtr, () => done);
        if (resolvedStatus !== REQUEST_DEVICE_STATUS_SUCCESS || !resolvedDevice) {
            throw new Error(nativeFailureMessage(`[fawn-webgpu] requestDevice failed (status=${resolvedStatus})`));
        }
        return resolvedDevice;
    } finally {
        cb.close();
    }
}

function bufferMapSync(instancePtr, bufferPtr, mode, offset, size) {
    if (wgpu.symbols.doeBufferMapSyncFlat) {
        const status = wgpu.symbols.doeBufferMapSyncFlat(
            instancePtr, bufferPtr, BigInt(mode), BigInt(offset), BigInt(size));
        if (status !== MAP_ASYNC_STATUS_SUCCESS) {
            throw new Error(nativeFailureMessage(`[fawn-webgpu] bufferMapAsync failed (status=${status})`));
        }
        return;
    }
    let mapStatus = null;
    let done = false;
    const cb = new JSCallback(
        (status, _msgData, _msgLen, _ud1, _ud2) => { mapStatus = status; done = true; },
        { args: [FFIType.u32, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.ptr], returns: FFIType.void },
    );
    try {
        const futureId = wgpu.symbols.doeBufferMapAsyncFlat(
            bufferPtr, BigInt(mode), BigInt(offset), BigInt(size),
            CALLBACK_MODE_ALLOW_PROCESS_EVENTS, cb.ptr, null, null);
        if (futureId === 0 || futureId === 0n) throw new Error("[fawn-webgpu] bufferMapAsync future unavailable");
        processEventsUntilDone(instancePtr, () => done);
        if (mapStatus !== MAP_ASYNC_STATUS_SUCCESS) {
            throw new Error(nativeFailureMessage(`[fawn-webgpu] bufferMapAsync failed (status=${mapStatus})`));
        }
    } finally {
        cb.close();
    }
}

function waitForSubmittedWorkDoneSync(instancePtr, queuePtr) {
    let queueStatus = null;
    let done = false;
    const cb = new JSCallback(
        (status, _msgData, _msgLen, _ud1, _ud2) => {
            queueStatus = status;
            done = true;
        },
        { args: [FFIType.u32, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.ptr], returns: FFIType.void },
    );
    try {
        const futureId = wgpu.symbols.doeQueueOnSubmittedWorkDoneFlat(
            queuePtr,
            CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
            cb.ptr,
            null,
            null,
        );
        if (futureId === 0 || futureId === 0n) {
            const error = new Error("[fawn-webgpu] queue work-done future unavailable");
            error.code = "DOE_QUEUE_UNAVAILABLE";
            throw error;
        }
        processEventsUntilDone(instancePtr, () => done, processEventsTimeoutNs);
        if (queueStatus !== REQUEST_DEVICE_STATUS_SUCCESS) {
            const error = new Error(nativeFailureMessage(`[fawn-webgpu] queue work-done failed (status=${queueStatus})`));
            if (queueStatus === 0) {
                error.code = "DOE_QUEUE_UNAVAILABLE";
            }
            throw error;
        }
    } finally {
        cb.close();
    }
}

// ---------------------------------------------------------------------------
// WebGPU wrapper classes — matches index.js surface exactly
// ---------------------------------------------------------------------------

const bunEncoderBackend = {
    computePassInit(pass, native) {
        pass._native = native;
    },
    computePassSetPipeline(pass, pipelineNative) {
        wgpu.symbols.wgpuComputePassEncoderSetPipeline(
            assertLiveResource(pass, "GPUComputePassEncoder.setPipeline", "GPUComputePassEncoder"),
            pipelineNative,
        );
    },
    computePassSetBindGroup(pass, index, bindGroupNative) {
        wgpu.symbols.wgpuComputePassEncoderSetBindGroup(
            assertLiveResource(pass, "GPUComputePassEncoder.setBindGroup", "GPUComputePassEncoder"),
            index,
            bindGroupNative,
            BigInt(0),
            null,
        );
    },
    computePassDispatchWorkgroups(pass, x, y, z) {
        wgpu.symbols.wgpuComputePassEncoderDispatchWorkgroups(
            assertLiveResource(pass, "GPUComputePassEncoder.dispatchWorkgroups", "GPUComputePassEncoder"),
            x,
            y,
            z,
        );
    },
    computePassDispatchWorkgroupsIndirect(pass, indirectBufferNative, indirectOffset) {
        wgpu.symbols.wgpuComputePassEncoderDispatchWorkgroupsIndirect(
            assertLiveResource(pass, "GPUComputePassEncoder.dispatchWorkgroupsIndirect", "GPUComputePassEncoder"),
            indirectBufferNative,
            BigInt(indirectOffset),
        );
    },
    computePassEnd(pass) {
        wgpu.symbols.wgpuComputePassEncoderEnd(assertLiveResource(pass, "GPUComputePassEncoder.end", "GPUComputePassEncoder"));
    },
    renderPassInit(pass, native) {
        pass._native = native;
    },
    renderPassSetPipeline(pass, pipelineNative) {
        wgpu.symbols.wgpuRenderPassEncoderSetPipeline(
            assertLiveResource(pass, "GPURenderPassEncoder.setPipeline", "GPURenderPassEncoder"),
            pipelineNative,
        );
    },
    renderPassSetBindGroup(pass, index, bindGroupNative) {
        wgpu.symbols.wgpuRenderPassEncoderSetBindGroup(
            assertLiveResource(pass, "GPURenderPassEncoder.setBindGroup", "GPURenderPassEncoder"),
            index,
            bindGroupNative,
            BigInt(0),
            null,
        );
    },
    renderPassSetVertexBuffer(pass, slot, bufferNative, offset, size) {
        wgpu.symbols.wgpuRenderPassEncoderSetVertexBuffer(
            assertLiveResource(pass, "GPURenderPassEncoder.setVertexBuffer", "GPURenderPassEncoder"),
            slot,
            bufferNative,
            BigInt(offset),
            BigInt(size ?? 0),
        );
    },
    renderPassSetIndexBuffer(pass, bufferNative, format, offset, size) {
        wgpu.symbols.wgpuRenderPassEncoderSetIndexBuffer(
            assertLiveResource(pass, "GPURenderPassEncoder.setIndexBuffer", "GPURenderPassEncoder"),
            bufferNative,
            INDEX_FORMAT_MAP[format] ?? INDEX_FORMAT_MAP.uint16,
            BigInt(offset),
            BigInt(size ?? 0),
        );
    },
    renderPassDraw(pass, vertexCount, instanceCount, firstVertex, firstInstance) {
        wgpu.symbols.wgpuRenderPassEncoderDraw(pass._native, vertexCount, instanceCount, firstVertex, firstInstance);
    },
    renderPassDrawIndexed(pass, indexCount, instanceCount, firstIndex, baseVertex, firstInstance) {
        wgpu.symbols.wgpuRenderPassEncoderDrawIndexed(
            assertLiveResource(pass, "GPURenderPassEncoder.drawIndexed", "GPURenderPassEncoder"),
            indexCount,
            instanceCount,
            firstIndex,
            baseVertex,
            firstInstance,
        );
    },
    renderPassEnd(pass) {
        wgpu.symbols.wgpuRenderPassEncoderEnd(assertLiveResource(pass, "GPURenderPassEncoder.end", "GPURenderPassEncoder"));
    },
    commandEncoderInit(encoder, native) {
        encoder._native = native;
    },
    commandEncoderBeginComputePass(encoder, _descriptor, classes) {
        const pass = wgpu.symbols.wgpuCommandEncoderBeginComputePass(
            assertLiveResource(encoder, "GPUCommandEncoder.beginComputePass", "GPUCommandEncoder"),
            null,
        );
        return new classes.DoeGPUComputePassEncoder(pass, encoder);
    },
    commandEncoderBeginRenderPass(encoder, descriptor, classes) {
        const { desc, _refs } = buildRenderPassDescriptor(descriptor);
        const pass = wgpu.symbols.wgpuCommandEncoderBeginRenderPass(
            assertLiveResource(encoder, "GPUCommandEncoder.beginRenderPass", "GPUCommandEncoder"),
            desc,
        );
        void _refs;
        return new classes.DoeGPURenderPassEncoder(pass, encoder);
    },
    commandEncoderCopyBufferToBuffer(encoder, srcNative, srcOffset, dstNative, dstOffset, size) {
        wgpu.symbols.wgpuCommandEncoderCopyBufferToBuffer(
            assertLiveResource(encoder, "GPUCommandEncoder.copyBufferToBuffer", "GPUCommandEncoder"),
            srcNative,
            BigInt(srcOffset),
            dstNative,
            BigInt(dstOffset),
            BigInt(size),
        );
    },
    commandEncoderFinish(encoder) {
        const cmd = wgpu.symbols.wgpuCommandEncoderFinish(
            assertLiveResource(encoder, "GPUCommandEncoder.finish", "GPUCommandEncoder"),
            null,
        );
        encoder._native = null;
        encoder._destroyed = true;
        return initResource({ _native: cmd }, "GPUCommandBuffer", encoder._resourceOwner);
    },
};

const {
    DoeGPUComputePassEncoder,
    DoeGPUCommandEncoder,
    DoeGPURenderPassEncoder,
} = createEncoderClasses(bunEncoderBackend);

const fullSurfaceBackend = {
    initBufferState(buffer) {
        buffer._mapMode = 0;
    },
    bufferMapAsync(wrapper, native, mode, offset, size) {
        if (wrapper._queue?.hasPendingSubmissions()) {
            waitForSubmittedWorkDoneSync(wrapper._instance, assertLiveResource(wrapper._queue, "GPUBuffer.mapAsync", "GPUQueue"));
            wrapper._queue.markSubmittedWorkDone();
        }
        bufferMapSync(wrapper._instance, native, mode, offset, size);
        wrapper._mapMode = mode;
    },
    bufferGetMappedRange(wrapper, native, offset, size) {
        const isWrite = (wrapper._mapMode & 0x0002) !== 0;
        if (isWrite) {
            const dataPtr = wgpu.symbols.wgpuBufferGetMappedRange(native, BigInt(offset), BigInt(size));
            if (!dataPtr) throw new Error("[fawn-webgpu] getMappedRange (write) returned NULL");
            return toArrayBuffer(dataPtr, 0, size);
        }
        const dataPtr = wgpu.symbols.wgpuBufferGetConstMappedRange(native, BigInt(offset), BigInt(size));
        if (!dataPtr) throw new Error("[fawn-webgpu] getMappedRange returned NULL");
        if (DOE_LIBRARY_FLAVOR === "doe-dropin") {
            return toArrayBuffer(dataPtr, 0, size);
        }
        const nativeView = toArrayBuffer(dataPtr, 0, size);
        const copy = new ArrayBuffer(size);
        new Uint8Array(copy).set(new Uint8Array(nativeView));
        return copy;
    },
    bufferUnmap(native, wrapper) {
        wgpu.symbols.wgpuBufferUnmap(native);
        wrapper._mapMode = 0;
    },
    bufferDestroy(native) {
        wgpu.symbols.wgpuBufferRelease(native);
    },
    initQueueState(queue) {
        queue._pendingSubmissions = 0;
    },
    queueHasPendingSubmissions(queue) {
        return queue._pendingSubmissions > 0;
    },
    queueMarkSubmittedWorkDone(queue) {
        queue._pendingSubmissions = 0;
    },
    queueSubmit(queue, native, buffers) {
        const ptrs = new BigUint64Array(buffers.length);
        for (let index = 0; index < buffers.length; index += 1) {
            ptrs[index] = BigInt(assertLiveResource(buffers[index], "GPUQueue.submit", "GPUCommandBuffer"));
        }
        wgpu.symbols.wgpuQueueSubmit(native, BigInt(buffers.length), ptrs);
        queue._pendingSubmissions += buffers.length;
    },
    queueWriteBuffer(_queue, native, bufferNative, bufferOffset, view) {
        wgpu.symbols.wgpuQueueWriteBuffer(native, bufferNative, BigInt(bufferOffset), view, BigInt(view.byteLength));
    },
    async queueOnSubmittedWorkDone(queue, native) {
        try {
            waitForSubmittedWorkDoneSync(queue._instance, native);
        } catch (error) {
            if (error?.code === "DOE_QUEUE_UNAVAILABLE") {
                return;
            }
            throw error;
        }
    },
    textureCreateView(_texture, native) {
        return wgpu.symbols.wgpuTextureCreateView(native, null);
    },
    textureDestroy(native) {
        wgpu.symbols.wgpuTextureRelease(native);
    },
    shaderModuleDestroy(native) {
        wgpu.symbols.wgpuShaderModuleRelease(native);
    },
    computePipelineGetBindGroupLayout(pipeline, index, classes) {
        if (pipeline._autoLayoutEntriesByGroup && process.platform === "darwin") {
            const entries = pipeline._autoLayoutEntriesByGroup.get(index) ?? [];
            return pipeline._device.createBindGroupLayout({ entries });
        }
        const native = process.platform === "darwin"
            ? wgpu.symbols.doeNativeComputePipelineGetBindGroupLayout(pipeline._native, index)
            : wgpu.symbols.wgpuComputePipelineGetBindGroupLayout(pipeline._native, index);
        return new classes.DoeGPUBindGroupLayout(native, pipeline._device);
    },
    deviceLimits,
    deviceFeatures,
    adapterLimits,
    adapterFeatures,
    preflightShaderSource,
    requireAutoLayoutEntriesFromNative,
    deviceGetQueue(native) {
        return wgpu.symbols.wgpuDeviceGetQueue(native);
    },
    deviceCreateBuffer(device, validated) {
        const descBytes = buildBufferDescriptor(validated);
        return wgpu.symbols.wgpuDeviceCreateBuffer(assertLiveResource(device, "GPUDevice.createBuffer", "GPUDevice"), descBytes);
    },
    deviceCreateShaderModule(device, code) {
        const { desc, _refs } = buildShaderModuleDescriptor(code);
        let mod;
        try {
            mod = wgpu.symbols.wgpuDeviceCreateShaderModule(assertLiveResource(device, "GPUDevice.createShaderModule", "GPUDevice"), desc);
        } catch (error) {
            throw enrichNativeCompilerError(error, "GPUDevice.createShaderModule");
        }
        void _refs;
        if (!mod) {
            throw compilerErrorFromMessage("GPUDevice.createShaderModule", nativeFailureMessage("createShaderModule failed"));
        }
        return mod;
    },
    deviceCreateComputePipeline(device, shaderNative, entryPoint, layoutNative) {
        const { desc, _refs } = buildComputePipelineDescriptor(shaderNative, entryPoint, layoutNative);
        let native;
        try {
            native = wgpu.symbols.wgpuDeviceCreateComputePipeline(assertLiveResource(device, "GPUDevice.createComputePipeline", "GPUDevice"), desc);
        } catch (error) {
            throw enrichNativeCompilerError(error, "GPUDevice.createComputePipeline");
        }
        void _refs;
        if (!native) {
            throw compilerErrorFromMessage("GPUDevice.createComputePipeline", nativeFailureMessage("createComputePipeline failed"));
        }
        return native;
    },
    deviceCreateBindGroupLayout(device, entries) {
        const { desc, _refs } = buildBindGroupLayoutDescriptor(entries);
        const native = wgpu.symbols.wgpuDeviceCreateBindGroupLayout(assertLiveResource(device, "GPUDevice.createBindGroupLayout", "GPUDevice"), desc);
        void _refs;
        return native;
    },
    deviceCreateBindGroup(device, layoutNative, entries) {
        const normalizedEntries = entries.map((entry) => ({
            binding: entry.binding,
            resource: entry.buffer
                ? { buffer: entry.buffer, offset: entry.offset ?? 0, size: entry.size }
                : entry.sampler
                    ? { sampler: entry.sampler }
                    : { textureView: entry.textureView },
        }));
        const { desc, _refs } = buildBindGroupDescriptor(layoutNative, normalizedEntries);
        const native = wgpu.symbols.wgpuDeviceCreateBindGroup(assertLiveResource(device, "GPUDevice.createBindGroup", "GPUDevice"), desc);
        void _refs;
        return native;
    },
    deviceCreatePipelineLayout(device, layouts) {
        const { desc, _refs } = buildPipelineLayoutDescriptor(layouts);
        const native = wgpu.symbols.wgpuDeviceCreatePipelineLayout(assertLiveResource(device, "GPUDevice.createPipelineLayout", "GPUDevice"), desc);
        void _refs;
        return native;
    },
    deviceCreateTexture(device, textureDescriptor, size, usage) {
        const descBytes = buildTextureDescriptor({
            ...textureDescriptor,
            usage,
            size,
            mipLevelCount: assertIntegerInRange(textureDescriptor.mipLevelCount ?? 1, "GPUDevice.createTexture", "descriptor.mipLevelCount", { min: 1, max: UINT32_MAX }),
        });
        return wgpu.symbols.wgpuDeviceCreateTexture(assertLiveResource(device, "GPUDevice.createTexture", "GPUDevice"), descBytes);
    },
    deviceCreateSampler(device, descriptor) {
        const descBytes = buildSamplerDescriptor(descriptor);
        return wgpu.symbols.wgpuDeviceCreateSampler(assertLiveResource(device, "GPUDevice.createSampler", "GPUDevice"), descBytes);
    },
    deviceCreateRenderPipeline(device, descriptor) {
        const { desc, _refs } = buildRenderPipelineDescriptor({
            layout: descriptor.layout,
            vertexModule: descriptor.vertexModule,
            vertexEntryPoint: descriptor.vertexEntryPoint,
            vertexBuffers: descriptor.vertexBuffers ?? [],
            fragmentModule: descriptor.fragmentModule,
            fragmentEntryPoint: descriptor.fragmentEntryPoint,
            colorFormat: descriptor.colorFormat,
            primitive: descriptor.primitive ?? null,
            depthStencil: descriptor.depthStencil ?? null,
            multisample: descriptor.multisample ?? null,
        });
        const native = wgpu.symbols.wgpuDeviceCreateRenderPipeline(
            assertLiveResource(device, "GPUDevice.createRenderPipeline", "GPUDevice"),
            desc,
        );
        void _refs;
        if (!native) {
            throw compilerErrorFromMessage("GPUDevice.createRenderPipeline", nativeFailureMessage("createRenderPipeline failed"));
        }
        return native;
    },
    deviceCreateCommandEncoder(device) {
        const native = wgpu.symbols.wgpuDeviceCreateCommandEncoder(assertLiveResource(device, "GPUDevice.createCommandEncoder", "GPUDevice"), null);
        return new DoeGPUCommandEncoder(native, device);
    },
    deviceDestroy(native) {
        wgpu.symbols.wgpuDeviceRelease(native);
    },
    adapterRequestDevice(adapter, _descriptor, classes) {
        const device = requestDeviceSync(adapter._instance, assertLiveResource(adapter, "GPUAdapter.requestDevice", "GPUAdapter"));
        return new classes.DoeGPUDevice(device, adapter._instance, deviceLimits(device));
    },
    adapterDestroy(native) {
        wgpu.symbols.wgpuAdapterRelease(native);
    },
    gpuRequestAdapter(gpu, _options, classes) {
        const adapter = requestAdapterSync(gpu._instance);
        return new classes.DoeGPUAdapter(adapter, gpu._instance);
    },
};

const {
    DoeGPUBuffer,
    DoeGPUQueue,
    DoeGPUTexture,
    DoeGPUTextureView,
    DoeGPUSampler,
    DoeGPURenderPipeline,
    DoeGPUShaderModule,
    DoeGPUComputePipeline,
    DoeGPUBindGroupLayout,
    DoeGPUBindGroup,
    DoeGPUPipelineLayout,
    DoeGPUDevice,
    DoeGPUAdapter,
    DoeGPU,
} = createFullSurfaceClasses({
    globals,
    backend: fullSurfaceBackend,
});

// ---------------------------------------------------------------------------
// Library initialization
// ---------------------------------------------------------------------------

let libraryLoaded = false;

function ensureLibrary() {
    if (libraryLoaded) return;
    if (!DOE_LIB_PATH) {
        throw new Error(
            "@simulatte/webgpu: libwebgpu_doe not found. Build it with `cd zig && zig build dropin` or set DOE_WEBGPU_LIB."
        );
    }
    wgpu = openLibrary(DOE_LIB_PATH);
    libraryLoaded = true;
}

// ---------------------------------------------------------------------------
// Public API — matches index.js exports exactly
// ---------------------------------------------------------------------------

export function create(createArgs = null) {
    ensureLibrary();
    const instance = wgpu.symbols.wgpuCreateInstance(null);
    return new DoeGPU(instance);
}

export function setupGlobals(target = globalThis, createArgs = null) {
    const gpu = create(createArgs);
    return setupGlobalsOnTarget(target, gpu, globals);
}

export async function requestAdapter(adapterOptions = undefined, createArgs = null) {
    return requestAdapterFromCreate(create, adapterOptions, createArgs);
}

export async function requestDevice(options = {}) {
    return requestDeviceFromRequestAdapter(requestAdapter, options);
}

export function providerInfo() {
    const flavor = DOE_LIBRARY_FLAVOR;
    return buildProviderInfo({
        loaded: !!DOE_LIB_PATH,
        loadError: !DOE_LIB_PATH ? "libwebgpu_doe not found" : "",
        defaultCreateArgs: [],
        doeNative: flavor === "doe-dropin",
        libraryFlavor: flavor,
        doeLibraryPath: DOE_LIB_PATH ?? "",
        buildMetadataSource: DOE_BUILD_METADATA.source,
        buildMetadataPath: DOE_BUILD_METADATA.path,
        leanVerifiedBuild: DOE_BUILD_METADATA.leanVerifiedBuild,
        proofArtifactSha256: DOE_BUILD_METADATA.proofArtifactSha256,
    });
}

export { createDoeRuntime, runDawnVsDoeCompare };
export { preflightShaderSource };

export function setNativeTimeoutMs(timeoutMs) {
    if (!Number.isInteger(timeoutMs) || timeoutMs < 1) {
        throw new Error("setNativeTimeoutMs: timeoutMs must be a positive integer.");
    }
    processEventsTimeoutNs = timeoutMs * 1_000_000;
}

export default {
    create,
    globals,
    setupGlobals,
    requestAdapter,
    requestDevice,
    providerInfo,
    preflightShaderSource,
    setNativeTimeoutMs,
    createDoeRuntime,
    runDawnVsDoeCompare,
};
