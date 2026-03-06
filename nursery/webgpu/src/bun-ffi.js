import { dlopen, FFIType, JSCallback, ptr as bunPtr, toArrayBuffer } from "bun:ffi";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createDoeRuntime, runDawnVsDoeCompare } from "./runtime_cli.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = resolve(__dirname, "..");

const CALLBACK_MODE_ALLOW_PROCESS_EVENTS = 2;
const REQUEST_ADAPTER_STATUS_SUCCESS = 1;
const REQUEST_DEVICE_STATUS_SUCCESS = 1;
const MAP_ASYNC_STATUS_SUCCESS = 1;
const STYPE_SHADER_SOURCE_WGSL = 0x00000002;
const PROCESS_EVENTS_TIMEOUT_NS = 5_000_000_000;

// Struct layout constants for 64-bit platforms (LP64 / LLP64).
const PTR_SIZE = 8;
const SIZE_T_SIZE = 8;

// WebGPU enum constants (standard values) — matches index.js.
export const globals = {
    GPUBufferUsage: {
        MAP_READ:      0x0001,
        MAP_WRITE:     0x0002,
        COPY_SRC:      0x0004,
        COPY_DST:      0x0008,
        INDEX:         0x0010,
        VERTEX:        0x0020,
        UNIFORM:       0x0040,
        STORAGE:       0x0080,
        INDIRECT:      0x0100,
        QUERY_RESOLVE: 0x0200,
    },
    GPUShaderStage: {
        VERTEX:   0x1,
        FRAGMENT: 0x2,
        COMPUTE:  0x4,
    },
    GPUMapMode: {
        READ:  0x0001,
        WRITE: 0x0002,
    },
    GPUTextureUsage: {
        COPY_SRC:          0x01,
        COPY_DST:          0x02,
        TEXTURE_BINDING:   0x04,
        STORAGE_BINDING:   0x08,
        RENDER_ATTACHMENT: 0x10,
    },
};

const DOE_LIMITS = Object.freeze({
    maxTextureDimension1D: 16384,
    maxTextureDimension2D: 16384,
    maxTextureDimension3D: 2048,
    maxTextureArrayLayers: 2048,
    maxBindGroups: 4,
    maxBindGroupsPlusVertexBuffers: 24,
    maxBindingsPerBindGroup: 1000,
    maxDynamicUniformBuffersPerPipelineLayout: 8,
    maxDynamicStorageBuffersPerPipelineLayout: 4,
    maxSampledTexturesPerShaderStage: 16,
    maxSamplersPerShaderStage: 16,
    maxStorageBuffersPerShaderStage: 8,
    maxStorageTexturesPerShaderStage: 4,
    maxUniformBuffersPerShaderStage: 12,
    maxUniformBufferBindingSize: 65536,
    maxStorageBufferBindingSize: 134217728,
    minUniformBufferOffsetAlignment: 256,
    minStorageBufferOffsetAlignment: 32,
    maxVertexBuffers: 8,
    maxBufferSize: 268435456,
    maxVertexAttributes: 16,
    maxVertexBufferArrayStride: 2048,
    maxInterStageShaderVariables: 16,
    maxColorAttachments: 8,
    maxColorAttachmentBytesPerSample: 32,
    maxComputeWorkgroupStorageSize: 32768,
    maxComputeInvocationsPerWorkgroup: 1024,
    maxComputeWorkgroupSizeX: 1024,
    maxComputeWorkgroupSizeY: 1024,
    maxComputeWorkgroupSizeZ: 64,
    maxComputeWorkgroupsPerDimension: 65535,
});

const DOE_FEATURES = Object.freeze(new Set(["shader-f16"]));

// ---------------------------------------------------------------------------
// Library resolution
// ---------------------------------------------------------------------------

const LIB_EXT = { darwin: "dylib", linux: "so", win32: "dll" };

function resolveDoeLibraryPath() {
    const ext = LIB_EXT[process.platform] ?? "so";
    const candidates = [
        process.env.DOE_WEBGPU_LIB,
        resolve(PACKAGE_ROOT, "prebuilds", `${process.platform}-${process.arch}`, `libdoe_webgpu.${ext}`),
        resolve(PACKAGE_ROOT, "..", "..", "zig", "zig-out", "lib", `libdoe_webgpu.${ext}`),
        resolve(process.cwd(), "zig", "zig-out", "lib", `libdoe_webgpu.${ext}`),
    ];
    for (const c of candidates) {
        if (c && existsSync(c)) return c;
    }
    return null;
}

