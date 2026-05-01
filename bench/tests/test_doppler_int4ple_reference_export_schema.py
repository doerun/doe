from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]


class DopplerInt4PleReferenceExportSchemaTests(unittest.TestCase):
    def test_tokenized_prompt_allows_program_bundle_provenance(self) -> None:
        schema = json.loads(
            (
                REPO_ROOT / "config/doppler-int4ple-reference-export.schema.json"
            ).read_text(encoding="utf-8")
        )
        tokenized_prompt = {
            "path": "bench/out/tokenized_prompt.u32",
            "sha256": "a" * 64,
            "dtype": "uint32",
            "tokenCount": 2,
            "source": "hash_matched_program_bundle_tokenIdsHash",
            "sourcePath": "bench/out/source_tokens.u32",
            "tokenIdsSha256": "b" * 64,
            "preview": [2, 105],
        }

        jsonschema.validate(tokenized_prompt, schema["properties"]["tokenizedPrompt"])

    def test_kv_cache_evidence_allows_doppler_byte_digest_proof(self) -> None:
        schema = json.loads(
            (
                REPO_ROOT / "config/doppler-int4ple-reference-export.schema.json"
            ).read_text(encoding="utf-8")
        )
        evidence = {
            "status": "output_ready",
            "realKvCache": True,
            "blocker": "",
            "mode": "sha256-layer-kv-bytes",
            "layout": "layer-major",
            "kvDtype": "float16",
            "byteDigest": "sha256:" + ("a" * 64),
            "layerDigestCount": 1,
            "seqLen": 1,
            "byteDigests": [
                {
                    "layer": 0,
                    "seqLen": 1,
                    "keyBytes": 1024,
                    "keyDigest": "sha256:" + ("b" * 64),
                    "valueBytes": 1024,
                    "valueDigest": "sha256:" + ("c" * 64),
                }
            ],
        }

        receipt = json.loads(
            (
                REPO_ROOT
                / "examples/doppler-int4ple-reference-export.gemma-4-e2b.contract.json"
            ).read_text(encoding="utf-8")
        )
        receipt["kvCacheEvidence"] = evidence

        jsonschema.Draft202012Validator(schema).validate(receipt)


if __name__ == "__main__":
    unittest.main()
