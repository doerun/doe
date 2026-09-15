# Zig review ledger

This is the persistent code-review log for owned Zig files. Component authority,
ownership decisions, and architectural exceptions remain in the applicable
`CATSCAN.md` chain and [`../source-layout.json`](../source-layout.json). Existing
module decisions and passing gates do not count as completed code reviews here.

## Review order

| Level | Review unit | Required examination before completion |
| --- | --- | --- |
| `file` | One Zig file | Read the whole file: responsibility, naming, data flow, ownership, errors, allocation, unsafe operations, tests, and relevant style rules. |
| `directory` | One directory | Review its direct files individually, then explain why they belong together, the public surface, placement, and missing or unnecessary files. |
| `within_directory` | Relationships inside one directory | Complete the directory review and child-directory relationship reviews; inspect duplicated decisions, imports, shared types, lifetime handoffs, and test/implementation boundaries together. |
| `cross_directory` | A named set of directories | Complete their internal reviews, then inspect dependency direction, competing authorities, contract conversions, resource transfers, and caller/callee assumptions across the boundary. |
| `system` | The complete owned Zig tree | Complete directory and cross-directory passes, then trace application/API paths through validation, preparation, execution, callbacks, cleanup, diagnostics, and errors. |

Directory passes repeat bottom-up through the hierarchy. A file checkmark never
completes a directory or relationship review. Passing every local review does
not establish an end-to-end runtime contract.

The queue derives file membership from tracked and non-ignored untracked Zig
files under `runtime/zig/`, excluding vendored sources and build outputs.
Production import edges come from the existing architecture analyzer. These
edges seed cross-directory tasks; reviewers must add other related directory
sets when shared semantics, callbacks, generated artifacts, or application flows
create a relationship that static imports do not reveal. Generated files are
reviewed with their generator and input contract, rather than edited by hand.

## Recorded evidence and history

[`log.json`](log.json) is append-only. Each entry names its level, targets,
reviewer, timestamp, source commit, exact input fingerprint, predecessor review,
prerequisite review IDs, findings, resolved findings, evidence, and next action.
The schema is [`../../../config/zig-review-log.schema.json`](../../../config/zig-review-log.schema.json).
Findings describe a concrete mechanism and affected symbol/path, not a score.
Resolved findings name the repair and its verification. Partial examination
stays `in_progress`; open findings stay `needs_changes`. `verified` requires
no open findings and retained verification evidence.

Append a new entry to continue or close a review; never overwrite the earlier
entry. `supersedes` points to the preceding entry for that same scope. A source
commit locates history; the input fingerprint also binds uncommitted source.
The queue computes current status independently of the recorded verdict:

- `pending`: no review exists for this scope.
- `in_progress` or `needs_changes`: the latest current review is unfinished.
- `stale`: source membership/content, applicable guidance, declared context, or
  evidence changed. A new file reopens containing directory and system reviews.
- `blocked`: a recorded completion lacks current completed prerequisite reviews.
- `verified`: the fingerprint, evidence, and every required lower-level review
  are current. This establishes review coverage, not correctness proof.
- `retired`: the reviewed scope no longer exists; its history remains readable.

Changes to style, this protocol, or applicable charters reopen affected reviews.
Architecture policy changes also reopen reviews; updates to the existing
`moduleDecisionReviews` metadata alone do not. Bind relevant contracts, consumer
files, generators, and test inputs outside the reviewed scope with `--context`.
No tool can infer every semantic dependency or prove that a person read a file.

## Commands

Run from the repository root:

```bash
python3 runtime/zig/tools/review_log.py --write
python3 runtime/zig/tools/review_log.py --check
python3 runtime/zig/tools/review_log.py --draft file --target build.zig \
  --reviewer codex --review-id build_file_001
```

`--write` regenerates [`queue.tsv`](queue.tsv) without changing the log.
`--check` validates the log, checks append-only history against `HEAD`, and
rejects a stale generated queue. Pending, stale, or blocked review coverage
remains visible; it does not block ordinary runtime development or release by
itself. Existing correctness and architecture gates retain their authority.
For committed-change or PR review, use `--base-ref` with the predecessor or PR
base; comparing only with `HEAD` cannot detect history rewritten in that commit.

`--draft` prints a current, unfinished record. Read the complete scope, add
specific findings and hash-bound evidence, then append the record to the log.
Use `--context` for each additional repository-relative input and `--evidence`
for each verification artifact. Drafting never grants review credit. Directory
targets are runtime-relative; the system target is `.`. Repeat `--target` for
a cross-directory review.

The version-1 TSV header is the generated view contract: level, targets, current
status, latest review, prerequisite scope keys, and next action. JSON owns review
history; TSV owns no policy and must not be hand-edited. Schema-version changes
require migration notes and corresponding consumer/test updates.
