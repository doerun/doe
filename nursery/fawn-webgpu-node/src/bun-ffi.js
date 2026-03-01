import { dlopen, FFIType } from "bun:ffi";

export function loadFawnDoeWebGPU(ffiPath) {
    const wgpu = dlopen(ffiPath, {
        wgpuCreateInstance: {
            args: [FFIType.ptr],
            returns: FFIType.ptr,
        },
    });

    return {
        setupGlobals: () => {
            console.log("[fawn-webgpu] Setting up bare-metal Zig globals");
        },
        createInstance: () => {
            const instancePtr = wgpu.symbols.wgpuCreateInstance(0);
            if (!instancePtr) {
                throw new Error("Failed to create WGPUInstance via dlopen FFI");
            }
            return { instance: instancePtr, tag: "DoeInstancePrototype" };
        },
        createAdapter: async () => {
            throw new Error(
                "createAdapter is not implemented in this Bun prototype yet. " +
                "It requires callback trampoline wiring for wgpuInstanceRequestAdapter."
            );
        },
        runBench: () => {
            console.log("[fawn-webgpu] Executing Fawn Doe headless loop...");
        }
    };
}
