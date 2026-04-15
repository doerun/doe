#!/usr/bin/env node

// README benchmark chart generator.
//
// Generates the committed SVG evidence charts used by the top-level and
// package README surfaces from a single JSON data file and artifact-backed
// compare reports.

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
    doe: '#9d4edd',
    incumbent: '#dc2626',
    mixed: '#f59e0b',
    positive: '#22c55e',
    panelTop: '#081121',
    panelBottom: '#0c1630',
    trackTop: '#0c1528',
    trackBottom: '#111b31',
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
const CHART_WIDTH = 1340;
const HEADER_HEIGHT = 126;
const ROW_HEIGHT = 176;
const ROW_GAP = 18;
const FOOTER_HEIGHT = 60;
const PANEL_X = 24;
const PANEL_WIDTH = CHART_WIDTH - (PANEL_X * 2);
const LABEL_X = 48;
const TRACK_X = 322;
const TRACK_WIDTH = 774;
const SERIES_LABEL_WIDTH = 90;
const METRIC_BAR_X = TRACK_X + SERIES_LABEL_WIDTH;
const METRIC_BAR_WIDTH = 520;
const METRIC_VALUE_X = METRIC_BAR_X + METRIC_BAR_WIDTH + 12;
const VALUE_PILL_X = 1134;
const VALUE_PILL_WIDTH = 160;
const HEADER_PILL_X = 998;
const HEADER_PILL_WIDTH = 296;
const ROW_TIME_SCALE_PADDING = 1.04;
const ROW_COUNT_SCALE_PADDING = 1.12;
const BAR_HEIGHT = 12;
const BAR_GAP = 6;
const METRIC_GROUPS = Object.freeze([
  { key: 'p50', label: 'p50 ms', yOffset: 26, field: 'P50Ms', scale: 'time' },
  { key: 'p95', label: 'p95 ms', yOffset: 78, field: 'P95Ms', scale: 'time' }
]);

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

function formatMs(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 'n/a';
  }
  return `${numeric.toLocaleString('en-US', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })} ms`;
}

function formatCount(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 'n/a';
  }
  return `n=${numeric.toLocaleString('en-US')}`;
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
    <stop offset="0%" stop-color="${SVG_THEME.palette.panelTop}" />
    <stop offset="55%" stop-color="#0b1325" />
    <stop offset="100%" stop-color="${SVG_THEME.palette.panelBottom}" />
  </linearGradient>
  <linearGradient id="readme-panel-stroke" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="${SVG_THEME.palette.architecture.loadBorder}" />
    <stop offset="48%" stop-color="${SVG_THEME.palette.architecture.edge}" />
    <stop offset="100%" stop-color="${SVG_THEME.palette.architecture.inferBorder}" />
  </linearGradient>
  <linearGradient id="readme-track-fill" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="${SVG_THEME.palette.trackTop}" />
    <stop offset="100%" stop-color="${SVG_THEME.palette.trackBottom}" />
  </linearGradient>
  <linearGradient id="readme-track-stroke" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#ffffff1d" />
    <stop offset="100%" stop-color="#ffffff08" />
  </linearGradient>
  <linearGradient id="readme-doe-grad" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#c77dff" />
    <stop offset="100%" stop-color="${SVG_THEME.palette.doe}" />
  </linearGradient>
  <linearGradient id="readme-incumbent-grad" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#f87171" />
    <stop offset="100%" stop-color="${SVG_THEME.palette.incumbent}" />
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
  return HEADER_HEIGHT + 30 + (rowCount * ROW_HEIGHT) + ((rowCount - 1) * ROW_GAP) + FOOTER_HEIGHT;
}

