# Browser recovery parity contract

Status: `draft`

## Objective

Define Dawn-vs-Doe browser parity checks for crash, hang, device-loss,
validation-error, and recovery behavior. The artifact records parity outcomes
without allowing hidden fallback in forced-Doe mode.

## Input shape

The parity schema is
[`config/browser-recovery-parity.schema.json`](../../../config/browser-recovery-parity.schema.json).
Each artifact declares runtime selector identity, Dawn and Doe evidence paths,
case rows, and fallback policy.

## Output artifacts

The artifact kind is `browser_recovery_parity`. Artifacts remain diagnostic
until generated from paired Dawn and forced-Doe browser runs. The smoke builder
extracts validation-error capture, `device.lost` surface availability, and
post-diagnostic compute recovery from paired smoke output; crash and hang rows
remain diagnostic until a harness exercises those cases directly.

## Failure taxonomy

The structural checker reports:

- `hidden_fallback_allowed`
- `invalid_schema_version`
- `invalid_artifact_kind`
- `unsafe_artifact_path`
- `missing_case_kind`
- `parity_status_mismatch`
- `missing_reason_code`

## Fallback policy

Hidden fallback is never allowed. Diagnostic or mismatch parity rows must carry
a reason code.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Builder:
  `python3 browser/chromium/scripts/build-browser-recovery-parity.py --report <browser-smoke-both.json> --out <recovery-parity.json>`
- Smoke runner hook:
  `./browser/chromium/scripts/run-smoke.sh --mode both --recovery-parity-out <recovery-parity.json>`
- Structural check:
  `python3 browser/chromium/scripts/check-browser-recovery-parity.py --parity examples/browser-recovery-parity.sample.json`

## Promotion criteria

Promotion requires paired Dawn and forced-Doe artifacts covering crash, hang,
device-loss, validation-error, and recovery cases, plus strict hidden-fallback
checks for forced Doe.
