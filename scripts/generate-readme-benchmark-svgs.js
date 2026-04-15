#!/usr/bin/env node

// README benchmark chart generator.
//
// Generates the committed SVG evidence charts used by the top-level and
// package README surfaces from a single JSON data file.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const CLAIMS_PATH = path.join(REPO_ROOT, 'assets', 'readme', 'benchmark-claims.json');
const OUTPUT_DIR = path.join(REPO_ROOT, 'assets', 'readme');

const SVG_THEME = Object.freeze({
  palette: Object.freeze({
    text: '#ffffff',
    muted: '#cbd5e1',
    grid: '#1f2937',
    accent: '#7c3aed',
    p50: '#9d4edd',
    p95: '#3b82f6',
    mixed: '#f59e0b',
    positive: '#22c55e',
    phase: Object.freeze({
      warmLoad: '#ef4444',
      prefill: '#fbbf24',
      decode: '#3b82f6'
    }),
    architecture: Object.freeze({
      loadBorder: '#ef4444',
      inferBorder: '#2563eb',
      edge: '#7c3aed'
    })
  }),
  fonts: Object.freeze({
    ui: 'Segoe UI, Helvetica Neue, Arial, sans-serif',
    mono: 'SFMono-Regular, Menlo, Consolas, Liberation Mono, monospace'
  }),
  textStroke: Object.freeze({
    color: '#000000',
    width: '2px',
    lineJoin: 'round'
  })
});

const FONT_UI = '\'Segoe UI\', \'Helvetica Neue\', Arial, sans-serif';
const FONT_MONO = 'SFMono-Regular, Menlo, Consolas, \'Liberation Mono\', monospace';
const CANVAS_PADDING = 14;
const CHART_WIDTH = 1200;
const HEADER_HEIGHT = 120;
const ROW_HEIGHT = 98;
const ROW_GAP = 16;
const FOOTER_HEIGHT = 54;
const PANEL_X = 24;
const PANEL_WIDTH = CHART_WIDTH - (PANEL_X * 2);
const LABEL_X = 48;
const TRACK_X = 378;
const TRACK_WIDTH = 600;
const VALUE_PILL_X = 1002;
const VALUE_PILL_WIDTH = 150;
const MAX_SCALE_PADDING = 1.08;

function escapeXml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll('\'', '&#39;');
}

function formatDelta(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 'Mixed';
  }
  const prefix = numeric >= 0 ? '+' : '';
  return `${prefix}${numeric.toFixed(1)}%`;
}

function makeSvgTextStyle(selector = 'text') {
  return `<defs><style>
  ${selector} { paint-order: stroke fill; stroke: ${SVG_THEME.textStroke.color}; stroke-width: ${SVG_THEME.textStroke.width}; stroke-linejoin: ${SVG_THEME.textStroke.lineJoin}; }
</style></defs>`;
}

function renderCanvas(width, height) {
  return `<rect x="0" y="0" width="${width}" height="${height}" fill="#020617" />
  <rect x="${CANVAS_PADDING}" y="${CANVAS_PADDING}" width="${width - (CANVAS_PADDING * 2)}" height="${height - (CANVAS_PADDING * 2)}" fill="#020817" fill-opacity="0.50" stroke="none" />`;
}

function renderDefs() {
  return `<defs>
  <linearGradient id="readme-canvas-glow" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="#7c3aed18" />
    <stop offset="45%" stop-color="#ef444410" />
    <stop offset="100%" stop-color="#2563eb12" />
  </linearGradient>
  <linearGradient id="readme-panel-fill" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="#081121" />
    <stop offset="55%" stop-color="#0b1325" />
    <stop offset="100%" stop-color="#0c1630" />
  </linearGradient>
  <linearGradient id="readme-panel-stroke" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="${SVG_THEME.palette.architecture.loadBorder}" />
    <stop offset="48%" stop-color="${SVG_THEME.palette.architecture.edge}" />
    <stop offset="100%" stop-color="${SVG_THEME.palette.architecture.inferBorder}" />
  </linearGradient>
  <linearGradient id="readme-track-fill" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#0c1528" />
    <stop offset="100%" stop-color="#111b31" />
  </linearGradient>
  <linearGradient id="readme-track-stroke" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#ffffff1d" />
    <stop offset="100%" stop-color="#ffffff08" />
  </linearGradient>
  <linearGradient id="readme-p50-grad" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#c77dff" />
    <stop offset="100%" stop-color="${SVG_THEME.palette.p50}" />
  </linearGradient>
  <linearGradient id="readme-p95-grad" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#60a5fa" />
    <stop offset="100%" stop-color="${SVG_THEME.palette.p95}" />
  </linearGradient>
  <linearGradient id="readme-chip-grad" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#7c3aed22" />
    <stop offset="100%" stop-color="#2563eb22" />
  </linearGradient>
  <linearGradient id="readme-pill-grad" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="#0f172a" />
    <stop offset="100%" stop-color="#172554" />
  </linearGradient>
  </defs>`;
}

