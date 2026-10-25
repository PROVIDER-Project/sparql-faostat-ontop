"""Compression integrity and failure handling; needs the zstd CLI, no Docker."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'loader/compress-duckdb.sh'
ZSTD = shutil.which('zstd')


@unittest.skipUnless(ZSTD, 'Requires zstd for real compression round-trip checks')
class CompressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / 'database with spaces.duckdb'
        self.output = self.root / 'database with spaces.duckdb.zst'
        self.partial = Path(str(self.output) + '.part')
        self.marker = Path(str(self.output) + '.completed')
        self.content = bytes(range(256)) * 4096 + bytes(1024 * 1024)
        self.input.write_bytes(self.content)

    def compress(self, env=None):
        return subprocess.run(['sh', str(SCRIPT), str(self.input), str(self.output), '6', '2'],
                              capture_output=True, text=True, env=env)

    def test_round_trip_then_skip_without_raw_database(self):
        raw_marker = Path(str(self.input) + '.complete')
        raw_marker.touch()
        self.output.write_bytes(b'old unmarked archive')
        result = self.compress()
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = subprocess.run([ZSTD, '-d', '--stdout', str(self.output)],
                                capture_output=True, check=True).stdout
        self.assertEqual(actual, self.content)
        self.assertFalse(self.input.exists())
        self.assertFalse(raw_marker.exists())
        self.assertTrue(self.marker.is_file())
        before = (self.output.stat().st_mtime_ns, self.marker.stat().st_mtime_ns)
        self.assertEqual(self.compress().returncode, 0)
        self.assertEqual(before, (self.output.stat().st_mtime_ns, self.marker.stat().st_mtime_ns))
        self.assertFalse(self.partial.exists())

    def test_missing_or_empty_database_is_rejected(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                self.input.unlink(missing_ok=True)
                if empty:
                    self.input.touch()
                self.marker.touch()
                self.assertNotEqual(self.compress().returncode, 0)
                self.assertFalse(self.marker.exists())
                self.assertFalse(self.output.exists())
                self.assertFalse(self.partial.exists())

    def test_output_cannot_replace_input(self):
        result = subprocess.run(['sh', str(SCRIPT), str(self.input), str(self.input)],
                                capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.input.read_bytes(), self.content)

    def test_compression_and_validation_failures_preserve_existing_archive(self):
        fake = self.root / 'zstd'
        fake.write_text('''#!/bin/sh
if [ "$1" = "$FAIL_STAGE" ]; then exit 7; fi
exec "$REAL_ZSTD" "$@"
''')
        fake.chmod(0o755)
        for stage in ('--compress', '--test'):
            with self.subTest(stage=stage):
                self.output.write_bytes(b'previous archive')
                env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'],
                           REAL_ZSTD=ZSTD, FAIL_STAGE=stage)
                self.assertEqual(self.compress(env).returncode, 7)
                self.assertEqual(self.output.read_bytes(), b'previous archive')
                self.assertEqual(self.input.read_bytes(), self.content)
                self.assertFalse(self.marker.exists())
                self.assertFalse(self.partial.exists())


if __name__ == '__main__':
    unittest.main()
