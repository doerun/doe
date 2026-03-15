#!/usr/bin/env node

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = resolve(__dirname, "..");
const README_PATH = resolve(PACKAGE_ROOT, "README.md");
const DOE_PACKAGE_ROOT = existsSync(resolve(PACKAGE_ROOT, "..", "webgpu-doe", "package.json"))
  ? resolve(PACKAGE_ROOT, "..", "webgpu-doe")
  : resolve(PACKAGE_ROOT, "node_modules", "@simulatte", "webgpu-doe");
const DOE_JS_PATH = resolve(DOE_PACKAGE_ROOT, "src", "index.js");
const DOE_DTS_PATH = resolve(DOE_PACKAGE_ROOT, "src", "index.d.ts");
const EXAMPLES_DIR = resolve(PACKAGE_ROOT, "examples", "doe-api");
const OUTPUT_DIR = resolve(PACKAGE_ROOT, "docs");
const OUTPUT_PATH = resolve(OUTPUT_DIR, "doe-api-reference.html");
const DOE_PACKAGE_SOURCE_PATH = "@simulatte/webgpu-doe/src/index.js";
const DOE_PACKAGE_TYPE_PATH = "@simulatte/webgpu-doe/src/index.d.ts";
const DOE_GITHUB_PREFIX = "https://github.com/clocksmith/fawn/tree/main/nursery/webgpu-doe/";

