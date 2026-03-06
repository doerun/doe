import { create, globals, setupGlobals, requestAdapter, requestDevice, providerInfo } from "./src/bun.js";

let passed = 0;
let failed = 0;

function assert(condition, message) {
    if (condition) {
        passed++;
    } else {
        failed++;
        console.error(`FAIL: ${message}`);
    }
}

function section(name) {
    console.log(`\n--- ${name} ---`);
}

// Contract: providerInfo returns expected shape
section("providerInfo");
const info = providerInfo();
assert(info.module === "@simulatte/webgpu", "providerInfo.module");
assert(typeof info.loaded === "boolean", "providerInfo.loaded is boolean");
assert(typeof info.doeLibraryPath === "string", "providerInfo.doeLibraryPath is string");
assert(typeof info.doeNative === "boolean", "providerInfo.doeNative is boolean");
assert(typeof info.libraryFlavor === "string", "providerInfo.libraryFlavor is string");
console.log("providerInfo:", JSON.stringify(info, null, 2));

// Contract: globals has required enum objects
section("globals");
assert(globals.GPUBufferUsage != null, "globals.GPUBufferUsage");
assert(globals.GPUShaderStage != null, "globals.GPUShaderStage");
assert(globals.GPUMapMode != null, "globals.GPUMapMode");
assert(globals.GPUTextureUsage != null, "globals.GPUTextureUsage");
assert(globals.GPUBufferUsage.STORAGE === 0x0080, "GPUBufferUsage.STORAGE value");
assert(globals.GPUShaderStage.COMPUTE === 0x4, "GPUShaderStage.COMPUTE value");
assert(globals.GPUMapMode.READ === 0x0001, "GPUMapMode.READ value");

// Contract: create returns GPU object with requestAdapter
section("create");
const gpu = create();
assert(gpu != null, "create() returns non-null");
assert(typeof gpu.requestAdapter === "function", "gpu.requestAdapter is function");

// Contract: setupGlobals installs navigator.gpu
section("setupGlobals");
const target = {};
const gpu2 = setupGlobals(target);
assert(target.navigator?.gpu === gpu2, "setupGlobals installs navigator.gpu");
assert(target.GPUBufferUsage != null, "setupGlobals installs GPUBufferUsage");

