import { dlopen, FFIType, JSCallback } from "bun:ffi";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const LIB_EXTENSION_BY_PLATFORM = {
    darwin: "dylib",
    linux: "so",
    win32: "dll",
};
const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DOE_PROVIDER_MODE = resolve_doe_provider_mode();
const DOE_LIBRARY_PATH = resolve_doe_library_path();
let doe_runtime = null;
let doe_runtime_error = null;

const PROVIDER_MODULE_SPECIFIER = resolve_provider_module_specifier();
const DEFAULT_PROVIDER_CREATE_ARGS = parse_create_args_from_env(
    process.env.FAWN_WEBGPU_CREATE_ARGS
);
let provider_module_namespace = null;
let provider_module_load_error = null;

try {
    provider_module_namespace = await import(PROVIDER_MODULE_SPECIFIER);
} catch (error) {
    provider_module_load_error = error;
}
initialize_doe_runtime();

function resolve_doe_provider_mode() {
    const raw = process.env.FAWN_WEBGPU_BUN_PROVIDER;
    if (typeof raw !== "string") return "auto";
    const normalized = raw.trim().toLowerCase();
    if (normalized === "doe") return "required";
    if (normalized === "provider") return "disabled";
    return "auto";
}

function first_existing_path(paths) {
    for (const path of paths) {
        if (!path) continue;
        if (existsSync(path)) return path;
    }
    return null;
}

function resolve_doe_library_path() {
    const preferredExt = LIB_EXTENSION_BY_PLATFORM[process.platform] ?? "so";
    return first_existing_path([
        process.env.FAWN_DOE_LIB,
        resolve(process.cwd(), `zig/zig-out/lib/libdoe_webgpu.${preferredExt}`),
        resolve(PACKAGE_ROOT, `../zig/zig-out/lib/libdoe_webgpu.${preferredExt}`),
        resolve(process.cwd(), "zig/zig-out/lib/libdoe_webgpu.dylib"),
        resolve(process.cwd(), "zig/zig-out/lib/libdoe_webgpu.so"),
        resolve(process.cwd(), "zig/zig-out/lib/libdoe_webgpu.dll"),
        resolve(PACKAGE_ROOT, "../zig/zig-out/lib/libdoe_webgpu.dylib"),
        resolve(PACKAGE_ROOT, "../zig/zig-out/lib/libdoe_webgpu.so"),
        resolve(PACKAGE_ROOT, "../zig/zig-out/lib/libdoe_webgpu.dll"),
    ]);
}

function initialize_doe_runtime() {
    if (DOE_PROVIDER_MODE === "disabled") {
        return;
    }
    if (!DOE_LIBRARY_PATH) {
        if (DOE_PROVIDER_MODE === "required") {
            throw new Error(
                "FAWN_WEBGPU_BUN_PROVIDER=doe requested Doe runtime, but libdoe_webgpu was not found. Set FAWN_DOE_LIB."
            );
        }
        return;
    }
    try {
        doe_runtime = loadFawnDoeWebGPU(DOE_LIBRARY_PATH);
    } catch (error) {
        doe_runtime_error = error;
        if (DOE_PROVIDER_MODE === "required") {
            throw error;
        }
    }
}

function resolve_provider_module_specifier() {
    const candidate = process.env.FAWN_WEBGPU_NODE_PROVIDER_MODULE;
    if (typeof candidate === "string" && candidate.trim().length > 0) {
        return candidate.trim();
    }
    return "webgpu";
}

function parse_create_args_from_env(raw) {
    if (typeof raw !== "string" || raw.trim().length === 0) {
        return [];
    }
    return raw
        .split(";")
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0);
}

function normalize_create_args(create_args) {
    if (create_args == null) {
        return [...DEFAULT_PROVIDER_CREATE_ARGS];
    }
    if (!Array.isArray(create_args)) {
        throw new Error("create(...) expects an array of string args.");
    }
    const normalized = [];
    for (const [index, value] of create_args.entries()) {
        if (typeof value !== "string") {
            throw new Error(
                `create(...) arg[${index}] must be a string, got ${typeof value}`
            );
        }
        const trimmed = value.trim();
        if (trimmed.length > 0) normalized.push(trimmed);
    }
    return normalized;
}

function resolve_provider_create_function() {
    if (!provider_module_namespace) {
        const message = provider_module_load_error
            ? provider_module_load_error.message || String(provider_module_load_error)
            : "provider module did not load";
        throw new Error(
            `Could not load WebGPU provider module '${PROVIDER_MODULE_SPECIFIER}': ${message}. ` +
                "Set FAWN_WEBGPU_NODE_PROVIDER_MODULE to a module exporting create(...) and globals."
        );
    }
    const from_namespace = provider_module_namespace.create;
    const from_default = provider_module_namespace.default?.create;
    const create_fn = typeof from_namespace === "function" ? from_namespace : from_default;
    if (typeof create_fn !== "function") {
        throw new Error(
            `Provider module '${PROVIDER_MODULE_SPECIFIER}' does not export create(...).`
        );
    }
    return create_fn;
}

