#!/usr/bin/env python3
"""Generate Lean comparability contract code from config/comparability-obligations.json."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        default="config/comparability-obligations.json",
        help="Comparability obligation contract JSON path relative to repo root.",
    )
    parser.add_argument(
        "--out",
        default="lean/Fawn/Generated/ComparabilityContract.lean",
        help="Generated Lean output path relative to repo root.",
    )
    return parser.parse_args()


def snake_to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    if not parts:
        raise ValueError("empty name")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object in {path}")
    return payload


def validate_expr(expr: Any, facts: set[str], *, label: str) -> None:
    if not isinstance(expr, dict):
        raise ValueError(f"{label}: expression must be object")
    keys = set(expr)
    if keys == {"const"}:
        if not isinstance(expr["const"], bool):
            raise ValueError(f"{label}.const must be bool")
        return
    if keys == {"fact"}:
        fact = expr["fact"]
        if not isinstance(fact, str) or fact not in facts:
            raise ValueError(f"{label}.fact must reference known fact")
        return
    if keys == {"not"}:
        validate_expr(expr["not"], facts, label=f"{label}.not")
        return
    if keys in ({"allOf"}, {"anyOf"}):
        values = expr[next(iter(keys))]
        if not isinstance(values, list) or not values:
            raise ValueError(f"{label}: boolean list must be non-empty")
        for index, child in enumerate(values):
            validate_expr(child, facts, label=f"{label}[{index}]")
        return
    raise ValueError(f"{label}: unsupported expression shape")


def load_contract(path: Path) -> tuple[list[str], list[dict[str, Any]], str]:
    raw_bytes = path.read_bytes()
    payload = load_json_object(path)
    if payload.get("schemaVersion") != 2:
        raise ValueError(f"{path}: schemaVersion must be 2")

    raw_facts = payload.get("facts")
    if not isinstance(raw_facts, list) or not raw_facts:
        raise ValueError(f"{path}: facts must be non-empty list")
    facts: list[str] = []
    for index, raw_fact in enumerate(raw_facts):
        if not isinstance(raw_fact, str) or not raw_fact:
            raise ValueError(f"{path}: facts[{index}] must be non-empty string")
        facts.append(raw_fact)
    if len(facts) != len(set(facts)):
        raise ValueError(f"{path}: duplicate facts")
    fact_set = set(facts)

    raw_obligations = payload.get("obligations")
    if not isinstance(raw_obligations, list) or not raw_obligations:
        raise ValueError(f"{path}: obligations must be non-empty list")
    obligations: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw_obligation in enumerate(raw_obligations):
        label = f"{path}: obligations[{index}]"
        if not isinstance(raw_obligation, dict):
            raise ValueError(f"{label} must be object")
        obligation_id = raw_obligation.get("id")
        if not isinstance(obligation_id, str) or not obligation_id:
            raise ValueError(f"{label}.id must be non-empty string")
        if obligation_id in ids:
            raise ValueError(f"{label}.id duplicate: {obligation_id}")
        ids.add(obligation_id)
        if not isinstance(raw_obligation.get("blocking"), bool):
            raise ValueError(f"{label}.blocking must be bool")
        validate_expr(raw_obligation.get("applicableWhen"), fact_set, label=f"{label}.applicableWhen")
        validate_expr(raw_obligation.get("passesWhen"), fact_set, label=f"{label}.passesWhen")
        obligations.append(raw_obligation)

    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return facts, obligations, sha256


def lean_expr(expr: dict[str, Any]) -> str:
    keys = set(expr)
    if keys == {"const"}:
        return "true" if expr["const"] else "false"
    if keys == {"fact"}:
        return f"facts.{snake_to_camel(expr['fact'])}"
    if keys == {"not"}:
        return f"!({lean_expr(expr['not'])})"
    if keys == {"allOf"}:
        return " && ".join(f"({lean_expr(item)})" for item in expr["allOf"])
    if keys == {"anyOf"}:
        return " || ".join(f"({lean_expr(item)})" for item in expr["anyOf"])
    raise ValueError(f"unsupported expression: {expr}")


def emit_lean(facts: list[str], obligations: list[dict[str, Any]], sha256: str) -> str:
    lines: list[str] = []
    lines.append("import Fawn.Core.Model")
    lines.append("")
    lines.append(f'def comparabilityContractSha256 : String := "{sha256}"')
    lines.append("")
    lines.append("inductive ComparabilityObligationId where")
    for obligation in obligations:
        lines.append(f"  | {snake_to_camel(obligation['id'])}")
    lines.append("  deriving Repr, DecidableEq")
    lines.append("")
    lines.append("structure ComparabilityObligation where")
    lines.append("  id : ComparabilityObligationId")
    lines.append("  blocking : Bool")
    lines.append("  applicable : Bool")
    lines.append("  passes : Bool")
    lines.append("  deriving Repr, DecidableEq")
    lines.append("")
    lines.append("def isFailedBlocking (item : ComparabilityObligation) : Bool :=")
    lines.append("  item.blocking && item.applicable && !item.passes")
    lines.append("")
    lines.append("def failedBlockingObligations (items : List ComparabilityObligation) : List ComparabilityObligation :=")
    lines.append("  items.filter isFailedBlocking")
    lines.append("")
    lines.append("def comparableFromObligations (items : List ComparabilityObligation) : Bool :=")
    lines.append("  (failedBlockingObligations items).isEmpty")
    lines.append("")
    lines.append("structure ComparabilityFacts where")
    for fact in facts:
        lines.append(f"  {snake_to_camel(fact)} : Bool")
    lines.append("  deriving Repr, DecidableEq")
    lines.append("")
    lines.append("def obligationsFromFacts (facts : ComparabilityFacts) : List ComparabilityObligation :=")
    lines.append("  [")
    for index, obligation in enumerate(obligations):
        constructor = snake_to_camel(obligation["id"])
        separator = "" if index == len(obligations) - 1 else ","
        lines.append(f"    {{ id := .{constructor}")
        lines.append(f"      blocking := {'true' if obligation['blocking'] else 'false'}")
        lines.append(f"      applicable := {lean_expr(obligation['applicableWhen'])}")
        lines.append(f"      passes := {lean_expr(obligation['passesWhen'])} }}{separator}")
    lines.append("  ]")
    lines.append("")
    lines.append("def comparableFromFacts (facts : ComparabilityFacts) : Bool :=")
    lines.append("  comparableFromObligations (obligationsFromFacts facts)")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    contract_path = (root / args.contract).resolve()
    out_path = (root / args.out).resolve()

    facts, obligations, sha256 = load_contract(contract_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(emit_lean(facts, obligations, sha256), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
