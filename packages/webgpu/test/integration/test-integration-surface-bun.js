import * as api from "../../src/bun.js";
import { runSurfaceConformance } from "./test-integration-surface.js";

const { failed } = await runSurfaceConformance(api, "bun");
process.exitCode = failed > 0 ? 1 : 0;
