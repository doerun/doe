// Integration tests for queue submission routing, serial tracking, and encoder fast-path logic.
//
// Guards against regressions in the following behaviors:
//
// 1. submitComputeDispatchCopy (synchronous Metal spin-poll path) must call markSubmittedWorkDone
//    so onSubmittedWorkDone() short-circuits instead of issuing a second queueFlush.
// 2. commandEncoderFinish returns a batched command buffer iff the encoder has exactly one
//    dispatch (t=0) followed by one copy (t=1) and was never materialized natively.
// 3. bufferMapAsync uses the direct bufferMapSync path when there are no pending submissions,
//    and flushAndMapSync only when there are.
// 4. Lazy encoder materializes to a native encoder when an operation forces it
//    (e.g. dispatchWorkgroupsIndirect, render pass, copyBufferToTexture).
// 5. Serial counters (_submittedSerial, _completedSerial) track state correctly across
//    multiple sequential submits.
// 6. Empty submit([]) is a no-op and does not increment the submitted serial.

import * as api from "../../src/node-runtime.js";

const { providerInfo, requestDevice, globals } = api;

let passed = 0;
let failed = 0;
let skipped = 0;

function assert(condition, message) {
    if (condition) {
        passed++;
    } else {
        failed++;
        console.error(`FAIL: ${message}`);
    }
}

function skip(message) {
    skipped++;
    console.log(`SKIP: ${message}`);
}

function section(name) {
    console.log(`\n--- queue-submission: ${name} ---`);
}

function isUnsupportedError(error) {
    return /unsupported|not supported|not implemented|not available|not wired|is not a function|unavailable/i.test(error?.message ?? String(error));
}

const info = providerInfo();
if (!info.loaded) {
    console.log("skip: library not loaded");
    process.exitCode = 0;
    process.exit(0);
}

const device = await requestDevice();
const { GPUBufferUsage, GPUMapMode } = globals;

const shaderModule = device.createShaderModule({
    code: `@group(0) @binding(0) var<storage, read_write> data: array<f32>;
@compute @workgroup_size(4) fn main(@builtin(global_invocation_id) id: vec3u) {
    data[id.x] = data[id.x] * 2.0;
}`,
});

const pipeline = device.createComputePipeline({
    layout: "auto",
    compute: { module: shaderModule, entryPoint: "main" },
});

const bgl = pipeline.getBindGroupLayout(0);

function makeStoragePair(size = 64) {
    return {
        storage: device.createBuffer({
            size,
            usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
        }),
        readback: device.createBuffer({
            size,
            usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST,
        }),
    };
}

function makeComputeCopyEncoder(storage, readback, x = 4) {
    const bg = device.createBindGroup({
        layout: bgl,
        entries: [{ binding: 0, resource: { buffer: storage } }],
    });
    const enc = device.createCommandEncoder();
    const pass = enc.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bg);
    pass.dispatchWorkgroups(x);
    pass.end();
    enc.copyBufferToBuffer(storage, 0, readback, 0, 16);
    return enc.finish();
}

// --- serial state: initial ---

section("queue serial state: initial");
assert(device.queue._submittedSerial === 0, "queue._submittedSerial starts at 0");
assert(device.queue._completedSerial === 0, "queue._completedSerial starts at 0");
assert(!device.queue.hasPendingSubmissions(), "hasPendingSubmissions() is false initially");

// --- empty submit: no-op ---
// Must not increment serial regardless of library path.

section("empty submit: no-op");
{
    const serialBefore = device.queue._submittedSerial;
    device.queue.submit([]);
    assert(device.queue._submittedSerial === serialBefore, "submit([]) does not increment serial");
    assert(!device.queue.hasPendingSubmissions(), "no pending submissions after submit([])");
}

// --- commandEncoderFinish: batched path ---
// compute dispatch (t=0) + copy (t=1) with no native encoder materialization
// must produce a batched command buffer for the submitComputeDispatchCopy fast path.

