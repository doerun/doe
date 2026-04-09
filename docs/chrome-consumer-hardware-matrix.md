# Chrome consumer hardware matrix

## Purpose

This document is an internal planning note for Chrome-based Doe validation on
consumer-grade hardware.

It is not a public product-support contract. It answers a narrower question:
what hardware mix gives the best practical coverage for Chrome on Linux, macOS,
and Windows across integrated and discrete GPU tiers.

This snapshot was written on 2026-04-08.

## Planning principles

- Test by `OS + Chrome/WebGPU backend + GPU/driver family + performance tier`.
- Do not let cloud availability distort the matrix. Integrated-GPU coverage is
  a first-class requirement for Chrome because many real consumer machines run
  Chrome on the low-power or integrated adapter by default.
- Treat Linux as a distinct engineering lane. Chrome/WebGPU support there is
  still a less stable surface than Windows or macOS and may require flags or
  extra driver validation.
- Use cloud where it buys repeatability. Use physical machines where cloud
  cannot realistically represent the target hardware.

## Recommended minimum matrix

This is the best first-pass matrix if the goal is broad, believable Chrome
coverage rather than maximizing raw GPU throughput.

| Lane | Host type | GPU class | Why it matters |
|------|-----------|-----------|----------------|
| macOS baseline | physical Mac mini or MacBook | Apple Silicon integrated GPU | Mainstream Chrome/macOS consumer path |
| Windows Intel baseline | physical laptop or mini PC | Intel integrated GPU | Common laptop path; useful for low-power and driver reality |
| Windows AMD baseline | physical laptop or mini PC | AMD integrated GPU | Common APU path with a different driver/backend stack |
| Windows high tier | physical desktop or laptop, or cloud | NVIDIA discrete GPU | Main high-end Windows consumer/perf lane |
| Linux baseline | physical mini PC or laptop | AMD integrated GPU | Best practical Linux consumer lane with fewer vendor-specific surprises |

If budget allows one more lane, add:

| Lane | Host type | GPU class | Why it matters |
|------|-----------|-----------|----------------|
| Linux high tier | physical desktop or cloud | NVIDIA discrete GPU | Important if Linux is a serious performance or support surface |

## Expanded matrix

If the goal is stronger coverage rather than the minimum credible set, use:

| Tier | macOS | Windows | Linux |
|------|-------|---------|-------|
| baseline | Apple Silicon integrated GPU | Intel integrated GPU, AMD integrated GPU | AMD integrated GPU |
| mid tier | Apple Silicon Pro-class GPU | NVIDIA `RTX 4060` / `4070` class | NVIDIA `RTX 4060` / `4070` class |
| high tier | Apple Silicon Max-class GPU if performance matters | higher-end NVIDIA desktop/laptop | higher-end NVIDIA desktop/laptop |

## Suggested hardware examples

These are examples, not hard requirements.

| Lane | Example hardware |
|------|------------------|
| macOS baseline | Mac mini `M2` or `M4` |
| macOS upper tier | Mac mini / MacBook Pro `M2 Pro`, `M3 Pro`, or `M4 Pro` |
| Windows Intel baseline | recent Intel laptop or mini PC with Iris Xe or Core Ultra integrated graphics |
| Windows AMD baseline | Ryzen APU system with `680M`, `780M`, or newer integrated graphics |
| Windows high tier | `RTX 4060` / `RTX 4070` laptop or desktop |
| Linux baseline | Ryzen APU mini PC or laptop on Ubuntu or Fedora |
| Linux high tier | `RTX 4060` / `RTX 4070` Linux desktop |

## What should be physical versus cloud

### Physical first

Prefer physical machines for:

- macOS consumer coverage
- Windows Intel integrated GPU coverage
- Windows AMD integrated GPU coverage
- Linux AMD integrated GPU coverage

These lanes are hard to represent well in public cloud and are exactly the
consumer surfaces most likely to expose real Chrome and driver behavior.

### Cloud where it helps

