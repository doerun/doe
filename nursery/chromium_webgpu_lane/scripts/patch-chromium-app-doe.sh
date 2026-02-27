#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/patch-chromium-app-doe.sh --app PATH [--doe-lib PATH] [--app-name NAME] [--app-icon PATH] [--force]

Patches a Chromium.app bundle so direct launch defaults to:
  --use-webgpu-runtime=doe
  --doe-webgpu-library-path=<resolved lib>

The script renames the original binary to `Chromium-real` and installs
an executable wrapper at `Contents/MacOS/Chromium`.

It also updates bundle metadata so the app displays as `Fawn` by default and,
optionally, replaces the dock icon from a provided .icns file.
EOF
}

fawn_default_doe_lib() {
  local ext="dylib"
  printf "%s\n" \
    "${FAWN_REPO_ROOT:-${REPO_ROOT}}/zig/zig-out/lib/libdoe_webgpu.${ext}" \
    "${REPO_ROOT}/zig/zig-out/lib/libdoe_webgpu.so" \
    "${REPO_ROOT}/zig/zig-out/lib/libdoe_webgpu.dylib" \
    "${REPO_ROOT}/zig/zig-out/lib/libdoe_webgpu.dll"
}

fawn_default_doe_icon() {
  local app_bundle_dir="${FAWN_REPO_ROOT:-${REPO_ROOT}}/zig/zig-out/app"
  printf "%s\n" \
    "${app_bundle_dir}/Doe Runtime.app/Contents/Resources/DoeRuntime.icns" \
    "${app_bundle_dir}/DoeRuntime.app/Contents/Resources/DoeRuntime.icns" \
    "${app_bundle_dir}/DoeRuntime.app/Contents/Resources/app.icns" \
    "${app_bundle_dir}/DoeRuntime.icns"
}

APP_PATH=""
DOE_LIB="${FAWN_DOE_LIB:-}"
APP_NAME="${FAWN_APP_NAME:-Fawn}"
APP_ICON=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --app" >&2
        exit 2
      fi
      APP_PATH="$2"
      shift 2
      ;;
    --doe-lib)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --doe-lib" >&2
        exit 2
      fi
      DOE_LIB="$2"
      shift 2
      ;;
    --app-name)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --app-name" >&2
        exit 2
      fi
      APP_NAME="$2"
      shift 2
      ;;
    --app-icon)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --app-icon" >&2
        exit 2
      fi
      APP_ICON="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --help|-h)
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

if [[ -z "${APP_PATH}" ]]; then
  echo "--app is required" >&2
  usage
  exit 2
fi

if [[ ! -d "${APP_PATH}" ]]; then
  echo "missing app bundle: ${APP_PATH}" >&2
  exit 1
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Mac-only operation (darwin only)" >&2
  exit 1
fi

if [[ -z "${DOE_LIB}" ]]; then
  while IFS= read -r candidate; do
    if [[ -f "${candidate}" ]]; then
      DOE_LIB="${candidate}"
      break
    fi
  done < <(fawn_default_doe_lib)
fi

if [[ -z "${DOE_LIB}" || ! -f "${DOE_LIB}" ]]; then
  echo "missing libdoe_webgpu path; set --doe-lib or FAWN_DOE_LIB" >&2
  exit 1
fi

MACOS_BIN="${APP_PATH}/Contents/MacOS/Chromium"
REAL_BIN="${MACOS_BIN}-real"
WRAPPER_MARKER="${MACOS_BIN}.fawn-doe-wrapped"

if [[ ! -x "${MACOS_BIN}" ]]; then
  echo "missing executable: ${MACOS_BIN}" >&2
  exit 1
fi

if [[ -f "${WRAPPER_MARKER}" && "${FORCE}" -eq 0 ]]; then
  echo "already wrapped: ${MACOS_BIN}"
fi

