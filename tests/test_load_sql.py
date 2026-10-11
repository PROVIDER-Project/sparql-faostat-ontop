"""Real DuckDB SQL checks using the existing JDBC jar; no Docker required.

Set DUCKDB_JDBC_JAR to override jdbc/duckdb_jdbc-1.5.6.0.jar.
"""
import csv
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JAR = Path(os.environ.get('DUCKDB_JDBC_JAR', ROOT / 'jdbc/duckdb_jdbc-1.5.6.0.jar'))


@unittest.skipUnless(JAR.is_file() and shutil.which('java') and shutil.which('javac'),
                     'Requires a JDK and the DuckDB JDBC jar (fetch service or DUCKDB_JDBC_JAR)')
class LoadSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = tempfile.TemporaryDirectory()
        subprocess.run(['javac', '-d', cls.classes.name, str(ROOT / 'tests/DuckDbScripts.java')], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.classes.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'fixture.duckdb'
        self.csv = self.root / 'fixture.csv'
        self.load = self.root / 'load.sql'
        self.load.write_text((ROOT / 'ontop/load.sql').read_text().replace(
            "'/data/FAOSTAT.csv.zst'", "'" + str(self.csv).replace("'", "''") + "'"))
        self.rows = [
            [2, "'004", 'Afghanistan', 221, "'01371", 'Almonds', 5312, 'Area harvested', 1961, 1961, 'ha', 0, 'A', ''],
            [2, "'004", 'Afghanistan', 221, "'01371", 'Almonds', 5312, 'Area harvested', 1962, 1962, 'ha', 1.5, '', 'note'],
            [3, "'008", 'Other', 222, "'01372", 'Other item', 5312, 'Area harvested', 1961, 1961, 't', '', 'B', ''],
            ['', '', '', 221, "'01371", 'Almonds', 5312, 'Area harvested', 1963, 1963, 'ha', 5, 'A', ''],
            [-2, "'009", 'Negative code', 221, "'01371", 'Almonds', 5312, 'Area harvested', 1961, 1961, 'ha', 7, 'A', ''],
        ]
        self.write_csv()

    def write_csv(self):
        with self.csv.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['Area Code', 'Area Code (M49)', 'Area', 'Item Code', 'Item Code (CPC)',
                             'Item', 'Element Code', 'Element', 'Year Code', 'Year', 'Unit', 'Value', 'Flag', 'Note'])
            writer.writerows(self.rows)

    def run_sql(self, *files):
        return subprocess.run(['java', '-cp', self.classes.name + os.pathsep + str(JAR),
                               'DuckDbScripts', str(self.database), *map(str, files)], capture_output=True, text=True)

    def assert_sql(self, sql):
        path = self.root / 'assert.sql'
        path.write_text(sql)
        result = self.run_sql(path)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_lookup_columns_code_lists_and_indexes(self):
        result = self.run_sql(self.load)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_sql("""
SELECT CASE WHEN count(*)=5 AND count(OBSERVATION_LOCAL_NAME)=3 THEN true ELSE error('row counts') END FROM faostat;
SELECT CASE WHEN OBS_VALUE_LEXICAL='0.0' AND UNIT='ha' AND NOTE IS NULL AND YEAR_LEXICAL='1961' THEN true ELSE error('terms') END FROM faostat WHERE OBSERVATION_LOCAL_NAME='2-221-5312-1961';
SELECT CASE WHEN count(*)=1 THEN true ELSE error('negative key') END FROM faostat WHERE OBSERVATION_LOCAL_NAME='~2D2-221-5312-1961';
SELECT CASE WHEN count(*)=3 THEN true ELSE error('area list') END FROM faostat_area;
SELECT CASE WHEN M49_CODE='004' THEN true ELSE error('M49') END FROM faostat_area WHERE AREA_CODE='2';
SELECT CASE WHEN CPC_CODE='01371' THEN true ELSE error('CPC') END FROM faostat_item WHERE ITEM_CODE='221';
SELECT CASE WHEN count(*)=2 THEN true ELSE error('null-valued row code list') END FROM faostat_flag;
SELECT CASE WHEN count(*)=10 AND sum(CAST(is_unique AS INTEGER))=2 THEN true ELSE error('indexes') END FROM duckdb_indexes() WHERE table_name='faostat';
""")
        # Running the SQL again replaces tables and indexes in the same transaction.
        self.assertEqual(self.run_sql(self.load).returncode, 0)

    def test_duplicate_fact_key_rolls_back(self):
        self.assertEqual(self.run_sql(self.load).returncode, 0)
        self.rows.append(list(self.rows[0]))
        self.write_csv()
        self.assertNotEqual(self.run_sql(self.load).returncode, 0)
        self.assert_sql("SELECT CASE WHEN count(*)=5 THEN true ELSE error('rollback') END FROM faostat;")

    def test_conflicting_code_list_label_rolls_back(self):
        self.assertEqual(self.run_sql(self.load).returncode, 0)
        self.rows[1][2] = 'Conflicting area name'
        self.write_csv()
        self.assertNotEqual(self.run_sql(self.load).returncode, 0)
        self.assert_sql("SELECT CASE WHEN AREA='Afghanistan' THEN true ELSE error('rollback') END FROM faostat_area WHERE AREA_CODE='2';")


if __name__ == '__main__':
    unittest.main()
