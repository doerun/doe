import { existsSync, readFileSync } from "node:fs";

const DEFAULT_KILL_SWITCH = "DOE_BROWSER_DISABLE_DOE_RUNTIME";
const TRUTHY_VALUES = new Set(["1", "true", "yes", "on"]);
const DEFAULT_PROFILE = Object.freeze({
  profileId: "",
  vendor: "unknown",
  api: "unknown",
  deviceFamily: "unknown",
  driver: "unknown",
});

function envFlagEnabled(env, name) {
  const value = env?.[name];
  if (typeof value !== "string") {
    return false;
  }
  return TRUTHY_VALUES.has(value.trim().toLowerCase());
}

export function loadRuntimeSelectorPolicy(path) {
  const payload = JSON.parse(readFileSync(path, "utf8"));
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`runtime selector policy must be an object: ${path}`);
  }
  return payload;
}

export function normalizeRuntimeProfile(profile = {}) {
  if (!profile || typeof profile !== "object" || Array.isArray(profile)) {
    return { ...DEFAULT_PROFILE };
  }
  return {
    profileId: typeof profile.profileId === "string" ? profile.profileId : DEFAULT_PROFILE.profileId,
    vendor: typeof profile.vendor === "string" && profile.vendor.length > 0 ? profile.vendor : DEFAULT_PROFILE.vendor,
    api: typeof profile.api === "string" && profile.api.length > 0 ? profile.api : DEFAULT_PROFILE.api,
    deviceFamily:
      typeof profile.deviceFamily === "string" && profile.deviceFamily.length > 0
        ? profile.deviceFamily
        : DEFAULT_PROFILE.deviceFamily,
    driver: typeof profile.driver === "string" && profile.driver.length > 0 ? profile.driver : DEFAULT_PROFILE.driver,
  };
}

function profileDenylisted(policy, profile) {
  if (!profile.profileId) {
    return false;
  }
  const rows = Array.isArray(policy?.denylist?.profiles) ? policy.denylist.profiles : [];
  return rows.some((row) => row && typeof row === "object" && row.profileId === profile.profileId);
}

export function resolveRuntimeSelection({ requestedMode, doeLibPath, policy, profile, env = process.env }) {
  const normalizedProfile = normalizeRuntimeProfile(profile);
  if (requestedMode === "dawn" || requestedMode === "doe") {
    return {
      selectionMode: requestedMode,
      selectedRuntime: requestedMode,
      forcedMode: requestedMode,
      fallbackApplied: false,
      fallbackReasonCode: "",
      hiddenFallbackAllowed: false,
      profile: normalizedProfile,
    };
  }

  if (requestedMode !== "auto") {
    throw new Error(`unsupported runtime selection mode: ${requestedMode}`);
  }

  const killSwitch = policy?.emergencyKillSwitch ?? {};
  const controlName =
    typeof killSwitch.controlName === "string" && killSwitch.controlName.length > 0
      ? killSwitch.controlName
      : DEFAULT_KILL_SWITCH;
  const killSwitchReason =
    typeof killSwitch.reasonCode === "string" && killSwitch.reasonCode.length > 0
      ? killSwitch.reasonCode
      : "global_disable_active";

  if (envFlagEnabled(env, controlName)) {
    return {
      selectionMode: "auto",
      selectedRuntime: "dawn",
      forcedMode: null,
      fallbackApplied: true,
      fallbackReasonCode: killSwitchReason,
      hiddenFallbackAllowed: false,
      profile: normalizedProfile,
    };
  }

  if (profileDenylisted(policy, normalizedProfile)) {
    return {
      selectionMode: "auto",
      selectedRuntime: "dawn",
      forcedMode: null,
      fallbackApplied: true,
      fallbackReasonCode: policy?.denylist?.reasonCode ?? "profile_denylisted",
      hiddenFallbackAllowed: false,
      profile: normalizedProfile,
    };
  }

  if (!doeLibPath || !existsSync(doeLibPath)) {
    return {
      selectionMode: "auto",
      selectedRuntime: "dawn",
      forcedMode: null,
      fallbackApplied: true,
      fallbackReasonCode: "runtime_artifact_missing",
      hiddenFallbackAllowed: false,
      profile: normalizedProfile,
    };
  }

  return {
    selectionMode: "auto",
    selectedRuntime: "doe",
    forcedMode: null,
    fallbackApplied: false,
    fallbackReasonCode: "",
    hiddenFallbackAllowed: false,
    profile: normalizedProfile,
  };
}
