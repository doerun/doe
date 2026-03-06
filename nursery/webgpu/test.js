import { loadFawnDoeWebGPU } from "./src/bun-ffi.js";
import { existsSync } from "node:fs";
import { join } from "node:path";

const LIB_EXTENSION_BY_PLATFORM = {
    darwin: "dylib",
    linux: "so",
    win32: "dll",
};

function resolveDoeLibPath() {
    if (process.env.FAWN_DOE_LIB) {
        return process.env.FAWN_DOE_LIB;
    }

    const ext = LIB_EXTENSION_BY_PLATFORM[process.platform] ?? "so";
    const candidates = [
        join(import.meta.dir, `../../zig/zig-out/lib/libdoe_webgpu.${ext}`),
        join(import.meta.dir, "../../zig/zig-out/lib/libdoe_webgpu.dylib"),
        join(import.meta.dir, "../../zig/zig-out/lib/libdoe_webgpu.so"),
        join(import.meta.dir, "../../zig/zig-out/lib/libdoe_webgpu.dll"),
    ];

    for (const candidate of candidates) {
        if (existsSync(candidate)) {
            return candidate;
        }
    }

    throw new Error(
        "Could not locate libdoe_webgpu. Set FAWN_DOE_LIB to an absolute library path."
    );
}

async function main() {
    const doeLibPath = resolveDoeLibPath();
    console.log(`Loading Fawn WebGPU from: ${doeLibPath}`);
    const webgpu = loadFawnDoeWebGPU(doeLibPath);

    webgpu.setupGlobals();
    const instance = webgpu.createInstance();
    console.log("Created instance:", instance);
    webgpu.runBench();
    console.log("Prototype benchmark complete.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
