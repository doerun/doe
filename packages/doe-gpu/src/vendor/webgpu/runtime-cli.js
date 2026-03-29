import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const LIB_EXTENSION_BY_PLATFORM = {
    darwin: "dylib",
    linux: "so",
    win32: "dll",
};

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const REPO_ROOT = resolve(PACKAGE_ROOT, "../..");
const DEFAULT_NUMERIC_STABILITY_POLICY_REGISTRY_PATH = "config/numeric-stability-policy.json";
const NUMERIC_STABILITY_MODULE_ID = "doe_numeric_stability";
const NUMERIC_STABILITY_MATMUL_LOGITS_SLICE_SERVICE_ID = "matmul_logits_slice";
const DEFAULT_NUMERIC_STABILITY_OPERATOR_FAMILY = "lm-head-slice";
const DEFAULT_NUMERIC_STABILITY_SEMANTIC_OP_ID = "matmul.logits";
const DEFAULT_NUMERIC_STABILITY_SEMANTIC_STAGE = "lm_head_slice";
const DEFAULT_NUMERIC_STABILITY_SEMANTIC_PHASE = "logits";
const DEFAULT_NUMERIC_STABILITY_FAST_POLICY_ID = "lm-head-slice/forward-f16accum-v1";
const DEFAULT_NUMERIC_STABILITY_STABLE_POLICY_ID = "lm-head-slice/forward-serial-v1";
const DEFAULT_NUMERIC_STABILITY_TRIGGER_POLICY_ID =
    "numeric-instability/selected-token-disagreement-with-reference-improvement-v1";
const DEFAULT_NUMERIC_STABILITY_ROUTING_POLICY_ID =
    "numeric-stability/prefer-stable-on-selected-token-disagreement-v1";

function firstExistingPath(paths) {
    for (const path of paths) {
        if (!path) continue;
        if (existsSync(path)) return path;
    }
    return null;
}

function requireExistingPath(label, path) {
    if (!path) {
        throw new Error(`Missing ${label}.`);
    }
    if (!existsSync(path)) {
        throw new Error(`${label} does not exist: ${path}`);
    }
}

