import * as api from "../../src/node-runtime.js";
import { runSurfaceConformance } from "./test-integration-surface.js";

const { failed } = await runSurfaceConformance(api, "node");
process.exitCode = failed > 0 ? 1 : 0;
