"""Compile and test an isolated changed policy through real build options."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
SCRATCH = HERE / "build-scratch"
PROBE = 'const policy = @import("src/backend/backend_policy.zig");\ncomptime { _ = policy; }\n'
STEP = '''    const policy_probe = b.addTest(.{ .root_module = b.createModule(.{
        .root_source_file = b.path("policy_probe.zig"), .target = target, .optimize = optimize,
        .imports = &.{.{ .name = "build_options", .module = build_options.createModule() }},
    }), .filters = &.{"backend runtime policy:"} });
    const run_policy_probe = b.addRunArtifact(policy_probe);
    b.step("policy-review-probe", "Isolated review probe").dependOn(&run_policy_probe.step);
'''


def main() -> None:
    policy = SCRATCH / "config/backend-runtime-policy.json"
    build = SCRATCH / "runtime/zig/build.zig"
    probe = SCRATCH / "runtime/zig/policy_probe.zig"
    assert not probe.exists()
    original_policy = policy.read_bytes()
    original_build = build.read_text()
    try:
        changed = json.loads(original_policy)
        changed["selectionPolicyHashSeed"] = 'policy-"quoted"\\newline\n'
        changed["lanes"]["vulkan_doe_app"]["deferredSubmissionSyncPolicy"] = "prefer_timeline_semaphore"
        policy.write_text(json.dumps(changed, indent=2) + "\n")
        (HERE / "changed-policy.json").write_bytes(policy.read_bytes())
        probe.write_text(PROBE)
        (HERE / "policy_probe.zig.txt").write_text(PROBE)
        marker = "    var proof_json:"
        assert original_build.count(marker) == 1
        build.write_text(original_build.replace(marker, STEP + marker))
        with (HERE / "changed-policy-probe.log").open("w") as output:
            subprocess.run(
                ["/home/x/.local/bin/zig", "build", "policy-review-probe", "--summary", "all", "-j2"],
                cwd=SCRATCH / "runtime/zig", stdout=output, stderr=subprocess.STDOUT, check=True,
            )
    finally:
        policy.write_bytes(original_policy)
        build.write_text(original_build)
        probe.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
