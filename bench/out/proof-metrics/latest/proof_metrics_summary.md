# Proof metrics summary

Promoted stable mirror of the current proof-backed shader evidence bundle.

- source bundle: `bench/out/scratch/20260409T000356Z/proof-metrics/`
- build flags: `-Dlean-verified=false` and `-Dlean-verified=true`
- note: compile and runtime deltas summarize the current proof-backed shader evidence pass over affine-loop, tiled, and flat-2D storage kernels

| Shader | Size | `min(...)` | `_doe_sizes` | `needs_sizes_buf` | Dispatch preconditions | Compile `p50` | Native Vulkan `p50/dispatch` | GPU timestamp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `affine_loop_storage` | `356 B -> 267 B` | `1 -> 0` | `true -> false` | `true -> false` | `0 -> 1` | `77,997 -> 56,967 ns` (`-27.0%`) | `31,666.7 -> 28,135.4 ns` (`-11.2%`) | `515.9 -> 507.5 ns` (`-1.6%`) |
| `tiled_storage` | `322 B -> 233 B` | `1 -> 0` | `true -> false` | `true -> false` | `0 -> 1` | `61,306 -> 46,959 ns` (`-23.4%`) | `28,000.6 -> 27,571.3 ns` (`-1.5%`) | `510.3 -> 502.3 ns` (`-1.6%`) |
| `flat_2d_storage` | `387 B -> 298 B` | `1 -> 0` | `true -> false` | `true -> false` | `0 -> 1` | `69,471 -> 51,657 ns` (`-25.6%`) | `28,465.2 -> 28,248.2 ns` (`-0.8%`) | `547.6 -> 531.4 ns` (`-3.0%`) |

Compile `p50` drops by about a quarter. Steady-state dispatch gets a smaller but measurable lift. GPU timestamps move only slightly.
