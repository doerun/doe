#!/usr/bin/env python3
"""Validate the frozen Qwen 3.6 27B Doppler reference fixture.

Parallel to ``bench/tools/validate_frozen_doppler_reference.py`` (the
generic fixture validator). This tool defaults ``--root`` to the Qwen
fixture dir at ``bench/fixtures/r3-2-27b-doppler-frozen/`` and emits a
typed Qwen-labeled receipt to ``bench/out/r3-2-27b-frozen-reference-validation/report.json``.

Two regimes:

  - Fixture present: walk the manifest, validate every cited artifact's
    sha256 / byteLength / .npy header against schema
    ``config/doe-frozen-doppler-reference.schema.json``, recompute
    fixtureDigest, and bind the receipt with ``verdict=bound`` iff
    every check passes. This delegates to ``validate_frozen_doppler_reference``'s
    ``validate_fixture`` so the schema enforcement is identical to the
    Gemma path.

  - Fixture absent: emit a typed ``not_attempted`` receipt naming the
    upstream-side capture work that must land before this validator can
    bind. The blocker text cites the Qwen Doppler reference branch so
    downstream readers can trace the gap.

The Qwen fixture's contents (when it lands) follow the same shape as
``bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots/`` — a manifest,
per-layer activation .npy probes, optional first-token logits, and the
fixtureDigest the receipt-hash guard pins downstream parity
receipts against.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)
from bench.tools.validate_frozen_doppler_reference import (  # noqa: E402
    MANIFEST_FILENAME,
    validate_fixture,
)

DEFAULT_ROOT = REPO_ROOT / "bench/fixtures/r3-2-27b-doppler-frozen"
DEFAULT_OUT = (
    REPO_ROOT / "bench/out/r3-2-27b-frozen-reference-validation/report.json"
)
# The current Qwen Doppler manifest (`qwen-3-6-27b-q4k-ehaf16`) declares
# `quantizationInfo.variantTag = "q4k-ef16-af32"`. The lane-key default
# tracks that tag so a future af16 sibling fixture cannot bind under the
# Qwen-af32 validator unless --lane-key is explicitly overridden.
DEFAULT_LANE_KEY = "q4k-ef16-af32"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--lane-key",
        default=DEFAULT_LANE_KEY,
        help=(
            "Lane key the fixture's dtypeProfile.variantTag must match. "
            f"Defaults to {DEFAULT_LANE_KEY!r} (current Qwen af32 lane). "
            "Override for af16 / non-af32 sibling fixtures."
        ),
    )
    p.add_argument(
        "--require-dtype-profile",
        action="store_true",
        help=(
            "Make `dtypeProfile` mandatory on the fixture manifest. "
            "Set when validating new af16 / non-af32 sibling fixtures."
        ),
    )
    return p.parse_args()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _absent_receipt(root: Path) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "artifactKind": "doe_frozen_doppler_reference_validation",
        "modelId": "qwen-3-6-27b-q4k-ehaf16",
        "modelFamily": "qwen3",
        "fixtureRoot": _rel(root),
        "manifestPath": _rel(root / MANIFEST_FILENAME),
        "schemaValid": False,
        "schemaErrors": [],
        "artifactViolations": [],
        "digestViolations": [],
        "fixtureDigestCited": "",
        "fixtureDigestRecomputed": "",
        "bound": False,
        "verdict": "not_attempted",
        "blocker": {
            "class": "qwen_frozen_reference_fixture_absent",
            "detail": (
                "The Qwen Doppler reference fixture has not yet been "
                "captured. The validator binds when the fixture root "
                "contains a frozen-reference.manifest.json conforming to "
                "config/doe-frozen-doppler-reference.schema.json plus the "
                "cited transcript / activations / first-token-logits "
                "artifacts."
            ),
            "upstreamCapture": (
                "Doppler-side Qwen reference inference run + "
                "tsir-fixture-writer.js boundary-probe capture lane "
                "(post_rmsnorm / post_qkv / post_attn / post_ffn at L=0) "
                "is the upstream prerequisite. Lives on the "
                "feat/qwen-3-6-bringup branch in the Doppler tree. "
                "Naming and shape mirror "
                "bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots/."
            ),
        },
        "claim": {
            "scope": (
                "Qwen 3.6 27B frozen Doppler reference fixture validator "
                "binding. Schema-enforces the manifest, hash-checks every "
                "cited artifact, and recomputes fixtureDigest when the "
                "fixture is present. Returns a typed 'not_attempted' "
                "receipt with named blocker when the fixture is absent so "
                "the gap is explicit instead of silent."
            ),
            "notWhat": (
                "Not a parity claim. Not a hardware receipt. Validator "
                "binding only — the parity check itself runs downstream "
                "once the fixture lands and binds single-block parity receipts via "
                "referenceFixtureHash."
            ),
        },
    }


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = root / MANIFEST_FILENAME

    if not manifest_path.is_file():
        receipt = _absent_receipt(root)
        receipt["laneKeyExpected"] = args.lane_key
    else:
        try:
            base = validate_fixture(
                root,
                lane_key=args.lane_key,
                require_dtype_profile=args.require_dtype_profile,
            )
        except SystemExit as err:
            sys.stderr.write(str(err) + "\n")
            return 2
        receipt = {
            "schemaVersion": 1,
            "artifactKind": base["artifactKind"],
            "modelId": "qwen-3-6-27b-q4k-ehaf16",
            "modelFamily": "qwen3",
            "fixtureRoot": _rel(root),
            "manifestPath": _rel(manifest_path),
            "schemaValid": base["schemaValid"],
            "schemaErrors": base["schemaErrors"],
            "artifactViolations": base["artifactViolations"],
            "digestViolations": base["digestViolations"],
            "laneViolations": base["laneViolations"],
            "laneKeyExpected": base["laneKeyExpected"],
            "dtypeProfile": base["dtypeProfile"],
            "fixtureDigestCited": base["fixtureDigestCited"],
            "fixtureDigestRecomputed": base["fixtureDigestRecomputed"],
            "bound": base["bound"],
            "verdict": base["verdict"],
            "claim": {
                "scope": (
                    "Qwen 3.6 27B frozen Doppler reference fixture is "
                    "present and validates against "
                    "config/doe-frozen-doppler-reference.schema.json. "
                    "Every cited artifact resolves with matching "
                    "sha256 / byteLength, and fixtureDigest recomputes "
                    "to its claimed value."
                ),
                "notWhat": (
                    "Not a parity claim against Doe-side TSIR boundary "
                    "probes — the parity validator consumes this binding "
                    "via referenceFixtureHash. Not a hardware receipt."
                ),
            },
        }

    try:
        enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    except ReceiptHashSpineError as err:
        sys.stderr.write(
            "validate_qwen_3_6_27b_frozen_doppler_reference: "
            f"receipt hash spine rejected emit:\n  {err}\n"
        )
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {_rel(args.out)} verdict={receipt['verdict']} "
        f"bound={receipt['bound']}"
    )
    return 0 if receipt["verdict"] == "bound" else 1


if __name__ == "__main__":
    sys.exit(main())
