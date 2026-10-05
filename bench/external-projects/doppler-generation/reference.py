"""CPU Gemma oracle using Transformers and upstream GGUF dequantization."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import torch
from gguf.quants import Q4_K
from tokenizers import Tokenizer
from transformers import Gemma3ForCausalLM, Gemma3TextConfig


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_tensor(root: Path, manifest: dict, descriptor: dict) -> torch.Tensor:
    spans = descriptor.get("spans") or [{"shardIndex": descriptor["shard"],
        "offset": descriptor["offset"], "size": descriptor["size"]}]
    chunks = []
    for span in spans:
        shard = manifest["shards"][span["shardIndex"]]
        with (root / shard["filename"]).open("rb") as stream:
            stream.seek(span["offset"])
            chunk = stream.read(span["size"])
            if len(chunk) != span["size"]:
                raise ValueError("Truncated tensor span")
            chunks.append(chunk)
    raw = b"".join(chunks)
    shape = descriptor["shape"]
    dtype = descriptor["dtype"]
    if dtype == "Q4_K_M":
        values = Q4_K.dequantize_blocks(np.frombuffer(raw, dtype=np.uint8).reshape(-1, 144))
        values = values.reshape(shape[0], -1)[:, :shape[1]].copy()
        return torch.from_numpy(values)
    if dtype == "BF16":
        return torch.from_numpy(np.frombuffer(raw, dtype=np.uint16).copy()).view(torch.bfloat16).float().reshape(shape)
    if dtype == "F16":
        return torch.from_numpy(np.frombuffer(raw, dtype=np.float16).astype(np.float32)).reshape(shape)
    raise ValueError(f"Unsupported reference dtype {dtype}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    root = Path(contract["model"]["path"])
    for artifact in contract["model"]["files"]:
        if digest(root / artifact["path"]) != artifact["sha256"]:
            raise ValueError(f"Model digest mismatch: {artifact['path']}")
    manifest = json.loads((root / "manifest.json").read_text())
    torch.set_num_threads(contract["oracle"]["cpuThreads"])
    config = Gemma3TextConfig(**contract["oracle"]["modelConfig"])
    config._attn_implementation = "eager"
    model = Gemma3ForCausalLM(config).float().eval()
    state = {name: read_tensor(root, manifest, descriptor)
             for name, descriptor in manifest["tensors"].items()}
    state["lm_head.weight"] = state["model.embed_tokens.weight"]
    model.load_state_dict(state, strict=True, assign=True)
    model.tie_weights()
    del state
    tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
    results = []
    with torch.inference_mode():
        for case in contract["cases"]:
            text = f"<start_of_turn>user\n{case['prompt']}<end_of_turn>\n<start_of_turn>model\n"
            prompt = tokenizer.encode(text).ids
            generated = []
            margins = []
            stop = "max_tokens"
            for _ in range(case["maxTokens"]):
                logits = model(torch.tensor([prompt + generated]), use_cache=False,
                               logits_to_keep=1).logits[0, -1].float()
                top = torch.topk(logits, 2)
                token = int(top.indices[0])
                margins.append(float(top.values[0] - top.values[1]))
                generated.append(token)
                if token in contract["generation"]["eosTokenIds"]:
                    stop = "eos"
                    break
                output = tokenizer.decode(generated, skip_special_tokens=True)
                if any(value in output for value in case["stopSequences"]):
                    stop = "stop_sequence"
                    break
            result = {"id": case["id"], "promptTokenIds": prompt,
                "tokenIds": generated, "outputText": tokenizer.decode(generated, skip_special_tokens=True),
                "stopReason": stop, "argmaxMargins": margins}
            results.append(result)
            print(json.dumps({"case": case["id"], "tokens": len(generated), "stopReason": stop}), flush=True)
    receipt = {"schemaVersion": 1, "classification": "independent-cpu-reference",
        "contractSha256": digest(args.contract), "sourceSha256": digest(Path(__file__)),
        "libraries": {name: importlib.metadata.version(name)
                      for name in ["torch", "transformers", "gguf", "tokenizers", "numpy"]},
        "implementation": "CPU Transformers Gemma3 eager attention, full-prefix recomputation; GGUF Q4_K dequantization; F32 state without F16 cache rounding. Exact streamed token/text/stopping is the gate, not bitwise logits.",
        "cases": results}
    args.out.write_text(json.dumps(receipt, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
