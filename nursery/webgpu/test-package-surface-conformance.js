import { DOE_LIMIT_NAMES, KNOWN_FEATURES } from "./src/shared/capabilities.js";

const KNOWN_FEATURE_NAMES = new Set(KNOWN_FEATURES.map(([name]) => name));
const EXPECTED_LIMIT_KEYS = JSON.stringify([...DOE_LIMIT_NAMES].sort());

function sameKeys(object) {
    return JSON.stringify(Object.keys(object).sort());
}

export async function runSurfaceConformance(api, label = "surface") {
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
        console.log(`\n--- ${label}: ${name} ---`);
    }

    function assertPublishedLimits(limits, path) {
        assert(limits != null && typeof limits === "object", `${path} is object`);
        assert(Object.isFrozen(limits), `${path} is frozen`);
        assert(sameKeys(limits) === EXPECTED_LIMIT_KEYS, `${path} exposes the shared limit registry`);
        for (const name of DOE_LIMIT_NAMES) {
            assert(typeof limits[name] === "number" && Number.isFinite(limits[name]) && limits[name] > 0, `${path}.${name} is a positive number`);
        }
    }

    function assertPublishedFeatures(features, path) {
        assert(features instanceof Set, `${path} is Set`);
        for (const name of features) {
            assert(KNOWN_FEATURE_NAMES.has(name), `${path} only publishes registered feature names`);
        }
    }

    const { create, globals, setupGlobals, requestAdapter, requestDevice, providerInfo, preflightShaderSource } = api;

    section("providerInfo");
    const info = providerInfo();
    assert(info.module === "@simulatte/webgpu", "providerInfo.module");
    assert(typeof info.loaded === "boolean", "providerInfo.loaded is boolean");
    assert(typeof info.doeLibraryPath === "string", "providerInfo.doeLibraryPath is string");
    assert(typeof info.doeNative === "boolean", "providerInfo.doeNative is boolean");
    assert(typeof info.libraryFlavor === "string", "providerInfo.libraryFlavor is string");
    assert(typeof info.buildMetadataSource === "string", "providerInfo.buildMetadataSource is string");
    assert(typeof info.buildMetadataPath === "string", "providerInfo.buildMetadataPath is string");
    assert(info.leanVerifiedBuild === null || typeof info.leanVerifiedBuild === "boolean", "providerInfo.leanVerifiedBuild is boolean|null");
    assert(info.proofArtifactSha256 === null || typeof info.proofArtifactSha256 === "string", "providerInfo.proofArtifactSha256 is string|null");
    console.log("providerInfo:", JSON.stringify(info, null, 2));

    section("globals");
    assert(globals.GPUBufferUsage != null, "globals.GPUBufferUsage");
    assert(globals.GPUShaderStage != null, "globals.GPUShaderStage");
    assert(globals.GPUMapMode != null, "globals.GPUMapMode");
    assert(globals.GPUTextureUsage != null, "globals.GPUTextureUsage");
    assert(globals.GPUBufferUsage.STORAGE === 0x0080, "GPUBufferUsage.STORAGE value");
    assert(globals.GPUShaderStage.COMPUTE === 0x4, "GPUShaderStage.COMPUTE value");
    assert(globals.GPUMapMode.READ === 0x0001, "GPUMapMode.READ value");

    section("create");
    const gpu = create();
    assert(gpu != null, "create() returns non-null");
    assert(typeof gpu.requestAdapter === "function", "gpu.requestAdapter is function");

    section("setupGlobals");
    const target = {};
    const gpu2 = setupGlobals(target);
    assert(target.navigator?.gpu === gpu2, "setupGlobals installs navigator.gpu");
    assert(target.GPUBufferUsage != null, "setupGlobals installs GPUBufferUsage");

    if (!info.loaded) {
        console.log("\nSkipping device tests: library not loaded.");
        console.log(`\nResults: ${passed} passed, ${failed} failed`);
        return { passed, failed };
    }

    section("requestAdapter");
    const adapter = await requestAdapter();
    assert(adapter != null, "requestAdapter returns non-null");
    assert(typeof adapter.requestDevice === "function", "adapter.requestDevice is function");
    assertPublishedFeatures(adapter.features, "adapter.features");
    assertPublishedLimits(adapter.limits, "adapter.limits");
    assert(adapter.limits.maxComputeInvocationsPerWorkgroup > 0, "adapter dynamic limits are available");

    section("adapter.requestDevice");
    const deviceFromAdapter = await adapter.requestDevice();
    assert(deviceFromAdapter != null, "adapter.requestDevice returns non-null");
    assert(deviceFromAdapter.queue != null, "adapter.requestDevice queue exists");
    assertPublishedLimits(deviceFromAdapter.limits, "adapter.requestDevice.limits");
    assertPublishedFeatures(deviceFromAdapter.features, "adapter.requestDevice.features");
    assert(deviceFromAdapter.limits !== adapter.limits, "adapter.requestDevice.limits is queried separately from adapter.limits");
    assert(deviceFromAdapter.features !== adapter.features, "adapter.requestDevice.features is queried separately from adapter.features");

    section("requestDevice");
    const device = await requestDevice();
    assert(device != null, "requestDevice returns non-null");
    assert(device.queue != null, "device.queue exists");
    assert(typeof device.queue.submit === "function", "device.queue.submit is function");
    assert(typeof device.queue.writeBuffer === "function", "device.queue.writeBuffer is function");
    assertPublishedLimits(device.limits, "device.limits");
    assertPublishedFeatures(device.features, "device.features");
    assert(device.limits.maxComputeInvocationsPerWorkgroup > 0, "device dynamic limits are available");

    section("compiler-backed preflight");
    const preflight = preflightShaderSource(`
@fragment
fn main(@location(0) uv: vec2f) -> @location(0) vec4f {
    return vec4f(uv, 0.0, 1.0);
}`);
    assert(preflight.ok === true, "preflight accepts simple fragment stage");

    section("createBuffer");
    const readbackBuf = device.createBuffer({
        size: 256,
        usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
    });
    assert(readbackBuf != null, "createBuffer returns non-null");
    assert(readbackBuf.size === 256, "buffer.size matches");
    assert(typeof readbackBuf.mapAsync === "function", "buffer.mapAsync exists");
    assert(typeof readbackBuf.getMappedRange === "function", "buffer.getMappedRange exists");
    assert(typeof readbackBuf.unmap === "function", "buffer.unmap exists");

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

    section("createShaderModule");
    const shaderModule = device.createShaderModule({
        code: `@group(0) @binding(0) var<storage, read_write> data: array<f32>;
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    data[id.x] = data[id.x] * 2.0;
}`,
    });
    assert(shaderModule != null, "createShaderModule returns non-null");
    assert(shaderModule._native != null, "shaderModule._native is set");

    section("createComputePipeline");
    const pipeline = device.createComputePipeline({
        layout: "auto",
        compute: { module: shaderModule, entryPoint: "main" },
    });
    assert(pipeline != null, "createComputePipeline returns non-null");
    const bgl = pipeline.getBindGroupLayout(0);
    assert(bgl != null, "getBindGroupLayout returns non-null");

    section("subgroup createShaderModule + createComputePipeline");
    const subgroupShaderModule = device.createShaderModule({
        code: `@group(0) @binding(0) var<storage, read_write> data: array<f32>;
@compute @workgroup_size(32) fn main(@builtin(global_invocation_id) id: vec3u) {
    let base = data[id.x];
    let reduced = subgroupAdd(base);
    let prefix = subgroupExclusiveAdd(base);
    let lane = subgroupBroadcast(base, 0u);
    let shuffled = subgroupShuffle(base, 1u);
    let mixed = subgroupShuffleXor(base, 1u);
    data[id.x] = reduced + prefix + lane + shuffled + mixed;
}`,
    });
    assert(subgroupShaderModule != null, "subgroup createShaderModule returns non-null");
    const subgroupPipeline = device.createComputePipeline({
        layout: "auto",
        compute: { module: subgroupShaderModule, entryPoint: "main" },
    });
    assert(subgroupPipeline != null, "subgroup createComputePipeline returns non-null");

    section("compute dispatch + readback");
    const storageBuf = device.createBuffer({
        size: 256,
        usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST | globals.GPUBufferUsage.COPY_SRC,
    });
    const resultBuf = device.createBuffer({
        size: 256,
        usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
    });

    const bindGroup = device.createBindGroup({
        layout: bgl,
        entries: [{ binding: 0, resource: { buffer: storageBuf } }],
    });
    assert(bindGroup != null, "createBindGroup returns non-null");

    const inputData = new Float32Array([10.0, 20.0, 30.0, 40.0]);
    device.queue.writeBuffer(storageBuf, 0, inputData);

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

    section("onSubmittedWorkDone");
    await device.queue.onSubmittedWorkDone();
    assert(true, "onSubmittedWorkDone completed");

    section("createTexture");
    const texture = device.createTexture({
        size: [4, 4],
        format: "rgba8unorm",
        usage: globals.GPUTextureUsage.RENDER_ATTACHMENT,
    });
    assert(texture != null, "createTexture returns non-null");
    const texView = texture.createView();
    assert(texView != null, "createView returns non-null");

    section("createSampler");
    const sampler = device.createSampler();
    assert(sampler != null, "createSampler returns non-null");

    section("sampler + texture bind group layout");
    const sampledLayout = device.createBindGroupLayout({
        entries: [
            {
                binding: 0,
                visibility: globals.GPUShaderStage.COMPUTE,
                sampler: { type: "filtering" },
            },
            {
                binding: 1,
                visibility: globals.GPUShaderStage.COMPUTE,
                texture: { sampleType: "float", viewDimension: "2d", multisampled: false },
            },
        ],
    });
    assert(sampledLayout != null, "createBindGroupLayout(sampler+texture) returns non-null");
    const sampledBindGroup = device.createBindGroup({
        layout: sampledLayout,
        entries: [
            { binding: 0, resource: sampler },
            { binding: 1, resource: texView },
        ],
    });
    assert(sampledBindGroup != null, "createBindGroup(sampler+texture) returns non-null");

    section("createRenderPipeline");
    const vertexShaderModule = device.createShaderModule({
        code: `@vertex
fn vs_main(@location(0) position: vec2f) -> @builtin(position) vec4f {
    return vec4f(position, 0.0, 1.0);
}`,
    });
    const fragmentShaderModule = device.createShaderModule({
        code: `@group(0) @binding(0) var<uniform> tint: vec4f;

@fragment
fn fs_main() -> @location(0) vec4f {
    return tint;
}`,
    });
    const renderBindGroupLayout = device.createBindGroupLayout({
        entries: [{
            binding: 0,
            visibility: globals.GPUShaderStage.FRAGMENT,
            buffer: { type: "uniform" },
        }],
    });
    const renderPipelineLayout = device.createPipelineLayout({
        bindGroupLayouts: [renderBindGroupLayout],
    });
    const renderPipeline = device.createRenderPipeline({
        layout: renderPipelineLayout,
        vertex: {
            module: vertexShaderModule,
            entryPoint: "vs_main",
            buffers: [{
                arrayStride: Float32Array.BYTES_PER_ELEMENT * 2,
                stepMode: "vertex",
                attributes: [{
                    shaderLocation: 0,
                    offset: 0,
                    format: "float32x2",
                }],
            }],
        },
        fragment: {
            module: fragmentShaderModule,
            entryPoint: "fs_main",
            targets: [{ format: "rgba8unorm" }],
        },
        depthStencil: {
            format: "depth32float",
            depthWriteEnabled: true,
            depthCompare: "less",
        },
    });
    assert(renderPipeline != null, "createRenderPipeline returns non-null");
    const renderTarget = device.createTexture({
        size: [4, 4],
        format: "rgba8unorm",
        usage: globals.GPUTextureUsage.RENDER_ATTACHMENT,
    });
    const depthTarget = device.createTexture({
        size: [4, 4],
        format: "depth32float",
        usage: globals.GPUTextureUsage.RENDER_ATTACHMENT,
    });
    const vertexBuffer = device.createBuffer({
        size: Float32Array.BYTES_PER_ELEMENT * 6,
        usage: globals.GPUBufferUsage.VERTEX | globals.GPUBufferUsage.COPY_DST,
    });
    const indexBuffer = device.createBuffer({
        size: Uint16Array.BYTES_PER_ELEMENT * 3,
        usage: globals.GPUBufferUsage.INDEX | globals.GPUBufferUsage.COPY_DST,
    });
    const tintBuffer = device.createBuffer({
        size: Float32Array.BYTES_PER_ELEMENT * 4,
        usage: globals.GPUBufferUsage.UNIFORM | globals.GPUBufferUsage.COPY_DST,
    });
    const renderBindGroup = device.createBindGroup({
        layout: renderBindGroupLayout,
        entries: [{ binding: 0, resource: { buffer: tintBuffer } }],
    });
    device.queue.writeBuffer(vertexBuffer, 0, new Float32Array([
        0.0, 0.5,
        -0.5, -0.5,
        0.5, -0.5,
    ]));
    device.queue.writeBuffer(indexBuffer, 0, new Uint16Array([0, 1, 2]));
    device.queue.writeBuffer(tintBuffer, 0, new Float32Array([1.0, 0.0, 0.0, 1.0]));
    const renderEncoder = device.createCommandEncoder();
    const renderPass = renderEncoder.beginRenderPass({
        colorAttachments: [{
            view: renderTarget.createView(),
            clearValue: { r: 0, g: 0, b: 0, a: 1 },
        }],
        depthStencilAttachment: {
            view: depthTarget.createView(),
            depthClearValue: 1.0,
            depthReadOnly: false,
        },
    });
    renderPass.setPipeline(renderPipeline);
    renderPass.setBindGroup(0, renderBindGroup);
    renderPass.setVertexBuffer(0, vertexBuffer);
    renderPass.setIndexBuffer(indexBuffer, "uint16");
    renderPass.drawIndexed(3);
    renderPass.end();
    device.queue.submit([renderEncoder.finish()]);
    await device.queue.onSubmittedWorkDone();
    assert(true, "render pipeline submit with vertex/index/depth completed");

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

    const multiBgl = device.createBindGroupLayout({
        entries: [
            { binding: 0, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "uniform" } },
            { binding: 1, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "read-only-storage" } },
            { binding: 2, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "storage" } },
        ],
    });
    assert(multiBgl != null, "createBindGroupLayout(uniform+read-only-storage+storage) returns non-null");

    section("validation parity");
    let sawInvalidEntries = false;
    try {
        device.createBindGroupLayout({ entries: {} });
    } catch (error) {
        sawInvalidEntries = /descriptor\.entries must be an array/.test(String(error?.message));
    }
    assert(sawInvalidEntries, "createBindGroupLayout rejects non-array entries");

    let sawEmptyShader = false;
    try {
        device.createShaderModule({ code: "" });
    } catch (error) {
        sawEmptyShader = /descriptor\.code must not be empty/.test(String(error?.message));
    }
    assert(sawEmptyShader, "createShaderModule rejects empty code");

    let sawBadTexture = false;
    try {
        device.createTexture({ size: [0, 4, 1], format: "rgba8unorm", usage: globals.GPUTextureUsage.RENDER_ATTACHMENT });
    } catch (error) {
        sawBadTexture = /descriptor\.size\[0\] must be an integer/.test(String(error?.message));
    }
    assert(sawBadTexture, "createTexture rejects invalid texture extents");

    section("owner destroy parity");
    const doomedDevice = await requestDevice();
    const doomedBuffer = doomedDevice.createBuffer({
        size: 16,
        usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
    });
    doomedDevice.destroy();

    let sawOwnerDestroyedBuffer = false;
    try {
        await doomedBuffer.mapAsync(globals.GPUMapMode.READ, 0, 4);
    } catch (error) {
        sawOwnerDestroyedBuffer = /cannot be used after GPUDevice was destroyed/.test(String(error?.message));
    }
    assert(sawOwnerDestroyedBuffer, "buffer rejects use after owning device destroy");

    let sawOwnerDestroyedQueue = false;
    try {
        doomedDevice.queue.submit([]);
    } catch (error) {
        sawOwnerDestroyedQueue = /GPUQueue cannot be used after GPUDevice was destroyed/.test(String(error?.message));
    }
    assert(sawOwnerDestroyedQueue, "queue rejects use after owning device destroy");

    console.log(`\nResults: ${passed} passed, ${failed} failed`);
    return { passed, failed };
}
