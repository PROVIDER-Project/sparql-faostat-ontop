"""Loader lifecycle tests; no Docker or real dataset required."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


LOADER = Path(__file__).resolve().parents[1] / 'loader' / 'load-duckdb.sh'


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'database with spaces.duckdb'
        self.marker = Path(str(self.database) + '.complete')
        self.sql = self.root / 'load.sql'
        self.sql.write_text('SELECT 1;\n')
        self.calls = self.root / 'calls'
        fake = self.root / 'duckdb'
        fake.write_text('''#!/bin/sh
printf '%s\\n' "$@" >> "$TEST_CALLS"
if [ "${TEST_WRITE_DB:-1}" = 1 ]; then
    printf 'database fixture\\n' > "$1"
fi
exit "${TEST_EXIT:-0}"
''')
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH'],
                        TEST_CALLS=str(self.calls))

    def run_loader(self, **env):
        return subprocess.run(['sh', str(LOADER), str(self.database), str(self.sql)],
                              env=dict(self.env, **env), capture_output=True, text=True)

    def test_success_then_skip_without_opening_duckdb(self):
        result = self.run_loader()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.is_file())
        self.assertEqual(self.calls.read_text().splitlines(),
                         [str(self.database), '-bail', '-f', str(self.sql)])
        calls = self.calls.read_text()
        self.assertEqual(self.run_loader(TEST_EXIT='1').returncode, 0)
        self.assertEqual(self.calls.read_text(), calls)

    def test_deleting_marker_requests_reload(self):
        self.assertEqual(self.run_loader().returncode, 0)
        self.marker.unlink()
        self.assertEqual(self.run_loader().returncode, 0)
        self.assertTrue(self.marker.is_file())
        self.assertEqual(len(self.calls.read_text().splitlines()), 8)

    def test_failure_leaves_no_marker_and_retries(self):
        result = self.run_loader(TEST_EXIT='7')
        self.assertEqual(result.returncode, 7)
        self.assertTrue(self.database.is_file())
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.run_loader().returncode, 0)
        self.assertTrue(self.marker.is_file())

    def test_stale_marker_and_missing_or_empty_database(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                if empty:
                    self.database.write_bytes(b'')
                elif self.database.exists():
                    self.database.unlink()
                self.marker.touch()
                self.assertEqual(self.run_loader(TEST_EXIT='7').returncode, 7)
                self.assertFalse(self.marker.exists())

    def test_success_without_database_is_not_marked_complete(self):
        self.assertEqual(self.run_loader(TEST_WRITE_DB='0').returncode, 1)
        self.assertFalse(self.marker.exists())


if __name__ == '__main__':
    unittest.main()