const DOE_LIB_PATH = resolveDoeLibraryPath();
let wgpu = null;

// ---------------------------------------------------------------------------
// FFI symbol bindings
// ---------------------------------------------------------------------------

function openLibrary(path) {
    return dlopen(path, {
        // Instance
        wgpuCreateInstance:       { args: [FFIType.ptr], returns: FFIType.ptr },
        wgpuInstanceRelease:      { args: [FFIType.ptr], returns: FFIType.void },
        wgpuInstanceWaitAny:      { args: [FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.u64], returns: FFIType.u32 },
        wgpuInstanceProcessEvents: { args: [FFIType.ptr], returns: FFIType.void },

        // Adapter/Device (flat helpers)
        doeRequestAdapterFlat:    { args: [FFIType.ptr, FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr], returns: FFIType.u64 },
        doeRequestDeviceFlat:     { args: [FFIType.ptr, FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr], returns: FFIType.u64 },
        wgpuAdapterRelease:       { args: [FFIType.ptr], returns: FFIType.void },
        wgpuDeviceRelease:        { args: [FFIType.ptr], returns: FFIType.void },
        wgpuDeviceGetQueue:       { args: [FFIType.ptr], returns: FFIType.ptr },

        // Buffer
        wgpuDeviceCreateBuffer:   { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuBufferRelease:        { args: [FFIType.ptr], returns: FFIType.void },
        wgpuBufferUnmap:          { args: [FFIType.ptr], returns: FFIType.void },
        wgpuBufferGetConstMappedRange: { args: [FFIType.ptr, FFIType.u64, FFIType.u64], returns: FFIType.ptr },
        wgpuBufferGetMappedRange: { args: [FFIType.ptr, FFIType.u64, FFIType.u64], returns: FFIType.ptr },
        doeBufferMapAsyncFlat:    { args: [FFIType.ptr, FFIType.u64, FFIType.u64, FFIType.u64, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr], returns: FFIType.u64 },

        // Queue
        wgpuQueueSubmit:          { args: [FFIType.ptr, FFIType.u64, FFIType.ptr], returns: FFIType.void },
        wgpuQueueWriteBuffer:     { args: [FFIType.ptr, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.u64], returns: FFIType.void },
        wgpuQueueRelease:         { args: [FFIType.ptr], returns: FFIType.void },
        doeQueueOnSubmittedWorkDoneFlat: { args: [FFIType.ptr, FFIType.u32, FFIType.ptr, FFIType.ptr, FFIType.ptr], returns: FFIType.u64 },

        // Shader
        wgpuDeviceCreateShaderModule: { args: [FFIType.ptr, FFIType.ptr], returns: FFIType.ptr },
        wgpuShaderModuleRelease:  { args: [FFIType.ptr], returns: FFIType.void },

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
        wgpuRenderPassEncoderDraw: { args: [FFIType.ptr, FFIType.u32, FFIType.u32, FFIType.u32, FFIType.u32], returns: FFIType.void },
        wgpuRenderPassEncoderEnd: { args: [FFIType.ptr], returns: FFIType.void },
        wgpuRenderPassEncoderRelease: { args: [FFIType.ptr], returns: FFIType.void },
    });
}

// ---------------------------------------------------------------------------
// Struct marshaling helpers
//
// All layouts assume 64-bit LP64/LLP64: ptr=8, size_t=8, u64=8, u32=4.
// WGPUStringView = { data: ptr@0, length: size_t@8 } = 16 bytes.
// ---------------------------------------------------------------------------

const encoder = new TextEncoder();

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
    const buf = new ArrayBuffer(48);
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

    const wgslBuf = new ArrayBuffer(32);
    const wgslView = new DataView(wgslBuf);
    writePtr(wgslView, 0, null);
    wgslView.setUint32(8, STYPE_SHADER_SOURCE_WGSL, true);
    writeStringView(wgslView, 16, codeBytes);
    const wgslArr = new Uint8Array(wgslBuf);

    const descBuf = new ArrayBuffer(24);
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
    const buf = new ArrayBuffer(80);
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
        // sampler/texture/storageTexture sub-structs (@56..120) remain zeroed
    }

    // WGPUBindGroupLayoutDescriptor: { nextInChain:ptr@0, label:sv@8, entryCount:size_t@24, entries:ptr@32 } = 40
    const descBuf = new ArrayBuffer(40);
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
        const bufferPtr = e.resource?.buffer?._native ?? e.resource?._native ?? null;
        writePtr(entryView, off + 16, bufferPtr);
        entryView.setBigUint64(off + 24, BigInt(e.resource?.offset ?? 0), true);
        entryView.setBigUint64(off + 32, e.resource?.size !== undefined ? BigInt(e.resource.size) : WHOLE_SIZE, true);
        writePtr(entryView, off + 40, null); // sampler
        writePtr(entryView, off + 48, null); // textureView
    }

    // WGPUBindGroupDescriptor: { nextInChain:ptr@0, label:sv@8, layout:ptr@24, entryCount:size_t@32, entries:ptr@40 } = 48
    const descBuf = new ArrayBuffer(48);
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

    const descBuf = new ArrayBuffer(48);
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
    r32float: 33, rg32float: 43, rgba32float: 52, depth32float: 55,
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

    const descBuf = new ArrayBuffer(64);
    const descView = new DataView(descBuf);
    writePtr(descView, 0, null);
    writeStringView(descView, 8, null);
    descView.setBigUint64(24, BigInt(colorAttachments.length), true);
    writePtr(descView, 32, colorAttachments.length > 0 ? bunPtr(attBuf) : null);
    writePtr(descView, 40, null); // depthStencilAttachment
    writePtr(descView, 48, null); // occlusionQuerySet
    writePtr(descView, 56, null); // timestampWrites

    return { desc: new Uint8Array(descBuf), _refs: [attBuf] };
}