function svgWrap(width, height, title, desc, body) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="chart-title chart-desc">
  <title id="chart-title">${escapeXml(title)}</title>
  <desc id="chart-desc">${escapeXml(desc)}</desc>
  ${makeSvgTextStyle()}
  ${renderCanvas(width, height)}
  ${body}
</svg>`;
}

function getChartHeight(rowCount) {
  return HEADER_HEIGHT + 28 + (rowCount * ROW_HEIGHT) + ((rowCount - 1) * ROW_GAP) + FOOTER_HEIGHT;
}

function renderHeader(title, subtitle, width) {
  return `<rect x="${CANVAS_PADDING}" y="${CANVAS_PADDING}" width="${width - (CANVAS_PADDING * 2)}" height="${HEADER_HEIGHT - 10}" fill="url(#readme-canvas-glow)" stroke="none" />
<text x="36" y="48" fill="${SVG_THEME.palette.accent}" font-family="${FONT_UI}" font-size="12" font-weight="bold" letter-spacing="1.2" stroke="none">BENCHMARK EVIDENCE</text>
<text x="36" y="86" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="30" font-weight="bold" stroke="none">${escapeXml(title)}</text>
<text x="36" y="110" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="13" stroke="none">${escapeXml(subtitle)}</text>
<rect x="935" y="36" width="229" height="34" rx="17" fill="url(#readme-pill-grad)" stroke="${SVG_THEME.palette.p95}" stroke-width="1.1" />
<text x="1049.5" y="57" text-anchor="middle" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="12" font-weight="bold" stroke="none">LONGER BAR = LARGER CLAIM</text>`;
}

function renderLegend(y) {
  return `<rect x="36" y="${y}" width="18" height="18" rx="6" fill="url(#readme-p50-grad)" />
<text x="64" y="${y + 13}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="13" stroke="none">p50 delta</text>
<rect x="200" y="${y}" width="18" height="18" rx="6" fill="url(#readme-p95-grad)" />
<text x="228" y="${y + 13}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="13" stroke="none">p95 delta</text>
<rect x="384" y="${y}" width="18" height="18" rx="6" fill="url(#readme-chip-grad)" stroke="${SVG_THEME.palette.accent}" stroke-width="1" />
<text x="412" y="${y + 13}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="13" stroke="none">platform lane</text>`;
}

function renderScaleLabels(y, maxValue) {
  const quarter = maxValue / 4;
  const labels = [0, quarter, quarter * 2, quarter * 3, maxValue];
  const text = [];
  for (let index = 0; index < labels.length; index += 1) {
    const value = labels[index];
    const x = TRACK_X + ((TRACK_WIDTH * index) / (labels.length - 1));
    text.push(`<line x1="${x}" y1="${y}" x2="${x}" y2="${y + 12}" stroke="#ffffff18" stroke-width="1" />`);
    text.push(`<text x="${x}" y="${y - 6}" text-anchor="${index === 0 ? 'start' : index === labels.length - 1 ? 'end' : 'middle'}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_MONO}" font-size="10" stroke="none">${escapeXml(formatDelta(value))}</text>`);
  }
  return text.join('\n');
}

function renderDeltaRow(row, rowIndex, maxValue) {
  const y = HEADER_HEIGHT + 28 + (rowIndex * (ROW_HEIGHT + ROW_GAP));
  const panelHeight = ROW_HEIGHT;
  const p50Width = Math.max(0, (TRACK_WIDTH * Number(row.p50)) / maxValue);
  const p95Width = Math.max(0, (TRACK_WIDTH * Number(row.p95)) / maxValue);
  return `<rect x="${PANEL_X}" y="${y}" width="${PANEL_WIDTH}" height="${panelHeight}" rx="24" fill="url(#readme-panel-fill)" stroke="url(#readme-panel-stroke)" stroke-width="1.4" />
<text x="${LABEL_X}" y="${y + 34}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="20" font-weight="bold" stroke="none">${escapeXml(row.label)}</text>
<rect x="${LABEL_X}" y="${y + 48}" width="164" height="28" rx="14" fill="url(#readme-chip-grad)" stroke="${SVG_THEME.palette.accent}" stroke-width="1.2" />
<text x="${LABEL_X + 16}" y="${y + 67}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="13" font-weight="bold" stroke="none">${escapeXml(row.platform)}</text>
<rect x="${TRACK_X}" y="${y + 18}" width="${TRACK_WIDTH}" height="24" rx="12" fill="url(#readme-track-fill)" stroke="url(#readme-track-stroke)" stroke-width="1.1" />
<rect x="${TRACK_X + 2}" y="${y + 20}" width="${Math.max(0, p50Width - 4)}" height="20" rx="10" fill="url(#readme-p50-grad)" />
<text x="${TRACK_X + 12}" y="${y + 35}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="11" font-weight="bold">${escapeXml(`p50 ${formatDelta(row.p50)}`)}</text>
<rect x="${TRACK_X}" y="${y + 52}" width="${TRACK_WIDTH}" height="24" rx="12" fill="url(#readme-track-fill)" stroke="url(#readme-track-stroke)" stroke-width="1.1" />
<rect x="${TRACK_X + 2}" y="${y + 54}" width="${Math.max(0, p95Width - 4)}" height="20" rx="10" fill="url(#readme-p95-grad)" />
<text x="${TRACK_X + 12}" y="${y + 69}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="11" font-weight="bold">${escapeXml(`p95 ${formatDelta(row.p95)}`)}</text>
<rect x="${VALUE_PILL_X}" y="${y + 14}" width="${VALUE_PILL_WIDTH}" height="30" rx="15" fill="${SVG_THEME.palette.positive}" />
<text x="${VALUE_PILL_X + (VALUE_PILL_WIDTH / 2)}" y="${y + 34}" text-anchor="middle" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="16" font-weight="bold" stroke="none">${escapeXml(formatDelta(row.p50))}</text>
<rect x="${VALUE_PILL_X}" y="${y + 50}" width="${VALUE_PILL_WIDTH}" height="24" rx="12" fill="url(#readme-pill-grad)" stroke="#ffffff1f" stroke-width="1" />
<text x="${VALUE_PILL_X + (VALUE_PILL_WIDTH / 2)}" y="${y + 66}" text-anchor="middle" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="11" font-weight="bold" stroke="none">${escapeXml(`p95 ${formatDelta(row.p95)}`)}</text>`;
}