function runProcess(command, args, spawn_options = {}) {
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

function readTraceMeta(path) {
    if (!path || !existsSync(path)) return null;
    const raw = readFileSync(path, "utf8");
    return JSON.parse(raw);
}

function clearOutputPath(path) {
    if (!path || !existsSync(path)) return;
    try {
        unlinkSync(path);
    } catch {
        // Leave the stale file in place rather than failing the run setup.
    }
}

function buildBenchArgs(options) {
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

function hasOptionFlag(args, flag) {
    return Array.isArray(args) && args.includes(flag);
}

export function resolveDoeRepoRoot(explicitPath) {
    const resolved = firstExistingPath([
        explicitPath ? resolve(explicitPath, "bench/native-compare/compare_dawn_vs_doe.py") : null,
        resolve(process.cwd(), "bench/native-compare/compare_dawn_vs_doe.py"),
        resolve(REPO_ROOT, "bench/native-compare/compare_dawn_vs_doe.py"),
    ]);
    if (!resolved) {
        throw new Error(
            "Could not locate Doe repo root. Pass { repoRoot } or run from a Doe checkout."
        );
    }
    return resolve(resolved, "..", "..");
}

export function resolveDoeBinaryPath(explicitPath) {
    const resolved = firstExistingPath([
        explicitPath,
        process.env.DOE_BIN,
        process.env.FAWN_DOE_BIN,
        resolve(process.cwd(), "runtime/zig/zig-out/bin/doe-zig-runtime"),
        resolve(REPO_ROOT, "runtime/zig/zig-out/bin/doe-zig-runtime"),
    ]);
    if (!resolved) {
        throw new Error(
            "Could not locate doe-zig-runtime. Set DOE_BIN or pass { binPath }."
        );
    }
    return resolved;
}

export function resolveDoeLibraryPath(explicitPath) {
    const preferredExt = LIB_EXTENSION_BY_PLATFORM[process.platform] ?? "so";
    return firstExistingPath([
        explicitPath,
        process.env.DOE_LIB,
        resolve(process.cwd(), `runtime/zig/zig-out/lib/libwebgpu_doe.${preferredExt}`),
        resolve(REPO_ROOT, `runtime/zig/zig-out/lib/libwebgpu_doe.${preferredExt}`),
        resolve(process.cwd(), "runtime/zig/zig-out/lib/libwebgpu_doe.dylib"),
        resolve(process.cwd(), "runtime/zig/zig-out/lib/libwebgpu_doe.so"),
        resolve(process.cwd(), "runtime/zig/zig-out/lib/libwebgpu_doe.dll"),
        resolve(REPO_ROOT, "runtime/zig/zig-out/lib/libwebgpu_doe.dylib"),
        resolve(REPO_ROOT, "runtime/zig/zig-out/lib/libwebgpu_doe.so"),
        resolve(REPO_ROOT, "runtime/zig/zig-out/lib/libwebgpu_doe.dll"),
    ]);
}

export function resolveDoeModuleRunnerPath(explicitPath, { required = true } = {}) {
    const resolved = firstExistingPath([
        explicitPath,
        process.env.DOE_MODULE_RUNNER,
        resolve(process.cwd(), "runtime/zig/zig-out/bin/module-core-runner"),
        resolve(REPO_ROOT, "runtime/zig/zig-out/bin/module-core-runner"),
    ]);
    if (!resolved && required) {
        throw new Error(
            "Could not locate module-core-runner. Set DOE_MODULE_RUNNER or pass { moduleRunnerPath }."
        );
    }
    return resolved;
}

export function resolveCompareScriptPath(explicitPath, repoRoot = null) {
    const resolved = firstExistingPath([
        explicitPath,
        repoRoot ? resolve(repoRoot, "bench/native-compare/compare_dawn_vs_doe.py") : null,
        resolve(process.cwd(), "bench/native-compare/compare_dawn_vs_doe.py"),
        resolve(REPO_ROOT, "bench/native-compare/compare_dawn_vs_doe.py"),
    ]);
    if (!resolved) {
        throw new Error(
            "Could not locate bench/native-compare/compare_dawn_vs_doe.py. Pass { compareScriptPath }."
        );
    }
    return resolved;
}

export function createDoeRuntime(options = {}) {
    const binPath = resolveDoeBinaryPath(options.binPath);
    const libPath = resolveDoeLibraryPath(options.libPath);
    const moduleRunnerPath = resolveDoeModuleRunnerPath(options.moduleRunnerPath, {
        required: false,
    });

    function runRaw(args, spawnOptions = {}) {
        const env = { ...process.env, ...(spawnOptions.env ?? {}) };
        if (libPath) {
            env.DOE_LIB = libPath;
        }
        return runProcess(binPath, args, {
            ...spawnOptions,
            env,
        });
    }

    function runBench(runOptions) {
        if (!runOptions || typeof runOptions !== "object") {
            throw new Error("runBench requires an options object.");
        }
        requireExistingPath("commandsPath", runOptions.commandsPath);
        if (runOptions.quirksPath) requireExistingPath("quirksPath", runOptions.quirksPath);
        clearOutputPath(runOptions.traceJsonlPath);
        clearOutputPath(runOptions.traceMetaPath);
        const args = buildBenchArgs(runOptions);
        const result = runRaw(args, {
            cwd: runOptions.cwd || REPO_ROOT,
        });
        const traceMeta = readTraceMeta(runOptions.traceMetaPath);
        return {
            ...result,
            traceJsonlPath: runOptions.traceJsonlPath ?? null,
            traceMetaPath: runOptions.traceMetaPath ?? null,
            traceMeta,
        };
    }

    function runModule(moduleOptions) {
        if (!moduleOptions || typeof moduleOptions !== "object") {
            throw new Error("runModule requires an options object.");
        }
        if (typeof moduleOptions.moduleId !== "string" || moduleOptions.moduleId.trim().length === 0) {
            throw new Error("runModule requires a non-empty moduleId.");
        }
        if (!moduleOptions.request || typeof moduleOptions.request !== "object") {
            throw new Error("runModule requires a request object.");
        }
        if (!moduleOptions.policyPath) {
            throw new Error("runModule requires an explicit policyPath.");
        }
        const runCwd = moduleOptions.cwd || REPO_ROOT;
        const policyPath = moduleOptions.policyPath;
        const resolvedPolicyPath = policyPath.startsWith("/")
            ? policyPath
            : resolve(runCwd, policyPath);
        requireExistingPath("policyPath", resolvedPolicyPath);
        const resolvedModuleRunnerPath = resolveDoeModuleRunnerPath(
            moduleOptions.moduleRunnerPath ?? moduleRunnerPath
        );
        const tempDir = mkdtempSync(join(tmpdir(), "doe-module-runner-"));
        const requestPath = join(tempDir, "request.json");
        try {
            writeFileSync(requestPath, `${JSON.stringify(moduleOptions.request, null, 2)}\n`, "utf8");
            const result = runProcess(
                resolvedModuleRunnerPath,
                [
                    "--module",
                    moduleOptions.moduleId,
                    "--request",
                    requestPath,
                    "--policy",
                    policyPath,
                ],
                {
                    cwd: runCwd,
                    env: { ...process.env },
                }
            );
            let output = null;
            if (result.ok && result.stdout.trim().length > 0) {
                output = JSON.parse(result.stdout);
            }
            return {
                ...result,
                output,
            };
        } finally {
            rmSync(tempDir, { recursive: true, force: true });
        }
    }

    function runNumericStabilityMatmulLogitsSlice(runOptions) {
        if (!runOptions || typeof runOptions !== "object") {
            throw new Error("runNumericStabilityMatmulLogitsSlice requires an options object.");
        }
        const autoArtifactDir =
            runOptions.receiptPath == null || runOptions.traceMetaPath == null
                ? mkdtempSync(join(tmpdir(), "doe-numeric-stability-"))
                : null;
        const receiptPath = resolve(
            runOptions.receiptPath ??
                join(autoArtifactDir, "matmul-logits-slice.numeric-stability.jsonl")
        );
        const traceMetaPath = resolve(
            runOptions.traceMetaPath ??
                join(autoArtifactDir, "matmul-logits-slice.trace-meta.json")
        );
        clearOutputPath(receiptPath);
        clearOutputPath(traceMetaPath);
        const moduleResult = runModule({
            moduleId: NUMERIC_STABILITY_MODULE_ID,
            moduleRunnerPath: runOptions.moduleRunnerPath ?? moduleRunnerPath,
            policyPath:
                runOptions.policyPath ?? DEFAULT_NUMERIC_STABILITY_POLICY_REGISTRY_PATH,
            cwd: runOptions.cwd || REPO_ROOT,
            request: {
                schemaVersion: 1,
                moduleId: NUMERIC_STABILITY_MODULE_ID,
                artifactKind: "request",
                serviceId: NUMERIC_STABILITY_MATMUL_LOGITS_SLICE_SERVICE_ID,
                operatorFamily:
                    runOptions.operatorFamily ?? DEFAULT_NUMERIC_STABILITY_OPERATOR_FAMILY,
                semanticOpId:
                    runOptions.semanticOpId ?? DEFAULT_NUMERIC_STABILITY_SEMANTIC_OP_ID,
                semanticStage:
                    runOptions.semanticStage ?? DEFAULT_NUMERIC_STABILITY_SEMANTIC_STAGE,
                semanticPhase:
                    runOptions.semanticPhase ?? DEFAULT_NUMERIC_STABILITY_SEMANTIC_PHASE,
                triggerPolicyId:
                    runOptions.triggerPolicyId ??
                    DEFAULT_NUMERIC_STABILITY_TRIGGER_POLICY_ID,
                routingPolicyId:
                    runOptions.routingPolicyId ??
                    DEFAULT_NUMERIC_STABILITY_ROUTING_POLICY_ID,
                fastPolicyId:
                    runOptions.fastPolicyId ?? DEFAULT_NUMERIC_STABILITY_FAST_POLICY_ID,
                stablePolicyId:
                    runOptions.stablePolicyId ?? DEFAULT_NUMERIC_STABILITY_STABLE_POLICY_ID,
                hiddenState: runOptions.hiddenState,
                candidates: runOptions.candidates,
                receiptPath,
                traceMetaPath,
            },
        });
        if (!moduleResult.ok) {
            throw new Error(
                `Doe numeric stability service failed (${moduleResult.exitCode}): ${moduleResult.stderr || moduleResult.stdout}`
            );
        }
        const output = moduleResult.output ?? null;
        const traceMeta = readTraceMeta(traceMetaPath);
        return {
            ...moduleResult,
            receiptPath,
            traceMetaPath,
            traceMeta,
            routeDecision: output?.routeDecision ?? null,
            token: output?.selectedToken ?? null,
            receipt: output?.receipt ?? null,
        };
    }

    return {
        binPath,
        libPath,
        moduleRunnerPath,
        runRaw,
        runBench,
        runModule,
        runNumericStabilityMatmulLogitsSlice,
    };
}

export function runDawnVsDoeCompare(options = {}) {
    const repoRoot = resolveDoeRepoRoot(options.repoRoot);
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

    if (!options.configPath && !hasOptionFlag(extraArgs, "--config")) {
        throw new Error("runDawnVsDoeCompare requires configPath or --config in extraArgs.");
    }

    return runProcess(pythonBin, args, {
        cwd: repoRoot,
        env: { ...process.env, ...(options.env ?? {}) },
    });
}