// ---------------------------------------------------------------------------
// Callback trampolines for async-to-sync bridging
//
// Uses CALLBACK_MODE_ALLOW_PROCESS_EVENTS + wgpuInstanceProcessEvents polling,
// matching the N-API addon strategy. wgpuInstanceWaitAny with timed waits is
// not supported on all backends (e.g. Vulkan/Dawn).
// ---------------------------------------------------------------------------

function processEventsUntilDone(instancePtr, isDone, timeoutNs = PROCESS_EVENTS_TIMEOUT_NS) {
    const start = Number(process.hrtime.bigint());
    while (!isDone()) {
        wgpu.symbols.wgpuInstanceProcessEvents(instancePtr);
        if (Number(process.hrtime.bigint()) - start >= timeoutNs) {
            throw new Error("[fawn-webgpu] processEvents timeout");
        }
    }
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
            throw new Error(`[fawn-webgpu] requestAdapter failed (status=${resolvedStatus})`);
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
            throw new Error(`[fawn-webgpu] requestDevice failed (status=${resolvedStatus})`);
        }
        return resolvedDevice;
    } finally {
        cb.close();
    }
}

function bufferMapSync(instancePtr, bufferPtr, mode, offset, size) {
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
            throw new Error(`[fawn-webgpu] bufferMapAsync failed (status=${mapStatus})`);
        }
    } finally {
        cb.close();
    }
}

const QUEUE_WORK_DONE_STATUS_SUCCESS = 1;

function queueFlush(instancePtr, queuePtr) {
    let cbStatus = null;
    let done = false;
    const cb = new JSCallback(
        (status, _msgData, _msgLen, _ud1, _ud2) => { cbStatus = status; done = true; },
        { args: [FFIType.u32, FFIType.ptr, FFIType.u64, FFIType.ptr, FFIType.ptr], returns: FFIType.void },
    );
    try {
        const futureId = wgpu.symbols.doeQueueOnSubmittedWorkDoneFlat(
            queuePtr, CALLBACK_MODE_ALLOW_PROCESS_EVENTS, cb.ptr, null, null);
        if (futureId === 0 || futureId === 0n) throw new Error("[fawn-webgpu] queueFlush future unavailable");
        processEventsUntilDone(instancePtr, () => done);
        if (cbStatus !== QUEUE_WORK_DONE_STATUS_SUCCESS) {
            throw new Error(`[fawn-webgpu] queueFlush failed (status=${cbStatus})`);
        }
    } finally {
        cb.close();
    }
}

// ---------------------------------------------------------------------------
// WebGPU wrapper classes — matches index.js surface exactly
// ---------------------------------------------------------------------------

class DoeGPUBuffer {
    constructor(native, instance, size, usage, queue) {
        this._native = native;
        this._instance = instance;
        this._queue = queue;
        this.size = size;
        this.usage = usage;
    }

