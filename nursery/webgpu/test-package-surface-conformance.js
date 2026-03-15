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

    section("structured error: preflight rejection");
    const badPreflight = preflightShaderSource(`fn main() { let x = !!!; }`);
    assert(badPreflight.ok === false, "preflight rejects invalid WGSL");
    assert(typeof badPreflight.message === "string" && badPreflight.message.length > 0, "preflight rejection has message");
    assert(typeof badPreflight.stage === "string" && badPreflight.stage.length > 0, "preflight rejection has stage");
    assert(typeof badPreflight.kind === "string" && badPreflight.kind.length > 0, "preflight rejection has kind");
    assert(typeof badPreflight.line === "number" && badPreflight.line > 0, "preflight rejection has line");
    assert(typeof badPreflight.column === "number" && badPreflight.column > 0, "preflight rejection has column");

    section("structured error: createShaderModule failure");
    let shaderError = null;
    try {
        device.createShaderModule({ code: `fn main() -> @location(0) vec4f { let x = !!!; return vec4f(0.0); }` });
    } catch (e) {
        shaderError = e;
    }
    assert(shaderError instanceof Error, "createShaderModule throws on invalid WGSL");
    assert(typeof shaderError?.stage === "string" && shaderError.stage.length > 0, "shader error has stage");
    assert(typeof shaderError?.line === "number" && shaderError.line > 0, "shader error has line");
    assert(typeof shaderError?.column === "number" && shaderError.column > 0, "shader error has column");

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

    section("indirect dispatch");
    try {
        const indirectShader = device.createShaderModule({
            code: `@group(0) @binding(0) var<storage, read> src: array<f32>;
@group(0) @binding(1) var<storage, read_write> dst: array<f32>;
@compute @workgroup_size(4) fn main(@builtin(global_invocation_id) id: vec3u) {
    dst[id.x] = src[id.x] * 2.0;
}`,
        });
        const indirectPipeline = device.createComputePipeline({
            layout: "auto",
            compute: { module: indirectShader, entryPoint: "main" },
        });
        const indirectSrc = device.createBuffer({
            size: 32,
            usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST,
        });
        const indirectDst = device.createBuffer({
            size: 32,
            usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC | globals.GPUBufferUsage.COPY_DST,
        });
        const indirectReadback = device.createBuffer({
            size: 32,
            usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
        });
        const indirectArgs = device.createBuffer({
            size: 12,
            usage: globals.GPUBufferUsage.INDIRECT | globals.GPUBufferUsage.COPY_DST,
        });
        device.queue.writeBuffer(indirectSrc, 0, new Float32Array([1, 2, 3, 4, 5, 6, 7, 8]));
        device.queue.writeBuffer(indirectArgs, 0, new Uint32Array([2, 1, 1]));
        const indirectBindGroup = device.createBindGroup({
            layout: indirectPipeline.getBindGroupLayout(0),
            entries: [
                { binding: 0, resource: { buffer: indirectSrc } },
                { binding: 1, resource: { buffer: indirectDst } },
            ],
        });
        const indirectEncoder = device.createCommandEncoder();
        const indirectPass = indirectEncoder.beginComputePass();
        indirectPass.setPipeline(indirectPipeline);
        indirectPass.setBindGroup(0, indirectBindGroup);
        indirectPass.dispatchWorkgroupsIndirect(indirectArgs, 0);
        indirectPass.end();
        indirectEncoder.copyBufferToBuffer(indirectDst, 0, indirectReadback, 0, 32);
        device.queue.submit([indirectEncoder.finish()]);
        await device.queue.onSubmittedWorkDone();
        await indirectReadback.mapAsync(globals.GPUMapMode.READ, 0, 32);
        const indirectResult = new Float32Array(indirectReadback.getMappedRange(0, 32));
        assert(indirectResult[0] === 2.0, "indirect dispatch result[0] === 2.0");
        assert(indirectResult[7] === 16.0, "indirect dispatch result[7] === 16.0");
        indirectReadback.unmap();
    } catch (e) {
        assert(false, `indirect dispatch threw: ${e}`);
    }

    section("shader module destroy");
    try {
        const destroyShader = device.createShaderModule({
            code: `@group(0) @binding(0) var<storage, read_write> buf: array<f32>;
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    buf[id.x] = buf[id.x] * 4.0;
}`,
        });
        assert(destroyShader != null, "shader module for destroy created");
        const destroyPipeline = device.createComputePipeline({
            layout: "auto",
            compute: { module: destroyShader, entryPoint: "main" },
        });
        assert(destroyPipeline != null, "pipeline using shader created before destroy");
        destroyShader.destroy?.();
        assert(true, "shaderModule.destroy() did not crash");
    } catch (e) {
        assert(false, `shader module destroy threw: ${e}`);
    }

    section("texture destroy");
    try {
        const destroyTexture = device.createTexture({
            size: [4, 4],
            format: "rgba8unorm",
            usage: globals.GPUTextureUsage.RENDER_ATTACHMENT,
        });
        assert(destroyTexture != null, "texture for destroy created");
        const destroyView = destroyTexture.createView();
        assert(destroyView != null, "view from texture created");
        destroyTexture.destroy();
        assert(true, "texture.destroy() did not crash");
    } catch (e) {
        assert(false, `texture destroy threw: ${e}`);
    }

    section("multiple dispatches in same encoder");
    try {
        const multiShaderA = device.createShaderModule({
            code: `@group(0) @binding(0) var<storage, read_write> buf: array<f32>;
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    buf[id.x] = buf[id.x] + 10.0;
}`,
        });
        const multiShaderB = device.createShaderModule({
            code: `@group(0) @binding(0) var<storage, read_write> buf: array<f32>;
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    buf[id.x] = buf[id.x] * 2.0;
}`,
        });
        const multiPipelineA = device.createComputePipeline({
            layout: "auto",
            compute: { module: multiShaderA, entryPoint: "main" },
        });
        const multiPipelineB = device.createComputePipeline({
            layout: "auto",
            compute: { module: multiShaderB, entryPoint: "main" },
        });

        const multiBufA = device.createBuffer({
            size: 32,
            usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC | globals.GPUBufferUsage.COPY_DST,
        });
        const multiBufB = device.createBuffer({
            size: 32,
            usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC | globals.GPUBufferUsage.COPY_DST,
        });
        const multiReadback = device.createBuffer({
            size: 64,
            usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
        });

        device.queue.writeBuffer(multiBufA, 0, new Float32Array([1.0, 2.0]));
        device.queue.writeBuffer(multiBufB, 0, new Float32Array([3.0, 4.0]));

        const bgA = device.createBindGroup({
            layout: multiPipelineA.getBindGroupLayout(0),
            entries: [{ binding: 0, resource: { buffer: multiBufA } }],
        });
        const bgB = device.createBindGroup({
            layout: multiPipelineB.getBindGroupLayout(0),
            entries: [{ binding: 0, resource: { buffer: multiBufB } }],
        });

        const encMulti = device.createCommandEncoder();
        const passMulti = encMulti.beginComputePass();
        passMulti.setPipeline(multiPipelineA);
        passMulti.setBindGroup(0, bgA);
        passMulti.dispatchWorkgroups(2);
        passMulti.setPipeline(multiPipelineB);
        passMulti.setBindGroup(0, bgB);
        passMulti.dispatchWorkgroups(2);
        passMulti.end();
        encMulti.copyBufferToBuffer(multiBufA, 0, multiReadback, 0, 8);
        encMulti.copyBufferToBuffer(multiBufB, 0, multiReadback, 32, 8);
        device.queue.submit([encMulti.finish()]);
        await device.queue.onSubmittedWorkDone();

        await multiReadback.mapAsync(globals.GPUMapMode.READ);
        const multiResult = new Float32Array(multiReadback.getMappedRange());
        // pipelineA: +10 → [11.0, 12.0]; pipelineB: *2 → [6.0, 8.0]
        assert(multiResult[0] === 11.0, "multi-dispatch pipelineA result[0] === 11.0");
        assert(multiResult[1] === 12.0, "multi-dispatch pipelineA result[1] === 12.0");
        assert(multiResult[8] === 6.0, "multi-dispatch pipelineB result[0] === 6.0");
        assert(multiResult[9] === 8.0, "multi-dispatch pipelineB result[1] === 8.0");
        multiReadback.unmap();
    } catch (e) {
        assert(false, `multiple dispatches in same encoder threw: ${e}`);
    }

    section("multiple bind groups in explicit layout");
    try {
        const mbShader = device.createShaderModule({
            code: `@group(0) @binding(0) var<storage, read> src: array<f32>;
@group(1) @binding(0) var<storage, read_write> dst: array<f32>;
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    dst[id.x] = src[id.x] * 5.0;
}`,
        });
        const mbBgl0 = device.createBindGroupLayout({
            entries: [
                { binding: 0, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "read-only-storage" } },
            ],
        });
        const mbBgl1 = device.createBindGroupLayout({
            entries: [
                { binding: 0, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "storage" } },
            ],
        });
        const mbLayout = device.createPipelineLayout({ bindGroupLayouts: [mbBgl0, mbBgl1] });
        const mbPipeline = device.createComputePipeline({
            layout: mbLayout,
            compute: { module: mbShader, entryPoint: "main" },
        });

        const srcBuf2 = device.createBuffer({
            size: 32,
            usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST,
        });
        const dstBuf2 = device.createBuffer({
            size: 32,
            usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC | globals.GPUBufferUsage.COPY_DST,
        });
        const readback2 = device.createBuffer({
            size: 32,
            usage: globals.GPUBufferUsage.MAP_READ | globals.GPUBufferUsage.COPY_DST,
        });

        device.queue.writeBuffer(srcBuf2, 0, new Float32Array([2.0, 4.0]));

        const bg2a = device.createBindGroup({
            layout: mbBgl0,
            entries: [
                { binding: 0, resource: { buffer: srcBuf2 } },
            ],
        });
        const bg2b = device.createBindGroup({
            layout: mbBgl1,
            entries: [
                { binding: 0, resource: { buffer: dstBuf2 } },
            ],
        });

        const enc2bg = device.createCommandEncoder();
        const pass2bg = enc2bg.beginComputePass();
        pass2bg.setPipeline(mbPipeline);
        pass2bg.setBindGroup(0, bg2a);
        pass2bg.setBindGroup(1, bg2b);
        pass2bg.dispatchWorkgroups(2);
        pass2bg.end();
        enc2bg.copyBufferToBuffer(dstBuf2, 0, readback2, 0, 8);
        device.queue.submit([enc2bg.finish()]);
        await device.queue.onSubmittedWorkDone();

        await readback2.mapAsync(globals.GPUMapMode.READ, 0, 8);
        const result2bg = new Float32Array(readback2.getMappedRange(0, 8));
        assert(result2bg[0] === 10.0, "multi bind-group result[0] === 10.0");
        assert(result2bg[1] === 20.0, "multi bind-group result[1] === 20.0");
        readback2.unmap();
    } catch (e) {
        assert(false, `multiple bind groups in explicit layout threw: ${e}`);
    }

    section("buffer copy with non-zero offsets");
    try {
        const offsetSrc = device.createBuffer({
            size: 64,
            usage: globals.GPUBufferUsage.COPY_SRC | globals.GPUBufferUsage.COPY_DST,
        });
        const offsetDst = device.createBuffer({
            size: 64,
            usage: globals.GPUBufferUsage.COPY_DST | globals.GPUBufferUsage.MAP_READ,
        });
        // Write 8 floats; bytes 8..24 (floats 2..5) are the region we'll copy
        device.queue.writeBuffer(offsetSrc, 0, new Float32Array([0.0, 0.0, 7.0, 8.0, 9.0, 10.0, 0.0, 0.0]));

        const encOffset = device.createCommandEncoder();
        // copy 8 bytes from src offset 8 → dst offset 4
        encOffset.copyBufferToBuffer(offsetSrc, 8, offsetDst, 4, 8);
        device.queue.submit([encOffset.finish()]);
        await device.queue.onSubmittedWorkDone();

        await offsetDst.mapAsync(globals.GPUMapMode.READ, 0, 16);
        const offsetResult = new Float32Array(offsetDst.getMappedRange(0, 16));
        // byte offset 4 in dst = float index 1
        assert(offsetResult[1] === 7.0, "offset copy dst[1] === 7.0 (src byte 8)");
        assert(offsetResult[2] === 8.0, "offset copy dst[2] === 8.0 (src byte 12)");
        offsetDst.unmap();
    } catch (e) {
        assert(false, `buffer copy with non-zero offsets threw: ${e}`);
    }

    section("render pipeline draw");
    try {
        const rtShaderVert = device.createShaderModule({
            code: `@vertex
fn vs(@builtin(vertex_index) vi: u32) -> @builtin(position) vec4f {
    var x: f32 = 0.0;
    var y: f32 = 0.0;
    if (vi == 0u) { x = 0.0; y = 1.0; }
    else if (vi == 1u) { x = -1.0; y = -1.0; }
    else { x = 1.0; y = -1.0; }
    return vec4f(x, y, 0.0, 1.0);
}`,
        });
        const rtShaderFrag = device.createShaderModule({
            code: `@fragment
fn fs() -> @location(0) vec4f {
    return vec4f(0.0, 1.0, 0.0, 1.0);
}`,
        });
        assert(rtShaderVert != null, "render draw: vertex shader compiled");
        assert(rtShaderFrag != null, "render draw: fragment shader compiled");
        const rtPipeline = device.createRenderPipeline({
            layout: "auto",
            vertex: { module: rtShaderVert, entryPoint: "vs" },
            fragment: {
                module: rtShaderFrag,
                entryPoint: "fs",
                targets: [{ format: "rgba8unorm" }],
            },
        });
        assert(rtPipeline != null, "render draw: pipeline created");

        const rtColorTex = device.createTexture({
            size: [4, 4],
            format: "rgba8unorm",
            usage: globals.GPUTextureUsage.RENDER_ATTACHMENT | globals.GPUTextureUsage.COPY_SRC,
        });

        const rtEncoder = device.createCommandEncoder();
        const rtPass = rtEncoder.beginRenderPass({
            colorAttachments: [{
                view: rtColorTex.createView(),
                clearValue: { r: 0, g: 0, b: 0, a: 0 },
                loadOp: "clear",
                storeOp: "store",
            }],
        });
        rtPass.setPipeline(rtPipeline);
        rtPass.draw(3);
        rtPass.end();
        const rtReadback = device.createBuffer({
            size: 1024,
            usage: globals.GPUBufferUsage.COPY_DST | globals.GPUBufferUsage.MAP_READ,
        });
        rtEncoder.copyTextureToBuffer(
            { texture: rtColorTex, mipLevel: 0, origin: { x: 0, y: 0, z: 0 } },
            { buffer: rtReadback, offset: 0, bytesPerRow: 256, rowsPerImage: 4 },
            { width: 4, height: 4, depthOrArrayLayers: 1 },
        );
        device.queue.submit([rtEncoder.finish()]);
        await device.queue.onSubmittedWorkDone();
        await rtReadback.mapAsync(globals.GPUMapMode.READ, 0, 1024);
        const rtBytes = new Uint8Array(rtReadback.getMappedRange(0, 1024));
        let sawGreen = false;
        for (let i = 1; i < rtBytes.length; i += 4) {
            if (rtBytes[i] > 0) {
                sawGreen = true;
                break;
            }
        }
        assert(sawGreen, "render draw: copied texture contains non-zero green channel");
        rtReadback.unmap();
    } catch (e) {
        assert(false, `render pipeline draw threw: ${e}`);
    }

    section("resource cleanup ordering");
    try {
        const cleanupShader = device.createShaderModule({
            code: `@group(0) @binding(0) var<storage, read_write> buf: array<f32>;
@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3u) {
    buf[id.x] = buf[id.x] - 1.0;
}`,
        });
        const cleanupBgl = device.createBindGroupLayout({
            entries: [{ binding: 0, visibility: globals.GPUShaderStage.COMPUTE, buffer: { type: "storage" } }],
        });
        const cleanupLayout = device.createPipelineLayout({ bindGroupLayouts: [cleanupBgl] });
        const cleanupPipeline = device.createComputePipeline({
            layout: cleanupLayout,
            compute: { module: cleanupShader, entryPoint: "main" },
        });
        const cleanupBuf = device.createBuffer({
            size: 16,
            usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST,
        });
        const cleanupBg = device.createBindGroup({
            layout: cleanupBgl,
            entries: [{ binding: 0, resource: { buffer: cleanupBuf } }],
        });
        assert(cleanupBg != null, "cleanup: bind group created");

        // Destroy in reverse order: bind group, pipeline, shader, buffer
        cleanupBg.destroy?.();
        cleanupPipeline.destroy?.();
        cleanupShader.destroy?.();
        cleanupBuf.destroy?.();
        assert(true, "resource cleanup reverse-order destroy did not crash");
    } catch (e) {
        assert(false, `resource cleanup ordering threw: ${e}`);
    }

    section("feature publication");
    const expectedFeatures = [
        'shader-f16',
        'subgroups',
        'indirect-first-instance',
        'depth-clip-control',
        'depth32float-stencil8',
        'bgra8unorm-storage',
        'float32-filterable',
        'float32-blendable',
        'texture-compression-astc',
    ];
    for (const name of expectedFeatures) {
        assert(device.features.has(name), `device.features contains '${name}'`);
    }
    const optionalFeatures = [
        'texture-compression-bc',
        'texture-compression-bc-sliced-3d',
        'texture-compression-etc2',
        'texture-compression-astc-sliced-3d',
        'rg11b10ufloat-renderable',
        'subgroups-f16',
    ];
    for (const name of optionalFeatures) {
        if (adapter.features.has(name) || device.features.has(name)) {
            assert(adapter.features.has(name), `adapter.features contains optional '${name}' when surfaced`);
            assert(device.features.has(name), `device.features contains optional '${name}' when surfaced`);
        }
    }

    section("compressed texture and format feature exercises");
    try {
        if (device.features.has('texture-compression-bc')) {
            const bcTexture = device.createTexture({
                size: [4, 4, 1],
                format: "bc1-rgba-unorm",
                usage: globals.GPUTextureUsage.TEXTURE_BINDING | globals.GPUTextureUsage.COPY_DST,
            });
            assert(bcTexture != null, "BC compressed texture creation succeeds");
            bcTexture.destroy();
        }

        if (device.features.has('texture-compression-etc2')) {
            const etc2Texture = device.createTexture({
                size: [4, 4, 1],
                format: "etc2-rgba8unorm",
                usage: globals.GPUTextureUsage.TEXTURE_BINDING | globals.GPUTextureUsage.COPY_DST,
            });
            assert(etc2Texture != null, "ETC2 compressed texture creation succeeds");
            etc2Texture.destroy();
        }

        if (device.features.has('texture-compression-astc-sliced-3d')) {
            const astc3dTexture = device.createTexture({
                size: [4, 4, 2],
                dimension: "3d",
                format: "astc-4x4-unorm",
                usage: globals.GPUTextureUsage.TEXTURE_BINDING | globals.GPUTextureUsage.COPY_DST,
            });
            assert(astc3dTexture != null, "ASTC sliced 3D texture creation succeeds");
            astc3dTexture.destroy();
        }

        if (device.features.has('texture-compression-bc-sliced-3d')) {
            const bc3dTexture = device.createTexture({
                size: [4, 4, 2],
                dimension: "3d",
                format: "bc1-rgba-unorm",
                usage: globals.GPUTextureUsage.TEXTURE_BINDING | globals.GPUTextureUsage.COPY_DST,
            });
            assert(bc3dTexture != null, "BC sliced 3D texture creation succeeds");
            bc3dTexture.destroy();
        }

        if (device.features.has('rg11b10ufloat-renderable')) {
            const rg11b10Texture = device.createTexture({
                size: [4, 4, 1],
                format: "rg11b10ufloat",
                usage: globals.GPUTextureUsage.RENDER_ATTACHMENT | globals.GPUTextureUsage.COPY_SRC,
            });
            assert(rg11b10Texture != null, "RG11B10 renderable texture creation succeeds");
            rg11b10Texture.destroy();
        }
    } catch (e) {
        assert(false, `compressed texture / format feature exercise threw: ${e}`);
    }

    section("subgroups-f16 shader exercise");
    try {
        if (device.features.has('subgroups-f16')) {
            const subgroupF16Shader = device.createShaderModule({
                code: `enable f16;
enable subgroups;
@group(0) @binding(0) var<storage, read_write> out_buf: array<f16>;
@compute @workgroup_size(32)
fn main(@builtin(local_invocation_index) lane: u32) {
    let value: f16 = 1h;
    let sum: f16 = subgroupAdd(value);
    if (lane == 0u) {
        out_buf[0] = sum;
    }
}`,
            });
            assert(subgroupF16Shader != null, "subgroups-f16 shader module creation succeeds");
        }
    } catch (e) {
        assert(false, `subgroups-f16 shader exercise threw: ${e}`);
    }

    section("render feature compiler exercises");
    try {
        if (device.features.has('clip-distances')) {
            const clipDistances = preflightShaderSource(`
struct VSOut {
  @builtin(position) pos: vec4f,
  @builtin(clip_distances) clip: array<f32, 4>,
};

@vertex
fn vs(@builtin(vertex_index) vi: u32) -> VSOut {
  var out: VSOut;
  out.pos = vec4f(0.0, 0.0, 0.0, 1.0);
  out.clip = array<f32, 4>(1.0, 1.0, 1.0, 1.0);
  return out;
}
`);
            assert(clipDistances.ok === true, "clip-distances shader preflight succeeds");
        }

        if (device.features.has('dual-source-blending')) {
            const dualSource = preflightShaderSource(`
struct FSOut {
  @location(0) @blend_src(0) color0: vec4f,
  @location(0) @blend_src(1) color1: vec4f,
};

@fragment
fn fs() -> FSOut {
  var out: FSOut;
  out.color0 = vec4f(1.0, 0.0, 0.0, 1.0);
  out.color1 = vec4f(0.0, 1.0, 0.0, 1.0);
  return out;
}
`);
            assert(dualSource.ok === true, "dual-source-blending shader preflight succeeds");
        }
    } catch (e) {
        assert(false, `render feature compiler exercises threw: ${e}`);
    }

    section("timestamp-query exercise");
    if (device.features.has('timestamp-query')) {
        try {
            const tsQuerySet = device.createQuerySet({ type: "timestamp", count: 2 });
            assert(tsQuerySet != null, "createQuerySet(timestamp) returns non-null");
            const tsResolveBuf = device.createBuffer({
                size: 16,
                usage: globals.GPUBufferUsage.QUERY_RESOLVE | globals.GPUBufferUsage.COPY_SRC,
            });
            const tsReadbackBuf = device.createBuffer({
                size: 16,
                usage: globals.GPUBufferUsage.COPY_DST | globals.GPUBufferUsage.MAP_READ,
            });
            const tsEncoder = device.createCommandEncoder();
            tsEncoder.writeTimestamp(tsQuerySet, 0);
            tsEncoder.writeTimestamp(tsQuerySet, 1);
            tsEncoder.resolveQuerySet(tsQuerySet, 0, 2, tsResolveBuf, 0);
            tsEncoder.copyBufferToBuffer(tsResolveBuf, 0, tsReadbackBuf, 0, 16);
            device.queue.submit([tsEncoder.finish()]);
            await device.queue.onSubmittedWorkDone();
            await tsReadbackBuf.mapAsync(globals.GPUMapMode.READ, 0, 16);
            const tsData = new BigUint64Array(tsReadbackBuf.getMappedRange(0, 16));
            assert(tsData[0] > 0n || tsData[1] > 0n, "timestamp query resolved non-zero timestamps");
            tsReadbackBuf.unmap();
        } catch (e) {
            assert(false, `timestamp-query exercise threw: ${e}`);
        }
    }

    section("query set lifecycle");
    if (device.features.has('timestamp-query')) {
        try {
            const lifecycleQs = device.createQuerySet({ type: "timestamp", count: 4 });
            assert(lifecycleQs != null, "query set created");
            assert(lifecycleQs.type === "timestamp", "querySet.type === 'timestamp'");
            assert(lifecycleQs.count === 4, "querySet.count === 4");
            lifecycleQs.destroy();
            assert(true, "querySet.destroy() did not crash");
        } catch (e) {
            assert(false, `query set lifecycle threw: ${e}`);
        }
    }

    section("drawIndirect method exists");
    try {
        const diVertShader = device.createShaderModule({
            code: `@vertex
fn vs(@builtin(vertex_index) vi: u32) -> @builtin(position) vec4f {
    return vec4f(0.0, 0.0, 0.0, 1.0);
}`,
        });
        const diFragShader = device.createShaderModule({
            code: `@fragment
fn fs() -> @location(0) vec4f {
    return vec4f(1.0, 0.0, 0.0, 1.0);
}`,
        });
        const diPipeline = device.createRenderPipeline({
            layout: "auto",
            vertex: { module: diVertShader, entryPoint: "vs" },
            fragment: {
                module: diFragShader,
                entryPoint: "fs",
                targets: [{ format: "rgba8unorm" }],
            },
        });
        const diColorTex = device.createTexture({
            size: [4, 4],
            format: "rgba8unorm",
            usage: globals.GPUTextureUsage.RENDER_ATTACHMENT,
        });
        const diEncoder = device.createCommandEncoder();
        const diPass = diEncoder.beginRenderPass({
            colorAttachments: [{
                view: diColorTex.createView(),
                clearValue: { r: 0, g: 0, b: 0, a: 0 },
                loadOp: "clear",
                storeOp: "store",
            }],
        });
        diPass.setPipeline(diPipeline);
        assert(typeof diPass.drawIndirect === "function", "GPURenderPassEncoder.drawIndirect is a function");
        diPass.end();
        device.queue.submit([diEncoder.finish()]);
        await device.queue.onSubmittedWorkDone();
    } catch (e) {
        assert(false, `drawIndirect method check threw: ${e}`);
    }

    section("adapter destroy");
    try {
        adapter.destroy?.();
        assert(true, "adapter.destroy() did not crash");
    } catch (e) {
        assert(false, `adapter.destroy() threw: ${e}`);
    }

    console.log(`\nResults: ${passed} passed, ${failed} failed`);
    return { passed, failed };
}
