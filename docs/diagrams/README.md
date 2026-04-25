# Doppler -> Doe -> Cerebras deck

This directory is the source text for a short external-facing slide deck.
The deck should read as a precise execution story, not a speculative design
brainstorm.

## One-sentence story

> Doppler gives Doe a raw JS + raw WGSL model contract; Doe preserves that
> contract through a Cerebras-specific lowering path so Gemma 4 31B evidence can
> be reproduced, extended, and checked by identity.

## Who is who

- **Doppler** is the source program owner. It supplies the Gemma program as raw
  JS orchestration, raw WGSL kernels, manifest identity, weight references,
  tokenizer/input contract, and reference transcripts.
- **Doe** is the lowering and evidence system. For normal GPU targets it lowers
  through Doe's existing WGSL/compiler surfaces toward WebGPU, Vulkan/SPIR-V,
  Metal/MSL, DXIL, and native runtimes. This deck only carves out Doe's
  Cerebras slice: TSIR where it applies, HostPlan, CSL artifacts, SDK runs, and
  receipts.
- **Cerebras** is the hardware validation surface. Cerebras-owned visuals use
  the Cerebras palette, not Doe purple/blue.

## Identity rule

Identity matters only at the evidence boundary:

1. Doppler source identity: manifest, execution graph, raw JS/WGSL digests,
   weights, tokenizer, and prompt contract.
2. Doe lowering identity: HostPlan, compile targets, emitted CSL, runner
   version, and execution transcript.
3. Receipt binding: WebGPU, simfabric, and hardware receipts are comparable only
   when they point back to the same Doppler contract.

That is why this is not "a hand-written CSL demo." The claim is same-program
portability.

## Slide contract

Every slide uses five strict sections:

- **Purpose** - why this slide exists.
- **Slide content** - exact visible content, not suggestions.
- **Visual spec** - required layout, colors, and reused icons.
- **Scope guard** - what the slide must not imply.
- **Evidence sources** - repo paths or bundle artifacts the slide cites.

Avoid tentative wording such as "might show" or "could be." The markdown is a
rendering contract for the eventual HTML/SVG deck.

## Future-facing assumption

The deck is allowed to be future-facing for the Cerebras conversation. It may
assume Gemma 4 31B evidence exists by presentation time: Doppler Program Bundle,
WebGPU reference, smoke-shape CSL receipts, bounded prefill/decode receipt, and
hardware receipt or typed blocker. Slide 16 must still distinguish evidence in
hand from evidence expected before send.

## Deck index

| # | Title | Job |
|---|---|---|
| 01 | Cover | State the preservation claim. |
| 02 | Problem | Explain why spatial compute needs exposed body shape. |
| 03 | Names and boundaries | Define Doppler, Doe, Cerebras, and the slice. |
| 04 | Execution surfaces | Establish WebGPU, Doe-CSL, and Cerebras hardware icons. |
| 05 | TSIR | Explain body preservation where TSIR applies. |
| 06 | HostPlan | Explain identity preservation across execution. |
| 07 | rms_norm | Simple body-preserving kernel walkthrough. |
| 08 | fused_gemv | Multi-axis reduction walkthrough. |
| 09 | kv_write | Stateful cache walkthrough. |
| 10 | attention_decode | Decode attention walkthrough. |
| 11 | JS to HostPlan | Show Doppler JS lowering into ordered launches. |
| 12 | HostPlan to PE programs | Show h2d, launch, d2h, and checkpoints. |
| 13 | Bundle | Show one contract feeding WebGPU, simfabric, hardware. |
| 14 | ONNX comparison | Contrast opaque op graphs with body-preserving lowering. |
| 15 | Limits | Say what the deck does not prove. |
| 16 | Evidence ledger | Pin claims to receipts. |
| 17 | Forward path | Show the remaining Cerebras validation path. |

## Visual rule

Doppler/Doe colors are red, blue, and purple. Cerebras hardware, PE grids,
fabric, SDK, and wafer visuals use Cerebras orange/charcoal. Identity hashes
use gold. ONNX/opaque-op contrast uses neutral gray, not Doppler red.