    async mapAsync(mode, offset = 0, size = this.size) {
        if (this._queue) queueFlush(this._instance, this._queue);
        bufferMapSync(this._instance, this._native, mode, offset, size);
    }

    getMappedRange(offset = 0, size = this.size) {
        const dataPtr = wgpu.symbols.wgpuBufferGetConstMappedRange(this._native, BigInt(offset), BigInt(size));
        if (!dataPtr) throw new Error("[fawn-webgpu] getMappedRange returned NULL");
        const nativeView = toArrayBuffer(dataPtr, 0, size);
        const copy = new ArrayBuffer(size);
        new Uint8Array(copy).set(new Uint8Array(nativeView));
        return copy;
    }

    unmap() {
        wgpu.symbols.wgpuBufferUnmap(this._native);
    }

    destroy() {
        wgpu.symbols.wgpuBufferRelease(this._native);
        this._native = null;
    }
}

class DoeGPUComputePassEncoder {
    constructor(native) { this._native = native; }

    setPipeline(pipeline) {
        wgpu.symbols.wgpuComputePassEncoderSetPipeline(this._native, pipeline._native);
    }

    setBindGroup(index, bindGroup) {
        wgpu.symbols.wgpuComputePassEncoderSetBindGroup(this._native, index, bindGroup._native, BigInt(0), null);
    }

    dispatchWorkgroups(x, y = 1, z = 1) {
        wgpu.symbols.wgpuComputePassEncoderDispatchWorkgroups(this._native, x, y, z);
    }

    dispatchWorkgroupsIndirect(indirectBuffer, indirectOffset = 0) {
        wgpu.symbols.wgpuComputePassEncoderDispatchWorkgroupsIndirect(this._native, indirectBuffer._native, BigInt(indirectOffset));
    }

    end() {
        wgpu.symbols.wgpuComputePassEncoderEnd(this._native);
    }
}

class DoeGPUCommandEncoder {
    constructor(native) { this._native = native; }

    beginComputePass(_descriptor) {
        const pass = wgpu.symbols.wgpuCommandEncoderBeginComputePass(this._native, null);
        return new DoeGPUComputePassEncoder(pass);
    }

    beginRenderPass(descriptor) {
        const { desc, _refs } = buildRenderPassDescriptor(descriptor);
        const pass = wgpu.symbols.wgpuCommandEncoderBeginRenderPass(this._native, desc);
        void _refs;
        return new DoeGPURenderPassEncoder(pass);
    }

    copyBufferToBuffer(src, srcOffset, dst, dstOffset, size) {
        wgpu.symbols.wgpuCommandEncoderCopyBufferToBuffer(
            this._native, src._native, BigInt(srcOffset), dst._native, BigInt(dstOffset), BigInt(size));
    }

    finish() {
        const cmd = wgpu.symbols.wgpuCommandEncoderFinish(this._native, null);
        return { _native: cmd };
    }
}

class DoeGPUQueue {
    constructor(native, instance) {
        this._native = native;
        this._instance = instance;
    }

    submit(commandBuffers) {
        const ptrs = new BigUint64Array(commandBuffers.length);
        for (let i = 0; i < commandBuffers.length; i++) {
            ptrs[i] = BigInt(commandBuffers[i]._native);
        }
        wgpu.symbols.wgpuQueueSubmit(this._native, BigInt(commandBuffers.length), ptrs);
    }

    writeBuffer(buffer, bufferOffset, data, dataOffset = 0, size) {
        let view = data;
        if (dataOffset > 0 || size !== undefined) {
            const byteOffset = data.byteOffset + dataOffset * (data.BYTES_PER_ELEMENT || 1);
            const byteLength = size !== undefined
                ? size * (data.BYTES_PER_ELEMENT || 1)
                : data.byteLength - dataOffset * (data.BYTES_PER_ELEMENT || 1);
            view = new Uint8Array(data.buffer, byteOffset, byteLength);
        }
        wgpu.symbols.wgpuQueueWriteBuffer(this._native, buffer._native, BigInt(bufferOffset), view, BigInt(view.byteLength));
    }

    async onSubmittedWorkDone() {
        queueFlush(this._instance, this._native);
    }
}

class DoeGPURenderPassEncoder {
    constructor(native) { this._native = native; }

    setPipeline(pipeline) {
        wgpu.symbols.wgpuRenderPassEncoderSetPipeline(this._native, pipeline._native);
    }

    draw(vertexCount, instanceCount = 1, firstVertex = 0, firstInstance = 0) {
        wgpu.symbols.wgpuRenderPassEncoderDraw(this._native, vertexCount, instanceCount, firstVertex, firstInstance);
    }

