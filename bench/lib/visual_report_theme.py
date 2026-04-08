"""Shared HTML helpers for Doe benchmark visualization pages."""

from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Any


def safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def format_delta(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:+.2f}%"


def delta_tone(value: Any) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return "neutral"
    if parsed > 0.0:
        return "good"
    if parsed < 0.0:
        return "bad"
    return "neutral"


def status_tone(status: str, *, kind: str = "comparison") -> str:
    token = status.strip().lower()
    if kind == "claim":
        if token == "claimable":
            return "good"
        if token in {"diagnostic", "not-evaluated"}:
            return "warn"
        if token in {"unsupported", "unimplemented", "non-claimable"}:
            return "bad"
        return "neutral"
    if token in {"claimable", "comparable"}:
        return "good"
    if token in {"diagnostic", "not-evaluated"}:
        return "warn"
    if token in {"unsupported", "unimplemented", "unreliable", "non-comparable"}:
        return "bad"
    return "neutral"


def badge(label: str, *, tone: str = "neutral") -> str:
    return f"<span class='badge {escape(tone)}'>{escape(label)}</span>"


def stat_card(
    label: str,
    value: str,
    *,
    detail: str = "",
    tone: str = "neutral",
) -> str:
    detail_html = ""
    if detail:
        detail_html = f"<div class='card-detail'>{escape(detail)}</div>"
    return (
        f"<article class='stat-card {escape(tone)}'>"
        f"<div class='card-label'>{escape(label)}</div>"
        f"<div class='card-value'>{escape(value)}</div>"
        f"{detail_html}"
        "</article>"
    )


def relative_href(page_path: str | Path, target_path: str | Path) -> str:
    page = Path(page_path)
    target = Path(target_path)
    relative = Path(os.path.relpath(str(target), start=str(page.parent)))
    return relative.as_posix()


