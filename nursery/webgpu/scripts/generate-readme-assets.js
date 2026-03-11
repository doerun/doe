#!/usr/bin/env node

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGE_ROOT = resolve(__dirname, '..');
const WORKSPACE_ROOT = resolve(PACKAGE_ROOT, '..', '..');
const CUBE_SUMMARY_PATH = resolve(WORKSPACE_ROOT, 'bench', 'out', 'cube', 'latest', 'cube.summary.json');
const OUTPUT_PATH = resolve(PACKAGE_ROOT, 'assets', 'package-surface-cube-snapshot.svg');

const UI_FONT = '"Segoe UI", "Helvetica Neue", Arial, sans-serif';
const MONO_FONT = 'SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';
const TEXT_STROKE = 'paint-order: stroke fill; stroke: #000000; stroke-width: 2px; stroke-linejoin: round;';

const SURFACE_SPECS = [
  {
    surface: 'node_package',
    title: 'Node package lane',
    supportLabel: 'Primary support',
    preferredHostProfile: 'mac_apple_silicon',
    focusSets: ['uploads', 'compute_e2e'],
    tone: 'left',
  },
  {
    surface: 'bun_package',
    title: 'Bun package lane',
    supportLabel: 'Validated support',
    preferredHostProfile: 'mac_apple_silicon',
    focusSets: ['compute_e2e', 'uploads'],
    tone: 'right',
  },
];

const STATUS_STYLE = {
  claimable: { fill: '#16a34a', stroke: '#86efac', label: 'CLAIMABLE' },
  comparable: { fill: '#d97706', stroke: '#fbbf24', label: 'COMPARABLE' },
  diagnostic: { fill: '#dc2626', stroke: '#fca5a5', label: 'DIAGNOSTIC' },
  unimplemented: { fill: '#3f3f46', stroke: '#71717a', label: 'UNIMPLEMENTED' },
};

function readCubeSummary(summaryPath) {
  return JSON.parse(readFileSync(summaryPath, 'utf8'));
}

function escapeXml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return 'n/a';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}

function compactIso(value) {
  if (!value) return 'n/a';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toISOString().replace('.000Z', 'Z');
}

function maxGeneratedAt(cells) {
  const stamps = cells
    .map((cell) => cell?.latestGeneratedAt ?? '')
    .filter((stamp) => stamp !== '');
  if (stamps.length === 0) return 'n/a';
  return compactIso(stamps.sort().at(-1));
}

function implementedScore(cell) {
  if (!cell) return 0;
  if ((cell.rowCount ?? 0) > 0 || (cell.reportCount ?? 0) > 0) return 2;
  if (cell.status && cell.status !== 'unimplemented') return 1;
  return 0;
}

function selectHostProfile(cells, preferredHostProfile) {
  const statsByHost = new Map();
  for (const cell of cells) {
    const host = cell.hostProfile ?? 'unknown';
    const current = statsByHost.get(host) ?? {
      hostProfile: host,
      populatedCells: 0,
      implementedCells: 0,
      totalRows: 0,
      claimableCells: 0,
      latestGeneratedAt: '',
    };
    const score = implementedScore(cell);
    if (score === 2) current.populatedCells += 1;
    if (score >= 1) current.implementedCells += 1;
    current.totalRows += cell.rowCount ?? 0;
    if (cell.status === 'claimable') current.claimableCells += 1;
    if ((cell.latestGeneratedAt ?? '') > current.latestGeneratedAt) {
      current.latestGeneratedAt = cell.latestGeneratedAt;
    }
    statsByHost.set(host, current);
  }

  const preferred = statsByHost.get(preferredHostProfile);
  if (preferred && preferred.populatedCells > 0) return preferred.hostProfile;

  const ranked = [...statsByHost.values()].sort((left, right) => {
    if (right.populatedCells !== left.populatedCells) {
      return right.populatedCells - left.populatedCells;
    }
    if (right.claimableCells !== left.claimableCells) {
      return right.claimableCells - left.claimableCells;
    }
    if (right.totalRows !== left.totalRows) {
      return right.totalRows - left.totalRows;
    }
    if (right.latestGeneratedAt !== left.latestGeneratedAt) {
      return right.latestGeneratedAt.localeCompare(left.latestGeneratedAt);
    }
    return left.hostProfile.localeCompare(right.hostProfile);
  });

  return ranked[0]?.hostProfile ?? preferredHostProfile;
}

