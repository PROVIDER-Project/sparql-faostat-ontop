"""Exercise publishing orchestration with a fake Docker CLI; never touches a registry."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ENDPOINT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('make'), 'Requires GNU Make')
class MakefileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / 'calls.jsonl'
        self.docker = self.root / 'docker'
        self.docker.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
with open(os.environ['FAKE_DOCKER_LOG'], 'a') as stream:
    stream.write(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
if sys.argv[1] == 'build':
    sys.exit(int(os.environ.get('FAKE_BUILD_EXIT', '0')))
''')
        self.docker.chmod(0o755)

    def make(self, *args, build_exit='0'):
        return subprocess.run(['make', '--no-print-directory', '-f', str(ENDPOINT / 'Makefile'),
                               'DOCKER=' + str(self.docker), *args],
                              cwd=self.root, capture_output=True, text=True,
                              env=dict(os.environ, FAKE_DOCKER_LOG=str(self.log),
                                       FAKE_BUILD_EXIT=build_exit))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_default_is_help_and_does_not_call_docker(self):
        result = self.make()
        self.assertEqual(result.returncode, 0, result.stderr)
        for target in ['help', 'build', 'test', 'login', 'publish']:
            self.assertRegex(result.stdout, 'make ' + target + r'\s+#')
        self.assertFalse(self.log.exists())

    def test_failed_build_prevents_push(self):
        result = self.make('publish', build_exit='7')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([call['args'][0] for call in self.calls()], ['build'])

    def test_publish_uses_independent_versions_and_the_endpoint_context(self):
        image = 'ghcr.io/example/faostat:2.0.0'
        result = self.make('publish', 'VERSION=2.0.0', 'DATABASE_VERSION=1.0.0', 'IMAGE=' + image)
        self.assertEqual(result.returncode, 0, result.stderr)
        build, push = self.calls()
        self.assertEqual(build['cwd'], str(ENDPOINT))
        self.assertEqual(build['args'][:3], ['build', '--tag', image])
        self.assertIn('ENDPOINT_VERSION=2.0.0', build['args'])
        self.assertIn('FAOSTAT_VERSION=1.0.0', build['args'])
        self.assertEqual(push['args'], ['push', image])


if __name__ == '__main__':
    unittest.main()
