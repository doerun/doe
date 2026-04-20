#!/usr/bin/env python3
"""Unit test for compute_execution_status() — the flip wire that
promotes executionStatus from not_attempted to simulator_success
when the cross-runtime parity verdict clears.

The flip is the single mechanical bridge between "cs_python re-runs
the E2B layer-block runner" and "the model receipt honestly reports
simulator_success". C7 in e2b_layer_block_self_check.py locks the
False branch against the current receipt; this test locks both
branches against every combination of the five input flags so the
truth table can't silently regress.

Run directly: python3 bench/tools/test_execution_status_flip.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bench" / "tools"))

from build_model_runtime_receipt import compute_execution_status  # noqa: E402


E2B_ID = "gemma-4-e2b-it-text-q4k-ehf16-af32"
B31_ID = "gemma-4-31b-it-text-q4k-ehf16-af32"
BLOCKER = "full_transformer_layer_block_incomplete"


def case(
    label: str,
    *,
    streaming_required: bool = True,
    missing_kernels: bool = False,
    fits: bool = True,
    parity_promotion_eligible: bool = False,
    model_id: str = E2B_ID,
    default_blocker: str = BLOCKER,
    expect_status: str,
    expect_blocker: str,
) -> tuple[bool, str]:
    status, blocker = compute_execution_status(
        streaming_required=streaming_required,
        missing_kernels=missing_kernels,
        fits=fits,
        parity_promotion_eligible=parity_promotion_eligible,
        model_id=model_id,
        default_blocker=default_blocker,
    )
    ok = status == expect_status and blocker == expect_blocker
    msg = (
        f"  {'PASS' if ok else 'FAIL'}  {label}: "
        f"got ({status!r}, {blocker!r}) "
        f"expected ({expect_status!r}, {expect_blocker!r})"
    )
    return ok, msg


def main() -> int:
    cases = [
        # Happy path: all gates pass → flip to simulator_success.
        case(
            "T1 e2b, promotionEligible=True, all structural pass",
            parity_promotion_eligible=True,
            expect_status="simulator_success",
            expect_blocker="none",
        ),
        # False branch from parity: not yet eligible.
        case(
            "T2 e2b, promotionEligible=False",
            parity_promotion_eligible=False,
            expect_status="not_attempted",
            expect_blocker=BLOCKER,
        ),
        # E2B id variants (case-insensitive match on 'e2b').
        case(
            "T3 modelId case-insensitive match",
            parity_promotion_eligible=True,
            model_id="GEMMA-4-E2B-IT",
            expect_status="simulator_success",
            expect_blocker="none",
        ),
        # 31B must not inherit E2B parity verdict.
        case(
            "T4 31b, promotionEligible=True, parity does not apply",
            parity_promotion_eligible=True,
            model_id=B31_ID,
            expect_status="not_attempted",
            expect_blocker=BLOCKER,
        ),
        # Missing kernels blocks the flip even when parity eligible.
        case(
            "T5 missing kernels blocks flip",
            parity_promotion_eligible=True,
            missing_kernels=True,
            default_blocker="partial_kernel_coverage",
            expect_status="not_attempted",
            expect_blocker="partial_kernel_coverage",
        ),
        # Memory plan not fitting blocks the flip.
        case(
            "T6 memory plan does not fit blocks flip",
            parity_promotion_eligible=True,
            fits=False,
            default_blocker="memory_plan_does_not_fit",
            expect_status="not_attempted",
            expect_blocker="memory_plan_does_not_fit",
        ),
        # Non-streaming lane (elementwise path) does not use the flip.
        case(
            "T7 non-streaming lane does not flip",
            parity_promotion_eligible=True,
            streaming_required=False,
            default_blocker="full_grid_compile_unattempted",
            expect_status="not_attempted",
            expect_blocker="full_grid_compile_unattempted",
        ),
        # Empty modelId must not count as E2B.
        case(
            "T8 empty modelId rejects flip",
            parity_promotion_eligible=True,
            model_id="",
            expect_status="not_attempted",
            expect_blocker=BLOCKER,
        ),
        # None modelId defensively handled.
        case(
            "T9 None modelId rejects flip",
            parity_promotion_eligible=True,
            model_id=None,  # type: ignore[arg-type]
            expect_status="not_attempted",
            expect_blocker=BLOCKER,
        ),
    ]

    print(
        f"compute_execution_status() truth-table test "
        f"({len(cases)} cases)"
    )
    print()
    fails = 0
    for ok, msg in cases:
        print(msg)
        if not ok:
            fails += 1

    print()
    if fails:
        print(f"FAIL — {fails}/{len(cases)} case(s) incorrect")
        return 1
    print(f"PASS — {len(cases)}/{len(cases)} cases correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
