#!/usr/bin/env node
import { resolve } from "node:path";
import { createDoeRuntime } from "../src/node-runtime.js";

function usage() {
    console.log(`Usage:
  fawn-webgpu-bench --commands PATH [options]

Options:
  --commands PATH            Command JSON input (required)
  --quirks PATH              Quirk JSON input
  --vendor NAME              Profile vendor
  --api NAME                 Profile API
  --family NAME              Device family
  --driver VERSION           Driver string
  --trace-jsonl PATH         Trace NDJSON output path
  --trace-meta PATH          Trace meta JSON output path
  --queue-wait-mode MODE     process-events|wait-any
  --queue-sync-mode MODE     per-command|deferred
  --upload-buffer-usage MODE copy-dst|copy-dst-copy-src
  --upload-submit-every N    Upload submission cadence
  --doe-bin PATH             doe-zig-runtime path override
  --doe-lib PATH             libwebgpu_doe path override
  --extra-arg ARG            Pass through additional arg to runtime (repeatable)
  --json                     Emit full JSON result
  --help                     Show this help
`);
}

function parseArgs(argv) {
    const opts = { extraArgs: [] };
    for (let i = 0; i < argv.length; i += 1) {
        const arg = argv[i];
        const next = argv[i + 1];
        switch (arg) {
            case "--help":
                opts.help = true;
                break;
            case "--json":
                opts.json = true;
                break;
            case "--commands":
                opts.commandsPath = next;
                i += 1;
                break;
            case "--quirks":
                opts.quirksPath = next;
                i += 1;
                break;
            case "--vendor":
                opts.vendor = next;
                i += 1;
                break;
            case "--api":
                opts.api = next;
                i += 1;
                break;
            case "--family":
                opts.family = next;
                i += 1;
                break;
            case "--driver":
                opts.driver = next;
                i += 1;
                break;
            case "--trace-jsonl":
                opts.traceJsonlPath = next;
                i += 1;
                break;
            case "--trace-meta":
                opts.traceMetaPath = next;
                i += 1;
                break;
            case "--queue-wait-mode":
                opts.queueWaitMode = next;
                i += 1;
                break;
            case "--queue-sync-mode":
                opts.queueSyncMode = next;
                i += 1;
                break;
            case "--upload-buffer-usage":
                opts.uploadBufferUsage = next;
                i += 1;
                break;
            case "--upload-submit-every":
                opts.uploadSubmitEvery = Number.parseInt(next ?? "", 10);
                i += 1;
                break;
            case "--doe-bin":
                opts.binPath = next;
                i += 1;
                break;
            case "--doe-lib":
                opts.libPath = next;
                i += 1;
                break;
            case "--extra-arg":
                opts.extraArgs.push(next ?? "");
                i += 1;
                break;
            default:
                throw new Error(`Unknown option: ${arg}`);
        }
    }
    return opts;
}

function toAbsolutePath(path) {
    if (!path) return path;
    return resolve(path);
}

function summarize(result) {
    const lines = [
        `ok: ${result.ok}`,
        `exitCode: ${result.exitCode}`,
    ];
    if (result.traceMetaPath) {
        lines.push(`traceMetaPath: ${result.traceMetaPath}`);
    }
    if (result.traceJsonlPath) {
        lines.push(`traceJsonlPath: ${result.traceJsonlPath}`);
    }
    if (result.traceMeta?.executionTotalNs != null) {
        lines.push(`executionTotalNs: ${result.traceMeta.executionTotalNs}`);
    }
    if (result.traceMeta?.executionEncodeTotalNs != null) {
        lines.push(`executionEncodeTotalNs: ${result.traceMeta.executionEncodeTotalNs}`);
    }
    if (result.traceMeta?.executionSubmitWaitTotalNs != null) {
        lines.push(`executionSubmitWaitTotalNs: ${result.traceMeta.executionSubmitWaitTotalNs}`);
    }
    return lines.join("\n");
}

function main() {
    const opts = parseArgs(process.argv.slice(2));
    if (opts.help) {
        usage();
        return;
    }
    if (!opts.commandsPath) {
        usage();
        throw new Error("--commands is required");
    }

    const runtime = createDoeRuntime({
        binPath: toAbsolutePath(opts.binPath),
        libPath: toAbsolutePath(opts.libPath),
    });

    const result = runtime.runBench({
        commandsPath: toAbsolutePath(opts.commandsPath),
        quirksPath: toAbsolutePath(opts.quirksPath),
        vendor: opts.vendor,
        api: opts.api,
        family: opts.family,
        driver: opts.driver,
        traceJsonlPath: toAbsolutePath(opts.traceJsonlPath),
        traceMetaPath: toAbsolutePath(opts.traceMetaPath),
        queueWaitMode: opts.queueWaitMode,
        queueSyncMode: opts.queueSyncMode,
        uploadBufferUsage: opts.uploadBufferUsage,
        uploadSubmitEvery: opts.uploadSubmitEvery,
        extraArgs: opts.extraArgs,
    });

    if (opts.json) {
        console.log(JSON.stringify(result, null, 2));
    } else {
        console.log(summarize(result));
    }
    process.exitCode = result.exitCode;
}

try {
    main();
} catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
}
