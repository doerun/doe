import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_DIR = dirname(fileURLToPath(import.meta.url));
const DOE_PACKAGE_DIR = resolve(PACKAGE_DIR, "..", "webgpu-doe");
const EXAMPLE_EXPECTATIONS = [
  {
    relativePath: join("examples", "direct-webgpu", "request-device.js"),
    expected: {
      createBuffer: true,
      createComputePipeline: true,
      createRenderPipeline: true,
      writeBuffer: true,
    },
  },
  {
    relativePath: join("examples", "direct-webgpu", "compute-dispatch.js"),
    expected: [2, 4, 6, 8],
  },
  {
    relativePath: join("examples", "direct-webgpu", "explicit-bind-group.js"),
    expected: [4, 8, 12, 16],
  },
  {
    relativePath: join("examples", "doe-api", "buffers-readback.js"),
    expected: [1, 2, 3, 4],
  },
  {
    relativePath: join("examples", "doe-api", "kernel-run.js"),
    expected: [2, 4, 6, 8],
  },
  {
    relativePath: join("examples", "doe-api", "kernel-create-and-dispatch.js"),
    expected: [5, 10, 15, 20],
  },
  {
    relativePath: join("examples", "doe-api", "compute-one-shot.js"),
    expected: [3, 6, 9, 12],
  },
  {
    relativePath: join("examples", "doe-api", "compute-one-shot-like-input.js"),
    expected: [2, 4, 6, 8],
  },
  {
    relativePath: join("examples", "doe-api", "compute-one-shot-multiple-inputs.js"),
    expected: [11, 22, 33, 44],
  },
  {
    relativePath: join("examples", "doe-api", "compute-one-shot-matmul.js"),
    expected: [110.8959, 110.7738, 110.5339, 111.1176, 110.7602, 110.3439, 110.8099, 111.1584],
  },
];

function npm_json(args, cwd) {
  return JSON.parse(execFileSync("npm", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }));
}

