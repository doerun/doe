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


if __name__ == "__main__":
    unittest.main()