// Guard: skip device-level tests if library not loaded
if (!info.loaded) {
    console.log("\nSkipping device tests: library not loaded.");
    console.log(`\nResults: ${passed} passed, ${failed} failed`);
    process.exitCode = failed > 0 ? 1 : 0;
} else {
    // Contract: requestAdapter returns adapter
    section("requestAdapter");
    const adapter = await requestAdapter();
    assert(adapter != null, "requestAdapter returns non-null");
    assert(typeof adapter.requestDevice === "function", "adapter.requestDevice is function");
    assert(adapter.features instanceof Set, "adapter.features is Set");
    assert(typeof adapter.limits === "object", "adapter.limits is object");

    // Contract: requestDevice returns device with queue and limits
    section("requestDevice");
    const device = await requestDevice();
    assert(device != null, "requestDevice returns non-null");
    assert(device.queue != null, "device.queue exists");
    assert(typeof device.queue.submit === "function", "device.queue.submit is function");
    assert(typeof device.queue.writeBuffer === "function", "device.queue.writeBuffer is function");
    assert(typeof device.limits === "object", "device.limits is object");
    assert(device.features instanceof Set, "device.features is Set");

    // Contract: createBuffer
    section("createBuffer");
    // MAP_READ can only be combined with COPY_DST per WebGPU spec
    const readbackBuf = device.createBuffer({
        size: 256,
        usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
    });
    assert(readbackBuf != null, "createBuffer returns non-null");
    assert(readbackBuf.size === 256, "buffer.size matches");
    assert(typeof readbackBuf.mapAsync === "function", "buffer.mapAsync exists");
    assert(typeof readbackBuf.getMappedRange === "function", "buffer.getMappedRange exists");
    assert(typeof readbackBuf.unmap === "function", "buffer.unmap exists");

    // Contract: queue.writeBuffer + buffer map/read round-trip
    section("writeBuffer + mapAsync round-trip");
    const testData = new Float32Array([1.0, 2.0, 3.0, 4.0]);
    device.queue.writeBuffer(readbackBuf, 0, testData);
    await readbackBuf.mapAsync(globals.GPUMapMode.READ, 0, 16);
    const mapped = readbackBuf.getMappedRange(0, 16);
    const readback = new Float32Array(mapped);
    assert(readback[0] === 1.0, "readback[0] === 1.0");
    assert(readback[1] === 2.0, "readback[1] === 2.0");
    assert(readback[2] === 3.0, "readback[2] === 3.0");
    assert(readback[3] === 4.0, "readback[3] === 4.0");
    readbackBuf.unmap();

    // Contract: createShaderModule
    section("createShaderModule");
    const shaderModule = device.createShaderModule({
        code: `@group(0) @binding(0) var<storage, read_write> data: array<f32>;
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    data[id.x] = data[id.x] * 2.0;
}`,
    });
    assert(shaderModule != null, "createShaderModule returns non-null");
    assert(shaderModule._native != null, "shaderModule._native is set");

    // Contract: createComputePipeline + getBindGroupLayout
    section("createComputePipeline");
    const pipeline = device.createComputePipeline({
        layout: "auto",
        compute: { module: shaderModule, entryPoint: "main" },
    });
    assert(pipeline != null, "createComputePipeline returns non-null");
    const bgl = pipeline.getBindGroupLayout(0);
    assert(bgl != null, "getBindGroupLayout returns non-null");

    // Contract: compute dispatch with readback via copy
    section("compute dispatch + readback");
    // STORAGE buffer for compute (cannot combine MAP_READ with STORAGE)
    const storageBuf = device.createBuffer({
        size: 256,
        usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST | globals.GPUBufferUsage.COPY_SRC,
    });
    // Readback buffer for CPU read
    const resultBuf = device.createBuffer({
        size: 256,
        usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
    });

    const bindGroup = device.createBindGroup({
        layout: bgl,
        entries: [{ binding: 0, resource: { buffer: storageBuf } }],
    });
    assert(bindGroup != null, "createBindGroup returns non-null");

    // Upload input data
    const inputData = new Float32Array([10.0, 20.0, 30.0, 40.0]);
    device.queue.writeBuffer(storageBuf, 0, inputData);

    // Dispatch compute + copy to readback
    const encoder = device.createCommandEncoder();
    assert(encoder != null, "createCommandEncoder returns non-null");
    const pass = encoder.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bindGroup);
    pass.dispatchWorkgroups(4);
    pass.end();
    encoder.copyBufferToBuffer(storageBuf, 0, resultBuf, 0, 16);
    const cmdBuf = encoder.finish();
    device.queue.submit([cmdBuf]);
    await device.queue.onSubmittedWorkDone();

    await resultBuf.mapAsync(globals.GPUMapMode.READ, 0, 16);
    const result = new Float32Array(resultBuf.getMappedRange(0, 16));
    assert(result[0] === 20.0, "compute result[0] === 20.0");
    assert(result[1] === 40.0, "compute result[1] === 40.0");
    assert(result[2] === 60.0, "compute result[2] === 60.0");
    assert(result[3] === 80.0, "compute result[3] === 80.0");
    resultBuf.unmap();

    // Contract: copyBufferToBuffer standalone
    section("copyBufferToBuffer");
    const srcBuf = device.createBuffer({
        size: 64,
        usage: globals.GPUBufferUsage.COPY_SRC | globals.GPUBufferUsage.COPY_DST,
    });
    const dstBuf = device.createBuffer({
        size: 64,
        usage: globals.GPUBufferUsage.COPY_DST | globals.GPUBufferUsage.MAP_READ,
    });
    device.queue.writeBuffer(srcBuf, 0, new Float32Array([100.0, 200.0]));
    const enc2 = device.createCommandEncoder();
    enc2.copyBufferToBuffer(srcBuf, 0, dstBuf, 0, 8);
    device.queue.submit([enc2.finish()]);
    await device.queue.onSubmittedWorkDone();
    await dstBuf.mapAsync(globals.GPUMapMode.READ, 0, 8);
    const copyResult = new Float32Array(dstBuf.getMappedRange(0, 8));
    assert(copyResult[0] === 100.0, "copy result[0] === 100.0");
    assert(copyResult[1] === 200.0, "copy result[1] === 200.0");
    dstBuf.unmap();

    // Contract: onSubmittedWorkDone
    section("onSubmittedWorkDone");
    await device.queue.onSubmittedWorkDone();
    assert(true, "onSubmittedWorkDone completed");

    // Contract: createTexture + createView
    section("createTexture");
    const texture = device.createTexture({
        size: [4, 4],
        format: "rgba8unorm",
        usage: globals.GPUTextureUsage.RENDER_ATTACHMENT,
    });
    assert(texture != null, "createTexture returns non-null");
    const texView = texture.createView();
    assert(texView != null, "createView returns non-null");

    // Contract: createSampler
    section("createSampler");
    const sampler = device.createSampler();
    assert(sampler != null, "createSampler returns non-null");

    // Contract: explicit bind group layout with typed buffer bindings
    section("explicit bind group layout + pipeline");
    const explicitBgl = device.createBindGroupLayout({
        entries: [{
            binding: 0,
            visibility: globals.GPUShaderStage.COMPUTE,
            buffer: { type: "storage" },
        }],
    });
    assert(explicitBgl != null, "createBindGroupLayout(storage) returns non-null");

    const pipelineLayout = device.createPipelineLayout({
        bindGroupLayouts: [explicitBgl],
    });
    assert(pipelineLayout != null, "createPipelineLayout returns non-null");

    // Use explicit layout in a compute pipeline to verify enum encoding is correct
    const explicitShader = device.createShaderModule({
        code: `@group(0) @binding(0) var<storage, read_write> buf: array<f32>;
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    buf[id.x] = buf[id.x] + 1.0;
}`,
    });
    const explicitPipeline = device.createComputePipeline({
        layout: pipelineLayout,
        compute: { module: explicitShader, entryPoint: "main" },
    });
    assert(explicitPipeline != null, "createComputePipeline with explicit layout returns non-null");

    // Run the pipeline with explicit layout
    const explicitBuf = device.createBuffer({
        size: 64,
        usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC | globals.GPUBufferUsage.COPY_DST,
    });
    const explicitReadback = device.createBuffer({
        size: 64,
        usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
    });
    device.queue.writeBuffer(explicitBuf, 0, new Float32Array([5.0, 6.0]));

    const explicitBg = device.createBindGroup({
        layout: explicitBgl,
        entries: [{ binding: 0, resource: { buffer: explicitBuf } }],
    });
    const enc3 = device.createCommandEncoder();
    const pass3 = enc3.beginComputePass();
    pass3.setPipeline(explicitPipeline);
    pass3.setBindGroup(0, explicitBg);
    pass3.dispatchWorkgroups(2);
    pass3.end();
    enc3.copyBufferToBuffer(explicitBuf, 0, explicitReadback, 0, 8);
    device.queue.submit([enc3.finish()]);
    await device.queue.onSubmittedWorkDone();

    await explicitReadback.mapAsync(globals.GPUMapMode.READ, 0, 8);
    const explicitResult = new Float32Array(explicitReadback.getMappedRange(0, 8));
    assert(explicitResult[0] === 6.0, "explicit layout compute result[0] === 6.0");
    assert(explicitResult[1] === 7.0, "explicit layout compute result[1] === 7.0");
    explicitReadback.unmap();

    // Also verify read-only-storage and uniform enum values don't crash
    const multiBgl = device.createBindGroupLayout({
        entries: [
            { binding: 0, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "uniform" } },
            { binding: 1, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "read-only-storage" } },
            { binding: 2, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "storage" } },
        ],
    });
    assert(multiBgl != null, "createBindGroupLayout(uniform+read-only-storage+storage) returns non-null");

    console.log(`\nResults: ${passed} passed, ${failed} failed`);
    process.exitCode = failed > 0 ? 1 : 0;
}
