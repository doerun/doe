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
const DEFAULT_ADAPTER_DENYLIST = Object.freeze({
  matched: false,
  reasonCode: "",
  profileId: "",
  vendor: "",
  api: "",
  deviceFamily: "",
  driverPattern: "",
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

function driverMatches(pattern, driver) {
  if (pattern === driver) {
    return true;
  }
  try {
    return new RegExp(pattern).test(driver);
  } catch {
    return false;
  }
}

function denylistRowMatchesProfile(row, profile) {
  if (!row || typeof row !== "object" || Array.isArray(row)) {
    return false;
  }
  if (typeof row.profileId !== "string" || row.profileId.length === 0) {
    return false;
  }
  if (profile.profileId && row.profileId === profile.profileId) {
    return true;
  }
  return (
    row.vendor === profile.vendor &&
    row.api === profile.api &&
    row.deviceFamily === profile.deviceFamily &&
    typeof row.driverPattern === "string" &&
    driverMatches(row.driverPattern, profile.driver)
  );
}

function adapterDenylistMatch(policy, profile) {
  if (!profile.profileId) {
    const hasAdapterFields =
      profile.vendor !== DEFAULT_PROFILE.vendor ||
      profile.api !== DEFAULT_PROFILE.api ||
      profile.deviceFamily !== DEFAULT_PROFILE.deviceFamily ||
      profile.driver !== DEFAULT_PROFILE.driver;
    if (!hasAdapterFields) {
      return { ...DEFAULT_ADAPTER_DENYLIST };
    }
  }
  const reasonCode =
    typeof policy?.denylist?.reasonCode === "string" && policy.denylist.reasonCode.length > 0
      ? policy.denylist.reasonCode
      : "profile_denylisted";
  const rows = Array.isArray(policy?.denylist?.profiles) ? policy.denylist.profiles : [];
  const row = rows.find((candidate) => denylistRowMatchesProfile(candidate, profile));
  if (!row) {
    return { ...DEFAULT_ADAPTER_DENYLIST };
  }
  return {
    matched: true,
    reasonCode,
    profileId: row.profileId,
    vendor: row.vendor,
    api: row.api,
    deviceFamily: row.deviceFamily,
    driverPattern: row.driverPattern,
  };
}

export function resolveRuntimeSelection({ requestedMode, doeLibPath, policy, profile, env = process.env }) {
  const normalizedProfile = normalizeRuntimeProfile(profile);
  const adapterDenylist = adapterDenylistMatch(policy, normalizedProfile);
  if (requestedMode === "dawn" || requestedMode === "doe") {
    return {
      selectionMode: requestedMode,
      selectedRuntime: requestedMode,
      forcedMode: requestedMode,
      fallbackApplied: false,
      fallbackReasonCode: "",
      hiddenFallbackAllowed: false,
      profile: normalizedProfile,
      adapterDenylist,
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
      adapterDenylist,
    };
  }

  if (adapterDenylist.matched) {
    return {
      selectionMode: "auto",
      selectedRuntime: "dawn",
      forcedMode: null,
      fallbackApplied: true,
      fallbackReasonCode: adapterDenylist.reasonCode,
      hiddenFallbackAllowed: false,
      profile: normalizedProfile,
      adapterDenylist,
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
      adapterDenylist,
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
    adapterDenylist,
  };
}
