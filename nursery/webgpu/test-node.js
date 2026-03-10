import { existsSync, mkdirSync } from "node:fs";
import os from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createDoeRuntime } from "./src/node-runtime.js";

const PACKAGE_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(PACKAGE_DIR, "..", "..");
const DEFAULT_COMMANDS = resolve(PACKAGE_DIR, "../../examples/upload_1kb_commands.json");
const DEFAULT_APPLE_QUIRKS = resolve(PACKAGE_DIR, "../../examples/quirks/apple_m3_noop_list.json");
const OUT_DIR = resolve(PACKAGE_DIR, "out");

function defaultBenchOptions() {
    if (process.env.FAWN_TEST_QUIRKS || process.env.FAWN_TEST_VENDOR || process.env.FAWN_TEST_API) {
        return {
            quirksPath: process.env.FAWN_TEST_QUIRKS || undefined,
            vendor: process.env.FAWN_TEST_VENDOR || undefined,
            api: process.env.FAWN_TEST_API || undefined,
            family: process.env.FAWN_TEST_FAMILY || undefined,
            driver: process.env.FAWN_TEST_DRIVER || undefined,
        };
    }

    if (process.platform === "darwin" && os.arch() === "arm64" && existsSync(DEFAULT_APPLE_QUIRKS)) {
        return {
            quirksPath: DEFAULT_APPLE_QUIRKS,
            vendor: "apple",
            api: "metal",
            family: "m3",
            driver: "1.0.0",
        };
    }

    return {};
}

function main() {
    if (!existsSync(DEFAULT_COMMANDS)) {
        console.log(`skip: commands file not found: ${DEFAULT_COMMANDS}`);
        return;
    }

    const runtime = createDoeRuntime({
        binPath: process.env.FAWN_DOE_BIN,
        libPath: process.env.FAWN_DOE_LIB,
    });

    mkdirSync(OUT_DIR, { recursive: true });
    const benchOptions = defaultBenchOptions();

    const result = runtime.runBench({
        commandsPath: DEFAULT_COMMANDS,
        quirksPath: benchOptions.quirksPath,
        vendor: benchOptions.vendor,
        api: benchOptions.api,
        family: benchOptions.family,
        driver: benchOptions.driver,
        cwd: REPO_ROOT,
        traceJsonlPath: resolve(OUT_DIR, "node-smoke.ndjson"),
        traceMetaPath: resolve(OUT_DIR, "node-smoke.meta.json"),
    });

    console.log(
        JSON.stringify(
            {
                ok: result.ok,
                exitCode: result.exitCode,
                traceMetaPath: result.traceMetaPath,
                executionTotalNs: result.traceMeta?.executionTotalNs ?? null,
                executionEncodeTotalNs: result.traceMeta?.executionEncodeTotalNs ?? null,
                executionSubmitWaitTotalNs: result.traceMeta?.executionSubmitWaitTotalNs ?? null,
            },
            null,
            2
        )
    );

    process.exitCode = result.exitCode;
}

try {
    main();
} catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
}
