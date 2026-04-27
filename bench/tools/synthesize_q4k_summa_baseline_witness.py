#!/usr/bin/env python3
"""Pin the existing simfabric multi-token decode receipt as the f32_dense
SUMMA baseline witness for the fused-dequant Q4K wedge (item 2 of the
post-hardware optimization roadmap).

Wedge 7 of `feat/fused-dequant-summa`. The validation gate has two
sides:

  baseline (f32_dense)   — `bench/out/r3-1-31b-multi-token-decode/receipt.json`
                           must keep its existing verdict and digests
                           after the wedge lands. This writer freezes
                           that contract: it copies the baseline's
                           hash-pinned structure into a separate
                           witness so the wedge's q4k_block256 receipt
                           can be compared against an immutable
                           reference.

  wedge (q4k_block256)   — emitted by
                           `synthesize_q4k_summa_dispatch_receipt.py`
                           when the simfabric run executes the new
                           dispatch path.

The wedge is "claimable" only when:
  - this baseline witness re-validates against the current
    `r3-1-31b-multi-token-decode/receipt.json` byte-for-byte (no
    Gemma 4 31B regression), AND
  - the q4k_block256 receipt's `tokenSequence` and
    `perStepLogitsDigests` match the baseline element-for-element
    (algorithm-exact dequant), AND
  - the q4k_block256 receipt records a smaller fabric-bytes count for
    the B operand broadcast (the wedge's whole point).

This writer emits the baseline witness only. Run order:

  1. `python3 bench/tools/synthesize_q4k_summa_baseline_witness.py`
  2. (sim run with b_dtype=.q4k_block256) → produces wedge receipt
  3. `python3 bench/tools/synthesize_q4k_summa_dispatch_receipt.py`
  4. `python3 -m unittest bench.tests.test_q4k_summa_receipt_parity`
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools._receipt_hash_guard import (  # noqa: E402
    ReceiptHashSpineError,
    enforce_receipt_hash_spine,
)

DEFAULT_BASELINE = (
    REPO_ROOT / "bench/out/r3-1-31b-multi-token-decode/receipt.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "bench/out/r3-1-31b-multi-token-decode-q4k-baseline-witness/receipt.json"
)


def _canonical_bytes(doc: object) -> bytes:
    return json.dumps(
        doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _canonical_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.baseline.is_file():
        sys.stderr.write(
            f"baseline receipt not found: {args.baseline}. The Gemma 4 "
            f"31B simfabric multi-token decode chain must run first.\n"
        )
        return 2

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    if baseline.get("verdict") != "pass":
        sys.stderr.write(
            f"baseline verdict is {baseline.get('verdict')!r}, not 'pass'. "
            f"Refusing to bind the q4k wedge to a non-passing baseline.\n"
        )
        return 2

    baseline_digest = _canonical_sha256(args.baseline)

    receipt = {
        "schemaVersion": 1,
        "artifactKind": "doe_q4k_summa_baseline_witness",
        "purpose": (
            "Hash-pin the f32_dense SUMMA multi-token decode receipt as "
            "an immutable baseline for the fused-dequant Q4K wedge "
            "(feat/fused-dequant-summa). Comparing the wedge's "
            "q4k_block256 receipt against this witness is how we "
            "verify Gemma 4 31B did not regress."
        ),
        "target": baseline.get("target"),
        "executionTarget": baseline.get("executionTarget"),
        "shape": baseline.get("shape"),
        "numSteps": baseline.get("numSteps"),
        "stopReason": baseline.get("stopReason"),
        "tokenSequence": list(baseline.get("tokenSequence") or []),
        "perStepLogitsDigests": list(
            baseline.get("perStepLogitsDigests") or []
        ),
        "baselineSourceReceipt": {
            "path": str(args.baseline.relative_to(REPO_ROOT)),
            "sha256": baseline_digest,
            "artifactKind": baseline.get("artifactKind"),
            "schemaVersion": baseline.get("schemaVersion"),
            "verdict": baseline.get("verdict"),
            "subprocessChain": baseline.get("subprocessChain"),
        },
        "wedgeContract": {
            "branch": "feat/fused-dequant-summa",
            "wedge": "fused_dequant_summa_q4k_block256",
            "bDtypeBaseline": "f32_dense",
            "bDtypeWedge": "q4k_block256",
            "expectedDeltas": [
                "fabric memcpy bytes per B broadcast: ~7x smaller "
                "(sizeof(f32) * weights → 144 bytes / 256 weights)",
                "host CPU dequant time: 0 (passthrough; PE program "
                "runs dequant_b_tile() per broadcast step)",
                "tokenSequence: BIT-IDENTICAL to baseline",
                "perStepLogitsDigests: BIT-IDENTICAL to baseline "
                "(algorithm_exact: same f32 accumulation, same "
                "reduction order, dequant arithmetic byte-identical "
                "to Doppler reference)",
            ],
            "regressionDefinition": (
                "Any drift in tokenSequence or perStepLogitsDigests "
                "is a hard regression; the wedge MUST be reverted. "
                "Smaller fabric bytes is necessary but not sufficient — "
                "structural parity is the gate."
            ),
            "alignmentInvariants": [
                "SUMMA Kt must be a multiple of 256 (Q4K block "
                "elements). Gemma 4 31B's compile sweep produces "
                "Kt = 2560 = 10 * 256, so this is satisfied for the "
                "baseline shape.",
            ],
        },
        "claim": {
            "scope": (
                "Frozen baseline witness for the fused-dequant SUMMA "
                "wedge. Bound to the existing simfabric multi-token "
                "decode receipt by content hash. NOT a wedge result on "
                "its own — pair with the q4k_block256 dispatch receipt."
            ),
            "notWhat": (
                "Not a speed claim. Not a wedge witness. Not hardware. "
                "This is the immutable LEFT side of the validation "
                "gate; the RIGHT side is the q4k_block256 receipt."
            ),
            "summary": (
                f"baseline {baseline_digest[:12]}… pinned at "
                f"{baseline.get('numSteps')}-step decode "
                f"({len(baseline.get('tokenSequence') or [])} tokens, "
                f"{len(baseline.get('perStepLogitsDigests') or [])} "
                f"per-step digests)."
            ),
        },
    }

    try:
        enforce_receipt_hash_spine(receipt, repo_root=REPO_ROOT)
    except ReceiptHashSpineError as err:
        sys.stderr.write(f"receipt hash spine rejected emit: {err}\n")
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