function main() {
  const temp_root = mkdtempSync(join(os.tmpdir(), "simulatte-webgpu-pack-"));
  const consumer_dir = join(temp_root, "consumer");
  let tarball_path = null;
  let doe_tarball_path = null;

  try {
    const pack_output = npm_json(["pack", "--json"], PACKAGE_DIR);
    const tarball_name = pack_output[0]?.filename;
    assert.ok(tarball_name, "npm pack --json did not produce a tarball filename");

    tarball_path = resolve(PACKAGE_DIR, tarball_name);
    if (existsSync(join(DOE_PACKAGE_DIR, "package.json"))) {
      const doe_pack_output = npm_json(["pack", "--json"], DOE_PACKAGE_DIR);
      const doe_tarball_name = doe_pack_output[0]?.filename;
      assert.ok(doe_tarball_name, "npm pack --json did not produce a Doe tarball filename");
      doe_tarball_path = resolve(DOE_PACKAGE_DIR, doe_tarball_name);
    }
    mkdirSync(consumer_dir, { recursive: true });
    writeFileSync(join(consumer_dir, "package.json"), JSON.stringify({
      name: "simulatte-webgpu-pack-test",
      private: true,
      type: "module",
    }, null, 2));

    const install_args = ["install", "--ignore-scripts"];
    if (doe_tarball_path) {
      install_args.push(doe_tarball_path);
    }
    install_args.push(tarball_path);

    execFileSync("npm", install_args, {
      cwd: consumer_dir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });

    const installed_package_dir = join(
      consumer_dir,
      "node_modules",
      "@simulatte",
      "webgpu",
    );
    const installed_package = JSON.parse(readFileSync(join(
      installed_package_dir,
      "package.json",
    ), "utf8"));

    for (const entry of readdirSync(join(installed_package_dir, "prebuilds"), { withFileTypes: true })) {
      if (!entry.isDirectory()) {
        continue;
      }
      const metadata_path = join(installed_package_dir, "prebuilds", entry.name, "metadata.json");
      if (!existsSync(metadata_path)) {
        continue;
      }
      const prebuild_metadata = JSON.parse(readFileSync(metadata_path, "utf8"));
      assert.equal(
        prebuild_metadata.package,
        installed_package.name,
        `prebuild metadata package mismatch for ${entry.name}`,
      );
      assert.equal(
        prebuild_metadata.packageVersion,
        installed_package.version,
        `prebuild metadata packageVersion mismatch for ${entry.name}`,
      );
    }

    assert.ok(installed_package.exports["./compute"], "packed tarball is missing ./compute export");
    assert.ok(installed_package.exports["./full"], "packed tarball is missing ./full export");
    const doe_docs_path = join(installed_package_dir, "docs", "doe-api-reference.html");
    assert.ok(existsSync(doe_docs_path), "packed tarball is missing docs/doe-api-reference.html");
    const doe_docs_html = readFileSync(doe_docs_path, "utf8");
    assert.match(doe_docs_html, /Doe API, as code and as contract\./);
    assert.match(doe_docs_html, /Run example/);
    for (const example of EXAMPLE_EXPECTATIONS) {
      assert.ok(
        existsSync(join(installed_package_dir, example.relativePath)),
        `packed tarball is missing example ${example.relativePath}`,
      );
    }

    const import_check = `
      import assert from "node:assert/strict";
      const full = await import("@simulatte/webgpu");
      const compute = await import("@simulatte/webgpu/compute");
      const explicitFull = await import("@simulatte/webgpu/full");

      assert.equal(typeof full.requestDevice, "function");
      assert.equal(typeof full.providerInfo, "function");
      assert.equal(typeof full.preflightShaderSource, "function");
      assert.equal(typeof full.doe.requestDevice, "function");
      assert.equal(typeof full.doe.bind, "function");
      assert.equal("buffers" in full.doe, false);
      assert.equal("buffer" in full.doe, false);
      assert.equal("kernel" in full.doe, false);
      assert.equal("compute" in full.doe, false);

      assert.equal(typeof compute.requestDevice, "function");
      assert.equal(typeof compute.doe.requestDevice, "function");
      assert.equal("buffers" in compute.doe, false);
      assert.equal("buffer" in compute.doe, false);
      assert.equal("kernel" in compute.doe, false);
      assert.equal("compute" in compute.doe, false);

      assert.equal(typeof explicitFull.requestDevice, "function");
      assert.equal(typeof explicitFull.doe.bind, "function");

      const gpu = await compute.doe.requestDevice();
      assert.ok(gpu.device.limits.maxComputeInvocationsPerWorkgroup > 0);
      assert.equal(typeof gpu.buffer.create, "function");
      assert.equal(typeof gpu.kernel.run, "function");
      assert.equal(typeof gpu.kernel.create, "function");
      assert.equal(typeof gpu.compute, "function");
      const input = gpu.buffer.create({ data: new Float32Array([1, 2, 3, 4]) });
      const output = gpu.buffer.create({ size: input.size, usage: "storageReadWrite" });

      await gpu.kernel.run({
        code: \`
          @group(0) @binding(0) var<storage, read> src: array<f32>;
          @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

          @compute @workgroup_size(4)
          fn main(@builtin(global_invocation_id) gid: vec3u) {
            let i = gid.x;
            dst[i] = src[i] * 2.0;
          }
        \`,
        bindings: [input, output],
        workgroups: 1,
      });

      const result = await gpu.buffer.read({ buffer: output, type: Float32Array });
      assert.deepEqual(Array.from(result), [2, 4, 6, 8]);

      const oneShot = await gpu.compute({
        code: \`
          @group(0) @binding(0) var<storage, read> src: array<f32>;
          @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

          @compute @workgroup_size(4)
          fn main(@builtin(global_invocation_id) gid: vec3u) {
            let i = gid.x;
            dst[i] = src[i] * 3.0;
          }
        \`,
        inputs: [new Float32Array([1, 2, 3, 4])],
        output: {
          type: Float32Array,
        },
        workgroups: 1,
      });
      assert.deepEqual(Array.from(oneShot), [3, 6, 9, 12]);

      const fullDevice = await full.requestDevice();
      assert.ok(fullDevice.limits.maxComputeInvocationsPerWorkgroup > 0);
      const preflightAccepted = full.preflightShaderSource(\`
        @fragment
        fn main(@location(0) uv: vec2f) -> @location(0) vec4f {
          return vec4f(uv, 0.0, 1.0);
        }
      \`);
      assert.equal(preflightAccepted.ok, true);

      // --- structured error fields: preflight rejection ---
      const preflightRejected = full.preflightShaderSource(\`
        fn main() { let x = !!!; }
      \`);
      assert.equal(preflightRejected.ok, false);
      assert.ok(preflightRejected.message.length > 0, "preflight rejection should have a message");
      assert.equal(typeof preflightRejected.stage, "string");
      assert.ok(preflightRejected.stage.length > 0, "preflight rejection should have stage");
      assert.equal(typeof preflightRejected.kind, "string");
      assert.ok(preflightRejected.kind.length > 0, "preflight rejection should have kind");
      assert.equal(typeof preflightRejected.line, "number");
      assert.ok(preflightRejected.line > 0, "preflight rejection should have line");
      assert.equal(typeof preflightRejected.column, "number");
      assert.ok(preflightRejected.column > 0, "preflight rejection should have column");

      // --- structured error fields: createShaderModule failure ---
      try {
        fullDevice.createShaderModule({
          code: \`fn main() -> @location(0) vec4f { let x = !!!; return vec4f(0); }\`,
        });
        assert.fail("createShaderModule should throw on invalid WGSL");
      } catch (shaderError) {
        assert.ok(shaderError instanceof Error, "shader error should be an Error");
        assert.ok(shaderError.message.length > 0, "shader error should have a message");
        assert.equal(typeof shaderError.stage, "string");
        assert.ok(shaderError.stage.length > 0, "shader error should have stage");
        assert.equal(typeof shaderError.line, "number");
        assert.ok(shaderError.line > 0, "error.line should be positive");
        assert.equal(typeof shaderError.column, "number");
        assert.ok(shaderError.column > 0, "error.column should be positive");
      }

      const subgroupShader = fullDevice.createShaderModule({
        code: \`
          @group(0) @binding(0) var<storage, read_write> data: array<f32>;

          @compute @workgroup_size(32)
          fn main(@builtin(global_invocation_id) gid: vec3u) {
            let base = data[gid.x];
            let reduced = subgroupAdd(base);
            let prefix = subgroupExclusiveAdd(base);
            let lane = subgroupBroadcast(base, 0u);
            let shuffled = subgroupShuffle(base, 1u);
            let mixed = subgroupShuffleXor(base, 1u);
            data[gid.x] = reduced + prefix + lane + shuffled + mixed;
          }
        \`,
      });
      const subgroupPipeline = fullDevice.createComputePipeline({
        layout: "auto",
        compute: { module: subgroupShader, entryPoint: "main" },
      });
      assert.ok(subgroupPipeline);

      const raw = gpu.device.createBuffer({
        size: input.size,
        usage: compute.globals.GPUBufferUsage.STORAGE | compute.globals.GPUBufferUsage.COPY_DST,
      });
      await assert.rejects(
        gpu.kernel.run({
          code: \`
            @group(0) @binding(0) var<storage, read> src: array<f32>;

            @compute @workgroup_size(1)
            fn main(@builtin(global_invocation_id) gid: vec3u) {
              _ = src[gid.x];
            }
          \`,
          bindings: [raw],
          workgroups: 1,
        }),
        /Doe binding access is required/
      );

      const oneShotRawUsage = await gpu.compute({
        code: \`
          @group(0) @binding(0) var<storage, read> src: array<f32>;
          @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

          @compute @workgroup_size(1)
          fn main(@builtin(global_invocation_id) gid: vec3u) {
            dst[gid.x] = src[gid.x];
          }
        \`,
        inputs: [{
          data: new Float32Array([1]),
          usage: /** @type {any} */ (compute.globals.GPUBufferUsage.STORAGE | compute.globals.GPUBufferUsage.COPY_DST),
          access: "storageRead",
        }],
        output: {
          type: Float32Array,
          usage: /** @type {any} */ (compute.globals.GPUBufferUsage.STORAGE | compute.globals.GPUBufferUsage.COPY_SRC),
          access: "storageReadWrite",
        },
        workgroups: [1, 1],
      });
      assert.deepEqual(Array.from(oneShotRawUsage), [1]);

      await assert.rejects(
        gpu.compute({
          code: \`
            @group(0) @binding(0) var<storage, read> src: array<f32>;
            @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

            @compute @workgroup_size(1)
            fn main(@builtin(global_invocation_id) gid: vec3u) {
              dst[gid.x] = src[gid.x];
            }
          \`,
          inputs: [{
            data: new Float32Array([1]),
            usage: /** @type {any} */ (compute.globals.GPUBufferUsage.STORAGE),
          }],
          output: {
            type: Float32Array,
          },
          workgroups: [1, 1],
        }),
        /accepts raw numeric usage flags only when explicit access is also provided/
      );

      const destroyedBuffer = gpu.buffer.create({
        size: 16,
        usage: "storageReadWrite",
      });
      destroyedBuffer.destroy();
      await assert.rejects(
        destroyedBuffer.mapAsync(compute.globals.GPUMapMode.READ),
        /GPUBuffer\\.mapAsync: GPUBuffer was destroyed/
      );
      assert.throws(
        () => gpu.device.queue.writeBuffer(destroyedBuffer, 0, new Uint8Array([1, 2, 3, 4])),
        /GPUQueue\\.writeBuffer: GPUBuffer was destroyed/
      );

      const sampledTexture = fullDevice.createTexture({
        size: [4, 4, 1],
        format: 'rgba8unorm',
        usage: full.globals.GPUTextureUsage.TEXTURE_BINDING,
      });
      const sampledView = sampledTexture.createView();
      const sampledSampler = fullDevice.createSampler();
      const sampledLayout = fullDevice.createBindGroupLayout({
        entries: [
          {
            binding: 0,
            visibility: full.globals.GPUShaderStage.COMPUTE,
            sampler: { type: 'filtering' },
          },
          {
            binding: 1,
            visibility: full.globals.GPUShaderStage.COMPUTE,
            texture: { sampleType: 'float', viewDimension: '2d', multisampled: false },
          },
        ],
      });
      const sampledGroup = fullDevice.createBindGroup({
        layout: sampledLayout,
        entries: [
          { binding: 0, resource: sampledSampler },
          { binding: 1, resource: sampledView },
        ],
      });
      assert.ok(sampledLayout);
      assert.ok(sampledGroup);

      // --- doe.bind(device) ---
      const bound = compute.doe.bind(gpu.device);
      assert.ok(bound.device === gpu.device);
      const boundInput = bound.buffer.create({ data: new Float32Array([10, 20]) });
      await bound.kernel.run({
        code: \`
          @group(0) @binding(0) var<storage, read> src: array<f32>;
          @group(0) @binding(1) var<storage, read_write> dst: array<f32>;
          @compute @workgroup_size(2)
          fn main(@builtin(global_invocation_id) gid: vec3u) {
            dst[gid.x] = src[gid.x] + 1.0;
          }
        \`,
        bindings: [boundInput, bound.buffer.create({ size: boundInput.size, usage: "storageReadWrite" })],
        workgroups: 1,
      });

      // --- multi-device doe.bind(device) isolation ---
      const multiAdapter = await compute.requestAdapter();
      assert.ok(multiAdapter, "multi-device test requires an adapter");
      const deviceA = await multiAdapter.requestDevice();
      const deviceB = await multiAdapter.requestDevice();
      assert.notEqual(deviceA, deviceB, "requestDevice() should return distinct device objects");
      assert.notEqual(deviceA.queue, deviceB.queue, "distinct devices should expose distinct queues");

      const gpuA = compute.doe.bind(deviceA);
      const gpuB = compute.doe.bind(deviceB);
      assert.ok(gpuA.device === deviceA);
      assert.ok(gpuB.device === deviceB);
      assert.notEqual(gpuA.device, gpuB.device, "bound Doe helpers should remain device-specific");

      const kernelCode = \`
        @group(0) @binding(0) var<storage, read> src: array<f32>;
        @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

        @compute @workgroup_size(4)
        fn main(@builtin(global_invocation_id) gid: vec3u) {
          let i = gid.x;
          dst[i] = src[i] * 10.0 + 1.0;
        }
      \`;

      const aIn = gpuA.buffer.create({ data: new Float32Array([1, 2, 3, 4]) });
      const aOut = gpuA.buffer.create({ size: aIn.size, usage: "storageReadWrite" });
      const bIn = gpuB.buffer.create({ data: new Float32Array([10, 20, 30, 40]) });
      const bOut = gpuB.buffer.create({ size: bIn.size, usage: "storageReadWrite" });

      const kernelA = gpuA.kernel.create({
        code: kernelCode,
        bindings: [aIn, aOut],
      });
      const kernelB = gpuB.kernel.create({
        code: kernelCode,
        bindings: [bIn, bOut],
      });

      await Promise.all([
        kernelA.dispatch({ bindings: [aIn, aOut], workgroups: 1 }),
        kernelB.dispatch({ bindings: [bIn, bOut], workgroups: 1 }),
      ]);

      const [aResult, bResult] = await Promise.all([
        gpuA.buffer.read({ buffer: aOut, type: Float32Array }),
        gpuB.buffer.read({ buffer: bOut, type: Float32Array }),
      ]);
      assert.deepEqual(Array.from(aResult), [11, 21, 31, 41]);
      assert.deepEqual(Array.from(bResult), [101, 201, 301, 401]);

      // --- kernel.create() + kernel.dispatch() reuse ---
      const kernelInput = gpu.buffer.create({ data: new Float32Array([1, 2, 3, 4]) });
      const kernelOutput = gpu.buffer.create({ size: kernelInput.size, usage: "storageReadWrite" });
      const kernel = gpu.kernel.create({
        code: \`
          @group(0) @binding(0) var<storage, read> src: array<f32>;
          @group(0) @binding(1) var<storage, read_write> dst: array<f32>;
          @compute @workgroup_size(4)
          fn main(@builtin(global_invocation_id) gid: vec3u) {
            dst[gid.x] = src[gid.x] * 5.0;
          }
        \`,
        bindings: [kernelInput, kernelOutput],
      });
      await kernel.dispatch({ bindings: [kernelInput, kernelOutput], workgroups: 1 });
      const kernelResult = await gpu.buffer.read({ buffer: kernelOutput, type: Float32Array });
      assert.deepEqual(Array.from(kernelResult), [5, 10, 15, 20]);

      // dispatch again with different data
      const kernelInput2 = gpu.buffer.create({ data: new Float32Array([10, 20, 30, 40]) });
      const kernelOutput2 = gpu.buffer.create({ size: kernelInput2.size, usage: "storageReadWrite" });
      await kernel.dispatch({ bindings: [kernelInput2, kernelOutput2], workgroups: 1 });
      const kernelResult2 = await gpu.buffer.read({ buffer: kernelOutput2, type: Float32Array });
      assert.deepEqual(Array.from(kernelResult2), [50, 100, 150, 200]);

      // --- readBuffer direct MAP_READ path ---
      const mappableBuf = gpu.buffer.create({
        size: 16,
        usage: ["readback"],
      });
      gpu.device.queue.writeBuffer(mappableBuf, 0, new Float32Array([5, 6, 7, 8]));
      const mappableResult = await gpu.buffer.read({ buffer: mappableBuf, type: Float32Array });
      assert.deepEqual(Array.from(mappableResult), [5, 6, 7, 8]);

      // --- 3-binding dispatch ---
      const triOnce = await gpu.compute({
        code: \`
          @group(0) @binding(0) var<storage, read> a: array<f32>;
          @group(0) @binding(1) var<storage, read> b: array<f32>;
          @group(0) @binding(2) var<storage, read> c: array<f32>;
          @group(0) @binding(3) var<storage, read_write> dst: array<f32>;
          @compute @workgroup_size(2)
          fn main(@builtin(global_invocation_id) gid: vec3u) {
            let i = gid.x;
            dst[i] = a[i] + b[i] + c[i];
          }
        \`,
        inputs: [
          new Float32Array([1, 2]),
          new Float32Array([10, 20]),
          new Float32Array([100, 200]),
        ],
        output: { type: Float32Array },
        workgroups: 1,
      });
      assert.deepEqual(Array.from(triOnce), [111, 222]);

      // --- validateWorkgroups error: invalid type ---
      await assert.rejects(
        gpu.kernel.run({
          code: \`@compute @workgroup_size(1) fn main() {}\`,
          bindings: [],
          workgroups: "bad",
        }),
        /Doe workgroups must be/
      );

      // --- validateWorkgroups error: zero workgroup ---
      await assert.rejects(
        gpu.kernel.run({
          code: \`@compute @workgroup_size(1) fn main() {}\`,
          bindings: [],
          workgroups: 0,
        }),
        /must be a positive integer/
      );

      // --- validateWorkgroups error: negative workgroup ---
      await assert.rejects(
        gpu.kernel.run({
          code: \`@compute @workgroup_size(1) fn main() {}\`,
          bindings: [],
          workgroups: -1,
        }),
        /must be a positive integer/
      );
    `;

    execFileSync("node", ["--input-type=module", "-e", import_check], {
      cwd: consumer_dir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });

    for (const example of EXAMPLE_EXPECTATIONS) {
      const output = execFileSync("node", [example.relativePath], {
        cwd: installed_package_dir,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      }).trim();
      assert.deepEqual(JSON.parse(output), example.expected);
    }
  } finally {
    if (tarball_path) {
      rmSync(tarball_path, { force: true });
    }
    if (doe_tarball_path) {
      rmSync(doe_tarball_path, { force: true });
    }
    rmSync(temp_root, { recursive: true, force: true });
  }
}

await main();
