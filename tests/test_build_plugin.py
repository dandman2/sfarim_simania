"""Verify versioned packaging using temporary copies, never advancing the real version."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('plugin_builder', PROJECT / 'build_plugin.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / 'plugin with spaces'
        self.root.mkdir()
        shutil.copytree(PROJECT / 'src', self.root / 'src', ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('build_plugin.cmd', 'build_plugin.py'):
            shutil.copyfile(PROJECT / name, self.root / name)
        (self.root / 'version.txt').write_text('1.0\n')
        self.original_constants = (self.root / 'src' / 'plugin_constants.py').read_bytes()

    def tearDown(self):
        self.temporary.cleanup()

    def test_sequential_builds_and_internal_version(self):
        first = builder.build(self.root)
        self.assertEqual(first.name, 'sfarim_simania_v1.1.zip')
        with zipfile.ZipFile(first) as archive:
            constants = archive.read('plugin_constants.py')
            self.assertIn(b'PLUGIN_VER_MINOR = 1', constants)
            self.assertIn(b'PLUGIN_VER_BUILD = 0', constants)
            self.assertIn('__init__.py', archive.namelist())
            self.assertIn('simania_html.py', archive.namelist())
            self.assertNotIn('version.txt', archive.namelist())
            self.assertFalse(any('__pycache__' in p for p in archive.namelist()))
        second = builder.build(self.root)
        self.assertEqual(second.name, 'sfarim_simania_v1.2.zip')
        self.assertTrue(first.exists())
        self.assertEqual((self.root / 'version.txt').read_text().strip(), '1.2')

    def test_existing_archive_is_not_overwritten(self):
        output = self.root / 'sfarim_simania_v1.1.zip'
        output.write_bytes(b'previous build')
        with self.assertRaises(FileExistsError):
            builder.build(self.root)
        self.assertEqual(output.read_bytes(), b'previous build')
        self.assertEqual((self.root / 'version.txt').read_text().strip(), '1.0')

    def test_invalid_version_does_not_change_constants(self):
        (self.root / 'version.txt').write_text('invalid')
        with self.assertRaises(ValueError):
            builder.build(self.root)
        self.assertEqual((self.root / 'src' / 'plugin_constants.py').read_bytes(), self.original_constants)
        self.assertEqual(list(self.root.glob('*.zip')), [])

    def test_failed_version_commit_rolls_back(self):
        original_replace = os.replace
        failed = False
        def fail_version_once(source, target):
            nonlocal failed
            if Path(target) == self.root / 'version.txt' and not failed:
                failed = True
                raise OSError('Simulated version write failure')
            return original_replace(source, target)
        with patch.object(builder.os, 'replace', side_effect=fail_version_once):
            with self.assertRaises(OSError):
                builder.build(self.root)
        self.assertEqual((self.root / 'src' / 'plugin_constants.py').read_bytes(), self.original_constants)
        self.assertEqual((self.root / 'version.txt').read_text().strip(), '1.0')
        self.assertEqual(list(self.root.glob('*.zip')), [])

    def test_minor_is_an_integer_not_a_decimal(self):
        self.assertEqual(builder.next_version('1.9'), (1, 10))

    @unittest.skipUnless(os.name == 'nt', 'Windows CMD launcher')
    def test_cmd_from_another_working_directory(self):
        result = subprocess.run(['cmd.exe', '/d', '/c', 'call', str(self.root / 'build_plugin.cmd')],
                                cwd=self.temporary.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue((self.root / 'sfarim_simania_v1.1.zip').is_file())
        self.assertEqual((self.root / 'version.txt').read_text().strip(), '1.1')

    def test_second_builder_is_rejected(self):
        with builder.build_lock(self.root):
            with self.assertRaises(RuntimeError):
                builder.build(self.root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