if [[ ! -f "${WRAPPER_MARKER}" || "${FORCE}" -eq 1 ]]; then
  if [[ -f "${REAL_BIN}" ]]; then
    if [[ "${FORCE}" -eq 0 ]]; then
      echo "wrapper target already exists: ${REAL_BIN}" >&2
      exit 1
    fi
    rm -f "${REAL_BIN}"
  fi

  mv "${MACOS_BIN}" "${REAL_BIN}"
  cat > "${MACOS_BIN}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
REAL_BINARY="\${SCRIPT_DIR}/Chromium-real"
DOE_LIB="${DOE_LIB}"

if [[ -n "\${FAWN_DOE_LIB:-}" ]]; then
  DOE_LIB="\${FAWN_DOE_LIB}"
fi

if [[ ! -x "\${REAL_BINARY}" ]]; then
  echo "missing real Chromium binary: \${REAL_BINARY}" >&2
  exit 1
fi

if [[ -z "\${DOE_LIB}" || ! -f "\${DOE_LIB}" ]]; then
  echo "missing libdoe_webgpu runtime: \${DOE_LIB}" >&2
  exit 1
fi

exec -a fawn-doe "\${REAL_BINARY}" \
  --use-webgpu-runtime=doe \
  --doe-webgpu-library-path="\${DOE_LIB}" \
  "\$@"
EOF
  chmod 0755 "${MACOS_BIN}"
  touch "${WRAPPER_MARKER}"
fi

INFO_PLIST="${APP_PATH}/Contents/Info.plist"
RESOURCES_DIR="${APP_PATH}/Contents/Resources"

if [[ -x "/usr/libexec/PlistBuddy" && -f "${INFO_PLIST}" ]]; then
  if [[ -n "${APP_NAME}" ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleName ${APP_NAME}" "${INFO_PLIST}" >/dev/null 2>&1 \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleName string ${APP_NAME}" "${INFO_PLIST}" >/dev/null 2>&1
    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName ${APP_NAME}" "${INFO_PLIST}" >/dev/null 2>&1 \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string ${APP_NAME}" "${INFO_PLIST}" >/dev/null 2>&1
    /usr/libexec/PlistBuddy -c "Set :CFBundleSpokenName ${APP_NAME}" "${INFO_PLIST}" >/dev/null 2>&1 \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleSpokenName string ${APP_NAME}" "${INFO_PLIST}" >/dev/null 2>&1
  fi
fi

if [[ -z "${APP_ICON}" ]]; then
  while IFS= read -r candidate; do
    if [[ -f "${candidate}" ]]; then
      APP_ICON="${candidate}"
      break
    fi
  done < <(fawn_default_doe_icon)
fi

if [[ -n "${APP_ICON}" && -f "${APP_ICON}" ]]; then
  if [[ -d "${RESOURCES_DIR}" ]]; then
    cp -f "${APP_ICON}" "${RESOURCES_DIR}/app.icns"
    if [[ -x "/usr/libexec/PlistBuddy" ]]; then
      /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "${INFO_PLIST}" >/dev/null 2>&1 || true
      /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile app.icns" "${INFO_PLIST}" >/dev/null 2>&1 \
        || /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string app.icns" "${INFO_PLIST}" >/dev/null 2>&1
    fi
  else
    echo "missing resources dir: ${RESOURCES_DIR}" >&2
  fi
else
  if [[ -n "${APP_ICON}" && ! -f "${APP_ICON}" ]]; then
    echo "warning: provided app icon not found: ${APP_ICON}" >&2
  fi
fi

echo "patched app bundle: ${APP_PATH}"
echo "runtime default: --use-webgpu-runtime=doe --doe-webgpu-library-path=${DOE_LIB}"
if [[ -n "${APP_NAME}" ]]; then
  echo "app name: ${APP_NAME}"
fi
if [[ -f "${RESOURCES_DIR}/app.icns" ]]; then
  echo "app icon: ${APP_ICON:-auto-discovered}"
fi
