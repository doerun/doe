#!/usr/bin/env python3
"""Preflight Gemma-4 E2B local model, cache, and handoff paths.

This tool does not download model weights. It resolves the writable local
roots and prints the exact shell exports and validation commands that the
Gemma-4 E2B Cerebras lane expects.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

RAW_BF16_MODEL_ID = "google/gemma-4-E2B-it"
RAW_BF16_MODEL_URL = "https://huggingface.co/google/gemma-4-E2B-it"
DEFAULT_MODELS_ROOT = "/home/x/model-downloads"
DEFAULT_HF_HOME = str(Path.home() / ".cache/huggingface")
DEFAULT_RAW_SNAPSHOT = "/home/x/model-downloads/gemma4-e2b-it"
DEFAULT_RDRR_FIXTURE = "config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json"
DEFAULT_RDRR_ROOT = "../doppler/models/local/gemma-4-e2b-it-q4k-ehf16-af32-int4ple"
EXTERNAL_MODELS_ROOT = "/media/x/models"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create the selected cache/model directories when possible.",
    )
    parser.add_argument(
        "--require-assets",
        action="store_true",
        help="Exit nonzero if the raw BF16 snapshot or RDRR artifact is absent.",
    )
    parser.add_argument(
        "--out-json",
        default="bench/out/gemma4-e2b-access-preflight.json",
    )
    parser.add_argument(
        "--print-shell",
        action="store_true",
        help="Print export lines after writing JSON.",
    )
    return parser.parse_args()


def resolve(raw: str | Path) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_dir(path: Path, create: bool) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "isDir": path.is_dir(),
        "created": False,
        "writable": False,
        "error": None,
    }
    try:
        if create and not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            record["created"] = True
        record["exists"] = path.exists()
        record["isDir"] = path.is_dir()
        if path.is_dir():
            probe = path / ".doe_write_probe"
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink()
            record["writable"] = True
    except OSError as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def first_usable_root(candidates: list[Path], create: bool) -> tuple[Path, list[dict[str, Any]]]:
    audits = [check_dir(candidate, create=False) for candidate in candidates]
    for candidate, audit in zip(candidates, audits):
        if audit["writable"]:
            return candidate, audits
    fallback = candidates[-1]
    if create:
        fallback_audit = check_dir(fallback, create=True)
        audits[-1] = fallback_audit
    return fallback, audits


def fixture_rdrr_root() -> Path:
    fixture_path = resolve(DEFAULT_RDRR_FIXTURE)
    fixture = load_json(fixture_path) or {}
    raw = os.environ.get("DOE_GEMMA4_E2B_RDRR_ROOT") or fixture.get("artifactRoot")
    return resolve(raw or DEFAULT_RDRR_ROOT)


def snapshot_audit(path: Path) -> dict[str, Any]:
    safetensors = sorted(p.name for p in path.glob("*.safetensors")) if path.is_dir() else []
    tokenizers = sorted(
        p.name for p in path.glob("tokenizer*")
    ) if path.is_dir() else []
    return {
        "path": str(path),
        "exists": path.is_dir(),
        "configJson": (path / "config.json").is_file(),
        "safetensorsFiles": safetensors,
        "safetensorsCount": len(safetensors),
        "tokenizerFiles": tokenizers,
        "ready": (
            path.is_dir()
            and (path / "config.json").is_file()
            and len(safetensors) >= 1
            and len(tokenizers) >= 1
        ),
    }


def rdrr_audit(path: Path) -> dict[str, Any]:
    shards = sorted(p.name for p in path.glob("shard_*.bin")) if path.is_dir() else []
    manifest = path / "manifest.json"
    origin = path / "origin.json"
    tokenizer = path / "tokenizer.json"
    return {
        "path": str(path),
        "exists": path.is_dir(),
        "manifestJson": manifest.is_file(),
        "originJson": origin.is_file(),
        "tokenizerJson": tokenizer.is_file(),
        "shardCount": len(shards),
        "ready": (
            path.is_dir()
            and manifest.is_file()
            and origin.is_file()
            and tokenizer.is_file()
            and len(shards) > 0
        ),
    }


def shell_exports(env: dict[str, str]) -> list[str]:
    return [f"export {key}={value}" for key, value in env.items()]


def main() -> int:
    args = parse_args()

    models_root_candidates = [
        resolve(os.environ["DOE_MODELS_ROOT"])
        if os.environ.get("DOE_MODELS_ROOT") else None,
        Path(EXTERNAL_MODELS_ROOT),
        Path(DEFAULT_MODELS_ROOT),
        Path.home() / ".cache/doe/models",
    ]
    candidates = [p for p in models_root_candidates if p is not None]
    models_root, model_root_audits = first_usable_root(candidates, args.create)

    hf_home = resolve(os.environ.get("HF_HOME") or DEFAULT_HF_HOME)
    hub_cache = resolve(
        os.environ.get("HUGGINGFACE_HUB_CACHE")
        or os.environ.get("HF_HUB_CACHE")
        or (hf_home / "hub")
    )
    raw_snapshot = resolve(
        os.environ.get("DOE_GEMMA4_E2B_SAFETENSORS_DIR")
        or DEFAULT_RAW_SNAPSHOT
    )
    rdrr_root = fixture_rdrr_root()

    env = {
        "HF_HOME": str(hf_home),
        "HUGGINGFACE_HUB_CACHE": str(hub_cache),
        "HF_HUB_CACHE": str(hub_cache),
        "DOE_MODELS_ROOT": str(models_root),
        "DOE_GEMMA4_E2B_SAFETENSORS_DIR": str(raw_snapshot),
        "DOE_GEMMA4_E2B_RDRR_ROOT": str(rdrr_root),
    }

    hf_audit = check_dir(hf_home, args.create)
    hub_audit = check_dir(hub_cache, args.create)
    raw_audit = snapshot_audit(raw_snapshot)
    rdrr = rdrr_audit(rdrr_root)
    external_audit = check_dir(Path(EXTERNAL_MODELS_ROOT), create=False)

    blockers: list[str] = []
    if not hf_audit["writable"]:
        blockers.append("hf_home_not_writable")
    if not hub_audit["writable"]:
        blockers.append("huggingface_hub_cache_not_writable")
    if not raw_audit["ready"]:
        blockers.append("raw_bf16_snapshot_absent_or_incomplete")
    if not rdrr["ready"]:
        blockers.append("doppler_rdrr_artifact_absent_or_incomplete")

    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "artifactKind": "doe_gemma4_e2b_access_preflight",
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "canonicalArtifacts": {
            "rawBf16": {
                "modelId": RAW_BF16_MODEL_ID,
                "sourceUrl": RAW_BF16_MODEL_URL,
                "localSnapshot": str(raw_snapshot),
                "tokenizerSource": "same snapshot tokenizer.json/tokenizer_config.json",
                "activeUse": "manifest_shape_oracle_and_bf16_smoke_slices",
            },
            "dopplerRdrrQ4k": {
                "fixture": DEFAULT_RDRR_FIXTURE,
                "artifactRoot": str(rdrr_root),
                "quantization": "Q4_K_M",
                "activeUse": "Doppler RDRR structural probe and smoke-contract parity",
            },
        },
        "cachePlan": {
            "selectedModelsRoot": str(models_root),
            "hfHome": hf_audit,
            "huggingfaceHubCache": hub_audit,
            "modelsRootCandidates": model_root_audits,
            "externalModelsRoot": external_audit,
            "externalModelsRootNote": (
                f"{EXTERNAL_MODELS_ROOT} is optional. If it is not writable, "
                "use the exported home-cache paths above instead of pointing "
                "Hugging Face token/cache files at it."
            ),
        },
        "assetAudit": {
            "rawBf16Snapshot": raw_audit,
            "dopplerRdrrQ4k": rdrr,
        },
        "shellExports": shell_exports(env),
        "downloadCommands": [
            "hf auth login --token <token> --add-to-git-credential false",
            (
                "hf download "
                f"{RAW_BF16_MODEL_ID} --local-dir "
                "$DOE_GEMMA4_E2B_SAFETENSORS_DIR"
            ),
        ],
        "validationCommands": [
            (
                "python3 bench/tools/probe_gemma4_e2b_manifest_shape.py "
                "--source-dir $DOE_GEMMA4_E2B_SAFETENSORS_DIR"
            ),
            (
                "python3 bench/tools/run_gemma4_e2b_manifest_shape_execution.py "
                "--source-dir $DOE_GEMMA4_E2B_SAFETENSORS_DIR"
            ),
            (
                "python3 bench/tools/probe_doppler_rdrr_artifact.py "
                "--artifact-root $DOE_GEMMA4_E2B_RDRR_ROOT"
            ),
            (
                "python3 bench/tools/run_doppler_rdrr_q4k_parity.py "
                "--artifact-root $DOE_GEMMA4_E2B_RDRR_ROOT"
            ),
        ],
        "demoScope": {
            "firstRow": "Gemma 4 E2B slice proof",
            "secondRow": "Gemma 4 31B structural/blocked row",
            "notShownAsClaim": [
                "full E2B end-to-end execution until model receipt is positive",
                "31B execution until generated streaming receipts exist",
                "Cerebras performance until hardware_success and methodology exist",
            ],
        },
    }

    out_path = resolve(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {rel(out_path)}")

    if args.print_shell:
        for line in payload["shellExports"]:
            print(line)

    if args.require_assets and blockers:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