    end() {
        wgpu.symbols.wgpuRenderPassEncoderEnd(this._native);
    }
}

class DoeGPUTexture {
    constructor(native) { this._native = native; }

    createView(_descriptor) {
        const view = wgpu.symbols.wgpuTextureCreateView(this._native, null);
        return new DoeGPUTextureView(view);
    }

    destroy() {
        wgpu.symbols.wgpuTextureRelease(this._native);
        this._native = null;
    }
}

class DoeGPUTextureView {
    constructor(native) { this._native = native; }
}

class DoeGPUSampler {
    constructor(native) { this._native = native; }
}

class DoeGPURenderPipeline {
    constructor(native) { this._native = native; }
}

class DoeGPUShaderModule {
    constructor(native) { this._native = native; }
}

class DoeGPUComputePipeline {
    constructor(native) { this._native = native; }

    getBindGroupLayout(index) {
        const layout = wgpu.symbols.wgpuComputePipelineGetBindGroupLayout(this._native, index);
        return new DoeGPUBindGroupLayout(layout);
    }
}

class DoeGPUBindGroupLayout {
    constructor(native) { this._native = native; }
}

class DoeGPUBindGroup {
    constructor(native) { this._native = native; }
}

class DoeGPUPipelineLayout {
    constructor(native) { this._native = native; }
}

class DoeGPUDevice {
    constructor(native, instance) {
        this._native = native;
        this._instance = instance;
        const q = wgpu.symbols.wgpuDeviceGetQueue(native);
        this.queue = new DoeGPUQueue(q, instance);
        this.limits = DOE_LIMITS;
        this.features = DOE_FEATURES;
    }

    createBuffer(descriptor) {
        const descBytes = buildBufferDescriptor(descriptor);
        const buf = wgpu.symbols.wgpuDeviceCreateBuffer(this._native, descBytes);
        return new DoeGPUBuffer(buf, this._instance, descriptor.size, descriptor.usage, this.queue._native);
    }

    createShaderModule(descriptor) {
        const code = descriptor.code || descriptor.source;
        if (!code) throw new Error("createShaderModule: descriptor.code is required");
        const { desc, _refs } = buildShaderModuleDescriptor(code);
        const mod = wgpu.symbols.wgpuDeviceCreateShaderModule(this._native, desc);
        void _refs;
        return new DoeGPUShaderModule(mod);
    }

    createComputePipeline(descriptor) {
        const shader = descriptor.compute?.module;
        const entryPoint = descriptor.compute?.entryPoint || "main";
        const layout = descriptor.layout === "auto" ? null : descriptor.layout;
        const { desc, _refs } = buildComputePipelineDescriptor(
            shader._native, entryPoint, layout?._native ?? null);
        const native = wgpu.symbols.wgpuDeviceCreateComputePipeline(this._native, desc);
        void _refs;
        return new DoeGPUComputePipeline(native);
    }

    async createComputePipelineAsync(descriptor) {
        return this.createComputePipeline(descriptor);
    }

    createBindGroupLayout(descriptor) {
        const entries = (descriptor.entries || []).map((e) => ({
            binding: e.binding,
            visibility: e.visibility,
            buffer: e.buffer ? {
                type: e.buffer.type || "uniform",
                hasDynamicOffset: e.buffer.hasDynamicOffset || false,
                minBindingSize: e.buffer.minBindingSize || 0,
            } : undefined,
        }));
        const { desc, _refs } = buildBindGroupLayoutDescriptor(entries);
        const native = wgpu.symbols.wgpuDeviceCreateBindGroupLayout(this._native, desc);
        void _refs;
        return new DoeGPUBindGroupLayout(native);
    }

    createBindGroup(descriptor) {
        const { desc, _refs } = buildBindGroupDescriptor(descriptor.layout._native, descriptor.entries || []);
        const native = wgpu.symbols.wgpuDeviceCreateBindGroup(this._native, desc);
        void _refs;
        return new DoeGPUBindGroup(native);
    }

    createPipelineLayout(descriptor) {
        const layouts = (descriptor.bindGroupLayouts || []).map((l) => l._native);
        const { desc, _refs } = buildPipelineLayoutDescriptor(layouts);
        const native = wgpu.symbols.wgpuDeviceCreatePipelineLayout(this._native, desc);
        void _refs;
        return new DoeGPUPipelineLayout(native);
    }

