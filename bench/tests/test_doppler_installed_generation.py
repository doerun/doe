"""Installation admission must reject checkout escape and altered archive bytes."""
from __future__ import annotations

import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / 'external-projects'
          / 'doppler-generation' / 'installed-generation.py')
SPEC = importlib.util.spec_from_file_location('installed_generation', SCRIPT)
assert SPEC is not None and SPEC.loader is not None
INSTALLATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLATION)


class TestInstalledGenerationAdmission(unittest.TestCase):
    def test_dependency_symlink_cannot_escape_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            consumer = root / 'consumer'
            (consumer / 'node_modules').mkdir(parents=True)
            checkout = root / 'checkout'
            checkout.mkdir()
            (consumer / 'node_modules/dependency').symlink_to(checkout)
            with self.assertRaisesRegex(ValueError, 'escapes consumer'):
                INSTALLATION.inventory(consumer)

    def test_archive_authenticates_the_installed_native_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / 'installed'
            package.mkdir()
            (package / 'native.so').write_bytes(b'wrong native bytes')
            archive = root / 'provider.tgz'
            with tarfile.open(archive, 'w:gz') as stream:
                member = tarfile.TarInfo('provider/native.so')
                content = b'exact retained native bytes'
                member.size = len(content)
                stream.addfile(member, io.BytesIO(content))
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                INSTALLATION.verify_archive_install(archive, package)
            (package / 'native.so').write_bytes(content)
            INSTALLATION.verify_archive_install(archive, package)


if __name__ == '__main__':
    unittest.main()