function renderMixedRow(row, rowIndex) {
  const y = HEADER_HEIGHT + 28 + (rowIndex * (ROW_HEIGHT + ROW_GAP));
  const panelHeight = ROW_HEIGHT;
  return `<rect x="${PANEL_X}" y="${y}" width="${PANEL_WIDTH}" height="${panelHeight}" rx="24" fill="url(#readme-panel-fill)" stroke="url(#readme-panel-stroke)" stroke-width="1.4" />
<text x="${LABEL_X}" y="${y + 34}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="20" font-weight="bold" stroke="none">${escapeXml(row.label)}</text>
<rect x="${LABEL_X}" y="${y + 48}" width="164" height="28" rx="14" fill="url(#readme-chip-grad)" stroke="${SVG_THEME.palette.accent}" stroke-width="1.2" />
<text x="${LABEL_X + 16}" y="${y + 67}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="13" font-weight="bold" stroke="none">${escapeXml(row.platform)}</text>
<rect x="${TRACK_X}" y="${y + 18}" width="${TRACK_WIDTH}" height="58" rx="18" fill="url(#readme-track-fill)" stroke="url(#readme-track-stroke)" stroke-width="1.1" />
<text x="${TRACK_X + 24}" y="${y + 44}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="16" font-weight="bold" stroke="none">Mixed evidence</text>
<text x="${TRACK_X + 24}" y="${y + 64}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="12" stroke="none">Current browser ORT results are not summarized as a single faster/slower claim.</text>
<rect x="${VALUE_PILL_X}" y="${y + 24}" width="${VALUE_PILL_WIDTH}" height="44" rx="22" fill="${SVG_THEME.palette.mixed}" />
<text x="${VALUE_PILL_X + (VALUE_PILL_WIDTH / 2)}" y="${y + 51}" text-anchor="middle" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="16" font-weight="bold" stroke="none">MIXED</text>`;
}

function renderChart(chartConfig) {
  const rows = Array.isArray(chartConfig.rows) ? chartConfig.rows : [];
  const deltaRows = rows.filter((row) => Number.isFinite(row?.p50) && Number.isFinite(row?.p95));
  const maxRawValue = deltaRows.reduce((current, row) => Math.max(current, row.p50, row.p95), 0);
  const maxValue = Math.max(1, maxRawValue * MAX_SCALE_PADDING);
  const height = getChartHeight(rows.length);

  const rowMarkup = rows.map((row, rowIndex) => {
    if (typeof row.status === 'string' && row.status.toLowerCase() === 'mixed') {
      return renderMixedRow(row, rowIndex);
    }
    return renderDeltaRow(row, rowIndex, maxValue);
  }).join('\n');

  const scaleY = HEADER_HEIGHT + 16;
  const legendY = height - 36;

  return svgWrap(
    CHART_WIDTH,
    height,
    chartConfig.title,
    chartConfig.caption ?? chartConfig.subtitle,
    `${renderDefs()}
${renderHeader(chartConfig.title, chartConfig.subtitle, CHART_WIDTH)}
${renderScaleLabels(scaleY, maxValue)}
${rowMarkup}
${renderLegend(legendY)}`
  );
}

function writeSvg(outputName, svgContent) {
  const outputPath = path.join(OUTPUT_DIR, outputName);
  fs.writeFileSync(outputPath, `${svgContent}\n`, 'utf8');
  return outputPath;
}

function main() {
  const claims = JSON.parse(fs.readFileSync(CLAIMS_PATH, 'utf8'));
  const outputs = [
    {
      name: 'package-claims.svg',
      svg: renderChart(claims.packageClaims)
    },
    {
      name: 'ort-claims.svg',
      svg: renderChart(claims.ortClaims)
    }
  ];

  for (const output of outputs) {
    const outputPath = writeSvg(output.name, output.svg);
    process.stdout.write(`${path.relative(REPO_ROOT, outputPath)}\n`);
  }
}

main();