section("commandEncoderFinish: batched for compute+copy pair");
{
    const { storage, readback } = makeStoragePair();
    const cmdBuf = makeComputeCopyEncoder(storage, readback);
    assert(cmdBuf._batched === true, "compute+copy encoder.finish() returns _batched: true");
    assert(Array.isArray(cmdBuf._commands), "batched cmdBuf._commands is array");
    assert(cmdBuf._commands.length === 2, "batched cmdBuf._commands has exactly 2 entries");
    assert(cmdBuf._commands[0]?.t === 0, "first batched command is dispatch (t=0)");
    assert(cmdBuf._commands[1]?.t === 1, "second batched command is copy (t=1)");
    // Destroy without submitting to avoid leaking queue state.
    storage.destroy();
    readback.destroy();
}

// --- commandEncoderFinish: dispatch-only is not batched ---
// Only the compute+copy 2-command pair qualifies for the fast path.
// A dispatch-only encoder (no trailing copy) must produce a native command buffer.

section("commandEncoderFinish: dispatch-only encoder is not batched");
{
    const { storage } = makeStoragePair();
    const bg = device.createBindGroup({
        layout: bgl,
        entries: [{ binding: 0, resource: { buffer: storage } }],
    });
    const enc = device.createCommandEncoder();
    const pass = enc.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bg);
    pass.dispatchWorkgroups(4);
    pass.end();
    // No copyBufferToBuffer — encoder has one command (dispatch only).
    const cmdBuf = enc.finish();
    assert(cmdBuf._batched === false, "dispatch-only encoder is not batched");
    assert(cmdBuf._native != null, "dispatch-only encoder has native handle");
    device.queue.submit([cmdBuf]);
    await device.queue.onSubmittedWorkDone();
    storage.destroy();
}

// --- synchronous submit path marks serial done ---
// After queue.submit() with a batched compute+copy buffer, hasPendingSubmissions() must
// return false. The submitComputeDispatchCopy path is synchronous (spin-polls until GPU
// signals), so the work is complete before submit() returns. Failing to mark done here
// causes onSubmittedWorkDone() to issue a second queueFlush on already-complete work.

section("submit via sync fast path: serial marked done immediately");
{
    const { storage, readback } = makeStoragePair();
    device.queue.writeBuffer(storage, 0, new Float32Array([1.0, 2.0, 3.0, 4.0]));
    const serialBefore = device.queue._submittedSerial;
    const cmdBuf = makeComputeCopyEncoder(storage, readback);
    device.queue.submit([cmdBuf]);
    assert(device.queue._submittedSerial === serialBefore + 1, "submit increments _submittedSerial by 1");
    assert(!device.queue.hasPendingSubmissions(), "hasPendingSubmissions() false after synchronous submit");
    assert(
        device.queue._completedSerial === device.queue._submittedSerial,
        "_completedSerial equals _submittedSerial after synchronous submit",
    );
    storage.destroy();
    readback.destroy();
}

// --- onSubmittedWorkDone short-circuits after sync submit ---
// When hasPendingSubmissions() is false, onSubmittedWorkDone() must return early without
// calling queueFlush. Verified by: no error is thrown (queueFlush on an empty queue with
// Doe unavailable throws DOE_QUEUE_UNAVAILABLE) and serial does not change.

section("onSubmittedWorkDone short-circuits: no second queueFlush");
{
    const { storage, readback } = makeStoragePair();
    device.queue.writeBuffer(storage, 0, new Float32Array([5.0, 10.0, 15.0, 20.0]));
    const cmdBuf = makeComputeCopyEncoder(storage, readback);
    device.queue.submit([cmdBuf]);
    assert(!device.queue.hasPendingSubmissions(), "no pending submissions after sync submit");
    const serialBefore = device.queue._submittedSerial;
    // Must not throw and must not increment serial (short-circuit path).
    let threw = false;
    try {
        await device.queue.onSubmittedWorkDone();
    } catch {
        threw = true;
    }
    assert(!threw, "onSubmittedWorkDone() does not throw when no pending submissions");
    assert(device.queue._submittedSerial === serialBefore, "onSubmittedWorkDone() did not alter serial");
    assert(!device.queue.hasPendingSubmissions(), "hasPendingSubmissions() still false after no-op onSubmittedWorkDone");
    storage.destroy();
    readback.destroy();
}

