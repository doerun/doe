# ONNX Vulkan evaluation distribution

This directory distributes the exact qualified evaluation archive and companion
assets through the existing Git repository. Obtain the commit-pinned download
URLs from the [installation guide](../../../../docs/onnx-vulkan-installation.md).
No qualified binary was rebuilt or recompressed for publication.

[SHA256SUMS](SHA256SUMS) binds the archive, manifest, original installation
instructions, standalone guide, [operator handoff](OPERATOR.txt),
[release notes](RELEASE-NOTES.md), and retained producer evidence. Verify the
archive before extracting executable bootstrap scripts. A repository commit and
its digests bind this distribution; it is not a GitHub Releases API release or
GitHub-enforced release immutability.

The source and original qualification remain pinned to
`55c937e4605e04b9828ff8ba5ebc8ae572169452`. The original
[delivery record](../delivery.json) keeps its historical local archive path;
this additive directory provides public binary custody without changing the
original record, numerical thresholds, or rejected performance verdict.

## Operator acceptance

[OPERATOR.txt](OPERATOR.txt) uses only the downloaded archive for the existing
install, verify, qualify, and run commands. It requires another physical
Linux/AMD Vulkan machine, complete results including failures, host dependencies,
and an operator account of any assistance. The supplied qualification and example
records belong to the producer and cannot be submitted as independent execution.

Independent reproduction and adoption remain unestablished. A concrete application
owner must supply an unacceptable condition and frozen acceptance before further
engineering is selected. The source/application-provider.h and C++ example inside
the archive preserve existing ONNX operators and explicit ownership. No new
pooling, shader, backend, or browser campaign follows from distribution alone.

## Publication checks

Before publishing, require every SHA256SUMS entry, every original delivery hash,
and every archive member to match the retained manifest. After pushing, download
all distribution assets anonymously using the publication commit, verify their
checksums against this directory, and retain that download with its check output.
The complete archive must match the original delivery digest. Public availability
and byte integrity do not establish independent GPU reproduction or superiority.