def render_page(
    *,
    title: str,
    eyebrow: str,
    headline: str,
    intro: str,
    meta_html: str = "",
    hero_extra_html: str = "",
    body_html: str,
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg-paper: #f6efe4;
      --bg-mist: #eef4f7;
      --bg-ink: #102033;
      --panel: rgba(255, 252, 246, 0.86);
      --panel-strong: rgba(255, 253, 249, 0.98);
      --line: rgba(28, 53, 77, 0.14);
      --line-strong: rgba(28, 53, 77, 0.22);
      --ink: #132033;
      --muted: #576578;
      --accent: #0d7c76;
      --accent-strong: #0a615d;
      --good-bg: #d8f2e5;
      --good-ink: #0d6c3d;
      --warn-bg: #f7ebc8;
      --warn-ink: #8e6110;
      --bad-bg: #f6d8d2;
      --bad-ink: #9c3b2d;
      --neutral-bg: #e2e8ef;
      --neutral-ink: #516273;
      --shadow: 0 18px 54px rgba(15, 23, 42, 0.08);
      --shadow-soft: 0 10px 28px rgba(15, 23, 42, 0.05);
      --font-body: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
      --font-heading: "Space Grotesk", ui-sans-serif, system-ui, sans-serif;
      --font-mono: "IBM Plex Mono", ui-monospace, monospace;
    }}
    * {{
      box-sizing: border-box;
    }}
    html {{
      scroll-behavior: smooth;
    }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: var(--font-body);
      background:
        radial-gradient(circle at top left, rgba(13, 124, 118, 0.18), transparent 28%),
        radial-gradient(circle at 88% 4%, rgba(208, 136, 29, 0.18), transparent 24%),
        linear-gradient(180deg, var(--bg-paper) 0%, #f5f8fb 20%, var(--bg-mist) 100%);
      min-height: 100vh;
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(16, 32, 51, 0.015) 1px, transparent 1px),
        linear-gradient(90deg, rgba(16, 32, 51, 0.015) 1px, transparent 1px);
      background-size: 28px 28px;
      mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.45), transparent 82%);
      pointer-events: none;
    }}
    main {{
      position: relative;
      max-width: 1460px;
      margin: 0 auto;
      padding: 28px 22px 72px;
    }}
    a {{
      color: var(--accent-strong);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    code {{
      font-family: var(--font-mono);
      font-size: 12px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      padding: 28px;
      border: 1px solid var(--line);
      border-radius: 26px;
      background:
        linear-gradient(145deg, rgba(255, 250, 243, 0.96), rgba(245, 251, 255, 0.92)),
        var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      width: 420px;
      height: 420px;
      top: -180px;
      right: -120px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(13, 124, 118, 0.18), transparent 70%);
      pointer-events: none;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--accent-strong);
    }}
    .eyebrow::before {{
      content: "";
      display: inline-block;
      width: 24px;
      height: 1px;
      background: currentColor;
    }}
    h1 {{
      margin: 12px 0 10px;
      font-family: var(--font-heading);
      font-size: clamp(34px, 4vw, 58px);
      line-height: 0.98;
      letter-spacing: -0.03em;
      max-width: 12ch;
    }}
    .intro {{
      max-width: 76ch;
      margin: 0;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.6;
    }}
    .hero-meta {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}
    .hero-extra {{
      margin-top: 20px;
    }}
    .stat-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-top: 20px;
    }}
    .stat-card {{
      padding: 16px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      box-shadow: var(--shadow-soft);
    }}
    .stat-card.good {{
      background: linear-gradient(180deg, rgba(216, 242, 229, 0.96), rgba(255, 253, 249, 0.98));
    }}
    .stat-card.warn {{
      background: linear-gradient(180deg, rgba(247, 235, 200, 0.95), rgba(255, 253, 249, 0.98));
    }}
    .stat-card.bad {{
      background: linear-gradient(180deg, rgba(246, 216, 210, 0.95), rgba(255, 253, 249, 0.98));
    }}
    .card-label {{
      color: var(--muted);
      font-size: 11px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .card-value {{
      margin-top: 8px;
      font-size: clamp(22px, 2.6vw, 34px);
      line-height: 1;
      font-weight: 700;
    }}
    .card-detail {{
      margin-top: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .section {{
      margin-top: 22px;
      padding: 20px;
      border-radius: 22px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow-soft);
      backdrop-filter: blur(10px);
    }}
    .section-head {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }}
    .section h2 {{
      margin: 0;
      font-family: var(--font-heading);
      font-size: 24px;
      letter-spacing: -0.02em;
    }}
    .section-copy {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
      max-width: 76ch;
    }}
    .badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 5px 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      background: var(--neutral-bg);
      color: var(--neutral-ink);
    }}
    .badge.good {{
      background: var(--good-bg);
      color: var(--good-ink);
    }}
    .badge.warn {{
      background: var(--warn-bg);
      color: var(--warn-ink);
    }}
    .badge.bad {{
      background: var(--bad-bg);
      color: var(--bad-ink);
    }}
    .badge.info {{
      background: rgba(183, 223, 244, 0.92);
      color: #195580;
    }}
    .badge.neutral {{
      background: var(--neutral-bg);
      color: var(--neutral-ink);
    }}
    .artifact-grid,
    .tile-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .tile {{
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 253, 249, 0.92);
    }}
    .tile h3 {{
      margin: 0 0 10px;
      font-family: var(--font-heading);
      font-size: 18px;
    }}
    .tile p {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }}
    .link-list {{
      display: grid;
      gap: 8px;
      margin-top: 14px;
      font-size: 13px;
    }}
    .link-list a code {{
      font-size: 12px;
    }}
    .table-shell {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.72);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
    }}
    th,
    td {{
      padding: 10px 12px;
      border-bottom: 1px solid rgba(21, 38, 59, 0.08);
      font-size: 13px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      background: rgba(241, 246, 250, 0.98);
      color: #31435a;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      z-index: 1;
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    .metric-positive {{
      color: var(--good-ink);
      font-weight: 700;
    }}
    .metric-negative {{
      color: var(--bad-ink);
      font-weight: 700;
    }}
    .metric-neutral {{
      color: var(--neutral-ink);
      font-weight: 700;
    }}
    .fine-print {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }}
    details {{
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255, 253, 249, 0.9);
      padding: 12px 14px;
    }}
    details + details {{
      margin-top: 12px;
    }}
    summary {{
      cursor: pointer;
      font-weight: 700;
      font-family: var(--font-heading);
    }}
    @media (max-width: 900px) {{
      main {{
        padding: 16px 14px 44px;
      }}
      .hero {{
        padding: 22px 18px;
      }}
      .section {{
        padding: 16px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="eyebrow">{escape(eyebrow)}</div>
      <h1>{escape(headline)}</h1>
      <p class="intro">{escape(intro)}</p>
      <div class="hero-meta">{meta_html}</div>
      <div class="hero-extra">{hero_extra_html}</div>
    </section>
    {body_html}
  </main>
</body>
</html>
"""
