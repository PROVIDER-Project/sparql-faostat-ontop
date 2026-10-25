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
if sys.argv[1] == 'run':
    sys.exit(int(os.environ.get('FAKE_RESOLVE_EXIT', '0')))
if sys.argv[1] == 'build':
    sys.exit(int(os.environ.get('FAKE_BUILD_EXIT', '0')))
''')
        self.docker.chmod(0o755)

    def make(self, *args, build_exit='0', resolve_exit='0'):
        return subprocess.run(['make', '--no-print-directory', '-f', str(ENDPOINT / 'Makefile'),
                               'DOCKER=' + str(self.docker),
                               'ARTIFACT_DIR=' + str(self.root / 'artifacts'), *args],
                              cwd=self.root, capture_output=True, text=True,
                              env=dict(os.environ, MAKEFLAGS='', MFLAGS='', MAKEOVERRIDES='', MAKELEVEL='0', M2_DIR=str(self.root / 'm2'), FAKE_DOCKER_LOG=str(self.log),
                                       FAKE_BUILD_EXIT=build_exit, FAKE_RESOLVE_EXIT=resolve_exit))

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
        self.assertEqual([call['args'][0] for call in self.calls()], ['run', 'build'])

    def test_failed_resolution_prevents_build_and_push(self):
        result = self.make('publish', resolve_exit='9')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([call['args'][0] for call in self.calls()], ['run'])

    def test_build_mounts_cache_writable_and_optional_settings_readonly(self):
        home = self.root / 'maven home'
        home.mkdir()
        settings = home / 'settings.xml'
        security = home / 'settings-security.xml'
        settings.write_text('<settings/>')
        security.write_text('<settingsSecurity/>')
        result = self.make('build', 'M2_DIR=' + str(home),
                           'M2_SETTINGS=' + str(settings), 'M2_SECURITY=' + str(security))
        self.assertEqual(result.returncode, 0, result.stderr)
        resolve, build = self.calls()
        args = resolve['args']
        self.assertIn(f'type=bind,src={home}/repository,dst=/maven-cache', args)
        self.assertIn(f'type=bind,src={settings},dst=/tmp/maven-home/.m2/settings.xml,readonly', args)
        self.assertIn(f'type=bind,src={security},dst=/tmp/maven-home/.m2/settings-security.xml,readonly', args)
        self.assertIn(f'{os.getuid()}:{os.getgid()}', args)
        self.assertTrue((home / 'repository').is_dir())
        self.assertFalse(any('settings' in arg or str(home) in arg for arg in build['args']))

    def test_local_database_repository_is_mounted_readonly(self):
        repository = self.root / 'database repository'
        repository.mkdir()
        result = self.make('resolve', 'DATABASE_REPOSITORY=' + str(repository))
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.calls()[0]['args']
        self.assertIn(f'type=bind,src={repository},dst=/database-repository,readonly', args)
        self.assertIn('FAOSTAT_LOCAL_REPOSITORY=true', args)

    def test_missing_or_disabled_database_repository_uses_remote_fallback(self):
        for repository in [str(self.root / 'not-deployed'), '']:
            with self.subTest(repository=repository):
                result = self.make('resolve', 'DATABASE_REPOSITORY=' + repository)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = self.calls()[-1]['args']
                self.assertFalse(any('dst=/database-repository' in arg for arg in args))
                self.assertNotIn('FAOSTAT_LOCAL_REPOSITORY=true', args)

    def test_env_file_and_command_line_override(self):
        config = self.root / 'build.env'
        config.write_text('M2_DIR=/datasets/from-file\nDATABASE_VERSION=1.2.3\n')
        result = self.make('show-config', 'ENV_FILE=' + str(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('/datasets/from-file', result.stdout)
        self.assertIn('1.2.3', result.stdout)
        result = self.make('show-config', 'ENV_FILE=' + str(config), 'M2_DIR=/datasets/from-cli')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('/datasets/from-cli', result.stdout)
        self.assertNotIn('/datasets/from-file', result.stdout)

    def test_missing_settings_are_optional_and_offline_is_forwarded(self):
        result = self.make('resolve', 'M2_SETTINGS=' + str(self.root / 'absent-settings'),
                           'M2_SECURITY=' + str(self.root / 'absent-security'), 'MAVEN_OFFLINE=true')
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.calls()[0]['args']
        self.assertFalse(any('dst=/tmp/maven-home/.m2/settings' in arg for arg in args))
        self.assertIn('MAVEN_OFFLINE=true', args)
        self.assertEqual(len(self.calls()), 1)

    def test_publish_uses_independent_versions_and_the_endpoint_context(self):
        image = 'ghcr.io/example/faostat:2.0.0'
        result = self.make('publish', 'VERSION=2.0.0', 'DATABASE_VERSION=1.0.0', 'IMAGE=' + image)
        self.assertEqual(result.returncode, 0, result.stderr)
        resolve, build, push = self.calls()
        self.assertEqual(resolve['args'][0], 'run')
        self.assertEqual(build['cwd'], str(ENDPOINT))
        self.assertEqual(build['args'][:3], ['build', '--tag', image])
        self.assertIn('ENDPOINT_VERSION=2.0.0', build['args'])
        self.assertIn('FAOSTAT_VERSION=1.0.0', build['args'])
        self.assertEqual(push['args'], ['push', image])


if __name__ == '__main__':
    unittest.main()
