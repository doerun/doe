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

