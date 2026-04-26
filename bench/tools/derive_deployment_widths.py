#!/usr/bin/env python3
"""Derive deployment-shape widths from a manifest-compile threshold sweep.

Mitigates "Deployment-shape width generator" from
docs/cerebras-north-star.md (Remaining no-hardware evidence gaps).

The manifest-compile sweep in
`bench/out/r3-1-31b-manifest-compile-sweep/sweep-summary.json` records
discrete cslc invocations at increasing `--size` values and brackets
the per-PE memory ceiling. This tool reads that sweep, identifies the
last passing width as the deployment ceiling, and emits a recommended
set of deployment widths up to (and including) the ceiling.

The generator is data-driven: callers can point it at any sweep
summary (e.g. produced by a future per-target sweep). It does not
re-run cslc — it only consumes the receipt the sweep already wrote.

Output schema: doe_deployment_widths_v1
  - sourceSweepPath: which sweep summary the recommendations came from
  - sweepThreshold: { lastPassing, firstFailing, intervalNarrowed }
  - deploymentCeiling: integer (== sweepThreshold.lastPassing)
  - recommendedWidths: sorted list of integers <= deploymentCeiling
  - claim: { scope, notWhat }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SWEEP_SUMMARY = (
    REPO_ROOT
    / "bench/out/r3-1-31b-manifest-compile-sweep/sweep-summary.json"
)
DEFAULT_OUT = REPO_ROOT / "bench/out/deployment-widths/derived-widths.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--sweep-summary",
        type=Path,
        default=DEFAULT_SWEEP_SUMMARY,
        help=(
            "Path to the manifest-compile sweep summary "
            "(doe_manifest_compile_sweep_summary)."
        ),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Where to write the derived-widths receipt.",
    )
    p.add_argument(
        "--include-power-of-two-only",
        action="store_true",
        help=(
            "Only include power-of-two widths in the recommendation. "
            "Default also includes the exact lastPassing width if it is "
            "not a power of two (e.g. 2560)."
        ),
    )
    return p.parse_args()


def load_summary(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(
            f"derive_deployment_widths: missing sweep summary {path}. "
            f"Run the threshold sweep first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def derive_widths(
    last_passing: int,
    *,
    power_of_two_only: bool,
) -> list[int]:
    if last_passing < 1:
        return []
    widths: set[int] = set()
    width = 1024
    while width <= last_passing:
        widths.add(width)
        width *= 2
    if not power_of_two_only and last_passing not in widths:
        widths.add(last_passing)
    return sorted(widths)


def main() -> int:
    args = parse_args()
    summary = load_summary(args.sweep_summary)
    threshold = summary.get("threshold") or {}
    last_passing = threshold.get("lastPassing")
    first_failing = threshold.get("firstFailing")
    interval = threshold.get("intervalNarrowed", "")
    if not isinstance(last_passing, int) or last_passing <= 0:
        sys.stderr.write(
            "derive_deployment_widths: sweep summary lacks "
            "threshold.lastPassing (int)\n"
        )
        return 2

    widths = derive_widths(
        last_passing, power_of_two_only=args.include_power_of_two_only
    )

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_deployment_widths_v1",
        "sourceSweepPath": str(
            args.sweep_summary.relative_to(REPO_ROOT)
            if args.sweep_summary.is_absolute()
            and str(args.sweep_summary).startswith(str(REPO_ROOT))
            else args.sweep_summary
        ),
        "sweepThreshold": {
            "lastPassing": last_passing,
            "firstFailing": first_failing,
            "intervalNarrowed": interval,
        },
        "deploymentCeiling": last_passing,
        "recommendedWidths": widths,
        "claim": {
            "scope": (
                f"Per-PE memory budget supports manifest-compile widths up to "
                f"{last_passing} (last passing in the source sweep). "
                f"Recommended deployment widths: {widths}."
            ),
            "notWhat": (
                "Not a manifest-shape success — it only states which widths "
                "the layer-block compile accepts, not which produce useful "
                "execution. Not a policy decision: callers still decide which "
                "widths to materialize and how to compose them across "
                "streaming residency. Not generalized to chained layers — "
                "the underlying sweep is L1 only."
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out} (deploymentCeiling={last_passing}, "
        f"widths={widths})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
