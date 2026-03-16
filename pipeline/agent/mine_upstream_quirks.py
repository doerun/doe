#!/usr/bin/env python3
"""Deterministic upstream quirk mining for driver workarounds.

Toggle patterns captured:
  Toggle::Name              — any reference; toggleContext="reference"
  ->Default(Toggle::X, v)   — per-device default; toggleContext="default_on"/"default_off"
  ->ForceSet(Toggle::X, v)  — forced value; toggleContext="force_on"/"force_off"
  ->ForceEnable(Toggle::X)  — forced enabled; toggleContext="force_on"
  ->ForceDisable(Toggle::X) — forced disabled; toggleContext="force_off"

Non-toggle workaround patterns captured:
  Vendor-conditional limit overrides   — limits->field = ... inside vendor guard
  Vendor-conditional alignment assigns — alignment = N inside vendor guard
  Vendor-conditional feature guards    — EnableFeature/DisableFeature inside vendor guard

Vendor detection uses gpu_info::IsVendor() and IsVendorMesa()/IsVendorProprietary()
patterns from Dawn source. Detected vendor overrides the --vendor CLI flag for
workaround hits. Bug tracker references (crbug.com, anglebug.com) are extracted
from nearby comments when present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# --- Shared constants ---

DEFAULT_OBSERVED_AT = "1970-01-01T00:00:00Z"
DEFAULT_ALLOWED_SUFFIXES = {
    ".cc",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".mm",
    ".m",
    ".rs",
    ".zig",
}
HASH_SEED = "0" * 64


# --- Toggle mining patterns ---

TOGGLE_RE = re.compile(r"\bToggle::([A-Za-z0-9_]+)\b")
_BOOL_RE = r"(true|false|1|0)"
_TOGGLE_CAPTURE = r"Toggle::([A-Za-z0-9_]+)"
TOGGLE_DEFAULT_RE = re.compile(
    r"->Default\(\s*" + _TOGGLE_CAPTURE + r"\s*,\s*" + _BOOL_RE + r"\s*\)"
)
TOGGLE_FORCESET_RE = re.compile(
    r"->ForceSet\(\s*" + _TOGGLE_CAPTURE + r"\s*,\s*" + _BOOL_RE + r"\s*\)"
)
TOGGLE_FORCEENABLE_RE = re.compile(r"->ForceEnable\(\s*" + _TOGGLE_CAPTURE + r"\s*\)")
TOGGLE_FORCEDISABLE_RE = re.compile(r"->ForceDisable\(\s*" + _TOGGLE_CAPTURE + r"\s*\)")

TOGGLE_CONTEXT_REFERENCE = "reference"
TOGGLE_CONTEXT_DEFAULT_ON = "default_on"
TOGGLE_CONTEXT_DEFAULT_OFF = "default_off"
TOGGLE_CONTEXT_FORCE_ON = "force_on"
TOGGLE_CONTEXT_FORCE_OFF = "force_off"


# --- Non-toggle workaround mining patterns ---

VENDOR_CONTEXT_LOOKBACK = 20

VENDOR_GPU_INFO_RE = re.compile(r"gpu_info::Is(\w+)\s*\(")
VENDOR_IS_METHOD_RE = re.compile(r"\bIs(\w+?)(?:Mesa|Proprietary)\s*\(\s*\)")

VENDOR_NORMALIZE: dict[str, str] = {
    "intel": "intel",
    "intelgen9": "intel",
    "intelgen12lp": "intel",
    "intelgen12": "intel",
    "intelgen12p": "intel",
    "amd": "amd",
    "nvidia": "nvidia",
    "qualcomm": "qualcomm",
    "qualcommacpi": "qualcomm",
    "arm": "arm",
    "mali": "arm",
    "apple": "apple",
    "samsung": "samsung",
    "imgtec": "imgtec",
    "swiftshader": "google",
    "broadcom": "broadcom",
    "powervr": "imgtec",
}

LIMIT_OVERRIDE_RE = re.compile(r"limits->([\w.]+)\s*=")
ALIGNMENT_ASSIGN_RE = re.compile(
    r"(?:lignment|ALIGNMENT)\w*\s*=\s*(\d+)"
)
FEATURE_GUARD_RE = re.compile(
    r"(Enable|Disable)Feature\(\s*Feature::(\w+)\s*\)"
)
BUG_REF_RE = re.compile(r"(?:crbug\.com|anglebug\.com|b)/(\d+)")
BUG_REF_WINDOW = 5

WORKAROUND_CATEGORY_LIMIT = "limit_override"
WORKAROUND_CATEGORY_ALIGNMENT = "alignment"
WORKAROUND_CATEGORY_FEATURE_GUARD = "feature_guard"

CATEGORY_TO_SCOPE: dict[str, str] = {
    WORKAROUND_CATEGORY_LIMIT: "memory",
    WORKAROUND_CATEGORY_ALIGNMENT: "alignment",
    WORKAROUND_CATEGORY_FEATURE_GUARD: "driver_toggle",
}

# --- Toggle promotion table ---
# Maps Dawn toggle names (case-insensitive) to promoted action kind + scope + params.
# Toggles not in this table remain as action: toggle (informational/trace-only).
# Toggles in this table are automatically promoted to their real action at mine time
# when the toggle context indicates activation (default_on, force_on).

WEBGPU_BUFFER_COPY_ALIGNMENT = 256

TOGGLE_PROMOTIONS: dict[str, dict[str, Any]] = {
    "usetemporarybufferincompressedtexturetotexturecopy": {
        "scope": "alignment",
        "safetyClass": "high",
        "action": {
            "kind": "use_temporary_buffer",
            "params": {
                "bufferAlignmentBytes": WEBGPU_BUFFER_COPY_ALIGNMENT,
                "reason": "Vulkan spec gap: compressed tex-to-tex with non-block-aligned extents (crbug.com/dawn/42)",
            },
        },
    },
    "usetempbufferinsmallformattexturetotexturecopyfromgreatertolessmiplevel": {
        "scope": "alignment",
        "safetyClass": "high",
        "action": {
            "kind": "use_temporary_buffer",
            "params": {
                "bufferAlignmentBytes": WEBGPU_BUFFER_COPY_ALIGNMENT,
                "reason": "Intel Gen9/Gen11 D3D12 CopyTextureRegion bug for small-format mip copies (crbug.com/1161355)",
            },
        },
    },
    "d3d12usetempbufferindepthstenciltextureandbuffercopywithnonzerobufferoffset": {
        "scope": "alignment",
        "safetyClass": "high",
        "action": {
            "kind": "use_temporary_buffer",
            "params": {
                "bufferAlignmentBytes": WEBGPU_BUFFER_COPY_ALIGNMENT,
                "reason": "D3D12 depth-stencil copy restriction without programmable MSAA (crbug.com/dawn/727)",
            },
        },
    },
    "d3d12usetempbufferintexturetotexturecopybetweendifferentdimensions": {
        "scope": "alignment",
        "safetyClass": "high",
        "action": {
            "kind": "use_temporary_buffer",
            "params": {
                "bufferAlignmentBytes": WEBGPU_BUFFER_COPY_ALIGNMENT,
                "reason": "D3D12 cross-dimension texture copy not natively supported (crbug.com/dawn/1216)",
            },
        },
    },
    "metalrenderr8rg8unormsmallmiptotemptexture": {
        "scope": "layout",
        "safetyClass": "high",
        "action": {
            "kind": "use_temporary_render_texture",
            "params": {
                "minMipLevel": 2,
                "formats": ["r8unorm", "rg8unorm"],
                "reason": "Intel Metal: rendering to R8/RG8 unorm at mip >= 2 is broken (crbug.com/dawn/1071)",
            },
        },
    },
}

# Activation contexts that mean the toggle is enabled (not just referenced)
PROMOTION_ACTIVE_CONTEXTS = {
    TOGGLE_CONTEXT_DEFAULT_ON,
    TOGGLE_CONTEXT_FORCE_ON,
}


def lookup_toggle_promotion(toggle: str, toggle_context: str) -> dict[str, Any] | None:
    """Look up a toggle in the promotion table.

    Returns the promotion entry if the toggle is known AND the context indicates
    activation (default_on or force_on). Returns None for references, force_off,
    default_off, or unknown toggles.
    """
    if toggle_context not in PROMOTION_ACTIVE_CONTEXTS:
        return None
    key = re.sub(r"[^a-z0-9]", "", toggle.lower())
    return TOGGLE_PROMOTIONS.get(key)


# --- Data classes ---

@dataclass(frozen=True)
class ToggleHit:
    root: Path
    source_path: Path
    toggle: str
    line: int
    toggle_context: str = TOGGLE_CONTEXT_REFERENCE


@dataclass(frozen=True)
class WorkaroundHit:
    root: Path
    source_path: Path
    line: int
    category: str
    vendor: str
    detail: str
    bug_ref: str = ""


# --- CLI ---

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        action="append",
        default=[],
        help="Source root to scan recursively. May be repeated.",
    )
    parser.add_argument(
        "--source-repo",
        required=True,
        help="Upstream repo identifier stored in provenance (for example dawn/main).",
    )
    parser.add_argument(
        "--source-commit",
        required=True,
        help="Upstream source commit stored in provenance.",
    )
    parser.add_argument("--vendor", required=True, help="Quirk match.vendor value.")
    parser.add_argument(
        "--api",
        required=True,
        choices=["vulkan", "metal", "d3d12", "webgpu"],
        help="Quirk match.api value.",
    )
    parser.add_argument(
        "--device-family",
        default="",
        help="Optional quirk match.deviceFamily value.",
    )
    parser.add_argument(
        "--driver-range",
        default="",
        help="Optional quirk match.driverRange value.",
    )
    parser.add_argument(
        "--observed-at",
        default=DEFAULT_OBSERVED_AT,
        help=(
            "RFC3339 timestamp for provenance.observedAt. "
            "Default is deterministic for reproducible fixtures."
        ),
    )
    parser.add_argument(
        "--allow-suffix",
        action="append",
        default=[],
        help="Allowed file suffix (including dot). May be repeated.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for mined quirk JSON array (quirks.schema records).",
    )
    parser.add_argument(
        "--manifest-output",
        required=True,
        help="Output path for mining manifest JSON.",
    )
    parser.add_argument(
        "--toggle-only",
        action="store_true",
        default=False,
        help="Mine toggle patterns only, skip non-toggle workaround extraction.",
    )
    return parser.parse_args()


# --- Utility functions ---

def normalize_suffixes(raw: list[str]) -> set[str]:
    if raw:
        normalized: set[str] = set()
        for suffix in raw:
            token = suffix.strip()
            if not token:
                continue
            if not token.startswith("."):
                token = "." + token
            normalized.add(token.lower())
        if normalized:
            return normalized
    return set(DEFAULT_ALLOWED_SUFFIXES)


def rfc3339_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def short_path_hash(path_value: str) -> str:
    return hashlib.sha256(path_value.encode("utf-8")).hexdigest()[:10]


def iter_candidate_files(root: Path, allowed_suffixes: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in allowed_suffixes:
            continue
        files.append(path)
    files.sort(key=lambda item: str(item))
    return files


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_match_object(
    *,
    vendor: str,
    api: str,
    device_family: str,
    driver_range: str,
) -> dict[str, str]:
    result: dict[str, str] = {"vendor": vendor, "api": api}
    if device_family:
        result["deviceFamily"] = device_family
    if driver_range:
        result["driverRange"] = driver_range
    return result


def build_hash_chain(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    previous_hash = HASH_SEED
    for idx, candidate in enumerate(candidates):
        candidate_blob = canonical_json(candidate)
        row_hash = hashlib.sha256(
            (previous_hash + ":" + candidate_blob).encode("utf-8")
        ).hexdigest()
        rows.append(
            {
                "index": idx,
                "quirkId": str(candidate.get("quirkId", "")),
                "hash": row_hash,
                "previousHash": previous_hash,
            }
        )
        previous_hash = row_hash
    return {
        "algorithm": "sha256",
        "seedHash": HASH_SEED,
        "finalHash": previous_hash,
        "rowCount": len(rows),
        "rows": rows,
    }


# --- Toggle mining ---

def candidate_quirk_id(
    *,
    vendor: str,
    api: str,
    toggle: str,
    source_path: str,
) -> str:
    path_token = short_path_hash(source_path)
    return (
        "auto."
        + vendor.lower().replace(" ", "_")
        + "."
        + api.lower()
        + ".toggle."
        + toggle.lower()
        + "."
        + path_token
    )


def build_candidate(
    *,
    toggle: str,
    source_repo: str,
    source_path: str,
    source_commit: str,
    vendor: str,
    api: str,
    device_family: str,
    driver_range: str,
    observed_at: str,
    toggle_context: str = TOGGLE_CONTEXT_REFERENCE,
) -> dict[str, Any]:
    promotion = lookup_toggle_promotion(toggle, toggle_context)

    if promotion:
        scope = promotion["scope"]
        action = promotion["action"]
        safety_class = promotion.get("safetyClass", "moderate")
    else:
        scope = "driver_toggle"
        action = {"kind": "toggle", "params": {"toggle": toggle}}
        safety_class = "moderate"

    return {
        "schemaVersion": 2,
        "quirkId": candidate_quirk_id(
            vendor=vendor,
            api=api,
            toggle=toggle,
            source_path=source_path,
        ),
        "scope": scope,
        "match": build_match_object(
            vendor=vendor,
            api=api,
            device_family=device_family,
            driver_range=driver_range,
        ),
        "action": action,
        "safetyClass": safety_class,
        "verificationMode": "guard_only",
        "proofLevel": "guarded",
        "provenance": {
            "sourceRepo": source_repo,
            "sourcePath": source_path,
            "sourceCommit": source_commit,
            "observedAt": observed_at,
        },
    }


def _bool_token_to_context(bool_token: str, on_ctx: str, off_ctx: str) -> str:
    return on_ctx if bool_token.lower() in ("true", "1") else off_ctx


def extract_toggle_hits(
    *,
    root: Path,
    candidate_files: list[Path],
) -> list[ToggleHit]:
    hits: list[ToggleHit] = []
    seen: set[tuple[str, int]] = set()

    for path in candidate_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        context_spans: set[tuple[int, int]] = set()

        for m in TOGGLE_DEFAULT_RE.finditer(text):
            toggle, bool_token = m.group(1), m.group(2)
            ctx = _bool_token_to_context(bool_token, TOGGLE_CONTEXT_DEFAULT_ON, TOGGLE_CONTEXT_DEFAULT_OFF)
            line = text.count("\n", 0, m.start()) + 1
            key = (str(path), line)
            if key not in seen:
                seen.add(key)
                context_spans.add((m.start(), m.end()))
                hits.append(ToggleHit(root=root, source_path=path, toggle=toggle, line=line, toggle_context=ctx))

        for m in TOGGLE_FORCESET_RE.finditer(text):
            toggle, bool_token = m.group(1), m.group(2)
            ctx = _bool_token_to_context(bool_token, TOGGLE_CONTEXT_FORCE_ON, TOGGLE_CONTEXT_FORCE_OFF)
            line = text.count("\n", 0, m.start()) + 1
            key = (str(path), line)
            if key not in seen:
                seen.add(key)
                context_spans.add((m.start(), m.end()))
                hits.append(ToggleHit(root=root, source_path=path, toggle=toggle, line=line, toggle_context=ctx))

        for m in TOGGLE_FORCEENABLE_RE.finditer(text):
            toggle = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            key = (str(path), line)
            if key not in seen:
                seen.add(key)
                context_spans.add((m.start(), m.end()))
                hits.append(ToggleHit(root=root, source_path=path, toggle=toggle, line=line, toggle_context=TOGGLE_CONTEXT_FORCE_ON))

        for m in TOGGLE_FORCEDISABLE_RE.finditer(text):
            toggle = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            key = (str(path), line)
            if key not in seen:
                seen.add(key)
                context_spans.add((m.start(), m.end()))
                hits.append(ToggleHit(root=root, source_path=path, toggle=toggle, line=line, toggle_context=TOGGLE_CONTEXT_FORCE_OFF))

        for m in TOGGLE_RE.finditer(text):
            if any(start <= m.start() < end for start, end in context_spans):
                continue
            toggle = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            key = (str(path), line)
            if key not in seen:
                seen.add(key)
                hits.append(ToggleHit(root=root, source_path=path, toggle=toggle, line=line, toggle_context=TOGGLE_CONTEXT_REFERENCE))

    hits.sort(
        key=lambda item: (
            str(item.source_path),
            item.line,
            item.toggle.lower(),
        )
    )
    return hits


# --- Non-toggle workaround mining ---

def normalize_vendor(raw: str) -> str | None:
    """Normalize a vendor name fragment extracted from Dawn source code."""
    return VENDOR_NORMALIZE.get(raw.lower())


def detect_vendor_on_line(line: str) -> str | None:
    """Detect a vendor name from a single source line."""
    for m in VENDOR_GPU_INFO_RE.finditer(line):
        vendor = normalize_vendor(m.group(1))
        if vendor:
            return vendor
    for m in VENDOR_IS_METHOD_RE.finditer(line):
        vendor = normalize_vendor(m.group(1))
        if vendor:
            return vendor
    return None


def find_nearby_bug_ref(lines: list[str], center: int) -> str:
    """Search nearby lines for a bug tracker reference."""
    start = max(0, center - BUG_REF_WINDOW)
    end = min(len(lines), center + BUG_REF_WINDOW + 1)
    for i in range(start, end):
        m = BUG_REF_RE.search(lines[i])
        if m:
            return m.group(0)
    return ""


def build_vendor_context(lines: list[str]) -> list[str | None]:
    """For each line, find the most recent vendor detection within the lookback window.

    Returns a list parallel to `lines` where each entry is either a normalized
    vendor string or None (no vendor guard detected nearby).
    """
    context: list[str | None] = [None] * len(lines)
    last_vendor: str | None = None
    last_vendor_line: int = -(VENDOR_CONTEXT_LOOKBACK + 1)

    for i, line in enumerate(lines):
        detected = detect_vendor_on_line(line)
        if detected:
            last_vendor = detected
            last_vendor_line = i
        if last_vendor is not None and (i - last_vendor_line) <= VENDOR_CONTEXT_LOOKBACK:
            context[i] = last_vendor

    return context


def workaround_quirk_id(
    *,
    vendor: str,
    api: str,
    category: str,
    detail: str,
    source_path: str,
) -> str:
    path_token = short_path_hash(source_path)
    detail_token = re.sub(r"[^a-z0-9_]", "_", detail.lower())[:40]
    return (
        "auto."
        + vendor.lower().replace(" ", "_")
        + "."
        + api.lower()
        + "."
        + category
        + "."
        + detail_token
        + "."
        + path_token
    )


def build_workaround_candidate(
    *,
    hit: WorkaroundHit,
    source_repo: str,
    source_commit: str,
    api: str,
    observed_at: str,
) -> dict[str, Any]:
    try:
        source_path = str(hit.source_path.relative_to(hit.root))
    except ValueError:
        source_path = str(hit.source_path)

    scope = CATEGORY_TO_SCOPE.get(hit.category, "memory")
    return {
        "schemaVersion": 2,
        "quirkId": workaround_quirk_id(
            vendor=hit.vendor,
            api=api,
            category=hit.category,
            detail=hit.detail,
            source_path=source_path,
        ),
        "scope": scope,
        "match": build_match_object(
            vendor=hit.vendor,
            api=api,
            device_family="",
            driver_range="",
        ),
        "action": {"kind": "no_op"},
        "safetyClass": "moderate",
        "verificationMode": "guard_only",
        "proofLevel": "guarded",
        "provenance": {
            "sourceRepo": source_repo,
            "sourcePath": source_path,
            "sourceCommit": source_commit,
            "observedAt": observed_at,
        },
    }


def extract_workaround_hits(
    *,
    root: Path,
    candidate_files: list[Path],
    fallback_vendor: str,
) -> list[WorkaroundHit]:
    """Extract non-toggle workaround patterns from source files.

    Only emits hits when a vendor-conditional guard is detected within
    VENDOR_CONTEXT_LOOKBACK lines. This filters out general-purpose
    code that is not vendor-specific.
    """
    hits: list[WorkaroundHit] = []
    seen: set[tuple[str, int, str]] = set()

    for path in candidate_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        lines = text.splitlines()
        vendor_context = build_vendor_context(lines)

        for i, line in enumerate(lines):
            vendor = vendor_context[i]
            if vendor is None:
                continue

            # Limit override: limits->fieldName = ...
            m = LIMIT_OVERRIDE_RE.search(line)
            if m:
                key = (str(path), i + 1, WORKAROUND_CATEGORY_LIMIT)
                if key not in seen:
                    seen.add(key)
                    hits.append(WorkaroundHit(
                        root=root,
                        source_path=path,
                        line=i + 1,
                        category=WORKAROUND_CATEGORY_LIMIT,
                        vendor=vendor,
                        detail=m.group(1),
                        bug_ref=find_nearby_bug_ref(lines, i),
                    ))

            # Alignment assignment: ...alignment... = N
            m = ALIGNMENT_ASSIGN_RE.search(line)
            if m:
                key = (str(path), i + 1, WORKAROUND_CATEGORY_ALIGNMENT)
                if key not in seen:
                    seen.add(key)
                    hits.append(WorkaroundHit(
                        root=root,
                        source_path=path,
                        line=i + 1,
                        category=WORKAROUND_CATEGORY_ALIGNMENT,
                        vendor=vendor,
                        detail=f"align_{m.group(1)}",
                        bug_ref=find_nearby_bug_ref(lines, i),
                    ))

            # Feature enable/disable: EnableFeature(Feature::X) or DisableFeature(Feature::X)
            m = FEATURE_GUARD_RE.search(line)
            if m:
                key = (str(path), i + 1, WORKAROUND_CATEGORY_FEATURE_GUARD)
                if key not in seen:
                    seen.add(key)
                    action_verb = m.group(1).lower()
                    feature_name = m.group(2)
                    hits.append(WorkaroundHit(
                        root=root,
                        source_path=path,
                        line=i + 1,
                        category=WORKAROUND_CATEGORY_FEATURE_GUARD,
                        vendor=vendor,
                        detail=f"{action_verb}_{feature_name}",
                        bug_ref=find_nearby_bug_ref(lines, i),
                    ))

    hits.sort(key=lambda h: (str(h.source_path), h.line, h.category))
    return hits


# --- Main ---

def main() -> int:
    args = parse_args()
    if not args.source_root:
        print("FAIL: at least one --source-root is required")
        return 1

    roots: list[Path] = []
    for raw in args.source_root:
        root = Path(raw)
        if not root.exists() or not root.is_dir():
            print(f"FAIL: invalid --source-root (missing directory): {root}")
            return 1
        roots.append(root.resolve())
    roots.sort(key=lambda item: str(item))

    allowed_suffixes = normalize_suffixes(args.allow_suffix)

    # --- Toggle mining (always runs) ---
    all_toggle_hits: list[ToggleHit] = []
    all_workaround_hits: list[WorkaroundHit] = []
    scanned_files = 0
    for root in roots:
        files = iter_candidate_files(root, allowed_suffixes)
        scanned_files += len(files)
        all_toggle_hits.extend(
            extract_toggle_hits(root=root, candidate_files=files)
        )
        if not args.toggle_only:
            all_workaround_hits.extend(
                extract_workaround_hits(
                    root=root,
                    candidate_files=files,
                    fallback_vendor=args.vendor,
                )
            )

    # --- Build toggle candidates ---
    toggle_candidates: list[dict[str, Any]] = []
    toggle_hit_rows: list[dict[str, Any]] = []
    for hit in all_toggle_hits:
        try:
            source_path = str(hit.source_path.relative_to(hit.root))
        except ValueError:
            source_path = str(hit.source_path)
        toggle_candidates.append(
            build_candidate(
                toggle=hit.toggle,
                source_repo=args.source_repo,
                source_path=source_path,
                source_commit=args.source_commit,
                vendor=args.vendor,
                api=args.api,
                device_family=args.device_family,
                driver_range=args.driver_range,
                observed_at=args.observed_at,
                toggle_context=hit.toggle_context,
            )
        )
        toggle_hit_rows.append(
            {
                "toggle": hit.toggle,
                "sourcePath": source_path,
                "line": hit.line,
                "toggleContext": hit.toggle_context,
            }
        )

    # --- Build workaround candidates ---
    workaround_candidates: list[dict[str, Any]] = []
    workaround_hit_rows: list[dict[str, Any]] = []
    for hit in all_workaround_hits:
        try:
            source_path = str(hit.source_path.relative_to(hit.root))
        except ValueError:
            source_path = str(hit.source_path)
        workaround_candidates.append(
            build_workaround_candidate(
                hit=hit,
                source_repo=args.source_repo,
                source_commit=args.source_commit,
                api=args.api,
                observed_at=args.observed_at,
            )
        )
        workaround_hit_rows.append(
            {
                "category": hit.category,
                "vendor": hit.vendor,
                "detail": hit.detail,
                "sourcePath": source_path,
                "line": hit.line,
                "bugRef": hit.bug_ref,
            }
        )

    # --- Merge and sort all candidates ---
    candidates = toggle_candidates + workaround_candidates
    candidates.sort(
        key=lambda item: (
            str(item.get("quirkId", "")),
            str(item.get("provenance", {}).get("sourcePath", "")),
        )
    )
    toggle_hit_rows.sort(
        key=lambda item: (
            str(item.get("sourcePath", "")),
            int(item.get("line", 0)),
            str(item.get("toggle", "")).lower(),
        )
    )
    workaround_hit_rows.sort(
        key=lambda item: (
            str(item.get("sourcePath", "")),
            int(item.get("line", 0)),
            str(item.get("category", "")),
        )
    )

    toggle_context_counts: dict[str, int] = {}
    for hit in all_toggle_hits:
        toggle_context_counts[hit.toggle_context] = toggle_context_counts.get(hit.toggle_context, 0) + 1

    workaround_category_counts: dict[str, int] = {}
    for hit in all_workaround_hits:
        workaround_category_counts[hit.category] = workaround_category_counts.get(hit.category, 0) + 1

    promoted_count = sum(
        1 for c in toggle_candidates if c["action"]["kind"] != "toggle"
    )

    # --- Output ---
    write_json(Path(args.output), candidates)

    manifest_payload: dict[str, Any] = {
        "schemaVersion": 2,
        "generatedAtUtc": rfc3339_now(),
        "sourceRepo": args.source_repo,
        "sourceCommit": args.source_commit,
        "sourceRoots": [str(root) for root in roots],
        "vendor": args.vendor,
        "api": args.api,
        "deviceFamily": args.device_family,
        "driverRange": args.driver_range,
        "observedAt": args.observed_at,
        "allowedSuffixes": sorted(allowed_suffixes),
        "scannedFileCount": scanned_files,
        "toggleHitCount": len(toggle_hit_rows),
        "toggleContextCounts": toggle_context_counts,
        "promotedToggleCount": promoted_count,
        "workaroundHitCount": len(workaround_hit_rows),
        "workaroundCategoryCounts": workaround_category_counts,
        "candidateCount": len(candidates),
        "hashChain": build_hash_chain(candidates),
        "toggleHits": toggle_hit_rows,
        "workaroundHits": workaround_hit_rows,
        "candidateOutputPath": str(Path(args.output)),
    }
    write_json(Path(args.manifest_output), manifest_payload)

    print("PASS: mined upstream quirks")
    if promoted_count:
        print(f"  promoted toggles: {promoted_count}")
    print(f"  toggle candidates: {len(toggle_candidates)}")
    print(f"  workaround candidates: {len(workaround_candidates)}")
    print(f"  total candidates: {Path(args.output)} ({len(candidates)})")
    print(f"  manifest: {Path(args.manifest_output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