function readArtifactMetrics(relativeArtifactPath) {
  const artifactPath = path.join(REPO_ROOT, relativeArtifactPath);
  const artifact = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
  const baselineStats = artifact?.overall?.baselineStatsMs;
  const comparisonStats = artifact?.overall?.comparisonStatsMs;
  const deltaPercent = artifact?.overall?.deltaPercent;
  if (!baselineStats || !comparisonStats || !deltaPercent) {
    throw new Error(`Artifact ${relativeArtifactPath} is missing compare summary fields.`);
  }
  return Object.freeze({
    baselineCount: baselineStats.count,
    baselineP50Ms: baselineStats.p50Ms,
    baselineP95Ms: baselineStats.p95Ms,
    comparisonCount: comparisonStats.count,
    comparisonP50Ms: comparisonStats.p50Ms,
    comparisonP95Ms: comparisonStats.p95Ms,
    deltaP50Percent: deltaPercent.p50Percent,
    deltaP95Percent: deltaPercent.p95Percent
  });
}

function resolveChartRows(rows) {
  return rows.map((row) => {
    if (typeof row.status === 'string' && row.status.toLowerCase() === 'mixed') {
      return row;
    }
    if (typeof row.artifactPath !== 'string' || row.artifactPath.length === 0) {
      throw new Error(`Row ${row.label} is missing artifactPath.`);
    }
    return Object.freeze({
      ...row,
      metrics: readArtifactMetrics(row.artifactPath)
    });
  });
}

function getRowScaleState(row) {
  return Object.freeze({
    maxTime: Math.max(
      1,
      Number(row.metrics.baselineP50Ms),
      Number(row.metrics.comparisonP50Ms),
      Number(row.metrics.baselineP95Ms),
      Number(row.metrics.comparisonP95Ms)
    ) * ROW_TIME_SCALE_PADDING,
    maxCount: Math.max(
      1,
      Number(row.metrics.baselineCount),
      Number(row.metrics.comparisonCount)
    ) * ROW_COUNT_SCALE_PADDING
  });
}

function renderHeader(title, subtitle, width) {
  return `<rect x="${CANVAS_PADDING}" y="${CANVAS_PADDING}" width="${width - (CANVAS_PADDING * 2)}" height="${HEADER_HEIGHT - 12}" fill="url(#readme-canvas-glow)" stroke="none" />
<text x="36" y="70" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="30" font-weight="bold" stroke="none">${escapeXml(title)}</text>
<text x="36" y="102" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="13" stroke="none">${escapeXml(subtitle)}</text>
<rect x="${HEADER_PILL_X}" y="34" width="${HEADER_PILL_WIDTH}" height="38" rx="19" fill="url(#readme-pill-grad)" stroke="${SVG_THEME.palette.incumbent}" stroke-width="1.1" />
<text x="${HEADER_PILL_X + (HEADER_PILL_WIDTH / 2)}" y="58" text-anchor="middle" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="12" font-weight="bold" stroke="none">BARS ARE IN MS, LOWER IS BETTER</text>`;
}

function renderLegend(y) {
  return `<rect x="36" y="${y}" width="18" height="18" rx="6" fill="url(#readme-doe-grad)" />
<text x="64" y="${y + 13}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="13" stroke="none">Doe timing bars</text>
<rect x="250" y="${y}" width="18" height="18" rx="6" fill="url(#readme-incumbent-grad)" />
<text x="278" y="${y + 13}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="13" stroke="none">comparison timing bars</text>
<rect x="540" y="${y}" width="18" height="18" rx="6" fill="${SVG_THEME.palette.positive}" />
<text x="568" y="${y + 13}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="13" stroke="none">green pill = p50 and p95 faster summary</text>`;
}

function renderScaleNote(y) {
  return `<text x="${TRACK_X}" y="${y}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="11" font-weight="bold" letter-spacing="0.7" stroke="none">EACH LANE SCALES ITS OWN BARS; EXACT MS AND SAMPLE COUNTS ARE PRINTED ON THE ROW.</text>`;
}

function getMetricValue(metrics, seriesKey, field) {
  return metrics[`${seriesKey}${field}`];
}

