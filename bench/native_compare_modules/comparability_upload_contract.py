"""Upload contract helpers for compare_dawn_vs_doe comparability."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

def is_dawn_writebuffer_upload_workload(workload: Any) -> bool:
    if workload.domain != "upload":
        return False
    return (
        "BufferUploadPerf.Run/" in workload.dawn_filter
        and "WriteBuffer" in workload.dawn_filter
    )


def validate_upload_apples_to_apples(
    workload: Any,
    *,
    comparability_mode: str,
) -> None:
    if workload.left_upload_submit_every < 1:
        raise ValueError(
            f"invalid workload {workload.id}: leftUploadSubmitEvery must be >= 1"
        )
    if workload.right_upload_submit_every < 1:
        raise ValueError(
            f"invalid workload {workload.id}: rightUploadSubmitEvery must be >= 1"
        )
    if workload.left_command_repeat % workload.left_upload_submit_every != 0:
        raise ValueError(
            f"invalid workload {workload.id}: leftCommandRepeat ({workload.left_command_repeat}) "
            f"must be divisible by leftUploadSubmitEvery ({workload.left_upload_submit_every})"
        )
    if workload.right_command_repeat % workload.right_upload_submit_every != 0:
        raise ValueError(
            f"invalid workload {workload.id}: rightCommandRepeat ({workload.right_command_repeat}) "
            f"must be divisible by rightUploadSubmitEvery ({workload.right_upload_submit_every})"
        )

    if not is_dawn_writebuffer_upload_workload(workload):
        return

    if comparability_mode == "strict" and workload.left_upload_buffer_usage != "copy-dst":
        raise ValueError(
            "strict upload comparability requires leftUploadBufferUsage=copy-dst "
            f"for Dawn WriteBuffer workload {workload.id}; got {workload.left_upload_buffer_usage}"
        )


def find_fawn_runtime_index(command: list[str]) -> int | None:
    for idx, token in enumerate(command):
        if Path(token).name == "doe-zig-runtime":
            return idx
    return None


def subprocess_combined_output(proc: subprocess.CompletedProcess[str]) -> str:
    stdout = proc.stdout if isinstance(proc.stdout, str) else ""
    stderr = proc.stderr if isinstance(proc.stderr, str) else ""
    return f"{stdout}\n{stderr}".strip()


def assert_runtime_not_stale(
    runtime_binary: Path,
    *,
    runtime_source_paths: tuple[Path, ...],
) -> None:
    if not runtime_binary.exists():
        return
    runtime_mtime = runtime_binary.stat().st_mtime
    stale_sources = [
        str(path)
        for path in runtime_source_paths
        if path.exists() and path.stat().st_mtime > runtime_mtime
    ]
    if stale_sources:
        raise ValueError(
            "strict upload comparability requires a rebuilt doe-zig-runtime binary; "
            "binary appears older than runtime sources: "
            + ", ".join(stale_sources)
        )


def verify_fawn_upload_runtime_contract(
    *,
    template: str,
    workload: Any,
    command_for_fn: Callable[..., list[str]],
    runtime_source_paths: tuple[Path, ...],
) -> None:
    queue_wait_mode_value: str | None = None
    for idx, arg in enumerate(workload.extra_args):
        if arg != "--queue-wait-mode":
            continue
        if idx + 1 >= len(workload.extra_args):
            raise ValueError(
                f"invalid workload {workload.id}: --queue-wait-mode requires a value"
            )
        queue_wait_mode_value = str(workload.extra_args[idx + 1])
        if queue_wait_mode_value not in ("process-events", "wait-any"):
            raise ValueError(
                f"invalid workload {workload.id}: --queue-wait-mode must be process-events|wait-any"
            )

    preflight_trace_jsonl = Path("/tmp/fawn-upload-preflight.ndjson")
    preflight_trace_meta = Path("/tmp/fawn-upload-preflight.meta.json")
    preflight_extra_args = list(workload.extra_args)
    preflight_extra_args.extend(
        [
            "--upload-buffer-usage",
            workload.left_upload_buffer_usage,
            "--upload-submit-every",
            str(workload.left_upload_submit_every),
        ]
    )

    queue_sync_mode = "per-command"
    for i, arg in enumerate(workload.extra_args):
        if arg == "--queue-sync-mode" and i + 1 < len(workload.extra_args):
            queue_sync_mode = workload.extra_args[i + 1]

    command = command_for_fn(
        template,
        workload=workload,
        workload_id=workload.id,
        commands_path=workload.commands_path,
        trace_jsonl=preflight_trace_jsonl,
        trace_meta=preflight_trace_meta,
        queue_sync_mode=queue_sync_mode,
        upload_buffer_usage=workload.left_upload_buffer_usage,
        upload_submit_every=workload.left_upload_submit_every,
        extra_args=preflight_extra_args,
    )
    runtime_index = find_fawn_runtime_index(command)
    if runtime_index is None:
        return

    runtime_token = command[runtime_index]
    runtime_binary = Path(runtime_token)
    if not runtime_binary.is_absolute():
        runtime_binary = Path.cwd() / runtime_binary
    assert_runtime_not_stale(
        runtime_binary,
        runtime_source_paths=runtime_source_paths,
    )

    runtime_prefix = command[: runtime_index + 1]
    help_proc = subprocess.run(
        [*runtime_prefix, "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    help_output = subprocess_combined_output(help_proc)
    required_flags = ["--upload-buffer-usage", "--upload-submit-every"]
    if queue_wait_mode_value is not None:
        required_flags.append("--queue-wait-mode")
    missing_flags = [flag for flag in required_flags if flag not in help_output]
    if missing_flags:
        raise ValueError(
            "strict upload comparability requires runtime upload knobs to be supported by the "
            f"executed doe-zig-runtime binary; missing help flags: {', '.join(missing_flags)}"
        )

    capability_checks = [
        (
            ["--upload-buffer-usage", "invalid-value", "--help"],
            "invalid --upload-buffer-usage",
        ),
        (
            ["--upload-submit-every", "0", "--help"],
            "invalid --upload-submit-every",
        ),
    ]
    if queue_wait_mode_value is not None:
        capability_checks.append(
            (
                ["--queue-wait-mode", "invalid-value", "--help"],
                "invalid --queue-wait-mode",
            )
        )
    for probe_args, expected_fragment in capability_checks:
        probe_proc = subprocess.run(
            [*runtime_prefix, *probe_args],
            text=True,
            capture_output=True,
            check=False,
        )
        probe_output = subprocess_combined_output(probe_proc)
        if expected_fragment not in probe_output:
            raise ValueError(
                "strict upload comparability requires runtime validation of upload knobs; "
                f"missing expected probe output '{expected_fragment}' for command: "
                f"{' '.join([*runtime_prefix, *probe_args])}"
            )
