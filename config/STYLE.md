# Doe JSON/config style guide

This guide is the JSON and configuration file style contract for `config/`.

## Core principles

- Schema-first. Every hand-authored config file should have a corresponding
  `.schema.json`; legacy and generated artifacts are documented separately.
- Strict validation. Most schemas use `"additionalProperties": false`. When a
  schema intentionally allows extension, say so explicitly in the schema and
  migration notes.
- Config is the source of truth for runtime behavior. No hidden defaults in
  code that override config values.
- Machine-readable. Config files are consumed by tooling, not just humans.

## File naming

- `kebab-case.json` for data files.
- `kebab-case.schema.json` for schemas (paired with data file).
- Domain-scoped prefixes: `backend-runtime-policy.json`,
  `numeric-stability-policy.json`.
- Variant suffixes for alternate profiles: `browser-claim-policy.release.json`,
  `claim-cycle.active.json`.
- Generated files go in `config/generated/`.

## Field naming

- `camelCase` for new JSON object keys.
- Existing `snake_case` fields are part of the on-disk contract in several
  registries and trace outputs; do not rename them without a migration.
- ID fields use `Id` suffix: `backendId`, `moduleId`, `policyId`,
  `workloadId`.
- Boolean fields use `is`/`has`/`requires` prefix when the bare noun is
  ambiguous: `isBlocking`, `requiresLean`. Bare booleans are fine when
  unambiguous: `blocking`, `shipped`, `applicable`.

```json
{
  "schemaVersion": 1,
  "backendId": "doe_metal",
  "policyId": "stable-token/lowest-index-among-max-v1",
  "isBlocking": true
}
```

## Identifier naming

- Workload and artifact identifiers: `snake_case`
  (`kernel_dispatch_stress`, `upload_aligned_4k`).
- Policy and route identifiers: `kebab-case` with `/` separators
  (`numeric-stability/prefer-stable-on-selected-token-disagreement-v1`).

## Schema conventions

- JSON Schema Draft 2020-12.
- Always include `$schema`, `title`, `type`, `additionalProperties`, and
  `required` at the top level.
- Lock `schemaVersion` with `"const"` constraint.
- Use `"enum"` for restricted string values.
- Nest object schemas with their own `additionalProperties` and `required`;
  default to `false` unless the contract intentionally allows extension.
- Use `"format": "date-time"` for ISO 8601 timestamps and `"format": "uri"`
  for repository references.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Backend runtime policy",
  "type": "object",
  "additionalProperties": false,
  "required": ["schemaVersion", "backends"],
  "properties": {
    "schemaVersion": { "type": "integer", "const": 1 },
    "backends": {
      "type": "array",
      "items": { "$ref": "#/$defs/Backend" }
    }
  }
}
```

## Versioning

Two versioning dimensions, never conflated:

- **Schema version** (`schemaVersion`): integer, locked in schema with
  `"const"`. Increments when the config structure changes.
- **Content version** (`registryVersion`, `catalogVersion`): stable
  human-readable identifier. It may be date-stamped, semantic, or a mixed
  release label such as `2026-03-29-execution-profiles-v1`.

```json
{
  "schemaVersion": 2,
  "registryVersion": "2026-03-28"
}
```

## Cross-references

- Reference other configs by **path** when the consumer resolves at load time:
  `"sourcePolicyPath": "config/backend-runtime-policy.json"`.
- Reference by **ID** when the consumer looks up in a registry:
  `"triggerPolicyId": "numeric-instability/selected-token-disagreement-v1"`.
- Do not embed the content of one config inside another. Reference and resolve.

## Hash and provenance

- Hash fields use `Hash` suffix: `quirkSetHash`, `selectionPolicyHash`,
  `traceHash`.
- Proof links carry `theorem`, `module`, `category`, and `artifactPath`.
- Source provenance fields: `sourceRepo`, `sourcePath`, `sourceCommit`,
  `observedAt`.

## Arrays and collections

- Array property names are plural: `backends`, `obligations`, `modules`.
- Items in arrays are objects with an `id` or `*Id` field for addressability.
- Order is significant only when documented (e.g. obligation evaluation order).

## Formatting

- 2-space indentation.
- Trailing newline.
- Keys sorted alphabetically within objects when generated; hand-authored files
  may use logical grouping.
- `json.dumps(value, indent=2, sort_keys=True) + "\n"` is the canonical
  serialization for emitted config artifacts.

## Migration

- Schema changes require a migration note in `config/migration-notes.md`.
- Bump `schemaVersion` in both the data file and the schema `"const"`.
- Update all consumers in the same change.

## Validation

- `config_validation.py` loads and validates configs against their schemas.
- CI runs schema validation as a blocking gate.
- Test coverage: `bench/tests/test_config_schemas.py` generates positive and
  negative cases per schema.