function findCell(cells, hostProfile, workloadSet) {
  return cells.find(
    (cell) => cell.hostProfile === hostProfile && cell.workloadSet === workloadSet,
  ) ?? {
    hostProfile,
    workloadSet,
    status: 'unimplemented',
    claimStatus: 'diagnostic',
    rowCount: 0,
    latestGeneratedAt: '',
  };
}

function focusLabel(workloadSet) {
  switch (workloadSet) {
    case 'compute_e2e':
      return 'Compute E2E';
    case 'uploads':
      return 'Uploads';
    default:
      return workloadSet;
  }
}

function pillForCell(cell) {
  const claimStatus = cell.claimStatus ?? cell.status ?? 'diagnostic';
  if (claimStatus === 'claimable') return STATUS_STYLE.claimable;
  return STATUS_STYLE[cell.status] ?? STATUS_STYLE.diagnostic;
}

function summarizeFocusCell(cell) {
  const statusLabel = (pillForCell(cell).label ?? 'DIAGNOSTIC').toLowerCase();
  return {
    title: focusLabel(cell.workloadSet),
    pill: pillForCell(cell),
    lines: [
      `${cell.rowCount ?? 0} rows | ${statusLabel}`,
      Number.isFinite(cell.deltaP50MedianPercent)
        ? `median p50 delta ${formatPercent(cell.deltaP50MedianPercent)}`
        : 'median p50 delta n/a',
    ],
  };
}

function renderMetricRow(summary, x, y, toneClass) {
  return `
  <rect x="${x}" y="${y}" width="452" height="82" rx="16" class="metric ${toneClass}"/>
  <text x="${x + 24}" y="${y + 31}" class="metricTitle">${escapeXml(summary.title)}</text>
  <rect x="${x + 296}" y="${y + 15}" width="132" height="28" rx="14" fill="${summary.pill.fill}" stroke="${summary.pill.stroke}" stroke-width="1.5"/>
  <text x="${x + 362}" y="${y + 34}" text-anchor="middle" class="pillText">${escapeXml(summary.pill.label)}</text>
  <text x="${x + 24}" y="${y + 57}" class="metricBody">${escapeXml(summary.lines[0])}</text>
  <text x="${x + 24}" y="${y + 77}" class="metricBody">${escapeXml(summary.lines[1])}</text>`;
}

function renderSurfaceCard(spec, cells, x) {
  const selectedHostProfile = selectHostProfile(cells, spec.preferredHostProfile);
  const focusCells = spec.focusSets.map((workloadSet) => findCell(cells, selectedHostProfile, workloadSet));
  const generatedAt = maxGeneratedAt(focusCells);
  const toneClass = spec.tone === 'left' ? 'toneLeft' : 'toneRight';
  const focusSummaries = focusCells.map(summarizeFocusCell);

  return `
  <rect x="${x}" y="176" width="488" height="318" rx="24" class="panel ${toneClass}"/>
  <text x="${x + 28}" y="216" class="cardTitle">${escapeXml(spec.title)}</text>
  <text x="${x + 28}" y="244" class="cardMeta">${escapeXml(`${spec.supportLabel} | ${selectedHostProfile}`)}</text>
  <text x="${x + 28}" y="266" class="cardMeta">${escapeXml(`latest populated cell ${generatedAt}`)}</text>
${renderMetricRow(focusSummaries[0], x + 18, 300, toneClass)}
${renderMetricRow(focusSummaries[1], x + 18, 396, toneClass)}`;
}

