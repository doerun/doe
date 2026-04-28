#!/usr/bin/env python3
"""HF transformers reference forward for Qwen 3.6 27B; diff L=0 post-attention against the upstream-side probe.

The upstream coherence-verify run captured per-probe .npy files at
``/tmp/qwen-l0-probes/layer_0/`` (post_attn / post_ffn / post_oproj /
post_qkv / pre_ffn / ffn_mlp_out). The L=0 layer is a linear-attention
(DeltaNet SSM) layer; first full-attention layer is L=3.

This tool runs the reference HF forward (CPU or GPU) on the same prompt,
extracts L=0 post-attention output via a forward hook on
``model.language_model.model.layers[0].self_attn`` (the SSM layer's
output module name; the Qwen3_5 architecture exposes it under
``self_attn`` for both linear and full attention layers), saves it as
.npy, then diffs against the upstream-side probe.

The first non-trivial divergence in the diff names the buggy op in the
upstream linear-attention runtime — that's the actionable next-step the
user named.

Usage::

  python3 bench/tools/hf_qwen_3_6_27b_l0_post_attn_diff.py \\
    --upstream-probe /tmp/qwen-l0-probes/layer_0/post_attn.npy \\
    --out bench/out/r3-2-27b-hf-reference-l0-diff/

Exits:
  0 — diff under threshold (upstream agrees with HF reference)
  1 — diff above threshold (upstream is buggy as suspected)
  2 — environment / weight-load failure
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPT = "The color of the sky is"
DEFAULT_MODEL_ID = "Qwen/Qwen3.6-27B"
DEFAULT_PROBE = Path("/tmp/qwen-l0-probes/layer_0/post_attn.npy")
DEFAULT_OUT_DIR = REPO_ROOT / "bench/out/r3-2-27b-hf-reference-l0-diff"
DIFF_TOLERANCE = 1e-2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    p.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    p.add_argument("--upstream-probe", type=Path, default=DEFAULT_PROBE)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--tolerance", type=float, default=DIFF_TOLERANCE)
    p.add_argument("--dtype", default="bfloat16")
    p.add_argument("--device", default="auto")
    p.add_argument(
        "--layer-idx",
        type=int,
        default=0,
        help="Layer index to probe; L=0/1/2 are linear-attention, L=3 is the first full-attention.",
    )
    return p.parse_args()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if not args.upstream_probe.is_file():
        sys.stderr.write(
            f"upstream probe not found at {args.upstream_probe}\n"
        )
        return 2

    try:
        import numpy as np
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as err:
        sys.stderr.write(f"required package missing: {err}\n")
        return 2

    upstream = np.load(args.upstream_probe)
    print(
        f"upstream probe: shape={upstream.shape} dtype={upstream.dtype} "
        f"min={upstream.min():.4f} max={upstream.max():.4f}"
    )

    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    torch_dtype = dtype_map.get(args.dtype, torch.bfloat16)

    print(f"loading {args.model_id} (dtype={args.dtype}, device={args.device})")
    try:
        tokenizer = AutoTokenizer.from_pretrained(args.model_id)
        model = AutoModelForCausalLM.from_pretrained(
            args.model_id,
            torch_dtype=torch_dtype,
            device_map=args.device if args.device != "cpu" else None,
            low_cpu_mem_usage=True,
        )
        model.eval()
    except Exception as err:
        sys.stderr.write(f"model load failed: {err}\n")
        traceback.print_exc()
        return 2

    if hasattr(model, "language_model"):
        layers = model.language_model.model.layers
    else:
        layers = model.model.layers
    layer_idx = getattr(args, "layer_idx", 0)
    layer = layers[layer_idx]
    if hasattr(layer, "linear_attn"):
        target = layer.linear_attn
        target_kind = "linear_attn"
    elif hasattr(layer, "self_attn"):
        target = layer.self_attn
        target_kind = "self_attn"
    else:
        sys.stderr.write(
            f"layer {layer_idx} has no linear_attn or self_attn attribute "
            f"(kind={type(layer).__name__})\n"
        )
        return 2
    print(f"L{layer_idx} attention kind: {target_kind}")

    captured: dict[str, "np.ndarray"] = {}

    def hook(_module, _input, output):
        # self_attn returns either a tensor or (tensor, ...). Capture
        # the leading hidden state.
        if isinstance(output, tuple):
            output = output[0]
        captured["post_attn"] = output.detach().to(torch.float32).cpu().numpy()

    handle = target.register_forward_hook(hook)
    try:
        # Upstream-side coherence verify used the chat template with
        # enable_thinking=False, which gives 18 tokens for the prompt
        # "The color of the sky is" (matches upstream probe shapes).
        chat_payload = tokenizer.apply_chat_template(
            [{"role": "user", "content": args.prompt}],
            add_generation_prompt=True,
            enable_thinking=False,
            tokenize=True,
            return_tensors="pt",
        )
        if hasattr(chat_payload, "keys") and "input_ids" in chat_payload.keys():
            ids = chat_payload["input_ids"]
        elif isinstance(chat_payload, torch.Tensor):
            ids = chat_payload
        else:
            ids = torch.tensor(chat_payload, dtype=torch.long)
        if not isinstance(ids, torch.Tensor):
            ids = torch.tensor(ids, dtype=torch.long)
        if ids.dim() == 1:
            ids = ids.unsqueeze(0)
        print(f"chat-template tokens: {ids.shape}")
        if args.device != "cpu" and torch.cuda.is_available():
            ids = ids.cuda()
        with torch.no_grad():
            model(ids)
    except Exception as err:
        sys.stderr.write(f"forward failed: {err}\n")
        traceback.print_exc()
        return 2
    finally:
        handle.remove()

    if "post_attn" not in captured:
        sys.stderr.write("hook did not capture output\n")
        return 2
    hf_post_attn = captured["post_attn"]
    print(
        f"hf post_attn: shape={hf_post_attn.shape} "
        f"min={hf_post_attn.min():.4f} max={hf_post_attn.max():.4f}"
    )

    np.save(args.out / "hf_l0_post_attn.npy", hf_post_attn)

    # Squeeze leading dims to match probe shape if needed.
    if hf_post_attn.shape != upstream.shape:
        try:
            hf_aligned = hf_post_attn.reshape(upstream.shape)
        except ValueError:
            hf_aligned = hf_post_attn.squeeze()
            if hf_aligned.shape != upstream.shape:
                sys.stderr.write(
                    f"shape mismatch: hf={hf_post_attn.shape} "
                    f"upstream={upstream.shape}; saving raw, no diff\n"
                )
                report = {
                    "schemaVersion": 1,
                    "artifactKind": "doe_hf_qwen_3_6_27b_l0_post_attn_diff",
                    "modelId": args.model_id,
                    "prompt": args.prompt,
                    "upstreamProbePath": str(args.upstream_probe),
                    "hfProbePath": _rel(args.out / "hf_l0_post_attn.npy"),
                    "shapeMismatch": True,
                    "hfShape": list(hf_post_attn.shape),
                    "upstreamShape": list(upstream.shape),
                }
                (args.out / "report.json").write_text(
                    json.dumps(report, indent=2) + "\n"
                )
                return 1
    else:
        hf_aligned = hf_post_attn

    diff = hf_aligned - upstream
    abs_diff = np.abs(diff)
    max_abs = float(abs_diff.max())
    mean_abs = float(abs_diff.mean())
    upstream_l2 = float(np.linalg.norm(upstream.astype(np.float32)))
    diff_l2 = float(np.linalg.norm(diff.astype(np.float32)))
    rel_l2 = diff_l2 / max(upstream_l2, 1e-9)

    bound = max_abs <= args.tolerance
    report = {
        "schemaVersion": 1,
        "artifactKind": "doe_hf_qwen_3_6_27b_l0_post_attn_diff",
        "modelId": args.model_id,
        "prompt": args.prompt,
        "upstreamProbePath": str(args.upstream_probe),
        "hfProbePath": _rel(args.out / "hf_l0_post_attn.npy"),
        "shape": list(upstream.shape),
        "tolerance": args.tolerance,
        "maxAbsDiff": max_abs,
        "meanAbsDiff": mean_abs,
        "upstreamL2": upstream_l2,
        "diffL2": diff_l2,
        "relL2": rel_l2,
        "bound": bound,
        "verdict": "agrees" if bound else "diverges",
        "diagnosis": (
            "Upstream linear-attention runtime appears correct relative to "
            "HF reference at L=0."
            if bound
            else "Upstream linear-attention runtime diverges from HF "
            "reference at L=0; first non-tiny divergence names the "
            "buggy op."
        ),
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"max_abs_diff={max_abs:.6e} mean={mean_abs:.6e} "
        f"rel_l2={rel_l2:.6e} verdict={report['verdict']}"
    )
    return 0 if bound else 1


if __name__ == "__main__":
    sys.exit(main())
