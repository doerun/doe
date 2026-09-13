"""Share immutable identical output bytes without changing evidence paths."""
from __future__ import annotations

import os
from pathlib import Path

from bench.lib.hash_utils import file_sha256


def deduplicate_outputs(directory: Path) -> dict[str, int]:
    """Replace completed duplicate numerical outputs with verified hard links."""
    owners: dict[tuple[int, str], Path] = {}
    linked = shared = 0
    for path in sorted(directory.iterdir()):
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