function build_provider_globals() {
    if (!provider_module_namespace) {
        return {};
    }
    const direct = provider_module_namespace.globals;
    const nested = provider_module_namespace.default?.globals;
    const source = (direct && typeof direct === "object") ? direct : nested;
    if (!source || typeof source !== "object") {
        return {};
    }
    return { ...source };
}

function define_global_if_missing(target, name, value) {
    if (!target || typeof target !== "object") return;
    if (value === undefined || value === null) return;
    if (target[name] !== undefined) return;
    Object.defineProperty(target, name, {
        value,
        writable: true,
        configurable: true,
        enumerable: false,
    });
}

export const globals = build_provider_globals();

export function create(createArgs = null) {
    if (doe_runtime) {
        return {
            requestAdapter: async (adapterOptions = undefined) =>
                doe_runtime.requestAdapter(adapterOptions),
            createAdapter: async (adapterOptions = undefined) =>
                doe_runtime.createAdapter(adapterOptions),
            releaseInstance: () => doe_runtime.releaseInstance(),
        };
    }
    const create_fn = resolve_provider_create_function();
    const args = normalize_create_args(createArgs);
    const gpu = create_fn(args);
    if (!gpu || typeof gpu.requestAdapter !== "function") {
        throw new Error(
            `Provider module '${PROVIDER_MODULE_SPECIFIER}' returned an invalid GPU object from create(...).`
        );
    }
    return gpu;
}

export function setupGlobals(target = globalThis, createArgs = null) {
    for (const [name, value] of Object.entries(globals)) {
        define_global_if_missing(target, name, value);
    }
    const gpu = create(createArgs);
    if (typeof target.navigator === "undefined") {
        Object.defineProperty(target, "navigator", {
            value: { gpu },
            writable: true,
            configurable: true,
            enumerable: false,
        });
    } else if (!target.navigator.gpu) {
        Object.defineProperty(target.navigator, "gpu", {
            value: gpu,
            writable: true,
            configurable: true,
            enumerable: false,
        });
    }
    return gpu;
}

export async function requestAdapter(adapterOptions = undefined, createArgs = null) {
    const gpu = create(createArgs);
    return gpu.requestAdapter(adapterOptions);
}

export async function requestDevice(options = {}) {
    const adapterOptions = options?.adapterOptions;
    const deviceDescriptor = options?.deviceDescriptor;
    const createArgs = options?.createArgs ?? null;
    const adapter = await requestAdapter(adapterOptions, createArgs);
    if (!adapter || typeof adapter.requestDevice !== "function") {
        throw new Error("Provider returned an invalid adapter object.");
    }
    return adapter.requestDevice(deviceDescriptor);
}

export function providerInfo() {
    return {
        module: PROVIDER_MODULE_SPECIFIER,
        loaded: !!provider_module_namespace,
        loadError: provider_module_load_error
            ? provider_module_load_error.message || String(provider_module_load_error)
            : "",
        defaultCreateArgs: [...DEFAULT_PROVIDER_CREATE_ARGS],
        doeProviderMode: DOE_PROVIDER_MODE,
        doeRuntimeActive: !!doe_runtime,
        doeLibraryPath: DOE_LIBRARY_PATH ?? "",
        doeLoadError: doe_runtime_error
            ? doe_runtime_error.message || String(doe_runtime_error)
            : "",
    };
}

/**
 * Load libdoe_webgpu via Bun FFI and expose WebGPU instance/adapter/device.
 *
 * The webgpu.h C ABI uses callback-based async for requestAdapter and
 * requestDevice. We use Bun's JSCallback to create C function pointers
 * that bridge into JS promises.
 *
 * C ABI contract (from zig/src/wgpu_types.zig):
 *   WGPUCallbackMode_WaitAnyOnly = 0x00000001
 *   WGPUWaitStatus.success = 1
 *   WGPURequestAdapterStatus.success = 1
 *   WGPURequestDeviceStatus.success = 1
 *
 *   WGPURequestAdapterCallbackInfo = { nextInChain, mode, callback, userdata1, userdata2 }
 *   WGPURequestDeviceCallbackInfo  = { nextInChain, mode, callback, userdata1, userdata2 }
 *   WGPUFutureWaitInfo = { future_id: u64, completed: u32 }
 *
 * Callback signatures:
 *   adapter_cb(status: u32, adapter: ptr, message_data: ptr, message_len: usize, userdata1: ptr, userdata2: ptr)
 *   device_cb(status: u32, device: ptr, message_data: ptr, message_len: usize, userdata1: ptr, userdata2: ptr)
 *
 * Note: WGPUStringView is { data: ptr, length: usize } — passed as two args in the C calling convention.
 */

