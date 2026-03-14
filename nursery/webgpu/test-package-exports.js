import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_DIR = dirname(fileURLToPath(import.meta.url));
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
    relativePath: join("examples", "doe-api", "compute-dispatch.js"),
    expected: [2, 4, 6, 8],
  },
  {
    relativePath: join("examples", "doe-api", "compile-and-dispatch.js"),
    expected: [5, 10, 15, 20],
  },
  {
    relativePath: join("examples", "doe-routines", "compute-once.js"),
    expected: [3, 6, 9, 12],
  },
  {
    relativePath: join("examples", "doe-routines", "compute-once-like-input.js"),
    expected: [2, 4, 6, 8],
  },
  {
    relativePath: join("examples", "doe-routines", "compute-once-multiple-inputs.js"),
    expected: [11, 22, 33, 44],
  },
  {
    relativePath: join("examples", "doe-routines", "compute-once-matmul.js"),
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

  try {
    const pack_output = npm_json(["pack", "--json"], PACKAGE_DIR);
    const tarball_name = pack_output[0]?.filename;
    assert.ok(tarball_name, "npm pack --json did not produce a tarball filename");

    tarball_path = resolve(PACKAGE_DIR, tarball_name);
    mkdirSync(consumer_dir, { recursive: true });
    writeFileSync(join(consumer_dir, "package.json"), JSON.stringify({
      name: "simulatte-webgpu-pack-test",
      private: true,
      type: "module",
    }, null, 2));

    execFileSync("npm", ["install", "--ignore-scripts", tarball_path], {
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
      assert.equal(typeof full.doe.buffers.fromData, "function");
      assert.equal(typeof full.doe.compute.run, "function");

      assert.equal(typeof compute.requestDevice, "function");
      assert.equal(typeof compute.doe.requestDevice, "function");
      assert.equal(typeof compute.doe.buffers.read, "function");
      assert.equal(typeof compute.doe.compute.once, "function");

      assert.equal(typeof explicitFull.requestDevice, "function");
      assert.equal(typeof explicitFull.doe.compute.compile, "function");

      const gpu = await compute.doe.requestDevice();
      assert.ok(gpu.device.limits.maxComputeInvocationsPerWorkgroup > 0);
      const input = gpu.buffers.fromData(new Float32Array([1, 2, 3, 4]));
      const output = gpu.buffers.like(input, {
        usage: "storageReadWrite",
      });

      await gpu.compute.run({
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

      const result = await gpu.buffers.read(output, Float32Array);
      assert.deepEqual(Array.from(result), [2, 4, 6, 8]);

      const oneShot = await gpu.compute.once({
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
      const preflightRejected = full.preflightShaderSource(\`
        @fragment
        fn main(@location(0) uv: vec2f) -> @location(0) vec4f {
          return vec4f(uv, 0.0, 1.0);
        }
      \`);
      assert.equal(preflightRejected.ok, false);
      assert.equal(preflightRejected.stage, "package_surface");
      assert.ok(preflightRejected.message.includes("package_surface"));

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
        gpu.compute.run({
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

      const oneShotRawUsage = await gpu.compute.once({
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
        gpu.compute.once({
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

      const destroyedBuffer = gpu.buffers.create({
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
    rmSync(temp_root, { recursive: true, force: true });
  }
}

await main();
