"""Evaluate the original application's input with ONNX's independent reference."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import onnx
from onnx.reference import ReferenceEvaluator
from reference_softmax import Softmax


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output must be new")
    policy_path = (
        Path(__file__).resolve().parents[3] / "config/onnx-vulkan-campaign.json"
    )
    policy = json.loads(policy_path.read_text())
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if digest(args.model) != policy["application"]["modelSha256"]:
        raise ValueError("Model identity drift")
    model = onnx.load(args.model)
    onnx.checker.check_model(model)
    count = 224 * 224 * 3
    values = (np.arange(count, dtype=np.float32) / np.float32(count + 1)).reshape(
        1, 3, 224, 224
    )
    input_name = model.graph.input[0].name
    if any(entry.domain == "" and entry.version != 12 for entry in model.opset_import):
        raise ValueError("The legacy Softmax oracle is pinned to opset 12")
    result = ReferenceEvaluator(model, new_ops=[Softmax]).run(
        ["softmaxout_1"], {input_name: values}
    )[0]
    if result.size != 1000 or not np.isfinite(result).all():
        raise ValueError("Original application output contract drift")
    args.out.mkdir(parents=True)
    result.astype("<f4").tofile(args.out / "reference.f32")
    np.save(args.out / "input.npy", values)
    receipt = {
        "schemaVersion": 1,
        "oracle": "onnx-reference-evaluator",
        "modelSha256": digest(args.model),
        "policySha256": digest(policy_path),
        "sourceSha256": digest(Path(__file__)),
        "onnxVersion": onnx.__version__,
        "inputName": input_name,
        "inputShape": list(values.shape),
        "inputSha256": digest(args.out / "input.npy"),
        "outputShape": list(result.shape),
        "outputSha256": digest(args.out / "reference.f32"),
        "top1": int(result.argmax()),
        "output": result.tolist(),
        "operators": [node.op_type for node in model.graph.node],
    }
    (args.out / "reference.json").write_text(json.dumps(receipt, indent=2) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