function renderSvg(summary) {
  const cells = summary.cells ?? [];
  const nodeCells = cells.filter((cell) => cell.surface === 'node_package');
  const bunCells = cells.filter((cell) => cell.surface === 'bun_package');
  const nodeHost = selectHostProfile(nodeCells, SURFACE_SPECS[0].preferredHostProfile);
  const bunHost = selectHostProfile(bunCells, SURFACE_SPECS[1].preferredHostProfile);
  const generatedAt = maxGeneratedAt([
    ...SURFACE_SPECS[0].focusSets.map((workloadSet) => findCell(nodeCells, nodeHost, workloadSet)),
    findCell(nodeCells, nodeHost, 'full_comparable'),
    ...SURFACE_SPECS[1].focusSets.map((workloadSet) => findCell(bunCells, bunHost, workloadSet)),
    findCell(bunCells, bunHost, 'full_comparable'),
  ]);

  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="640" viewBox="0 0 1200 640" role="img" aria-labelledby="title desc">
  <title id="title">Package surface benchmark cube snapshot</title>
  <desc id="desc">Two-card package surface snapshot for Node and Bun generated from bench/out/cube/latest/cube.summary.json.</desc>
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#050816"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
    <linearGradient id="panel-left" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ef444420"/>
      <stop offset="60%" stop-color="#ef444426"/>
      <stop offset="100%" stop-color="#7c3aed22"/>
    </linearGradient>
    <linearGradient id="panel-right" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#7c3aed20"/>
      <stop offset="60%" stop-color="#7c3aed24"/>
      <stop offset="100%" stop-color="#2563eb22"/>
    </linearGradient>
    <style>
      .title { font: 700 34px ${UI_FONT}; fill: #ffffff; ${TEXT_STROKE} }
      .subtitle { font: 500 18px ${UI_FONT}; fill: #cbd5e1; ${TEXT_STROKE} }
      .cardTitle { font: 700 26px ${UI_FONT}; fill: #ffffff; ${TEXT_STROKE} }
      .cardMeta { font: 500 16px ${UI_FONT}; fill: #cbd5e1; ${TEXT_STROKE} }
      .metricTitle { font: 700 18px ${UI_FONT}; fill: #ffffff; ${TEXT_STROKE} }
      .metricBody { font: 500 15px ${MONO_FONT}; fill: #e2e8f0; ${TEXT_STROKE} }
      .pillText { font: 700 13px ${UI_FONT}; fill: #f8fafc; letter-spacing: 0.5px; ${TEXT_STROKE} }
      .foot { font: 500 14px ${UI_FONT}; fill: #cbd5e1; ${TEXT_STROKE} }
      .panel { stroke-width: 4; }
      .toneLeft { fill: url(#panel-left); stroke: #ef4444; }
      .toneRight { fill: url(#panel-right); stroke: #2563eb; }
      .metric { fill: #020617a8; stroke-width: 1.8; }
      .metric.toneLeft { stroke: #ef4444; }
      .metric.toneRight { stroke: #2563eb; }
    </style>
  </defs>
  <rect width="1200" height="640" fill="url(#bg)"/>
  <text x="72" y="72" class="title">@simulatte/webgpu package snapshot</text>
  <text x="72" y="102" class="subtitle">Derived from bench/out/cube/latest/cube.summary.json | latest populated cell ${escapeXml(generatedAt)}</text>
  <text x="72" y="128" class="subtitle">Package-surface evidence only. Backend-native strict claim lanes remain separate.</text>
${renderSurfaceCard(SURFACE_SPECS[0], nodeCells, 72)}
${renderSurfaceCard(SURFACE_SPECS[1], bunCells, 640)}
  <text x="72" y="590" class="foot">Generated by nursery/webgpu/scripts/generate-readme-assets.js.</text>
  <text x="72" y="612" class="foot">Static claim and comparability card from the package-surface cube. It is not a substitute for strict backend reports.</text>
</svg>
`;
}

function main() {
  const summary = readCubeSummary(CUBE_SUMMARY_PATH);
  const svg = renderSvg(summary);
  mkdirSync(dirname(OUTPUT_PATH), { recursive: true });
  writeFileSync(
    OUTPUT_PATH,
    `<!-- Generated by scripts/generate-readme-assets.js. Do not edit by hand. -->\n${svg}`,
  );
  console.log(`Wrote ${OUTPUT_PATH}`);
}

main();
