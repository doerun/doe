"""Share immutable identical output bytes without changing evidence paths."""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from bench.lib.hash_utils import file_sha256


def write_json(path: Path, value: Any) -> None:
    """Keep the previous receipt intact when replacement cannot complete."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ProcessOutputRetention:
    """Own cohort retention outside each child, including failed executions."""

    def __init__(self, directory: Path, mode: str,
                 minimum_free_bytes: int | None) -> None:
        if mode not in ('none', 'hardlink-identical-outputs'):
            raise ValueError(f'Unsupported output retention: {mode}')
        if mode != 'none' and (minimum_free_bytes is None or minimum_free_bytes <= 0):
            raise ValueError('Output retention requires a positive configured free-space bound')
        if mode == 'none' and minimum_free_bytes is not None:
            raise ValueError('Free-space admission requires declared output retention')
        self.directory = directory
        self.mode = mode
        self.minimum_free_bytes = minimum_free_bytes
        self.totals = {'filesLinked': 0, 'duplicateLogicalBytes': 0}
        self.owners: dict[tuple[int, str], Path] = {}
        self.processes: set[Path] = set()

    @contextlib.contextmanager
    def process(self, output: Path) -> Iterator[None]:
        """Admit one child, then retain its exact output paths and bytes."""
        if self.mode == 'none':
            yield
            return
        if output.parent.resolve() != self.directory.resolve() or output in self.processes:
            raise ValueError('Retained child requires a fresh path in its cohort directory')
        available = shutil.disk_usage(self.directory).free
        if available < self.minimum_free_bytes:
            raise ValueError('Insufficient free space before application process: '
                             f'expected at least {self.minimum_free_bytes} bytes, observed {available}')
        self.processes.add(output)
        try:
            yield
        finally:
            paths = (path for path in self.directory.iterdir()
                     if path.name.startswith(output.name + '.'))
            observed = share_outputs(paths, self.owners)
            for key, value in observed.items():
                self.totals[key] += value
            write_json(self.directory / 'process-output-retention.json', {
                'schemaVersion': 1, 'kind': 'compute-program-output-retention',
                **self.totals,
            })


def deduplicate_outputs(directory: Path) -> dict[str, int]:
    """Replace completed duplicate numerical outputs with verified hard links."""
    return share_outputs(directory.iterdir(), {})


def share_outputs(paths: Iterable[Path], owners: dict[tuple[int, str], Path]) -> dict[str, int]:
    """Retain one representative per distinct output; verify it before sharing."""
    linked = shared = 0
    for path in sorted(paths):
        if path.suffix not in ('.f32', '.f64'):
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Expected a regular completed numerical output: {path}')
        key = (path.stat().st_size, file_sha256(path))
        owner = owners.setdefault(key, path)
        if path.samefile(owner):
            continue
        temporary = path.with_name(path.name + '.verified-link')
        try:
            os.link(owner, temporary)
            if file_sha256(temporary) != key[1] or file_sha256(path) != key[1]:
                raise ValueError(f'Numerical output changed during retention: {path}')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        linked += 1
        shared += key[0]
    return {'filesLinked': linked, 'duplicateLogicalBytes': shared}
