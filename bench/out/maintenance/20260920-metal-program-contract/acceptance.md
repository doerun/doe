# Acceptance receipt

Toolchain: Zig 0.15.2, Linux x86_64. Base commit is retained in
[base-commit.txt](base-commit.txt). This receipt covers the source checkpoint;
it does not admit a release package or performance result.

| Command | Exit | Evidence and scope |
| --- | --- | --- |
| `zig build test test-core test-full test-wgsl doe-runtime -Doptimize=ReleaseFast --summary all` | 0 | [Final suites and executable build](acceptance-final.log), run in `runtime/zig`; includes format, import, layout, ABI, bridge and test-inventory gates. Per-suite counts remain in the log; the suites overlap and their sum is not unique coverage. |
| `zig build test -Doptimize=ReleaseFast -Dtest-filter='Metal repair proof' --summary all` | 0 | [Physical fixture selection](physical-fixtures.log), run in `runtime/zig`; every selected fixture skips on Linux. No physical acceptance. |
| `python3 bench/gates/schema_gate.py` | 0 | [Schema gate](schema.log). Existing serialized fields remain unchanged. |
| `python3 -m unittest bench.tests.test_doc_link_coverage` | 0 | [Documentation test](doc-links.log). |
| `ssh -o BatchMode=yes -o ConnectTimeout=5 mac.lan 'uname -s; command -v zig; xcrun --show-sdk-path'` | 255 | [Apple availability probe](physical-availability.log); connection timed out. Apple SDK and Metal execution remain unavailable. |

The review log binds the final source, contexts and these evidence bytes. Its
append-only history is checked against the retained base both before and after
the checkpoint commit. Earlier aggregate/core logs are intermediate receipts;
`acceptance-final.log` is the final host acceptance.

Completed host checks establish the exercised ownership and rejection behavior.
They do not validate Objective-C against an Apple SDK, execute shaders on Metal,
qualify the ordinary package path, establish GPU residency or measure performance.