    createTexture(descriptor) {
        const descBytes = buildTextureDescriptor(descriptor);
        const native = wgpu.symbols.wgpuDeviceCreateTexture(this._native, descBytes);
        return new DoeGPUTexture(native);
    }

    createSampler(descriptor = {}) {
        const descBytes = buildSamplerDescriptor(descriptor);
        const native = wgpu.symbols.wgpuDeviceCreateSampler(this._native, descBytes);
        return new DoeGPUSampler(native);
    }

    createRenderPipeline(_descriptor) {
        // Stub: descriptor is not marshaled yet (matches Node N-API stub).
        const native = wgpu.symbols.wgpuDeviceCreateRenderPipeline(this._native, null);
        return new DoeGPURenderPipeline(native);
    }

    createCommandEncoder(_descriptor) {
        const native = wgpu.symbols.wgpuDeviceCreateCommandEncoder(this._native, null);
        return new DoeGPUCommandEncoder(native);
    }

    destroy() {
        wgpu.symbols.wgpuDeviceRelease(this._native);
        this._native = null;
    }
}

class DoeGPUAdapter {
    constructor(native, instance) {
        this._native = native;
        this._instance = instance;
        this.features = DOE_FEATURES;
        this.limits = DOE_LIMITS;
    }

    async requestDevice(_descriptor) {
        const device = requestDeviceSync(this._instance, this._native);
        return new DoeGPUDevice(device, this._instance);
    }

    destroy() {
        wgpu.symbols.wgpuAdapterRelease(this._native);
        this._native = null;
    }
}

class DoeGPU {
    constructor(instance) {
        this._instance = instance;
    }

    async requestAdapter(_options) {
        const adapter = requestAdapterSync(this._instance);
        return new DoeGPUAdapter(adapter, this._instance);
    }
}

// ---------------------------------------------------------------------------
// Library initialization
// ---------------------------------------------------------------------------

let libraryLoaded = false;

function ensureLibrary() {
    if (libraryLoaded) return;
    if (!DOE_LIB_PATH) {
        throw new Error(
            "@simulatte/webgpu: libdoe_webgpu not found. Build it with `cd fawn/zig && zig build dropin` or set DOE_WEBGPU_LIB."
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
    for (const [name, value] of Object.entries(globals)) {
        if (target[name] === undefined) {
            Object.defineProperty(target, name, {
                value,
                writable: true,
                configurable: true,
                enumerable: false,
            });
        }
    }
    const gpu = create(createArgs);
    if (typeof target.navigator === "undefined") {
        Object.defineProperty(target, "navigator", {
            value: { gpu },
            writable: true,
            configurable: true,
            enumerable: false,
        });
    } else if (!target.navigator.gpu) {
        Object.defineProperty(target.navigator, "gpu", {
            value: gpu,
            writable: true,
            configurable: true,
            enumerable: false,
        });
    }
    return gpu;
}

export async function requestAdapter(adapterOptions = undefined, createArgs = null) {
    const gpu = create(createArgs);
    return gpu.requestAdapter(adapterOptions);
}

export async function requestDevice(options = {}) {
    const createArgs = options?.createArgs ?? null;
    const adapter = await requestAdapter(options?.adapterOptions, createArgs);
    return adapter.requestDevice(options?.deviceDescriptor);
}

function libraryFlavor(libraryPath) {
    if (!libraryPath) return "missing";
    if (/libdoe_webgpu\.(so|dylib|dll)$/.test(libraryPath)) return "doe-dropin";
    if (/lib(webgpu|webgpu_dawn|wgpu_native)\.(so|dylib|dll)/.test(libraryPath)) return "delegate";
    return "unknown";
}

export function providerInfo() {
    const flavor = libraryFlavor(DOE_LIB_PATH);
    return {
        module: "@simulatte/webgpu",
        loaded: !!DOE_LIB_PATH,
        loadError: !DOE_LIB_PATH ? "libdoe_webgpu not found" : "",
        defaultCreateArgs: [],
        doeNative: flavor === "doe-dropin" && process.platform !== "linux",
        libraryFlavor: flavor,
        doeLibraryPath: DOE_LIB_PATH ?? "",
    };
}

export { createDoeRuntime, runDawnVsDoeCompare };

export default {
    create,
    globals,
    setupGlobals,
    requestAdapter,
    requestDevice,
    providerInfo,
    createDoeRuntime,
    runDawnVsDoeCompare,
};