function renderMetricBlock(row, group, rowY, scaleState) {
  const trackY = rowY + group.yOffset;
  const maxValue = group.scale === 'time' ? scaleState.maxTime : scaleState.maxCount;
  const series = [
    {
      key: 'baseline',
      label: row.baselineLabel,
      fill: 'url(#readme-doe-grad)'
    },
    {
      key: 'comparison',
      label: row.comparisonLabel,
      fill: 'url(#readme-incumbent-grad)'
    }
  ];
  const labelY = trackY - 8;
  const markup = [
    `<text x="${TRACK_X}" y="${labelY}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="11" font-weight="bold" letter-spacing="0.7" stroke="none">${escapeXml(group.label.toUpperCase())}</text>`
  ];

  for (const [seriesIndex, seriesEntry] of series.entries()) {
    const y = trackY + (seriesIndex * (BAR_HEIGHT + BAR_GAP));
    const value = Number(getMetricValue(row.metrics, seriesEntry.key, group.field));
    const width = Math.max(0, (METRIC_BAR_WIDTH * value) / maxValue);
    const valueLabel = group.scale === 'time' ? formatMs(value) : formatCount(value);
    markup.push(`<circle cx="${TRACK_X + 8}" cy="${y + 6}" r="4" fill="${seriesEntry.fill === 'url(#readme-doe-grad)' ? SVG_THEME.palette.doe : SVG_THEME.palette.incumbent}" stroke="none" />
<text x="${TRACK_X + 20}" y="${y + 10}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="11" font-weight="bold" stroke="none">${escapeXml(seriesEntry.label)}</text>
<rect x="${METRIC_BAR_X}" y="${y}" width="${METRIC_BAR_WIDTH}" height="${BAR_HEIGHT}" rx="6" fill="url(#readme-track-fill)" stroke="url(#readme-track-stroke)" stroke-width="1" />
<rect x="${METRIC_BAR_X + 1}" y="${y + 1}" width="${Math.max(0, width - 2)}" height="${BAR_HEIGHT - 2}" rx="5" fill="${seriesEntry.fill}" />
<text x="${METRIC_VALUE_X}" y="${y + 10}" fill="${SVG_THEME.palette.text}" font-family="${FONT_MONO}" font-size="11" stroke="none">${escapeXml(valueLabel)}</text>`);
  }

  return markup.join('\n');
}

function renderMeasuredRow(row, rowIndex) {
  const y = HEADER_HEIGHT + 30 + (rowIndex * (ROW_HEIGHT + ROW_GAP));
  const panelHeight = ROW_HEIGHT;
  const scaleState = getRowScaleState(row);
  const baselineSamples = formatCount(row.metrics.baselineCount);
  const comparisonSamples = formatCount(row.metrics.comparisonCount);
  return `<rect x="${PANEL_X}" y="${y}" width="${PANEL_WIDTH}" height="${panelHeight}" rx="24" fill="url(#readme-panel-fill)" stroke="url(#readme-panel-stroke)" stroke-width="1.4" />
<text x="${LABEL_X}" y="${y + 38}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="22" font-weight="bold" stroke="none">${escapeXml(row.label)}</text>
<rect x="${LABEL_X}" y="${y + 52}" width="176" height="30" rx="15" fill="url(#readme-chip-grad)" stroke="${SVG_THEME.palette.accent}" stroke-width="1.2" />
<text x="${LABEL_X + 16}" y="${y + 72}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="13" font-weight="bold" stroke="none">${escapeXml(row.platform)}</text>
${METRIC_GROUPS.map((group) => renderMetricBlock(row, group, y, scaleState)).join('\n')}
<text x="${TRACK_X}" y="${y + 152}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="12" font-weight="bold" stroke="none">${escapeXml(`${row.baselineLabel} ${baselineSamples}`)}</text>
<text x="${TRACK_X + 148}" y="${y + 152}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="12" font-weight="bold" stroke="none">${escapeXml(`${row.comparisonLabel} ${comparisonSamples}`)}</text>
<rect x="${VALUE_PILL_X}" y="${y + 22}" width="${VALUE_PILL_WIDTH}" height="40" rx="20" fill="${SVG_THEME.palette.positive}" />
<text x="${VALUE_PILL_X + (VALUE_PILL_WIDTH / 2)}" y="${y + 48}" text-anchor="middle" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="18" font-weight="bold" stroke="none">${escapeXml(formatDelta(row.metrics.deltaP50Percent))}</text>
<rect x="${VALUE_PILL_X}" y="${y + 72}" width="${VALUE_PILL_WIDTH}" height="34" rx="17" fill="url(#readme-pill-grad)" stroke="#ffffff1f" stroke-width="1" />
<text x="${VALUE_PILL_X + (VALUE_PILL_WIDTH / 2)}" y="${y + 93}" text-anchor="middle" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="12" font-weight="bold" stroke="none">${escapeXml(`p95 ${formatDelta(row.metrics.deltaP95Percent)}`)}</text>
<rect x="${VALUE_PILL_X}" y="${y + 116}" width="${VALUE_PILL_WIDTH}" height="28" rx="14" fill="#0f172a" stroke="#ffffff12" stroke-width="1" />
<text x="${VALUE_PILL_X + (VALUE_PILL_WIDTH / 2)}" y="${y + 134}" text-anchor="middle" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="11" font-weight="bold" stroke="none">artifact-backed compare</text>`;
}

