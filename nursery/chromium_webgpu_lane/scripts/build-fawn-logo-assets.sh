#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LANE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${LANE_DIR}/assets/logo/source/fawn-icon-main.svg"
LINUX_OUT="${LANE_DIR}/assets/logo/compiled/linux"
MACOS_OUT="${LANE_DIR}/assets/logo/compiled/macos"

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/build-fawn-logo-assets.sh [--source PATH] [--linux-out PATH] [--macos-out PATH]

Build compiled logo assets for the Chromium lane.

Defaults:
  --source    ${LANE_DIR}/assets/logo/source/fawn-icon-main.svg
  --linux-out ${LANE_DIR}/assets/logo/compiled/linux
  --macos-out ${LANE_DIR}/assets/logo/compiled/macos
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --source" >&2
        exit 2
      fi
      SOURCE="$2"
      shift 2
      ;;
    --linux-out)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --linux-out" >&2
        exit 2
      fi
      LINUX_OUT="$2"
      shift 2
      ;;
    --macos-out)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --macos-out" >&2
        exit 2
      fi
      MACOS_OUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ ! -f "${SOURCE}" ]]; then
  echo "missing source svg: ${SOURCE}" >&2
  exit 1
fi

mkdir -p "${LINUX_OUT}" "${MACOS_OUT}"

render_png_linux() {
  local source_path="$1"
  local out_path="$2"
  local size="$3"

  if [[ "$(uname -s)" == "Darwin" ]] && command -v sips >/dev/null 2>&1; then
    sips --setProperty format png "${source_path}" --out "${out_path}" --resampleHeightWidthMax "${size}" >/dev/null
    return
  fi

  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert --format=png --width="${size}" --height="${size}" "${source_path}" -o "${out_path}"
    return
  fi

  if command -v inkscape >/dev/null 2>&1; then
    inkscape "${source_path}" --export-type=png --export-filename="${out_path}" --export-width="${size}" --export-height="${size}" >/dev/null 2>&1
    return
  fi

  if command -v magick >/dev/null 2>&1; then
    magick "${source_path}" -resize "${size}x${size}" "${out_path}"
    return
  fi

  return 1
}

PNG_SIZES=(16 32 64 128 256 512)
for size in "${PNG_SIZES[@]}"; do
  out_file="${LINUX_OUT}/fawn-icon-main-${size}.png"
  if render_png_linux "${SOURCE}" "${out_file}" "${size}"; then
    echo "wrote ${out_file}"
  else
    echo "skipping linux png render for ${out_file}; no supported renderer found" >&2
    break
  fi
done

if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  iconset_dir="$(mktemp -d)/fawn.iconset"
  mkdir -p "${iconset_dir}"

  write_icon_png() {
    local src_size="$1"
    local dst_name="$2"
    local tmp_path="${iconset_dir}/.${dst_name}"
    sips --setProperty format png "${SOURCE}" --out "${tmp_path}" --resampleHeightWidthMax "${src_size}" >/dev/null
    mv "${tmp_path}" "${iconset_dir}/${dst_name}"
  }

  write_icon_png 16 icon_16x16.png
  write_icon_png 32 icon_16x16@2x.png
  write_icon_png 32 icon_32x32.png
  write_icon_png 64 icon_32x32@2x.png
  write_icon_png 64 icon_64x64.png
  write_icon_png 128 icon_64x64@2x.png
  write_icon_png 128 icon_128x128.png
  write_icon_png 256 icon_128x128@2x.png
  write_icon_png 256 icon_256x256.png
  write_icon_png 512 icon_256x256@2x.png
  write_icon_png 512 icon_512x512.png
  write_icon_png 1024 icon_512x512@2x.png

  iconutil -c icns "${iconset_dir}" -o "${MACOS_OUT}/fawn-icon-main.icns"
  rm -rf "${iconset_dir%/fawn.iconset}"
  echo "wrote ${MACOS_OUT}/fawn-icon-main.icns"
else
  echo "skipping macOS icns render; install sips/iconutil (macOS) or build manually"
fi

echo "logo asset build complete"
