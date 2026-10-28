import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

module_path = Path(__file__).resolve().parents[1] / 'scripts/build_windows.py'
spec = importlib.util.spec_from_file_location('radici_build', module_path)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class ReleaseSafetyTests(unittest.TestCase):
    def test_dependency_zip_cannot_escape_or_add_symlinks(self):
        with self.assertRaises(ValueError):
            build.safe_zip_name('safe\\leak')
        for name in ('../leak', '/absolute', 'C:/windows/file', 'safe/../../leak', 'folder./file'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with zipfile.ZipFile(root / 'dependency.zip', 'w') as archive:
                    info = zipfile.ZipInfo(name)
                    info.filename = name  # Preserve malicious separators on Windows too.
                    archive.writestr(info, b'payload')
                with self.assertRaises(ValueError):
                    build.extract_zip(root / 'dependency.zip', root / 'out')
                self.assertFalse((root / 'leak').exists())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            info = zipfile.ZipInfo('link')
            info.external_attr = 0o120777 << 16
            with zipfile.ZipFile(root / 'dependency.zip', 'w') as archive:
                archive.writestr(info, 'target')
            with self.assertRaises(ValueError):
                build.extract_zip(root / 'dependency.zip', root / 'out')

    def test_cached_dependency_tampering_is_rejected_without_a_download(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(build, 'DEPS', Path(directory)):
            (Path(directory) / 'library.whl').write_bytes(b'tampered')
            with patch.object(build.urllib.request, 'urlopen') as network:
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    build.fetch(dict(filename='library.whl', sha256='0' * 64, url='https://example.invalid/library.whl'))
                network.assert_not_called()

    def test_download_hash_failure_removes_partial_and_never_installs_it(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(build, 'DEPS', Path(directory)):
            with patch.object(build.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad data')):
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    build.fetch(dict(filename='library.whl', sha256='0' * 64, url='https://example.invalid/library.whl'))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_user_archives_and_credentials_cannot_enter_source_archive(self):
        for name in ('runtime/tree.json', 'Dati/tree.json', 'Foto/family.jpg', 'Backup/copy.zip', '.env', '.secrets/password.txt', 'tree.gramps', 'tree.db', 'identity.pfx'):
            self.assertFalse(build.source_allowed(name), name)
        self.assertTrue(build.source_allowed('app/engine.py'))
        self.assertTrue(build.source_allowed('app/fonts/CrimsonText-Regular.ttf'))

    def test_signed_release_requires_an_explicit_expected_certificate(self):
        with patch.dict(build.os.environ, {'SIGNPATH_CERT_THUMBPRINT': ''}), patch.object(build.subprocess, 'run') as process:
            with self.assertRaisesRegex(ValueError, 'expected production'):
                build.verify_signatures([Path('Radici.exe')])
            process.assert_not_called()