// --- bufferMapAsync: direct map path after sync submit ---
// When hasPendingSubmissions() is false, mapAsync must use bufferMapSync (direct) not
// flushAndMapSync. Verified via correct round-trip: compute doubles input values and
// mapAsync reads back the doubled result without triggering a second queue flush.

section("bufferMapAsync: uses direct path when no pending submissions");
{
    const { storage, readback } = makeStoragePair();
    device.queue.writeBuffer(storage, 0, new Float32Array([3.0, 4.0, 5.0, 6.0]));
    const cmdBuf = makeComputeCopyEncoder(storage, readback);
    device.queue.submit([cmdBuf]);
    assert(!device.queue.hasPendingSubmissions(), "no pending submissions before mapAsync");
    await readback.mapAsync(GPUMapMode.READ, 0, 16);
    const result = new Float32Array(readback.getMappedRange(0, 16));
    assert(result[0] === 6.0, "readback[0] === 6.0 (3.0 * 2)");
    assert(result[1] === 8.0, "readback[1] === 8.0 (4.0 * 2)");
    assert(result[2] === 10.0, "readback[2] === 10.0 (5.0 * 2)");
    assert(result[3] === 12.0, "readback[3] === 12.0 (6.0 * 2)");
    readback.unmap();
    storage.destroy();
    readback.destroy();
}

// --- clearBuffer zeros a written range ---
// This covers the encoder path end to end when the backend exposes the command.

section("commandEncoder.clearBuffer zeros written bytes");
{
    const size = 16;
    const buffer = device.createBuffer({
        size,
        usage: GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
    });
    const readback = device.createBuffer({
        size,
        usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
    });
    device.queue.writeBuffer(buffer, 0, new Uint32Array([0x11111111, 0x22222222, 0x33333333, 0x44444444]));

    const enc = device.createCommandEncoder();
    if (typeof enc.clearBuffer !== "function") {
        skip("clearBuffer is not exposed on this backend");
    } else {
        try {
            enc.clearBuffer(buffer, 0, size);
            enc.copyBufferToBuffer(buffer, 0, readback, 0, size);
            device.queue.submit([enc.finish()]);
            await device.queue.onSubmittedWorkDone();
            await readback.mapAsync(GPUMapMode.READ, 0, size);
            const result = new Uint32Array(readback.getMappedRange(0, size));
            assert(result.every((value) => value === 0), "clearBuffer zeroes the copied range");
            readback.unmap();
        } catch (error) {
            if (isUnsupportedError(error)) {
                skip(`clearBuffer unavailable: ${error?.message ?? error}`);
            } else {
                failed++;
                console.error(`FAIL (unexpected error): ${error?.message ?? error}`);
            }
        }
    }

    buffer.destroy();
    readback.destroy();
}

// --- multiple sequential submits: serial monotonically increases and is always marked done ---
// Every batched compute+copy submit must leave the queue in a completed state. Over N
// sequential submits the serial must equal the initial value plus N.

section("multiple sequential submits: serial tracking");
{
    const serialStart = device.queue._submittedSerial;
    const N = 3;
    for (let i = 0; i < N; i++) {
        const { storage, readback } = makeStoragePair();
        device.queue.writeBuffer(storage, 0, new Float32Array([1.0, 2.0, 3.0, 4.0]));
        const cmdBuf = makeComputeCopyEncoder(storage, readback);
        device.queue.submit([cmdBuf]);
        assert(
            !device.queue.hasPendingSubmissions(),
            `no pending submissions after submit ${i + 1}/${N}`,
        );
        storage.destroy();
        readback.destroy();
    }
    assert(device.queue._submittedSerial === serialStart + N, `serial incremented ${N} times`);
    assert(
        device.queue._completedSerial === device.queue._submittedSerial,
        "all submits marked complete",
    );
}

