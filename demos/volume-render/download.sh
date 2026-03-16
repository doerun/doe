#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/data"

# Try primary host, fall back to Utah mirror
PRIMARY="https://klacansky.com/open-scivis-datasets"
MIRROR="http://open-scivis-datasets.sci.utah.edu/open-scivis-datasets"

download_and_verify() {
  local file="$1"
  local path="$2"  # e.g. fuel/fuel_64x64x64_uint8.raw
  local expected_sha="$3"

  if [ -f "$file" ]; then
    echo "✓ $file (already present)"
    return
  fi

  echo "→ downloading $file"
  if ! curl -fL --progress-bar -o "$file" "$PRIMARY/$path" 2>/dev/null; then
    echo "  primary unreachable, trying mirror..."
    curl -fL --progress-bar -o "$file" "$MIRROR/$path"
  fi

  if [ -n "$expected_sha" ]; then
    local actual
    actual=$(shasum -a 512 "$file" | awk '{print $1}')
    if [ "$actual" != "$expected_sha" ]; then
      echo "✗ checksum mismatch for $file"
      rm "$file"
      exit 1
    fi
  fi
  echo "✓ $file"
}

download_and_verify \
  "fuel_64x64x64_uint8.raw" \
  "fuel/fuel_64x64x64_uint8.raw" \
  "77fdd7c657da1946bafc84e88c6b8a03ae104a79a5bdec3c7db9257480ef4bf72551a08d22fd237c8e387dd2571b575f1a1a11f5f32b1fa4d4ef385d9fe1d613"

download_and_verify \
  "silicium_98x34x34_uint8.raw" \
  "silicium/silicium_98x34x34_uint8.raw" \
  "8ef2b9a84eb94693596b57f3f21f5ea75c1c25654011e3aed39a27f5e4259ebbbd2486ff39bb32b551bb44f3fa25123e7128cfd3fc053134f0806e23bb24a819"

download_and_verify \
  "hydrogen_atom_128x128x128_uint8.raw" \
  "hydrogen_atom/hydrogen_atom_128x128x128_uint8.raw" \
  "bc80b55ffc983f41b3981433707b59f6c8b3f16cc9cd3ea18087cb9e734b702eb1ad0410f36f38881b2e2fa85617dc0858bb2d9fbd3188abb39af43ea84e3521"

# Larger datasets (no checksum yet — populated after first successful download)
download_and_verify "bonsai_256x256x256_uint8.raw"           "bonsai/bonsai_256x256x256_uint8.raw"                     ""
download_and_verify "engine_256x256x128_uint8.raw"           "engine/engine_256x256x128_uint8.raw"                     ""
download_and_verify "foot_256x256x256_uint8.raw"             "foot/foot_256x256x256_uint8.raw"                         ""
download_and_verify "marmoset_neurons_512x512x314_uint16.raw" "marmoset_neurons/marmoset_neurons_512x512x314_uint16.raw" ""

echo ""
echo "All datasets ready."
