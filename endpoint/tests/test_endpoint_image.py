"""Opt-in real endpoint checks; no host data mounts or container network access.

Build first, then set FAOSTAT_ENDPOINT_IMAGE to enable these tests.
"""
import json
import os
import shutil
import subprocess
import time
import unittest
from urllib.parse import urlencode

IMAGE = os.environ.get('FAOSTAT_ENDPOINT_IMAGE')


@unittest.skipUnless(IMAGE and shutil.which('docker'),
                     'Set FAOSTAT_ENDPOINT_IMAGE to test a built endpoint with Docker')
class EndpointImageTests(unittest.TestCase):
    @classmethod
    def docker(cls, *args):
        return subprocess.run(['docker', *args], capture_output=True, text=True,
                              check=True, timeout=180).stdout.strip()

    @classmethod
    def setUpClass(cls):
        cls.container = cls.docker('run', '-d', '--network', 'none', IMAGE)
        cls.addClassCleanup(subprocess.run, ['docker', 'rm', '-f', '-v', cls.container],
                            capture_output=True, check=False, timeout=30)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = json.loads(cls.docker('inspect', '--format', '{{json .State}}', cls.container))
            if state.get('Health', {}).get('Status') == 'healthy':
                return
            if not state['Running']:
                break
            time.sleep(2)
        raise RuntimeError('Endpoint did not become healthy: ' + cls.docker('logs', cls.container)[-12000:])

    def query(self, sparql):
        url = 'http://localhost:8080/sparql?' + urlencode({'query': sparql})
        response = self.docker('exec', self.container, 'wget', '-qO-',
                               '--header=Accept: application/sparql-results+json', url)
        return json.loads(response)['results']['bindings']

    def test_observation_count(self):
        rows = self.query('SELECT (COUNT(*) AS ?n) WHERE { ?o a <http://purl.org/linked-data/cube#Observation> }')
        self.assertEqual(int(rows[0]['n']['value']), 4114755)

    def test_country_link_count(self):
        rows = self.query('SELECT (COUNT(*) AS ?n) WHERE { ?area <https://example.org/faostat/vocab/hasCountry> ?country }')
        self.assertEqual(int(rows[0]['n']['value']), 1222)

    def test_fixed_observation_and_literal_types(self):
        rows = self.query('''SELECT ?value ?year ?unit ?flag WHERE {
          <https://example.org/faostat/observation/QCL/2-221-5312-1961>
            <http://purl.org/linked-data/sdmx/2009/measure#obsValue> ?value ;
            <http://purl.org/linked-data/sdmx/2009/dimension#refPeriod> ?year ;
            <http://purl.org/linked-data/sdmx/2009/attribute#unitMeasure> ?unit ;
            <https://example.org/faostat/vocab/flag> ?flag .
        }''')
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(float(row['value']['value']), 0.0)
        self.assertEqual(row['value']['datatype'], 'http://www.w3.org/2001/XMLSchema#double')
        self.assertEqual(row['year']['value'], '1961')
        self.assertEqual(row['year']['datatype'], 'http://www.w3.org/2001/XMLSchema#gYear')
        self.assertEqual(row['unit']['value'], 'https://example.org/faostat/unit/ha')
        self.assertEqual(row['flag']['value'], 'https://example.org/faostat/flag/A')

    def test_leading_zero_codes(self):
        rows = self.query('''SELECT ?m49 ?cpc WHERE {
          <https://example.org/faostat/area/2> <https://example.org/faostat/vocab/m49Code> ?m49 .
          <https://example.org/faostat/item/221> <https://example.org/faostat/vocab/cpcCode> ?cpc .
        }''')
        self.assertEqual(rows[0]['m49']['value'], '004')
        self.assertEqual(rows[0]['cpc']['value'], '01371')

    def test_self_contained_read_only_database(self):
        info = json.loads(self.docker('inspect', self.container))[0]
        self.assertEqual(info['HostConfig']['NetworkMode'], 'none')
        self.assertFalse(any(mount['Type'] == 'bind' for mount in info['Mounts']))
        self.assertEqual(info['Config']['User'], 'ontop')
        self.docker('exec', self.container, 'sh', '-c',
                    'test -r /data/faostat.duckdb && test ! -w /data/faostat.duckdb')
        labels = info['Config']['Labels']
        self.assertTrue(labels['org.aksw.faostat.artifact.version'])
        self.assertEqual(labels['org.aksw.faostat.artifact.checksum.algorithm'], 'SHA-1')
        for name in ('faostat.duckdb.zst.sha1', 'duckdb_jdbc.jar.sha1'):
            digest = self.docker('exec', self.container, 'cat', '/opt/ontop/input/' + name)
            self.assertRegex(digest, r'^[0-9a-fA-F]{40}$')


if __name__ == '__main__':
    unittest.main()