function renderMixedRow(row, rowIndex) {
  const y = HEADER_HEIGHT + 30 + (rowIndex * (ROW_HEIGHT + ROW_GAP));
  const panelHeight = ROW_HEIGHT;
  return `<rect x="${PANEL_X}" y="${y}" width="${PANEL_WIDTH}" height="${panelHeight}" rx="24" fill="url(#readme-panel-fill)" stroke="url(#readme-panel-stroke)" stroke-width="1.4" />
<text x="${LABEL_X}" y="${y + 38}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="22" font-weight="bold" stroke="none">${escapeXml(row.label)}</text>
<rect x="${LABEL_X}" y="${y + 52}" width="176" height="30" rx="15" fill="url(#readme-chip-grad)" stroke="${SVG_THEME.palette.accent}" stroke-width="1.2" />
<text x="${LABEL_X + 16}" y="${y + 72}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="13" font-weight="bold" stroke="none">${escapeXml(row.platform)}</text>
<rect x="${TRACK_X}" y="${y + 28}" width="${TRACK_WIDTH}" height="118" rx="18" fill="url(#readme-track-fill)" stroke="url(#readme-track-stroke)" stroke-width="1.1" />
<text x="${TRACK_X + 24}" y="${y + 60}" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="18" font-weight="bold" stroke="none">Mixed evidence</text>
<text x="${TRACK_X + 24}" y="${y + 86}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="13" stroke="none">Current browser ORT results are not summarized as a single faster or slower timing claim.</text>
<text x="${TRACK_X + 24}" y="${y + 112}" fill="${SVG_THEME.palette.muted}" font-family="${FONT_UI}" font-size="13" stroke="none">The chart keeps this lane explicit instead of forcing a misleading bar summary.</text>
<rect x="${VALUE_PILL_X}" y="${y + 54}" width="${VALUE_PILL_WIDTH}" height="54" rx="27" fill="${SVG_THEME.palette.mixed}" />
<text x="${VALUE_PILL_X + (VALUE_PILL_WIDTH / 2)}" y="${y + 87}" text-anchor="middle" fill="${SVG_THEME.palette.text}" font-family="${FONT_UI}" font-size="18" font-weight="bold" stroke="none">MIXED</text>`;
}

function renderChart(chartConfig) {
  const rows = resolveChartRows(Array.isArray(chartConfig.rows) ? chartConfig.rows : []);
  const height = getChartHeight(rows.length);
  const rowMarkup = rows.map((row, rowIndex) => {
    if (typeof row.status === 'string' && row.status.toLowerCase() === 'mixed') {
      return renderMixedRow(row, rowIndex);
    }
    return renderMeasuredRow(row, rowIndex);
  }).join('\n');
  const legendY = height - 40;

  return svgWrap(
    CHART_WIDTH,
    height,
    chartConfig.title,
    chartConfig.caption ?? chartConfig.subtitle,
    `${renderDefs()}
${renderHeader(chartConfig.title, chartConfig.subtitle, CHART_WIDTH)}
${renderScaleNote(148)}
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
