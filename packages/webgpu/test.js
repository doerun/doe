import { create, providerInfo } from "./src/bun.js";

async function main() {
    const info = providerInfo();
    console.log("Provider info:", JSON.stringify(info, null, 2));

    if (!info.loaded) {
        console.log("skip: library not loaded");
        return;
    }

    const gpu = create();
    console.log("Created GPU instance");

    const adapter = await gpu.requestAdapter();
    console.log("Got adapter:", adapter != null);

    const device = await adapter.requestDevice();
    console.log("Got device:", device != null);
    console.log("Queue:", device.queue != null);
    console.log("Prototype smoke test complete.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