const CALLBACK_MODE_WAIT_ANY_ONLY = 1;
const WAIT_STATUS_SUCCESS = 1;
const REQUEST_ADAPTER_STATUS_SUCCESS = 1;
const REQUEST_DEVICE_STATUS_SUCCESS = 1;
const WAIT_TIMEOUT_NS = BigInt(5_000_000_000); // 5 seconds

export function loadFawnDoeWebGPU(ffiPath) {
    const wgpu = dlopen(ffiPath, {
        wgpuCreateInstance: {
            args: [FFIType.ptr],
            returns: FFIType.ptr,
        },
        doeRequestAdapterFlat: {
            args: [
                FFIType.ptr,   // instance
                FFIType.ptr,   // options (nullable)
                FFIType.u32,   // mode (WGPUCallbackMode)
                FFIType.ptr,   // callback fn ptr
                FFIType.ptr,   // userdata1
                FFIType.ptr,   // userdata2
            ],
            returns: FFIType.u64, // WGPUFuture.id
        },
        wgpuInstanceWaitAny: {
            args: [
                FFIType.ptr,   // instance
                FFIType.u64,   // futureCount (usize)
                FFIType.ptr,   // futureWaitInfos array ptr
                FFIType.u64,   // timeoutNs
            ],
            returns: FFIType.u32, // WGPUWaitStatus
        },
        wgpuInstanceProcessEvents: {
            args: [FFIType.ptr],
            returns: FFIType.void,
        },
        doeRequestDeviceFlat: {
            args: [
                FFIType.ptr,   // adapter
                FFIType.ptr,   // descriptor (nullable)
                FFIType.u32,   // mode (WGPUCallbackMode)
                FFIType.ptr,   // callback fn ptr
                FFIType.ptr,   // userdata1
                FFIType.ptr,   // userdata2
            ],
            returns: FFIType.u64, // WGPUFuture.id
        },
        wgpuDeviceGetQueue: {
            args: [FFIType.ptr],
            returns: FFIType.ptr,
        },
        wgpuAdapterRelease: {
            args: [FFIType.ptr],
            returns: FFIType.void,
        },
        wgpuDeviceRelease: {
            args: [FFIType.ptr],
            returns: FFIType.void,
        },
        wgpuInstanceRelease: {
            args: [FFIType.ptr],
            returns: FFIType.void,
        },
    });

    let instancePtr = null;

    function ensureInstance() {
        if (instancePtr) return instancePtr;
        instancePtr = wgpu.symbols.wgpuCreateInstance(null);
        if (!instancePtr) {
            throw new Error("[fawn-webgpu] Failed to create WGPUInstance via FFI");
        }
        return instancePtr;
    }

    /**
     * Request an adapter via callback trampoline.
     *
     * The C API expects WGPURequestAdapterCallbackInfo as a struct argument.
     * Bun's dlopen flattens struct args into individual parameters.
     * We create a JSCallback for the C callback, invoke requestAdapter,
     * then call wgpuInstanceWaitAny to pump the future until the callback fires.
     */
    async function doeRequestAdapter(adapterOptions) {
        const inst = ensureInstance();
        let resolvedAdapter = null;
        let resolvedStatus = null;

        const callback = new JSCallback(
            (status, adapter, msgData, msgLen, ud1, ud2) => {
                resolvedStatus = status;
                resolvedAdapter = adapter;
            },
            {
                args: [
                    FFIType.u32,  // status
                    FFIType.ptr,  // adapter
                    FFIType.ptr,  // message.data
                    FFIType.u64,  // message.length (usize)
                    FFIType.ptr,  // userdata1
                    FFIType.ptr,  // userdata2
                ],
                returns: FFIType.void,
            }
        );

        try {
            const futureId = wgpu.symbols.doeRequestAdapterFlat(
                inst,
                null, // default adapter options
                CALLBACK_MODE_WAIT_ANY_ONLY,
                callback.ptr,
                null, // userdata1
                null  // userdata2
            );

            // Build WGPUFutureWaitInfo: { future_id: u64, completed: u32 }
            // Layout: 8 bytes for u64 future id + 4 bytes for u32 completed bool
            const waitInfo = new ArrayBuffer(16);
            const waitView = new DataView(waitInfo);
            // futureId is returned as a BigInt from FFI u64
            waitView.setBigUint64(0, BigInt(futureId), true);
            waitView.setUint32(8, 0, true); // completed = false

            const waitStatus = wgpu.symbols.wgpuInstanceWaitAny(
                inst,
                BigInt(1),    // futureCount = 1
                waitInfo,     // Bun passes ArrayBuffer as ptr
                WAIT_TIMEOUT_NS
            );

            if (waitStatus !== WAIT_STATUS_SUCCESS) {
                throw new Error(
                    `[fawn-webgpu] wgpuInstanceWaitAny failed with status ${waitStatus}`
                );
            }

            if (resolvedStatus !== REQUEST_ADAPTER_STATUS_SUCCESS || !resolvedAdapter) {
                throw new Error(
                    `[fawn-webgpu] requestAdapter failed with status ${resolvedStatus}`
                );
            }

            return resolvedAdapter;
        } finally {
            callback.close();
        }
    }

    /**
     * Request a device from an adapter via callback trampoline.
     */
    async function doeRequestDevice(adapterPtr, deviceDescriptor) {
        const inst = ensureInstance();
        let resolvedDevice = null;
        let resolvedStatus = null;

        const callback = new JSCallback(
            (status, device, msgData, msgLen, ud1, ud2) => {
                resolvedStatus = status;
                resolvedDevice = device;
            },
            {
                args: [
                    FFIType.u32,  // status
                    FFIType.ptr,  // device
                    FFIType.ptr,  // message.data
                    FFIType.u64,  // message.length (usize)
                    FFIType.ptr,  // userdata1
                    FFIType.ptr,  // userdata2
                ],
                returns: FFIType.void,
            }
        );

        try {
            const futureId = wgpu.symbols.doeRequestDeviceFlat(
                adapterPtr,
                null, // default device descriptor
                CALLBACK_MODE_WAIT_ANY_ONLY,
                callback.ptr,
                null, // userdata1
                null  // userdata2
            );

            const waitInfo = new ArrayBuffer(16);
            const waitView = new DataView(waitInfo);
            waitView.setBigUint64(0, BigInt(futureId), true);
            waitView.setUint32(8, 0, true);

            const waitStatus = wgpu.symbols.wgpuInstanceWaitAny(
                inst,
                BigInt(1),
                waitInfo,
                WAIT_TIMEOUT_NS
            );

            if (waitStatus !== WAIT_STATUS_SUCCESS) {
                throw new Error(
                    `[fawn-webgpu] wgpuInstanceWaitAny (device) failed with status ${waitStatus}`
                );
            }

            if (resolvedStatus !== REQUEST_DEVICE_STATUS_SUCCESS || !resolvedDevice) {
                throw new Error(
                    `[fawn-webgpu] requestDevice failed with status ${resolvedStatus}`
                );
            }

            return resolvedDevice;
        } finally {
            callback.close();
        }
    }

    return {
        setupGlobals: () => {
            console.log("[fawn-webgpu] Setting up bare-metal Zig globals");
        },
        createInstance: () => {
            const inst = ensureInstance();
            return { instance: inst, tag: "DoeInstance" };
        },
        createAdapter: async (adapterOptions) => {
            const adapterPtr = await doeRequestAdapter(adapterOptions);
            return {
                ptr: adapterPtr,
                tag: "DoeAdapter",
                requestDevice: async (deviceDescriptor) => {
                    const devicePtr = await doeRequestDevice(adapterPtr, deviceDescriptor);
                    const queuePtr = wgpu.symbols.wgpuDeviceGetQueue(devicePtr);
                    return {
                        ptr: devicePtr,
                        queue: queuePtr ? { ptr: queuePtr, tag: "DoeQueue" } : null,
                        tag: "DoeDevice",
                        release: () => wgpu.symbols.wgpuDeviceRelease(devicePtr),
                    };
                },
                release: () => wgpu.symbols.wgpuAdapterRelease(adapterPtr),
            };
        },
        requestAdapter: async (adapterOptions) => {
            const adapterPtr = await doeRequestAdapter(adapterOptions);
            return {
                ptr: adapterPtr,
                tag: "DoeAdapter",
                requestDevice: async (deviceDescriptor) => {
                    const devicePtr = await doeRequestDevice(adapterPtr, deviceDescriptor);
                    const queuePtr = wgpu.symbols.wgpuDeviceGetQueue(devicePtr);
                    return {
                        ptr: devicePtr,
                        queue: queuePtr ? { ptr: queuePtr, tag: "DoeQueue" } : null,
                        tag: "DoeDevice",
                        release: () => wgpu.symbols.wgpuDeviceRelease(devicePtr),
                    };
                },
                release: () => wgpu.symbols.wgpuAdapterRelease(adapterPtr),
            };
        },
        releaseInstance: () => {
            if (instancePtr) {
                wgpu.symbols.wgpuInstanceRelease(instancePtr);
                instancePtr = null;
            }
        },
        runBench: () => {
            console.log("[fawn-webgpu] Executing Fawn Doe headless loop...");
        },
    };
}
