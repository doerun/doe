import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_DIR = dirname(fileURLToPath(import.meta.url));

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

    const installed_package = JSON.parse(readFileSync(join(
      consumer_dir,
      "node_modules",
      "@simulatte",
      "webgpu",
      "package.json",
    ), "utf8"));

    assert.ok(installed_package.exports["./compute"], "packed tarball is missing ./compute export");
    assert.ok(installed_package.exports["./full"], "packed tarball is missing ./full export");

    const import_check = `
      import assert from "node:assert/strict";
      const full = await import("@simulatte/webgpu");
      const compute = await import("@simulatte/webgpu/compute");
      const explicitFull = await import("@simulatte/webgpu/full");

      assert.equal(typeof full.requestDevice, "function");
      assert.equal(typeof full.providerInfo, "function");
      assert.equal(typeof full.doe.runCompute, "function");
      assert.equal(typeof full.doe.bind, "function");

      assert.equal(typeof compute.requestDevice, "function");
      assert.equal(typeof compute.doe.readBuffer, "function");
      assert.equal(typeof compute.doe.bind, "function");

      assert.equal(typeof explicitFull.requestDevice, "function");
      assert.equal(typeof explicitFull.doe.compileCompute, "function");

      const device = await compute.requestDevice();
      const gpu = compute.doe.bind(device);
      const input = gpu.createBufferFromData(new Float32Array([1, 2, 3, 4]));
      const output = gpu.createBuffer({
        size: input.size,
        usage: "storage-readwrite",
      });

      await gpu.runCompute({
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

      const result = await gpu.readBuffer(output, Float32Array);
      assert.deepEqual(Array.from(result), [2, 4, 6, 8]);

      const raw = device.createBuffer({
        size: input.size,
        usage: compute.globals.GPUBufferUsage.STORAGE | compute.globals.GPUBufferUsage.COPY_DST,
      });
      await assert.rejects(
        gpu.runCompute({
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
    `;

    execFileSync("node", ["--input-type=module", "-e", import_check], {
      cwd: consumer_dir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } finally {
    if (tarball_path) {
      rmSync(tarball_path, { force: true });
    }
    rmSync(temp_root, { recursive: true, force: true });
  }
}

await main();
