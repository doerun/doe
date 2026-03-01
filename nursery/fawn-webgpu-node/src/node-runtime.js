import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const LIB_EXTENSION_BY_PLATFORM = {
    darwin: "dylib",
    linux: "so",
    win32: "dll",
};

const WORKSPACE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
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

function first_existing_path(paths) {
    for (const path of paths) {
        if (!path) continue;
        if (existsSync(path)) return path;
    }
    return null;
}

function require_existing_path(label, path) {
    if (!path) {
        throw new Error(`Missing ${label}.`);
    }
    if (!existsSync(path)) {
        throw new Error(`${label} does not exist: ${path}`);
    }
}

function run_process(command, args, spawn_options = {}) {
    const result = spawnSync(command, args, {
        encoding: "utf8",
        ...spawn_options,
    });
    if (result.error) throw result.error;
    return {
        ok: result.status === 0,
        exitCode: result.status ?? 1,
        stdout: result.stdout ?? "",
        stderr: result.stderr ?? "",
        signal: result.signal ?? null,
        command: [command, ...args],
    };
}

function read_trace_meta(path) {
    if (!path || !existsSync(path)) return null;
    const raw = readFileSync(path, "utf8");
    return JSON.parse(raw);
}

function build_bench_args(options) {
    const args = ["--commands", options.commandsPath];
    if (options.quirksPath) args.push("--quirks", options.quirksPath);
    if (options.vendor) args.push("--vendor", options.vendor);
    if (options.api) args.push("--api", options.api);
    if (options.family) args.push("--family", options.family);
    if (options.driver) args.push("--driver", options.driver);
    if (options.queueWaitMode) args.push("--queue-wait-mode", options.queueWaitMode);
    if (options.queueSyncMode) args.push("--queue-sync-mode", options.queueSyncMode);
    if (options.uploadBufferUsage) args.push("--upload-buffer-usage", options.uploadBufferUsage);
    if (Number.isInteger(options.uploadSubmitEvery) && options.uploadSubmitEvery > 0) {
        args.push("--upload-submit-every", String(options.uploadSubmitEvery));
    }
    args.push("--backend", "native", "--execute");
    if (options.traceJsonlPath) args.push("--trace-jsonl", options.traceJsonlPath);
    if (options.traceMetaPath) args.push("--trace-meta", options.traceMetaPath);
    if (Array.isArray(options.extraArgs) && options.extraArgs.length > 0) {
        args.push(...options.extraArgs);
    }
    return args;
}

function has_option_flag(args, flag) {
    return Array.isArray(args) && args.includes(flag);
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
    };
}

export function resolveFawnRepoRoot(explicitPath) {
    const resolved = first_existing_path([
        explicitPath ? resolve(explicitPath, "bench/compare_dawn_vs_doe.py") : null,
        resolve(process.cwd(), "bench/compare_dawn_vs_doe.py"),
        resolve(WORKSPACE_ROOT, "bench/compare_dawn_vs_doe.py"),
    ]);
    if (!resolved) {
        throw new Error(
            "Could not locate Fawn repo root. Pass { repoRoot } or run from a Fawn checkout."
        );
    }
    return resolve(resolved, "..", "..");
}

export function resolveDoeBinaryPath(explicitPath) {
    const resolved = first_existing_path([
        explicitPath,
        process.env.FAWN_DOE_BIN,
        resolve(process.cwd(), "zig/zig-out/bin/doe-zig-runtime"),
        resolve(WORKSPACE_ROOT, "zig/zig-out/bin/doe-zig-runtime"),
    ]);
    if (!resolved) {
        throw new Error(
            "Could not locate doe-zig-runtime. Set FAWN_DOE_BIN or pass { binPath }."
        );
    }
    return resolved;
}

export function resolveDoeLibraryPath(explicitPath) {
    const preferredExt = LIB_EXTENSION_BY_PLATFORM[process.platform] ?? "so";
    return first_existing_path([
        explicitPath,
        process.env.FAWN_DOE_LIB,
        resolve(process.cwd(), `zig/zig-out/lib/libdoe_webgpu.${preferredExt}`),
        resolve(WORKSPACE_ROOT, `zig/zig-out/lib/libdoe_webgpu.${preferredExt}`),
        resolve(process.cwd(), "zig/zig-out/lib/libdoe_webgpu.dylib"),
        resolve(process.cwd(), "zig/zig-out/lib/libdoe_webgpu.so"),
        resolve(process.cwd(), "zig/zig-out/lib/libdoe_webgpu.dll"),
        resolve(WORKSPACE_ROOT, "zig/zig-out/lib/libdoe_webgpu.dylib"),
        resolve(WORKSPACE_ROOT, "zig/zig-out/lib/libdoe_webgpu.so"),
        resolve(WORKSPACE_ROOT, "zig/zig-out/lib/libdoe_webgpu.dll"),
    ]);
}

export function resolveCompareScriptPath(explicitPath, repoRoot = null) {
    const resolved = first_existing_path([
        explicitPath,
        repoRoot ? resolve(repoRoot, "bench/compare_dawn_vs_doe.py") : null,
        resolve(process.cwd(), "bench/compare_dawn_vs_doe.py"),
        resolve(WORKSPACE_ROOT, "bench/compare_dawn_vs_doe.py"),
    ]);
    if (!resolved) {
        throw new Error(
            "Could not locate bench/compare_dawn_vs_doe.py. Pass { compareScriptPath }."
        );
    }
    return resolved;
}

export function createDoeRuntime(options = {}) {
    const binPath = resolveDoeBinaryPath(options.binPath);
    const libPath = resolveDoeLibraryPath(options.libPath);

    function runRaw(args, spawnOptions = {}) {
        const env = { ...process.env, ...(spawnOptions.env ?? {}) };
        if (libPath) {
            env.FAWN_DOE_LIB = libPath;
        }
        return run_process(binPath, args, {
            ...spawnOptions,
            env,
        });
    }

    function runBench(runOptions) {
        if (!runOptions || typeof runOptions !== "object") {
            throw new Error("runBench requires an options object.");
        }
        require_existing_path("commandsPath", runOptions.commandsPath);
        if (runOptions.quirksPath) require_existing_path("quirksPath", runOptions.quirksPath);
        const args = build_bench_args(runOptions);
        const result = runRaw(args);
        const traceMeta = read_trace_meta(runOptions.traceMetaPath);
        return {
            ...result,
            traceJsonlPath: runOptions.traceJsonlPath ?? null,
            traceMetaPath: runOptions.traceMetaPath ?? null,
            traceMeta,
        };
    }

    return {
        binPath,
        libPath,
        runRaw,
        runBench,
    };
}

export function runDawnVsDoeCompare(options = {}) {
    const repoRoot = resolveFawnRepoRoot(options.repoRoot);
    const scriptPath = resolveCompareScriptPath(options.compareScriptPath, repoRoot);
    const pythonBin = options.pythonBin || process.env.PYTHON_BIN || "python3";
    const extraArgs = Array.isArray(options.extraArgs) ? options.extraArgs : [];

    const args = [scriptPath];
    if (options.configPath) {
        args.push("--config", resolve(options.configPath));
    }
    if (options.outPath) {
        args.push("--out", resolve(options.outPath));
    }
    args.push(...extraArgs);

    if (!options.configPath && !has_option_flag(extraArgs, "--config")) {
        throw new Error("runDawnVsDoeCompare requires configPath or --config in extraArgs.");
    }

    return run_process(pythonBin, args, {
        cwd: repoRoot,
        env: { ...process.env, ...(options.env ?? {}) },
    });
}
