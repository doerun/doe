import { DOE_LIMIT_NAMES, KNOWN_FEATURES } from "../../src/shared/capabilities.js";

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

    section("adapter.info");
    const adapterInfo = adapter.info;
    assert(adapterInfo != null && typeof adapterInfo === "object", "adapter.info is object");
    assert(Object.isFrozen(adapterInfo), "adapter.info is frozen");
    assert(typeof adapterInfo.vendor === "string", "adapter.info.vendor is string");
    assert(typeof adapterInfo.architecture === "string", "adapter.info.architecture is string");
    assert(typeof adapterInfo.device === "string", "adapter.info.device is string");
    assert(typeof adapterInfo.description === "string", "adapter.info.description is string");
    assert(Number.isFinite(adapterInfo.subgroupMinSize) && adapterInfo.subgroupMinSize >= 0, "adapter.info.subgroupMinSize is finite");
    assert(Number.isFinite(adapterInfo.subgroupMaxSize) && adapterInfo.subgroupMaxSize >= 0, "adapter.info.subgroupMaxSize is finite");
    assert(adapterInfo.subgroupMaxSize >= adapterInfo.subgroupMinSize, "adapter.info subgroup range is ordered");

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
    assert(typeof shaderModule.getCompilationInfo === "function", "shaderModule.getCompilationInfo exists");
    const compilationInfo = await shaderModule.getCompilationInfo();
    assert(compilationInfo != null && typeof compilationInfo === "object", "shaderModule.getCompilationInfo returns object");
    assert(Array.isArray(compilationInfo.messages), "shaderModule.getCompilationInfo.messages is array");
    for (const [index, message] of compilationInfo.messages.entries()) {
        assert(message != null && typeof message === "object", `compilationInfo.messages[${index}] is object`);
        assert(typeof message.type === "string", `compilationInfo.messages[${index}].type is string`);
        assert(typeof message.message === "string", `compilationInfo.messages[${index}].message is string`);
    }

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

    srcBuf.destroy();
    dstBuf.destroy();
    storageBuf.destroy();
    resultBuf.destroy();
    readbackBuf.destroy();
    device.destroy?.();
    deviceFromAdapter.destroy?.();

    console.log(`\nResults: ${passed} passed, ${failed} failed`);
    return { passed, failed };
}
