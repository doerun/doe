# Fawn Licensing and Third-Party Usage

## Doe (this project)

Doe is an independent WebGPU implementation. No Dawn or wgpu source code is copied
into Doe runtime paths. Doe calls native graphics APIs (Metal, Vulkan, D3D12) directly.

## Dawn (BSD 3-Clause)

Dawn is vendored at `bench/vendor/dawn/` as a benchmark oracle and comparison baseline.
The BSD 3-Clause license (`bench/vendor/dawn/LICENSE`) governs all Dawn source in this tree.

### What BSD 3-Clause permits

1. **Mining Gerrit commit history** (`dawn-research/`): Public commit metadata on a
   public Gerrit instance are facts. Facts are not copyrightable. No license governs
   reading public API metadata.

2. **Vendoring Dawn as benchmark oracle** (`bench/vendor/dawn/`): Permitted. Attribution
   is satisfied by the vendored LICENSE file retained in the source tree.

3. **Building Doe as a competing implementation**: BSD 3-Clause places no restriction
   on competing implementations, studying public source code, or reimplementing APIs.
   There is no copyleft (GPL), no patent retaliation (Apache 2.0), and no non-compete
   clause.

4. **Calling Dawn via dawn_delegate/dawn_oracle**: Permitted as dynamic linking against
   a BSD-licensed library.

5. **Mining Dawn source for driver quirk patterns** (`agent/mine_upstream_quirks.py`):
   Extracting toggle names, vendor guard patterns, and workaround descriptions from
   BSD-licensed source is permitted. The miner reads Dawn source to identify behavioral
   patterns; no Dawn code is copied into Doe runtime paths.

### BSD 3-Clause obligations

1. **Retain copyright notice**: Done. `bench/vendor/dawn/LICENSE` is present and
   unmodified in the source tree.

2. **Reproduce notice in binary distributions**: If shipping a binary that includes
   Dawn code (e.g. the dawn_delegate benchmark binary), the BSD notice must appear
   in accompanying documentation.

3. **No endorsement**: Do not use "Dawn", "Tint", or "Google" names to endorse or
   promote Doe.

### What to watch

If any verbatim Dawn source code were copied into Doe runtime paths (`zig/src/`),
that code would carry the BSD 3-Clause attribution requirement. As of this writing,
no Dawn source has been copied -- Doe calls native APIs directly, and the
dawn_delegate paths link against Dawn as a separate binary.

## wgpu

wgpu is referenced as a baseline comparison target. No wgpu source is vendored or
linked. If wgpu source is vendored in the future, its license (MIT/Apache 2.0) must
be retained and the same attribution discipline applied.
