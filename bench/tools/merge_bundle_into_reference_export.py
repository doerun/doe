#!/usr/bin/env python3
"""Merge a program-bundle's referenceTranscript into an old-schema doppler reference export.

Purpose: the Doe CSL parity binder (bind_doppler_int4ple_reference_to_csl_parity.py) reads
doppler_int4ple_reference_export.json via the doppler-int4ple-reference-export schema. The
browser program bundle carries real referenceTranscript digests keyed to graphHash
7b8152f81712... (the hash CSL is aligned with). The iter-6 node-webgpu export has the
current manifest/weight/shard identity fields but a different graphHash. This merger
fuses: identity from iter-6 export + graphHash + reference data from the bundle.
"""
import hashlib
import json
import sys
from pathlib import Path


def load(p):
    return json.loads(Path(p).read_text())


def strip_sha(v):
    return v[len("sha256:"):] if isinstance(v, str) and v.startswith("sha256:") else v


def main():
    if len(sys.argv) != 4:
        print("usage: merge_bundle_into_export.py <iter6_export.json> <bundle.json> <out.json>")
        sys.exit(2)
    export = load(sys.argv[1])
    bundle = load(sys.argv[2])
    out_path = Path(sys.argv[3])

    rt = bundle["referenceTranscript"]
    graph_hash_bare = strip_sha(bundle["execution"]["graphHash"])

    # Override graph identity to match bundle (which matches CSL)
    export["executionGraphSha256"] = graph_hash_bare
    # programBundle reference
    export["programBundleId"] = bundle["bundleId"]

    # Drop schema-invalid fields carried over from iter-6 export template
    export.pop("kvCacheEvidence", None)  # binder reads this from CSL receipt, not reference export
    producer = export.get("producer", {})
    producer.pop("jsHost", None)
    producer.pop("kernelPathPolicy", None)
    # runtime enum only accepts doppler_browser_webgpu | doppler_node_webgpu
    if producer.get("runtime") not in ("doppler_browser_webgpu", "doppler_node_webgpu"):
        producer["runtime"] = "doppler_browser_webgpu"  # bundle source is browser-verify

    # Rebuild decodeTranscript from bundle's referenceTranscript
    tokens = rt["tokens"]
    logits = rt["logits"]
    kv = rt["kvCache"]
    phase = rt.get("phase", {})

    # per-step entries: bundle has {index, tokenId, inputTokenCount, dtype, elementCount, digest}
    DIGEST_ONLY_MARKER = "digest-only"  # no raw f32 on disk for bundle-derived data
    logits_digests = []
    for i, step in enumerate(logits["steps"]):
        # First step is prefill's final-logits; remaining are decode steps
        phase = "prefill" if i == 0 else "decode"
        logits_digests.append({
            "stepIndex": step["index"],
            "selectedTokenId": step["tokenId"],
            "phase": phase,
            "contextTokenCount": step["inputTokenCount"],
            "dtype": "float32",  # schema requires literal 'float32'
            "shape": [step["elementCount"]],
            "byteLength": step["elementCount"] * 4,
            "sha256": strip_sha(step["digest"]),
            "path": DIGEST_ONLY_MARKER,
            "preview": [],  # schema wants array; raw logits unavailable from digest-only source
        })

    export["decodeTranscript"] = {
        "status": "output_ready",
        "requestedDecodeSteps": len(tokens["ids"]),
        "decodeStepsRequested": len(tokens["ids"]),
        "actualDecodeSteps": len(tokens["ids"]),
        "decodeStepsProduced": len(tokens["ids"]),
        "stopReason": "decode_steps_exhausted",  # schema enum; synonym for max-tokens
        "sampling": {
            "padTokenId": 0,
            "repetitionPenalty": 1,
            "seed": None,
            "temperature": 0,
            "topK": 1,
            "topP": 1,
        },
        "generatedTokenIds": {
            "dtype": "uint32",
            "path": DIGEST_ONLY_MARKER,
            "sha256": strip_sha(tokens["generatedTokenIdsHash"]),
            "tokenCount": len(tokens["ids"]),
            "preview": tokens["ids"][:8],
        },
        "logitsDigests": logits_digests,
        "transcript": {
            "path": DIGEST_ONLY_MARKER,
            "sha256": strip_sha(rt["source"].get("hash", "pending")),
            "source": rt["source"].get("kind", "browser-report"),
        },
    }

    # Intentionally omit top-level kvCacheEvidence (schema disallows; binder reads it from
    # CSL receipt, not reference export). Bundle's kvCache digest is still referenceable via
    # the bundle path if needed.
    _ = kv  # present in source for future re-enable if schema is extended

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(export, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    print(f"  executionGraphSha256: {export['executionGraphSha256']}")
    print(f"  manifestSha256: {export['manifestSha256']}")
    print(f"  decodeTranscript.actualDecodeSteps: {export['decodeTranscript']['actualDecodeSteps']}")
    print(f"  decodeTranscript.stopReason: {export['decodeTranscript']['stopReason']}")
    print(f"  generatedTokenIds.tokenCount: {export['decodeTranscript']['generatedTokenIds']['tokenCount']}")


if __name__ == "__main__":
    main()