const API_ENTRY_SPECS = [
  {
    id: "doe.requestDevice",
    title: "doe.requestDevice",
    signature: "doe.requestDevice(options?) -> Promise<gpu>",
    marker: "Request a device and return the bound Doe API in one step.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
  {
    id: "doe.bind",
    title: "doe.bind",
    signature: "doe.bind(device) -> gpu",
    marker: "Wrap an existing device in the bound Doe API.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
  {
    id: "gpu.buffer.create",
    title: "gpu.buffer.create",
    signature: "gpu.buffer.create(options) -> GPUBuffer",
    marker: "Create a buffer with explicit size and Doe usage tokens.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
  {
    id: "gpu.buffer.read",
    title: "gpu.buffer.read",
    signature: "gpu.buffer.read(options) -> Promise<TypedArray>",
    marker: "Read a buffer back into a typed array.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
  {
    id: "gpu.kernel.run",
    title: "gpu.kernel.run",
    signature: "gpu.kernel.run(options) -> Promise<void>",
    marker: "Compile and dispatch a one-off compute job.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
  {
    id: "gpu.kernel.create",
    title: "gpu.kernel.create",
    signature: "gpu.kernel.create(options) -> DoeKernel",
    marker: "Compile a reusable compute kernel.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
  {
    id: "DoeKernel",
    title: "DoeKernel",
    signature: "class DoeKernel",
    marker: "Reusable compute kernel compiled by `gpu.kernel.create(...)`.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
  {
    id: "DoeKernel.dispatch",
    title: "kernel.dispatch",
    signature: "kernel.dispatch(options) -> Promise<void>",
    marker: "Dispatch this compiled kernel once.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
  {
    id: "gpu.compute",
    title: "gpu.compute",
    signature: "gpu.compute(options) -> Promise<TypedArray>",
    marker: "Run a one-shot typed-array compute workflow.",
    sourcePath: DOE_PACKAGE_SOURCE_PATH,
    typePath: DOE_PACKAGE_TYPE_PATH,
    sourceLabel: "Source",
    typeLabel: "Types",
  },
];

const EXAMPLE_ORDER = [
  {
    filename: "buffers-readback.js",
    title: "Buffer create + readback",
    summary: "Create a Doe-managed buffer from host data, then read it back through gpu.buffer.read(...).",
    apiIds: ["gpu.buffer.create", "gpu.buffer.read"],
    accent: "buffer",
  },
  {
    filename: "kernel-run.js",
    title: "One-off kernel run",
    summary: "Use gpu.kernel.run(...) when you want explicit buffers but do not need to keep compiled kernel state.",
    apiIds: ["gpu.kernel.run", "gpu.buffer.create", "gpu.buffer.read"],
    accent: "kernel",
  },
  {
    filename: "kernel-create-and-dispatch.js",
    title: "Reusable kernel dispatch",
    summary: "Compile a DoeKernel once with gpu.kernel.create(...), then dispatch it explicitly.",
    apiIds: ["gpu.kernel.create", "DoeKernel", "DoeKernel.dispatch"],
    accent: "kernel",
  },
  {
    filename: "compute-one-shot.js",
    title: "One-shot compute",
    summary: "Run the opinionated gpu.compute(...) helper with one typed-array input and inferred output sizing.",
    apiIds: ["gpu.compute"],
    accent: "compute",
  },
  {
    filename: "compute-one-shot-like-input.js",
    title: "One-shot compute with likeInput",
    summary: "Use gpu.compute(...) with a uniform input and likeInput sizing to keep output shape explicit.",
    apiIds: ["gpu.compute"],
    accent: "compute",
  },
  {
    filename: "compute-one-shot-multiple-inputs.js",
    title: "One-shot compute with multiple inputs",
    summary: "Feed multiple typed-array inputs through gpu.compute(...) while keeping the shader and result explicit.",
    apiIds: ["gpu.compute"],
    accent: "compute",
  },
  {
    filename: "compute-one-shot-matmul.js",
    title: "One-shot compute matmul",
    summary: "Run a larger matrix multiply through gpu.compute(...) with explicit tensor dimensions and output size.",
    apiIds: ["gpu.compute"],
    accent: "compute",
  },
];

function readUtf8(path) {
  return readFileSync(path, "utf8");
}

function resolveDocLink(path) {
  if (path.startsWith("@simulatte/webgpu-doe/")) {
    return `${DOE_GITHUB_PREFIX}${path.slice("@simulatte/webgpu-doe/".length)}`;
  }
  return `../${path}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}

function stripMarkdownInline(value) {
  return value
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
}

function extractIntro(readme) {
  const lines = readme.split("\n");
  const intro = [];
  for (const line of lines) {
    if (line.startsWith("## Start here")) {
      break;
    }
    if (line.startsWith("# ")) {
      continue;
    }
    if (line.includes("<") && line.includes(">")) {
      continue;
    }
    if (line.trim() === "") {
      if (intro.length > 0 && intro.at(-1) !== "") {
        intro.push("");
      }
      continue;
    }
    intro.push(line);
  }
  return intro.join("\n").trim();
}

function extractDocBlock(source, marker) {
  const markerIndex = source.indexOf(marker);
  if (markerIndex === -1) {
    throw new Error(`Could not find marker in doe.js: ${marker}`);
  }
  const start = source.lastIndexOf("/**", markerIndex);
  const end = source.indexOf("*/", start);
  if (start === -1 || end === -1) {
    throw new Error(`Could not find JSDoc block for marker: ${marker}`);
  }
  return source
    .slice(start + 3, end)
    .split("\n")
    .map((line) => line.replace(/^\s*\*\s?/, ""))
    .join("\n")
    .trim();
}

function parseDocBlock(block) {
  const lines = block.split("\n");
  const summary = stripMarkdownInline(lines[0]?.trim() ?? "");
  const sections = {
    summary,
    surface: "",
    input: "",
    returns: "",
    details: [],
    notes: [],
    example: "",
  };

  let inExample = false;
  let seenExample = false;
  const exampleLines = [];

  for (let index = 1; index < lines.length; index += 1) {
    const raw = lines[index];
    const line = raw.trim();
    if (line === "```js") {
      inExample = true;
      seenExample = true;
      continue;
    }
    if (line === "```") {
      inExample = false;
      continue;
    }
    if (inExample) {
      exampleLines.push(raw);
      continue;
    }
    if (line.startsWith("Surface:")) {
      sections.surface = stripMarkdownInline(line.slice("Surface:".length).trim());
      continue;
    }
    if (line.startsWith("Input:")) {
      sections.input = stripMarkdownInline(line.slice("Input:".length).trim());
      continue;
    }
    if (line.startsWith("Returns:")) {
      sections.returns = stripMarkdownInline(line.slice("Returns:".length).trim());
      continue;
    }
    if (line.startsWith("- ")) {
      sections.notes.push(stripMarkdownInline(line.slice(2).trim()));
      continue;
    }
    if (line !== "" && !seenExample && !line.startsWith("This example")) {
      sections.details.push(stripMarkdownInline(line));
    }
  }

  sections.details = sections.details.filter((line) => line !== "");
  sections.example = exampleLines.join("\n").trim();
  return sections;
}

function extractSignatureSnippet(dts, signature) {
  const escaped = signature.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(escaped, "m");
  return regex.test(dts);
}

function readExamples() {
  return EXAMPLE_ORDER.map((spec) => {
    const source = readUtf8(resolve(EXAMPLES_DIR, spec.filename)).trim();
    return {
      ...spec,
      source,
      runnableSource: source.replace(/^import\s+\{\s*doe\s*\}\s+from\s+"@simulatte\/webgpu\/compute";\n\n?/, ""),
      tokens: `${spec.title} ${spec.summary} ${spec.filename} ${spec.apiIds.join(" ")}`.toLowerCase(),
    };
  });
}

function buildApiEntries(doeSource, dtsSource) {
  return API_ENTRY_SPECS.map((spec) => {
    const doc = parseDocBlock(extractDocBlock(doeSource, spec.marker));
    return {
      id: spec.id,
      title: spec.title,
      signature: spec.signature,
      doc,
      sourcePath: spec.sourcePath,
      typePath: spec.typePath,
      sourceLabel: spec.sourceLabel,
      typeLabel: spec.typeLabel,
      hasTypeHint: extractSignatureSnippet(dtsSource, "compute<T") || spec.id !== "gpu.compute",
      tokens: `${spec.title} ${spec.signature} ${doc.summary} ${doc.surface} ${doc.input} ${doc.returns} ${doc.details.join(" ")} ${doc.notes.join(" ")}`.toLowerCase(),
    };
  });
}

function renderApiEntry(entry) {
  const notes = entry.doc.notes
    .map((note) => `<li>${escapeHtml(note)}</li>`)
    .join("");
  const details = entry.doc.details
    .map((line) => `<p>${escapeHtml(line)}</p>`)
    .join("");
  const exampleBlock = entry.doc.example
    ? `<details class="apiExample"><summary>JSDoc example</summary><pre><code>${escapeHtml(entry.doc.example)}</code></pre></details>`
    : "";

  return `
    <article class="apiCard searchTarget" data-search="${escapeAttribute(entry.tokens)}" id="${escapeAttribute(entry.id)}">
      <div class="apiHeader">
        <div>
          <div class="eyebrow">${escapeHtml(entry.doc.surface)}</div>
          <h3>${escapeHtml(entry.title)}</h3>
        </div>
        <code class="signature">${escapeHtml(entry.signature)}</code>
      </div>
      <p class="summary">${escapeHtml(entry.doc.summary)}</p>
      <dl class="contractGrid">
        <div><dt>Input</dt><dd>${escapeHtml(entry.doc.input)}</dd></div>
        <div><dt>Returns</dt><dd>${escapeHtml(entry.doc.returns)}</dd></div>
      </dl>
      <div class="detailsBody">${details}</div>
      ${notes ? `<ul class="notes">${notes}</ul>` : ""}
      ${exampleBlock}
      <div class="linkRow">
        <a href="${escapeAttribute(resolveDocLink(entry.sourcePath))}">${escapeHtml(entry.sourceLabel)}</a>
        <a href="${escapeAttribute(resolveDocLink(entry.typePath))}">${escapeHtml(entry.typeLabel)}</a>
      </div>
    </article>`;
}

function renderExampleCard(example) {
  return `
    <article class="exampleCard searchTarget" data-search="${escapeAttribute(example.tokens)}" data-accent="${escapeAttribute(example.accent)}" id="example-${escapeAttribute(example.filename)}">
      <div class="exampleTop">
        <div>
          <div class="eyebrow">Example</div>
          <h3>${escapeHtml(example.title)}</h3>
        </div>
        <code class="filename">${escapeHtml(example.filename)}</code>
      </div>
      <p class="summary">${escapeHtml(example.summary)}</p>
      <div class="exampleLinks">
        ${example.apiIds.map((apiId) => `<a href="#${escapeAttribute(apiId)}">${escapeHtml(apiId)}</a>`).join("")}
      </div>
      <div class="buttonRow">
        <button type="button" class="runButton" data-run-example="${escapeAttribute(example.filename)}">Run example</button>
        <button type="button" class="ghostButton" data-reset-example="${escapeAttribute(example.filename)}">Reset</button>
        <button type="button" class="ghostButton" data-copy-example="${escapeAttribute(example.filename)}">Copy</button>
        <a class="ghostLink" href="../examples/doe-api/${escapeAttribute(example.filename)}">Open source</a>
      </div>
      <div class="outputShell">
        <div class="outputMeta" data-output-meta="${escapeAttribute(example.filename)}">Ready to run in a browser with WebGPU.</div>
        <div class="metricChips" data-output-stats="${escapeAttribute(example.filename)}"></div>
        <canvas class="chartCanvas" data-output-chart="${escapeAttribute(example.filename)}" width="960" height="220"></canvas>
        <div class="valueGrid" data-output-values="${escapeAttribute(example.filename)}"></div>
        <pre class="outputBlock" data-output-text="${escapeAttribute(example.filename)}"></pre>
      </div>
      <details class="editorDetails">
        <summary>View or edit source</summary>
        <div class="editorShell">
          <textarea class="editor" data-example-editor="${escapeAttribute(example.filename)}" spellcheck="false">${escapeHtml(example.source)}</textarea>
        </div>
      </details>
    </article>`;
}

function buildPage(data) {
  const apiCards = data.apiEntries.map(renderApiEntry).join("\n");
  const exampleCards = data.examples.map(renderExampleCard).join("\n");
  const dataJson = JSON.stringify(data);

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Doe API reference</title>
  <style>
    :root {
      --bg: #06111a;
      --bg-2: #0d1b2a;
      --panel: rgba(8, 15, 26, 0.76);
      --panel-2: rgba(12, 24, 38, 0.92);
      --line: rgba(160, 196, 255, 0.16);
      --text: #eef6ff;
      --muted: #93a8bf;
      --hot: #fb7185;
      --cold: #22d3ee;
      --gold: #facc15;
      --success: #34d399;
      --paper: rgba(255, 255, 255, 0.03);
      --shadow: 0 30px 80px rgba(0, 0, 0, 0.35);
      --radius: 28px;
      --radius-sm: 18px;
      --mono: "SFMono-Regular", Menlo, Consolas, monospace;
      --sans: "Instrument Sans", "Inter", "Segoe UI", system-ui, sans-serif;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body {
      margin: 0;
      font-family: var(--sans);
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(34, 211, 238, 0.22), transparent 32%),
        radial-gradient(circle at top right, rgba(251, 113, 133, 0.18), transparent 28%),
        linear-gradient(160deg, var(--bg) 0%, var(--bg-2) 100%);
      min-height: 100vh;
    }
    a { color: inherit; }
    code, pre, textarea { font-family: var(--mono); }
    .shell {
      display: grid;
      grid-template-columns: 248px minmax(0, 1fr);
      gap: 20px;
      width: min(1380px, calc(100vw - 40px));
      margin: 20px auto 56px;
    }
    .rail {
      position: sticky;
      top: 24px;
      height: calc(100vh - 48px);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: linear-gradient(180deg, rgba(7, 13, 23, 0.92), rgba(10, 19, 32, 0.84));
      box-shadow: var(--shadow);
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 20px;
      backdrop-filter: blur(20px);
    }
    .brand {
      display: grid;
      gap: 8px;
    }
    .brand h1 {
      margin: 0;
      font-size: 1.4rem;
      letter-spacing: -0.03em;
    }
    .brand p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 0.95rem;
    }
    .search {
      width: 100%;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      padding: 12px 14px;
      font: inherit;
    }
    .navGroup {
      display: grid;
      gap: 8px;
    }
    .navGroup h2 {
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
    }
    .navGroup a {
      text-decoration: none;
      color: var(--text);
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid transparent;
      transition: 160ms ease;
    }
    .navGroup a:hover {
      border-color: rgba(255, 255, 255, 0.12);
      transform: translateX(3px);
    }
    .navMeta {
      margin-top: auto;
      color: var(--muted);
      font-size: 0.85rem;
      line-height: 1.6;
    }
    main {
      display: grid;
      gap: 24px;
    }
    .hero,
    .panel,
    .supportPanel {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: linear-gradient(180deg, rgba(10, 18, 30, 0.86), rgba(13, 23, 37, 0.78));
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }
    .hero {
      padding: 36px;
      overflow: hidden;
      position: relative;
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: auto -60px -60px auto;
      width: 240px;
      height: 240px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(250, 204, 21, 0.3), transparent 68%);
      pointer-events: none;
    }
    .eyebrow {
      color: var(--gold);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      margin-bottom: 10px;
    }
    .hero h2 {
      margin: 0;
      max-width: 12ch;
      font-size: clamp(2.3rem, 4.8vw, 4.6rem);
      letter-spacing: -0.06em;
      line-height: 0.98;
    }
    .hero p {
      max-width: 680px;
      color: var(--muted);
      line-height: 1.75;
      font-size: 1rem;
      margin: 18px 0 0;
      white-space: pre-line;
    }
    .heroGrid {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.9fr);
      gap: 24px;
      align-items: end;
    }
    .heroStats {
      display: grid;
      gap: 14px;
    }
    .heroStat {
      border-radius: 18px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .heroStat strong {
      display: block;
      font-size: 1.65rem;
      letter-spacing: -0.04em;
    }
    .heroStat span {
      color: var(--muted);
      display: block;
      margin-top: 6px;
      line-height: 1.5;
    }
    .sectionHeader {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 18px;
    }
    .sectionHeader h2 {
      margin: 0;
      font-size: 1.7rem;
      letter-spacing: -0.04em;
    }
    .sectionHeader p {
      margin: 0;
      color: var(--muted);
      max-width: 720px;
      line-height: 1.6;
    }
    .panel {
      padding: 28px;
    }
    .statusGrid,
    .apiGrid,
    .examplesGrid {
      display: grid;
      gap: 18px;
    }
    .statusGrid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .statusCard,
    .apiCard,
    .exampleCard {
      border-radius: 22px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .statusCard {
      padding: 18px;
    }
    .statusCard dt {
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--muted);
    }
    .statusCard dd {
      margin: 12px 0 0;
      font-size: 1.2rem;
      letter-spacing: -0.03em;
    }
    .apiGrid {
      grid-template-columns: minmax(0, 1fr);
    }
    .apiCard {
      padding: 20px;
      display: grid;
      gap: 16px;
    }
    .apiHeader {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
    }
    .apiHeader h3,
    .exampleTop h3 {
      margin: 4px 0 0;
      font-size: 1.3rem;
      letter-spacing: -0.03em;
    }
    .signature,
    .filename {
      white-space: nowrap;
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(34, 211, 238, 0.1);
      border: 1px solid rgba(34, 211, 238, 0.24);
      color: #baf7ff;
      font-size: 0.84rem;
    }
    .summary,
    .detailsBody p,
    .outputMeta {
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }
    .contractGrid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin: 0;
    }
    .contractGrid div {
      padding: 14px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.07);
    }
    .contractGrid dt {
      color: var(--gold);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      margin-bottom: 8px;
    }
    .contractGrid dd {
      margin: 0;
      line-height: 1.55;
    }
    .notes {
      margin: 0;
      padding-left: 18px;
      color: #d6e7fb;
      display: grid;
      gap: 8px;
    }
    .apiExample summary {
      cursor: pointer;
      color: #d6e7fb;
    }
    .apiExample pre,
    .outputBlock,
    .editor {
      margin: 0;
      background: rgba(3, 7, 13, 0.92);
      border-radius: 18px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #dbebff;
      font-size: 0.9rem;
      line-height: 1.55;
    }
    .apiExample pre,
    .outputBlock {
      padding: 16px;
      overflow: auto;
    }
    .linkRow,
    .exampleLinks,
    .buttonRow {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    .linkRow a,
    .exampleLinks a,
    .ghostLink {
      text-decoration: none;
      color: #c7dbf7;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .examplesGrid {
      grid-template-columns: minmax(0, 1fr);
    }
    .exampleCard {
      padding: 20px;
      display: grid;
      gap: 14px;
    }
    .exampleTop {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
    }
    .editor {
      width: 100%;
      min-height: 240px;
      resize: vertical;
      padding: 18px;
      white-space: pre;
    }
    .runButton,
    .ghostButton {
      appearance: none;
      border: none;
      cursor: pointer;
      border-radius: 999px;
      padding: 11px 15px;
      font: inherit;
      color: var(--text);
    }
    .runButton {
      background: linear-gradient(135deg, var(--cold), #60a5fa);
      color: #041521;
      font-weight: 700;
    }
    .ghostButton {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .outputShell {
      display: grid;
      gap: 12px;
    }
    .metricChips {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .metricChip,
    .valuePill {
      border-radius: 999px;
      padding: 8px 12px;
      background: var(--paper);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #d6e7fb;
      font-size: 0.85rem;
    }
    .chartCanvas {
      width: 100%;
      height: 220px;
      display: block;
      border-radius: 18px;
      background: rgba(3, 7, 13, 0.92);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .valueGrid {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .editorDetails {
      border-radius: 18px;
      background: var(--paper);
      border: 1px solid rgba(255, 255, 255, 0.08);
      overflow: hidden;
    }
    .editorDetails summary {
      cursor: pointer;
      padding: 14px 16px;
      color: #d6e7fb;
      font-weight: 600;
    }
    .editorShell {
      padding: 0 16px 16px;
    }
    .hidden {
      display: none !important;
    }
    .footerNote {
      color: var(--muted);
      line-height: 1.7;
    }
    @media (max-width: 1180px) {
      .shell {
        grid-template-columns: 1fr;
      }
      .rail {
        position: static;
        height: auto;
      }
      .apiGrid,
      .examplesGrid,
      .statusGrid,
      .heroGrid,
      .contractGrid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="rail">
      <div class="brand">
        <div class="eyebrow">Doe API</div>
        <h1>Interactive reference</h1>
        <p>Generated from the real Doe source docs, type surface, and shipped examples.</p>
      </div>
      <input class="search" id="search" type="search" placeholder="Search API and examples" />
      <nav class="navGroup">
        <h2>Jump to</h2>
        <a href="#overview">Overview</a>
        <a href="#runtime">Runtime check</a>
        <a href="#api">API reference</a>
        <a href="#examples">Live examples</a>
      </nav>
      <div class="navGroup">
        <h2>Primary APIs</h2>
        ${data.apiEntries.map((entry) => `<a href="#${escapeAttribute(entry.id)}">${escapeHtml(entry.title)}</a>`).join("")}
      </div>
      <div class="navMeta">
        <div>Output: <code>docs/doe-api-reference.html</code></div>
        <div>Source docs: <code>@simulatte/webgpu-doe/src/index.js</code></div>
        <div>Type surface: <code>@simulatte/webgpu-doe/src/index.d.ts</code></div>
        <div>Examples: <code>examples/doe-api/</code></div>
      </div>
    </aside>
    <main>
      <section class="hero" id="overview">
        <div class="heroGrid">
          <div>
            <div class="eyebrow">2026 package docs</div>
            <h2>Doe API, as code and as contract.</h2>
            <p>${escapeHtml(data.intro)}</p>
          </div>
          <div class="heroStats">
            <div class="heroStat">
              <strong>${data.apiEntries.length}</strong>
              <span>public Doe API entries documented from current JSDoc and type shape</span>
            </div>
            <div class="heroStat">
              <strong>${data.examples.length}</strong>
              <span>shipped Doe examples, live-editable and runnable in a browser with WebGPU</span>
            </div>
            <div class="heroStat">
              <strong>1 page</strong>
              <span>API reference, live examples, and runtime status in one self-contained artifact</span>
            </div>
          </div>
        </div>
      </section>

      <section class="panel" id="runtime">
        <div class="sectionHeader">
          <div>
            <div class="eyebrow">Runtime check</div>
            <h2>Can this browser run the examples?</h2>
          </div>
          <p>The page executes the shipped Doe examples through a browser-side Doe demo adapter over WebGPU. It runs real WGSL and real GPU work when WebGPU is available.</p>
        </div>
        <div class="statusGrid">
          <dl class="statusCard">
            <dt>WebGPU</dt>
            <dd id="status-webgpu">Checking…</dd>
          </dl>
          <dl class="statusCard">
            <dt>Adapter</dt>
            <dd id="status-adapter">Pending</dd>
          </dl>
          <dl class="statusCard">
            <dt>Device</dt>
            <dd id="status-device">Pending</dd>
          </dl>
        </div>
      </section>

      <section class="panel" id="api">
        <div class="sectionHeader">
          <div>
            <div class="eyebrow">API reference</div>
            <h2>Current shipped Doe surface</h2>
          </div>
          <p>Each card is generated from the public JSDoc in <code>@simulatte/webgpu-doe/src/index.js</code> and linked back to the implementation and type surface.</p>
        </div>
        <div class="apiGrid">
          ${apiCards}
        </div>
      </section>

      <section class="panel" id="examples">
        <div class="sectionHeader">
          <div>
            <div class="eyebrow">Live examples</div>
            <h2>Shipped examples that actually run</h2>
          </div>
          <p>These editors start from the real files in <code>examples/doe-api/</code>. Run them as-is, tweak them inline, or use them to compare the explicit kernel path against the one-shot <code>gpu.compute(...)</code> helper.</p>
        </div>
        <div class="examplesGrid">
          ${exampleCards}
        </div>
      </section>

      <section class="supportPanel panel">
        <div class="sectionHeader">
          <div>
            <div class="eyebrow">Generated from</div>
            <h2>Source-of-truth inputs</h2>
          </div>
          <p>The page is generated, not hand-maintained. When the Doe API changes, regenerate this artifact from the current source, types, examples, and README contract language.</p>
        </div>
        <p class="footerNote">
          Inputs: <code>README.md</code>, <code>@simulatte/webgpu-doe/src/index.js</code>, <code>@simulatte/webgpu-doe/src/index.d.ts</code>, and
          the shipped Doe example files in <code>examples/doe-api/</code>. Generated by
          <code>scripts/generate-doe-api-docs.js</code>.
        </p>
      </section>
    </main>
  </div>

  <script id="doe-api-data" type="application/json">${escapeHtml(dataJson)}</script>
  <script type="module">
    const DOC_DATA = JSON.parse(document.getElementById("doe-api-data").textContent);
    const outputState = new Map();
    let doePromise = null;

    function setStatus(id, text) {
      document.getElementById(id).textContent = text;
    }

    function resolveBufferUsageToken(token, combined = false) {
      switch (token) {
        case "upload":
          return GPUBufferUsage.COPY_DST;
        case "readback":
          return combined
            ? GPUBufferUsage.COPY_SRC
            : GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ;
        case "uniform":
          return GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST;
        case "storageRead":
          return GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST;
        case "storageReadWrite":
          return GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST | GPUBufferUsage.COPY_SRC;
        default:
          throw new Error(\`Unknown Doe buffer usage token: \${token}\`);
      }
    }

    function resolveBufferUsage(usage) {
      if (typeof usage === "number") return usage;
      if (typeof usage === "string") return resolveBufferUsageToken(usage);
      if (Array.isArray(usage)) {
        const combined = usage.length > 1;
        return usage.reduce((mask, token) => mask | (
          typeof token === "number"
            ? token
            : resolveBufferUsageToken(token, combined)
        ), 0);
      }
      throw new Error("Doe buffer usage must be a number, string, or string array.");
    }

    function inferBindingAccessToken(token) {
      switch (token) {
        case "uniform":
          return "uniform";
        case "storageRead":
          return "storageRead";
        case "storageReadWrite":
          return "storageReadWrite";
        default:
          return null;
      }
    }

    function inferBindingAccess(usage) {
      if (typeof usage === "number" || usage == null) return null;
      const tokens = typeof usage === "string"
        ? [usage]
        : Array.isArray(usage)
          ? usage.filter((token) => typeof token !== "number")
          : null;
      if (!tokens) return null;
      const inferred = [...new Set(tokens.map(inferBindingAccessToken).filter(Boolean))];
      if (inferred.length > 1) {
        throw new Error(\`Doe buffer usage cannot imply multiple binding access modes: \${inferred.join(", ")}\`);
      }
      return inferred[0] ?? null;
    }

    function normalizeDataView(data) {
      if (ArrayBuffer.isView(data)) {
        return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
      }
      if (data instanceof ArrayBuffer) {
        return new Uint8Array(data);
      }
      throw new Error("Doe buffer data must be an ArrayBuffer or ArrayBufferView.");
    }

    function resolveBufferSize(source, meta) {
      if (source && typeof source === "object" && typeof source.size === "number") {
        return source.size;
      }
      if (meta.has(source)) {
        return meta.get(source).size;
      }
      if (ArrayBuffer.isView(source)) {
        return source.byteLength;
      }
      if (source instanceof ArrayBuffer) {
        return source.byteLength;
      }
      throw new Error("Doe buffer-like source must expose a byte size or be ArrayBuffer-backed data.");
    }

    function normalizeWorkgroups(workgroups) {
      if (typeof workgroups === "number") return [workgroups, 1, 1];
      if (Array.isArray(workgroups) && workgroups.length === 2) return [workgroups[0], workgroups[1], 1];
      if (Array.isArray(workgroups) && workgroups.length === 3) return workgroups;
      throw new Error("Doe workgroups must be a number, [x, y], or [x, y, z].");
    }

    function validatePositiveInteger(value, label) {
      if (!Number.isInteger(value) || value < 1) {
        throw new Error(\`\${label} must be a positive integer.\`);
      }
    }

    function createBrowserDoe(device) {
      const bufferMeta = new WeakMap();

      function rememberBuffer(buffer, usage, size) {
        bufferMeta.set(buffer, {
          bindingAccess: inferBindingAccess(usage),
          size,
        });
        return buffer;
      }

      function inferredBindingAccessForBuffer(buffer) {
        return bufferMeta.get(buffer)?.bindingAccess ?? null;
      }

      function validateWorkgroups(workgroups) {
        const normalized = normalizeWorkgroups(workgroups);
        const [x, y, z] = normalized;
        validatePositiveInteger(x, "Doe workgroups.x");
        validatePositiveInteger(y, "Doe workgroups.y");
        validatePositiveInteger(z, "Doe workgroups.z");
        return normalized;
      }

      function normalizeBinding(binding, index) {
        const entry = binding && typeof binding === "object" && "buffer" in binding
          ? binding
          : { buffer: binding };
        const access = entry.access ?? inferredBindingAccessForBuffer(entry.buffer);
        if (!access) {
          throw new Error(
            "Doe binding access is required for buffers without Doe helper usage metadata. " +
            "Pass { buffer, access } or create the buffer through gpu.buffer.create(...) with a bindable usage token."
          );
        }
        return {
          binding: index,
          buffer: entry.buffer,
          access,
        };
      }

      function bindGroupLayoutEntry(binding) {
        const bufferType = binding.access === "uniform"
          ? "uniform"
          : binding.access === "storageRead"
            ? "read-only-storage"
            : "storage";
        return {
          binding: binding.binding,
          visibility: GPUShaderStage.COMPUTE,
          buffer: { type: bufferType },
        };
      }

      function bindGroupEntry(binding) {
        return {
          binding: binding.binding,
          resource: { buffer: binding.buffer },
        };
      }

      class BrowserDoeKernel {
        constructor(pipeline, layout) {
          this.pipeline = pipeline;
          this.layout = layout;
        }

        async dispatch(options) {
          const bindings = (options.bindings ?? []).map(normalizeBinding);
          const workgroups = validateWorkgroups(options.workgroups);
          const bindGroup = device.createBindGroup({
            layout: this.layout,
            entries: bindings.map(bindGroupEntry),
          });
          const encoder = device.createCommandEncoder({ label: options.label ?? undefined });
          const pass = encoder.beginComputePass({ label: options.label ?? undefined });
          pass.setPipeline(this.pipeline);
          if (bindings.length > 0) {
            pass.setBindGroup(0, bindGroup);
          }
          pass.dispatchWorkgroups(workgroups[0], workgroups[1], workgroups[2]);
          pass.end();
          device.queue.submit([encoder.finish()]);
          await device.queue.onSubmittedWorkDone();
        }
      }

      function createBuffer(options) {
        if (!options || typeof options !== "object") {
          throw new Error("Doe buffer options must be an object.");
        }
        if (options.data != null) {
          const view = normalizeDataView(options.data);
          const usage = options.usage ?? "storageRead";
          const size = options.size ?? view.byteLength;
          const buffer = rememberBuffer(device.createBuffer({
            label: options.label ?? undefined,
            size,
            usage: resolveBufferUsage(usage),
            mappedAtCreation: false,
          }), usage, size);
          device.queue.writeBuffer(buffer, 0, view);
          return buffer;
        }
        validatePositiveInteger(options.size, "Doe buffer size");
        return rememberBuffer(device.createBuffer({
          label: options.label ?? undefined,
          size: options.size,
          usage: resolveBufferUsage(options.usage),
          mappedAtCreation: options.mappedAtCreation ?? false,
        }), options.usage, options.size);
      }

      async function readBuffer(options) {
        if (!options || typeof options !== "object") {
          throw new Error("Doe buffer.read options must be an object.");
        }
        const buffer = options.buffer;
        const type = options.type;
        if (!buffer || typeof buffer !== "object") {
          throw new Error("Doe buffer.read requires a buffer.");
        }
        if (typeof type !== "function") {
          throw new Error("Doe buffer.read type must be a typed-array constructor.");
        }
        const fullSize = resolveBufferSize(buffer, bufferMeta);
        const offset = options.offset ?? 0;
        const size = options.size ?? Math.max(0, fullSize - offset);
        const staging = device.createBuffer({
          label: options.label ?? undefined,
          size,
          usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
        });
        const encoder = device.createCommandEncoder({ label: options.label ?? undefined });
        encoder.copyBufferToBuffer(buffer, offset, staging, 0, size);
        device.queue.submit([encoder.finish()]);
        await device.queue.onSubmittedWorkDone();
        await staging.mapAsync(GPUMapMode.READ);
        const copy = staging.getMappedRange().slice(0);
        staging.unmap();
        staging.destroy();
        return new type(copy);
      }

      function createKernel(options) {
        const bindings = (options.bindings ?? []).map(normalizeBinding);
        const shader = device.createShaderModule({ code: options.code });
        const bindGroupLayout = device.createBindGroupLayout({
          entries: bindings.map(bindGroupLayoutEntry),
        });
        const pipelineLayout = device.createPipelineLayout({
          bindGroupLayouts: [bindGroupLayout],
        });
        const pipeline = device.createComputePipeline({
          layout: pipelineLayout,
          compute: {
            module: shader,
            entryPoint: options.entryPoint ?? "main",
          },
        });
        return new BrowserDoeKernel(pipeline, bindGroupLayout);
      }

      async function runKernel(options) {
        const kernel = createKernel(options);
        await kernel.dispatch({
          bindings: options.bindings ?? [],
          workgroups: options.workgroups,
          label: options.label,
        });
      }

      function usesRawNumericFlags(usage) {
        return typeof usage === "number" || (Array.isArray(usage) && usage.some((token) => typeof token === "number"));
      }

      function assertLayer3Usage(usage, access, path) {
        if (usesRawNumericFlags(usage) && !access) {
          throw new Error(\`Doe \${path} accepts raw numeric usage flags only when explicit access is also provided.\`);
        }
      }

      function normalizeOnceInput(input, index) {
        if (ArrayBuffer.isView(input) || input instanceof ArrayBuffer) {
          const buffer = createBuffer({ data: input });
          return {
            binding: buffer,
            buffer,
            byteLength: resolveBufferSize(input, bufferMeta),
            owned: true,
          };
        }
        if (input && typeof input === "object" && "data" in input) {
          assertLayer3Usage(input.usage, input.access, \`compute input \${index} usage\`);
          const buffer = createBuffer({
            data: input.data,
            usage: input.usage ?? "storageRead",
            label: input.label,
          });
          return {
            binding: input.access ? { buffer, access: input.access } : buffer,
            buffer,
            byteLength: resolveBufferSize(input.data, bufferMeta),
            owned: true,
          };
        }
        if (input && typeof input === "object" && "buffer" in input) {
          return {
            binding: input,
            buffer: input.buffer,
            byteLength: resolveBufferSize(input.buffer, bufferMeta),
            owned: false,
          };
        }
        if (input && typeof input === "object") {
          return {
            binding: input,
            buffer: input,
            byteLength: resolveBufferSize(input, bufferMeta),
            owned: false,
          };
        }
        throw new Error(\`Doe compute input \${index} must be data, a Doe input spec, or a buffer.\`);
      }

      function normalizeOnceOutput(output, inputs) {
        if (!output || typeof output !== "object") {
          throw new Error("Doe compute output is required.");
        }
        if (typeof output.type !== "function") {
          throw new Error("Doe compute output.type must be a typed-array constructor.");
        }
        const fallbackInputIndex = inputs.length > 0 ? 0 : null;
        const likeInputIndex = output.likeInput ?? fallbackInputIndex;
        const size = output.size ?? (
          likeInputIndex != null && inputs[likeInputIndex]
            ? inputs[likeInputIndex].byteLength
            : null
        );
        if (!(size > 0)) {
          throw new Error("Doe compute output size must be provided or derived from likeInput.");
        }
        assertLayer3Usage(output.usage, output.access, "compute output usage");
        const buffer = createBuffer({
          size,
          usage: output.usage ?? "storageReadWrite",
          label: output.label,
        });
        return {
          binding: output.access ? { buffer, access: output.access } : buffer,
          buffer,
          type: output.type,
          readOptions: output.read ?? {},
        };
      }

      async function compute(options) {
        const inputs = (options.inputs ?? []).map((input, index) => normalizeOnceInput(input, index));
        const output = normalizeOnceOutput(options.output, inputs);
        validateWorkgroups(options.workgroups);
        try {
          await runKernel({
            code: options.code,
            entryPoint: options.entryPoint,
            bindings: [...inputs.map((input) => input.binding), output.binding],
            workgroups: options.workgroups,
            label: options.label,
          });
          return await readBuffer({ buffer: output.buffer, type: output.type, ...output.readOptions });
        } finally {
          output.buffer.destroy?.();
          for (const input of inputs) {
            if (input.owned) {
              input.buffer.destroy?.();
            }
          }
        }
      }

      return {
        device,
        buffer: {
          create: createBuffer,
          read: readBuffer,
        },
        kernel: {
          run: runKernel,
          create: createKernel,
        },
        compute,
      };
    }

    async function ensureDoe() {
      if (doePromise) return doePromise;
      if (!("gpu" in navigator)) {
        throw new Error("WebGPU is unavailable in this browser.");
      }
      setStatus("status-webgpu", "WebGPU available");
      doePromise = (async () => {
        const adapter = await navigator.gpu.requestAdapter();
        if (!adapter) {
          throw new Error("No WebGPU adapter was returned.");
        }
        setStatus("status-adapter", adapter.name || "Adapter ready");
        const device = await adapter.requestDevice();
        setStatus("status-device", "Device ready");
        return {
          requestDevice: async () => createBrowserDoe(device),
          bind: (rawDevice) => createBrowserDoe(rawDevice),
        };
      })();
      return doePromise;
    }

    function parseConsoleOutput(lines) {
      const trimmed = lines.join("\\n").trim();
      if (!trimmed) return { text: "No console output.", data: null };
      try {
        return {
          text: trimmed,
          data: JSON.parse(trimmed),
        };
      } catch {
        return { text: trimmed, data: null };
      }
    }

    function clearChart(canvas) {
      const context = canvas.getContext("2d");
      context.clearRect(0, 0, canvas.width, canvas.height);
    }

    function renderViz(statsTarget, canvas, valuesTarget, data) {
      statsTarget.innerHTML = "";
      valuesTarget.innerHTML = "";
      clearChart(canvas);
      if (!Array.isArray(data) || data.length === 0 || !data.every((value) => typeof value === "number")) {
        return;
      }

      const count = data.length;
      const min = Math.min(...data);
      const max = Math.max(...data);
      const mean = data.reduce((sum, value) => sum + value, 0) / count;
      const stats = [
        \`count \${count}\`,
        \`min \${Number(min.toFixed(4))}\`,
        \`max \${Number(max.toFixed(4))}\`,
        \`mean \${Number(mean.toFixed(4))}\`,
      ];
      for (const stat of stats) {
        const chip = document.createElement("div");
        chip.className = "metricChip";
        chip.textContent = stat;
        statsTarget.appendChild(chip);
      }

      for (const value of data.slice(0, 16)) {
        const pill = document.createElement("div");
        pill.className = "valuePill";
        pill.textContent = Number(value.toFixed(4)).toString();
        valuesTarget.appendChild(pill);
      }

      const context = canvas.getContext("2d");
      const { width, height } = canvas;
      const padX = 26;
      const padY = 24;
      const range = max - min || 1;
      const stepX = count > 1 ? (width - padX * 2) / (count - 1) : 0;

      context.clearRect(0, 0, width, height);
      context.strokeStyle = "rgba(255,255,255,0.12)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(padX, height - padY);
      context.lineTo(width - padX, height - padY);
      context.moveTo(padX, padY);
      context.lineTo(padX, height - padY);
      context.stroke();

      context.beginPath();
      data.forEach((value, index) => {
        const x = padX + index * stepX;
        const y = height - padY - ((value - min) / range) * (height - padY * 2);
        if (index === 0) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      });
      context.strokeStyle = "rgba(34, 211, 238, 0.95)";
      context.lineWidth = 3;
      context.stroke();

      context.lineTo(width - padX, height - padY);
      context.lineTo(padX, height - padY);
      context.closePath();
      context.fillStyle = "rgba(34, 211, 238, 0.12)";
      context.fill();
    }

    function attachSearch() {
      const input = document.getElementById("search");
      const targets = [...document.querySelectorAll(".searchTarget")];
      input.addEventListener("input", () => {
        const query = input.value.trim().toLowerCase();
        for (const target of targets) {
          const haystack = target.dataset.search || "";
          target.classList.toggle("hidden", query !== "" && !haystack.includes(query));
        }
      });
    }

    function attachExampleControls() {
      for (const example of DOC_DATA.examples) {
        const editor = document.querySelector(\`[data-example-editor="\${CSS.escape(example.filename)}"]\`);
        const meta = document.querySelector(\`[data-output-meta="\${CSS.escape(example.filename)}"]\`);
        const text = document.querySelector(\`[data-output-text="\${CSS.escape(example.filename)}"]\`);
        const stats = document.querySelector(\`[data-output-stats="\${CSS.escape(example.filename)}"]\`);
        const chart = document.querySelector(\`[data-output-chart="\${CSS.escape(example.filename)}"]\`);
        const values = document.querySelector(\`[data-output-values="\${CSS.escape(example.filename)}"]\`);

        document.querySelector(\`[data-reset-example="\${CSS.escape(example.filename)}"]\`).addEventListener("click", () => {
          editor.value = example.source;
          meta.textContent = "Reset to shipped example.";
          text.textContent = "";
          stats.innerHTML = "";
          values.innerHTML = "";
          clearChart(chart);
        });

        document.querySelector(\`[data-copy-example="\${CSS.escape(example.filename)}"]\`).addEventListener("click", async () => {
          await navigator.clipboard.writeText(editor.value);
          meta.textContent = "Copied example source.";
        });

        document.querySelector(\`[data-run-example="\${CSS.escape(example.filename)}"]\`).addEventListener("click", async () => {
          meta.textContent = "Running…";
          text.textContent = "";
          stats.innerHTML = "";
          values.innerHTML = "";
          clearChart(chart);
          try {
            const doe = await ensureDoe();
            const logs = [];
            const scopedConsole = {
              log(...args) {
                logs.push(args.map((value) => typeof value === "string" ? value : JSON.stringify(value)).join(" "));
              },
            };
            const runnable = editor.value.replace(/^import\\s+\\{\\s*doe\\s*\\}\\s+from\\s+"@simulatte\\/webgpu\\/compute";\\n\\n?/, "");
            const fn = new Function("doe", "console", \`return (async () => {\\n\${runnable}\\n})();\`);
            await fn(doe, scopedConsole);
            const parsed = parseConsoleOutput(logs);
            meta.textContent = "Ran successfully.";
            text.textContent = parsed.text;
            renderViz(stats, chart, values, parsed.data);
          } catch (error) {
            meta.textContent = "Run failed.";
            text.textContent = error && error.stack ? error.stack : String(error);
          }
        });
      }
    }

    async function initRuntimeStatus() {
      if (!("gpu" in navigator)) {
        setStatus("status-webgpu", "Unavailable");
        setStatus("status-adapter", "No WebGPU");
        setStatus("status-device", "No WebGPU");
        return;
      }
      setStatus("status-webgpu", "Available");
      try {
        await ensureDoe();
      } catch (error) {
        setStatus("status-adapter", "Failed");
        setStatus("status-device", error?.message || "Unavailable");
      }
    }

    attachSearch();
    attachExampleControls();
    initRuntimeStatus();
  </script>
</body>
</html>`;
}

function main() {
  const intro = extractIntro(readUtf8(README_PATH));
  const doeSource = readUtf8(DOE_JS_PATH);
  const dtsSource = readUtf8(DOE_DTS_PATH);
  const apiEntries = buildApiEntries(doeSource, dtsSource);
  const examples = readExamples();

  const html = buildPage({
    intro,
    apiEntries,
    examples,
  });

  mkdirSync(OUTPUT_DIR, { recursive: true });
  writeFileSync(OUTPUT_PATH, html);
  process.stdout.write(`${OUTPUT_PATH}\n`);
}

main();
