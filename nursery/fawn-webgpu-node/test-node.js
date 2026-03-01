import { existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createDoeRuntime } from "./src/node-runtime.js";

const PACKAGE_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_COMMANDS = resolve(PACKAGE_DIR, "../../examples/buffer_upload_1kb_commands.json");
const OUT_DIR = resolve(PACKAGE_DIR, "out");

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

    const result = runtime.runBench({
        commandsPath: DEFAULT_COMMANDS,
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