// --- lazy encoder materializes on dispatchWorkgroupsIndirect ---
// The lazy encoder optimization defers native encoder creation for simple compute+copy pairs.
// dispatchWorkgroupsIndirect cannot be batched (it requires a native pass to call the
// indirect dispatch API), so it must trigger ensureNodeCommandEncoderNative(). The finished
// command buffer must be non-batched (has _native, not _commands).

section("commandEncoderFinish: dispatchWorkgroupsIndirect produces non-batched encoder");
{
    const indirectBuf = device.createBuffer({
        size: 12,
        usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST | GPUBufferUsage.INDIRECT,
    });
    // Write dispatch args: x=4, y=1, z=1.
    device.queue.writeBuffer(indirectBuf, 0, new Uint32Array([4, 1, 1]));
    await device.queue.onSubmittedWorkDone();

    const { storage, readback } = makeStoragePair();
    device.queue.writeBuffer(storage, 0, new Float32Array([2.0, 4.0, 6.0, 8.0]));
    const bg = device.createBindGroup({
        layout: bgl,
        entries: [{ binding: 0, resource: { buffer: storage } }],
    });

    const enc = device.createCommandEncoder();
    const pass = enc.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bg);
    pass.dispatchWorkgroupsIndirect(indirectBuf, 0);
    pass.end();
    enc.copyBufferToBuffer(storage, 0, readback, 0, 16);
    const cmdBuf = enc.finish();

    assert(cmdBuf._batched === false, "encoder with dispatchWorkgroupsIndirect is not batched");
    assert(cmdBuf._native != null, "encoder with dispatchWorkgroupsIndirect has native handle");

    device.queue.submit([cmdBuf]);
    await device.queue.onSubmittedWorkDone();

    await readback.mapAsync(GPUMapMode.READ, 0, 16);
    const result = new Float32Array(readback.getMappedRange(0, 16));
    assert(result[0] === 4.0, "indirect dispatch result[0] === 4.0 (2.0 * 2)");
    assert(result[1] === 8.0, "indirect dispatch result[1] === 8.0 (4.0 * 2)");
    readback.unmap();

    indirectBuf.destroy();
    storage.destroy();
    readback.destroy();
}

// --- encode+copy order matters: copy before dispatch is not batched ---
// The fast path requires dispatch (t=0) strictly before copy (t=1). Reversed order must
// not be misidentified as a fast-path candidate and must produce a native command buffer.

section("commandEncoderFinish: copy-before-dispatch order is not batched");
{
    const { storage, readback } = makeStoragePair();
    const bg = device.createBindGroup({
        layout: bgl,
        entries: [{ binding: 0, resource: { buffer: storage } }],
    });

    const enc = device.createCommandEncoder();
    // Copy first, then dispatch. This reverses the expected t=0,t=1 order in _commands.
    enc.copyBufferToBuffer(storage, 0, readback, 0, 16);
    const pass = enc.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, bg);
    pass.dispatchWorkgroups(4);
    pass.end();
    // copyBufferToBuffer on a lazy encoder pushes {t:1,...} to _commands without
    // materializing the native encoder. beginComputePass then returns a lazy pass
    // (encoder._native is still null). dispatchWorkgroups pushes {t:0,...}, leaving
    // _commands = [{t:1,...}, {t:0,...}]. encoder.finish() checks cmds[0].t === 0
    // which fails, so it falls through to ensureNodeCommandEncoderNative.
    // Key invariant: reversed order must never be misidentified as batched.
    const cmdBuf = enc.finish();
    assert(cmdBuf._batched === false, "copy-before-dispatch encoder is not batched");

    device.queue.submit([cmdBuf]);
    await device.queue.onSubmittedWorkDone();
    storage.destroy();
    readback.destroy();
}

console.log(`\nResults: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exitCode = failed > 0 ? 1 : 0;