Use cloud for:

- Windows + NVIDIA repeatable automation
- Linux + NVIDIA repeatable automation
- burst capacity for reruns, smoke lanes, and benchmark reproduction

## Provider guidance

### Google Cloud Platform

GCP is useful for Windows and Linux NVIDIA lanes, not for the full consumer
matrix.

- Compute Engine is a Linux/Windows VM platform.
- Current Google Cloud GPU surfaces are NVIDIA-based.
- Windows Server images are documented as supporting several NVIDIA-backed GPU
  families, including `G2`, `G4`, and `N1+GPU`.

Recommended GCP use:

- one Windows Server 2022 NVIDIA lane
- one Linux NVIDIA lane
- optionally use `G2`/`L4` as the default modern Windows GPU lane
- use `N1 + T4` only if cost is the main driver

Avoid using GCP as the primary plan for:

- macOS
- Intel integrated GPU coverage
- AMD integrated GPU coverage

### macOS in cloud

If you do not want to own Macs, use EC2 Mac rather than trying to force macOS
onto GCP.

AWS EC2 Mac currently exposes both:

- `mac1.metal` for Intel Macs
- `mac2.metal` for Apple Silicon Macs

That makes EC2 Mac the practical cloud option for macOS-specific Chrome lanes.

## Chrome-specific implications

The matrix should reflect actual Chrome behavior, not just OS availability.

- Chrome/WebGPU is a first-class path on Windows and macOS.
- Chrome notes that on Windows laptops it often uses the same adapter Chrome is
  already using, which is generally the integrated GPU. That makes Windows
  integrated-GPU coverage mandatory, not optional.
- Chrome/Linux WebGPU remains a more conditional surface and may require
  explicit flags and driver validation.

## Recommended lane structure

Split execution into three levels.

### Smoke

Run everywhere.

- launch Chrome
- verify `navigator.gpu`
- capture `chrome://gpu`
- request adapter/device
- run one tiny render workload
- run one tiny compute workload

### Compatibility

Run on all baseline machines.

- run the real browser test suite
- capture adapter, backend, driver, and browser version metadata
- keep the suite short enough to rerun after driver or Chrome updates

### Performance

Run only on selected lanes.

- macOS baseline or upper tier
- Windows Intel integrated baseline
- Windows NVIDIA high tier
- Linux AMD baseline or Linux NVIDIA high tier

Do not make every machine a performance lane. Most of the matrix should answer
compatibility and regression questions, not benchmarking questions.

## Acquisition order

If starting from scratch, buy or provision in this order:

1. one Apple Silicon Mac
2. one Windows Intel integrated-GPU machine
3. one Windows AMD integrated-GPU machine
4. one Windows NVIDIA lane, physical or GCP
5. one Linux AMD integrated-GPU machine
6. one Linux NVIDIA lane if Linux performance matters

## Short recommendation

The best practical setup is:

- physical machines for integrated-GPU consumer coverage
- GCP only for repeatable NVIDIA Windows/Linux lanes
- one physical Mac first, with EC2 Mac only if elastic macOS capacity becomes
  necessary

This keeps the matrix aligned with actual consumer Chrome behavior instead of
optimizing for whichever hardware happens to be easiest to rent.

## Sources

- Chrome WebGPU overview:
  <https://developer.chrome.com/docs/web-platform/webgpu/overview>
- Chrome WebGPU troubleshooting:
  <https://developer.chrome.com/docs/web-platform/webgpu/troubleshooting-tips>
- Web.dev browser support summary:
  <https://web.dev/blog/webgpu-supported-major-browsers>
- Chrome headless GPU testing guidance:
  <https://developer.chrome.com/blog/supercharge-web-ai-testing>
- Google Cloud OS and GPU support details:
  <https://cloud.google.com/compute/docs/images/os-details>
- Google Cloud GPU documentation:
  <https://cloud.google.com/compute/docs/gpus>
- AWS EC2 Mac instances:
  <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-mac-instances.html>
