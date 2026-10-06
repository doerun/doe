"""Legacy Softmax specification for the pinned opset-12 application's oracle."""

from __future__ import annotations

import numpy as np
from onnx import NodeProto
from onnx.defs import OpSchema
from onnx.defs import get_schema
from onnx.reference.op_run import OpRun


class Softmax(OpRun):
    op_domain = ""

    def __init__(
        self, node: NodeProto, run_params: dict, schema: OpSchema | None = None
    ) -> None:
        super().__init__(node, run_params, schema=get_schema("Softmax", 12))

    def _run(self, value: np.ndarray, axis: int = 1) -> tuple[np.ndarray]:
        axis = axis % value.ndim
        rows = int(np.prod(value.shape[:axis]))
        matrix = value.reshape(rows, -1)
        shifted = matrix - matrix.max(axis=1, keepdims=True)
        exponentials = np.exp(shifted)
        return (
            (exponentials / exponentials.sum(axis=1, keepdims=True)).reshape(
                value.shape
            ),
        )
