from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.tools.verify_per_kernel_byte_identity import (  # noqa: E402
    build_receipt,
    compare_kernel,
)


def _make_kernel(
    root: Path,
    *,
    name: str,
    layout: bytes,
    pe_program: bytes,
    metadata: dict,
) -> None:
    kdir = root / name
    kdir.mkdir(parents=True)
    (kdir / "layout.csl").write_bytes(layout)
    (kdir / "pe_program.csl").write_bytes(pe_program)
    (kdir / "pe_program.metadata.json").write_text(
        json.dumps(metadata, sort_keys=True),
        encoding="utf-8",
    )


class CompareKernelTest(unittest.TestCase):
    def test_match_when_bytes_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left"
            right = tmp_path / "right"
            for root in (left, right):
                _make_kernel(
                    root,
                    name="embed",
                    layout=b"layout {}",
                    pe_program=b"fn compute() void {}",
                    metadata={"exports": []},
                )
            record = compare_kernel(
                name="embed", left_root=left, right_root=right
            )
            self.assertTrue(record["match"])
            for filename in (
                "layout.csl",
                "pe_program.csl",
                "pe_program.metadata.json",
            ):
                self.assertTrue(record["artifacts"][filename]["match"])

    def test_mismatch_on_layout_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left"
            right = tmp_path / "right"
            _make_kernel(
                left,
                name="embed",
                layout=b"layout {}",
                pe_program=b"fn compute() void {}",
                metadata={"exports": []},
            )
            _make_kernel(
                right,
                name="embed",
                layout=b"layout { changed }",
                pe_program=b"fn compute() void {}",
                metadata={"exports": []},
            )
            record = compare_kernel(
                name="embed", left_root=left, right_root=right
            )
            self.assertFalse(record["match"])
            self.assertFalse(record["artifacts"]["layout.csl"]["match"])
            self.assertTrue(record["artifacts"]["pe_program.csl"]["match"])

    def test_mismatch_on_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left"
            right = tmp_path / "right"
            _make_kernel(
                left,
                name="embed",
                layout=b"layout {}",
                pe_program=b"fn compute() void {}",
                metadata={"exports": []},
            )
            (right / "embed").mkdir(parents=True)
            (right / "embed/layout.csl").write_bytes(b"layout {}")
            # pe_program.csl absent on the right side
            (right / "embed/pe_program.metadata.json").write_text(
                json.dumps({"exports": []}, sort_keys=True),
                encoding="utf-8",
            )
            record = compare_kernel(
                name="embed", left_root=left, right_root=right
            )
            self.assertFalse(record["match"])
            self.assertFalse(
                record["artifacts"]["pe_program.csl"]["match"]
            )
            self.assertIsNone(
                record["artifacts"]["pe_program.csl"]["rightSha256"]
            )


class BuildReceiptTest(unittest.TestCase):
    def test_bound_when_all_kernels_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left"
            right = tmp_path / "right"
            for root in (left, right):
                _make_kernel(
                    root,
                    name="embed",
                    layout=b"L1",
                    pe_program=b"P1",
                    metadata={"exports": [{"symbol": "output"}]},
                )
                _make_kernel(
                    root,
                    name="rmsnorm",
                    layout=b"L2",
                    pe_program=b"P2",
                    metadata={"exports": [{"symbol": "output"}]},
                )
            receipt = build_receipt(
                left_root=left,
                right_root=right,
                label_left="48L",
                label_right="1L",
            )
            self.assertEqual(receipt["verdict"], "bound")
            self.assertIsNone(receipt["blocker"])
            self.assertEqual(receipt["totals"]["sharedKernelCount"], 2)
            self.assertEqual(receipt["totals"]["matchCount"], 2)
            self.assertEqual(receipt["totals"]["mismatchCount"], 0)
            self.assertEqual(
                receipt["receiptClass"],
                "manifest_shape_per_kernel_identity",
            )

    def test_blocked_on_byte_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left"
            right = tmp_path / "right"
            _make_kernel(
                left,
                name="embed",
                layout=b"L_left",
                pe_program=b"P",
                metadata={"exports": []},
            )
            _make_kernel(
                right,
                name="embed",
                layout=b"L_right",
                pe_program=b"P",
                metadata={"exports": []},
            )
            receipt = build_receipt(
                left_root=left,
                right_root=right,
                label_left="48L",
                label_right="1L",
            )
            self.assertEqual(receipt["verdict"], "blocked")
            self.assertEqual(
                receipt["blocker"], "per_kernel_byte_mismatch"
            )

    def test_blocked_on_kernel_set_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left"
            right = tmp_path / "right"
            _make_kernel(
                left,
                name="embed",
                layout=b"L",
                pe_program=b"P",
                metadata={"exports": []},
            )
            _make_kernel(
                left,
                name="rmsnorm",
                layout=b"L",
                pe_program=b"P",
                metadata={"exports": []},
            )
            _make_kernel(
                right,
                name="embed",
                layout=b"L",
                pe_program=b"P",
                metadata={"exports": []},
            )
            receipt = build_receipt(
                left_root=left,
                right_root=right,
                label_left="48L",
                label_right="1L",
            )
            self.assertEqual(receipt["verdict"], "blocked")
            self.assertEqual(receipt["blocker"], "kernel_set_mismatch")
            self.assertEqual(receipt["leftOnlyKernels"], ["rmsnorm"])
            self.assertEqual(receipt["rightOnlyKernels"], [])

    def test_blocked_on_no_shared_kernels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left"
            right = tmp_path / "right"
            left.mkdir()
            right.mkdir()
            receipt = build_receipt(
                left_root=left,
                right_root=right,
                label_left="48L",
                label_right="1L",
            )
            self.assertEqual(receipt["verdict"], "blocked")
            self.assertEqual(receipt["blocker"], "no_shared_kernels")

    def test_self_compare_is_bound(self) -> None:
        """Smoke test: comparing a compile root to itself must be bound.

        This is the cheapest way to confirm the verifier is reliable
        before running it against real 1L/48L emissions.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "compile"
            _make_kernel(
                root,
                name="embed",
                layout=b"L",
                pe_program=b"P",
                metadata={"exports": []},
            )
            receipt = build_receipt(
                left_root=root,
                right_root=root,
                label_left="self",
                label_right="self",
            )
            self.assertEqual(receipt["verdict"], "bound")


if __name__ == "__main__":
    unittest.main()
