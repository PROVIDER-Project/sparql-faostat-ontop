"""Check the endpoint's JDBC properties with the real driver; no Docker required."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ENDPOINT = Path(__file__).resolve().parents[1]
JAVA = shutil.which('java')
JAR = Path(os.environ.get('DUCKDB_JDBC_JAR',
                          ENDPOINT / 'target/artifacts/duckdb_jdbc.jar'))


class JdbcStreamingTests(unittest.TestCase):
    @unittest.skipUnless(JAVA and JAR.is_file(),
                         'Requires a JDK and DuckDB JDBC jar (DUCKDB_JDBC_JAR)')
    def test_unbounded_result_can_be_closed_after_ten_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [JAVA, '--class-path', str(JAR),
                 str(ENDPOINT / 'tests/TestJdbcStreaming.java'),
                 str(ENDPOINT / 'ontop/faostat.properties'),
                 str(Path(directory) / 'fixture.duckdb')],
                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
