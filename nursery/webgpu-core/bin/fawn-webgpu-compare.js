#!/usr/bin/env node
import { resolve } from "node:path";
import { runDawnVsDoeCompare } from "../src/node-runtime.js";

function usage() {
    console.log(`Usage:
  fawn-webgpu-compare --config PATH [options] [-- <extra compare args>]

Options:
  --config PATH                compare_dawn_vs_doe config JSON path (required unless passed in --extra-arg)
  --out PATH                   output report path
  --repo-root PATH             Fawn repo root override
  --compare-script PATH        compare_dawn_vs_doe.py path override
  --python BIN                 Python executable (default: python3)
  --extra-arg ARG              pass-through arg (repeatable)
  --help                       show this help
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
            case "--config":
                opts.configPath = next;
                i += 1;
                break;
            case "--out":
                opts.outPath = next;
                i += 1;
                break;
            case "--repo-root":
                opts.repoRoot = next;
                i += 1;
                break;
            case "--compare-script":
                opts.compareScriptPath = next;
                i += 1;
                break;
            case "--python":
                opts.pythonBin = next;
                i += 1;
                break;
            case "--extra-arg":
                opts.extraArgs.push(next ?? "");
                i += 1;
                break;
            case "--":
                opts.extraArgs.push(...argv.slice(i + 1));
                i = argv.length;
                break;
            default:
                throw new Error(`Unknown option: ${arg}`);
        }
    }
    return opts;
}

function toAbsolute(path) {
    if (!path) return path;
    return resolve(path);
}

function main() {
    const opts = parseArgs(process.argv.slice(2));
    if (opts.help) {
        usage();
        return;
    }

    const result = runDawnVsDoeCompare({
        repoRoot: toAbsolute(opts.repoRoot),
        compareScriptPath: toAbsolute(opts.compareScriptPath),
        pythonBin: opts.pythonBin,
        configPath: toAbsolute(opts.configPath),
        outPath: toAbsolute(opts.outPath),
        extraArgs: opts.extraArgs,
    });

    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    process.exitCode = result.exitCode;
}

try {
    main();
} catch (error) {
    usage();
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
}
