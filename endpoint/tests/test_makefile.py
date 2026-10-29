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
if sys.argv[1:3] == ['manifest', 'inspect']:
    is_digest = '@sha256:' in sys.argv[-1]
    state = os.environ.get('FAKE_DIGEST_STATUS' if is_digest else 'FAKE_MANIFEST_STATUS', 'missing')
    if state == 'present':
        print('{}')
        sys.exit(0)
    message = os.environ.get('FAKE_DIGEST_ERROR' if is_digest else 'FAKE_MANIFEST_ERROR') or ('no such manifest: ' + sys.argv[-1])
    print(message, file=sys.stderr)
    sys.exit(1)
if sys.argv[1:3] == ['image', 'inspect']:
    print(os.environ.get('FAKE_REPO_DIGESTS', ''))
    sys.exit(int(os.environ.get('FAKE_IMAGE_INSPECT_EXIT', '0')))
if sys.argv[1] == 'run':
    sys.exit(int(os.environ.get('FAKE_RESOLVE_EXIT', '0')))
if sys.argv[1] == 'build':
    sys.exit(int(os.environ.get('FAKE_BUILD_EXIT', '0')))
''')
        self.docker.chmod(0o755)

    def make(self, *args, build_exit='0', resolve_exit='0',
             manifest_status='missing', manifest_error='', extra_env=None):
        environment = dict(os.environ)
        for name in ['VERSION', 'DATABASE_VERSION', 'DUCKDB_JDBC_VERSION']:
            environment.pop(name, None)
        environment.update(extra_env or {})
        return subprocess.run(['make', '--no-print-directory', '-f', str(ENDPOINT / 'Makefile'),
                               'DOCKER=' + str(self.docker),
                               'ARTIFACT_DIR=' + str(self.root / 'artifacts'), *args],
                              cwd=self.root, capture_output=True, text=True,
                              env=dict(environment, MAKEFLAGS='', MFLAGS='', MAKEOVERRIDES='', MAKELEVEL='0', M2_DIR=str(self.root / 'm2'), FAKE_DOCKER_LOG=str(self.log),
                                       FAKE_BUILD_EXIT=build_exit, FAKE_RESOLVE_EXIT=resolve_exit,
                                       FAKE_MANIFEST_STATUS=manifest_status,
                                       FAKE_MANIFEST_ERROR=manifest_error))

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
        self.assertEqual([call['args'][0] for call in self.calls()], ['manifest', 'run', 'build'])

    def test_failed_resolution_prevents_build_and_push(self):
        result = self.make('publish', resolve_exit='9')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([call['args'][0] for call in self.calls()], ['manifest', 'run'])

    def test_existing_remote_tag_blocks_before_build_and_explains_version_override(self):
        image = 'ghcr.io/example/existing:7.0.0'
        result = self.make('publish', 'IMAGE=' + image, manifest_status='present')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([call['args'] for call in self.calls()],
                         [['manifest', 'inspect', image]])
        self.assertIn('build.conf', result.stderr)
        self.assertIn('VERSION=NEW_VERSION', result.stderr)
        self.assertIn('IMAGE', result.stderr)

    def test_uncertain_registry_failures_never_build_or_push(self):
        for message in ['unauthorized: authentication required',
                        'denied: requested access to the resource is denied',
                        'dial tcp: i/o timeout',
                        'x509: certificate signed by unknown authority',
                        'docker: unknown command: manifest',
                        'repository not found or may require login']:
            with self.subTest(message=message):
                before = len(self.calls()) if self.log.exists() else 0
                result = self.make('publish', manifest_error=message)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([call['args'][0] for call in self.calls()[before:]],
                                 ['manifest'])
                self.assertIn('Could not establish', result.stderr)
                self.assertIn(message, result.stderr)

    def test_explicit_missing_manifest_errors_allow_publication(self):
        for message in ['no such manifest: ghcr.io/example/image:new',
                        'manifest unknown', 'manifest unknown: manifest unknown',
                        'registry error: MANIFEST_UNKNOWN: unknown tag']:
            with self.subTest(message=message):
                before = len(self.calls()) if self.log.exists() else 0
                result = self.make('publish', manifest_error=message)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([call['args'][0] for call in self.calls()[before:]],
                                 ['manifest', 'run', 'build', 'image', 'push'])

    def test_existing_manifest_digest_blocks_new_tag_after_build(self):
        digest = 'sha256:' + 'a' * 64
        image = 'ghcr.io/example/image:new'
        result = self.make('publish', 'IMAGE=' + image, extra_env={
            'FAKE_REPO_DIGESTS': 'other.registry/source@' + digest,
            'FAKE_DIGEST_STATUS': 'present'})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([call['args'][0] for call in self.calls()],
                         ['manifest', 'run', 'build', 'image', 'manifest'])
        self.assertEqual(self.calls()[-1]['args'],
                         ['manifest', 'inspect', 'ghcr.io/example/image@' + digest])
        self.assertIn('already present remotely', result.stderr)
        self.assertIn('nothing was pushed', result.stderr)

    def test_missing_digest_allows_push_and_preserves_registry_port(self):
        digest = 'sha256:' + 'b' * 64
        result = self.make('publish', 'IMAGE=registry.example:5000/team/image:new',
                           extra_env={'FAKE_REPO_DIGESTS': 'old.registry/image@' + digest})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call['args'][0] for call in self.calls()],
                         ['manifest', 'run', 'build', 'image', 'manifest', 'push'])
        self.assertEqual(self.calls()[-2]['args'],
                         ['manifest', 'inspect', 'registry.example:5000/team/image@' + digest])

    def test_unknown_digest_is_reported_and_not_replaced_with_image_id(self):
        result = self.make('publish')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No local manifest digest available', result.stdout)
        self.assertEqual(sum(call['args'][0] == 'manifest' for call in self.calls()), 1)
        self.assertEqual(self.calls()[-1]['args'][0], 'push')

    def test_digest_check_errors_prevent_push(self):
        digest = 'sha256:' + 'c' * 64
        for message in ['unauthorized: authentication required', 'dial tcp: i/o timeout']:
            with self.subTest(message=message):
                before = len(self.calls()) if self.log.exists() else 0
                result = self.make('publish', extra_env={
                    'FAKE_REPO_DIGESTS': 'ghcr.io/example/image@' + digest,
                    'FAKE_DIGEST_ERROR': message})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([call['args'][0] for call in self.calls()[before:]],
                                 ['manifest', 'run', 'build', 'image', 'manifest'])
                self.assertIn('Could not check remote manifest', result.stderr)

    def test_local_inspection_failure_prevents_push(self):
        result = self.make('publish', extra_env={'FAKE_IMAGE_INSPECT_EXIT': '7'})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls()[-1]['args'][:2], ['image', 'inspect'])
        self.assertIn('Cannot inspect the built image', result.stderr)

    def test_known_digests_are_deduplicated(self):
        first = 'sha256:' + 'd' * 64
        second = 'sha256:' + 'e' * 64
        result = self.make('publish', extra_env={'FAKE_REPO_DIGESTS':
            'registry.one/image@' + first + '\nregistry.two/image@' + first +
            '\nregistry.three/image@' + second})
        self.assertEqual(result.returncode, 0, result.stderr)
        probes = [c for c in self.calls() if c['args'][:2] == ['manifest', 'inspect']]
        self.assertEqual(len(probes), 3)  # One tag check, two distinct digest checks.

    def test_local_build_is_unguarded_even_when_remote_tag_exists(self):
        result = self.make('build', manifest_status='present')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call['args'][0] for call in self.calls()], ['run', 'build'])

    def test_parallel_publish_still_checks_before_building(self):
        result = self.make('--jobs=4', 'publish')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call['args'][0] for call in self.calls()],
                         ['manifest', 'run', 'build', 'image', 'push'])

    @unittest.skipUnless(shutil.which('bash'), 'Requires Bash')
    def test_build_conf_is_sourceable_and_supplies_default_versions(self):
        config = ENDPOINT / 'build.conf'
        sourced = subprocess.run(
            ['bash', '--noprofile', '--norc', '-eu', '-c',
             '. "$1"; printf "%s\\n" "$VERSION" "$DATABASE_VERSION" "$DUCKDB_JDBC_VERSION"',
             'bash', str(config)], capture_output=True, text=True, check=True)
        defaults = sourced.stdout.splitlines()
        self.assertEqual(len(defaults), 3)
        result = self.make('show-config', 'ENV_FILE=' + str(self.root / 'absent.env'))
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = dict(line.split(None, 1) for line in result.stdout.splitlines())
        for name, value in zip(['VERSION', 'DATABASE_VERSION', 'DUCKDB_JDBC_VERSION'], defaults):
            self.assertEqual(settings[name], value)

    def test_version_override_precedence(self):
        config = self.root / 'versions.env'
        config.write_text('VERSION=3.0.0\n')
        inherited = {'VERSION': '2.0.0'}
        absent = str(self.root / 'absent.env')
        for args, expected in [(['ENV_FILE=' + absent], '2.0.0'),
                               (['ENV_FILE=' + str(config)], '3.0.0'),
                               (['ENV_FILE=' + str(config), 'VERSION=4.0.0'], '4.0.0')]:
            with self.subTest(expected=expected):
                result = self.make('show-config', *args, extra_env=inherited)
                self.assertEqual(result.returncode, 0, result.stderr)
                settings = dict(line.split(None, 1) for line in result.stdout.splitlines())
                self.assertEqual(settings['VERSION'], expected)

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
        inspect, resolve, build, local_inspect, push = self.calls()
        self.assertEqual(local_inspect['args'][:2], ['image', 'inspect'])
        self.assertEqual(local_inspect['args'][-1], image)
        self.assertEqual(inspect['args'], ['manifest', 'inspect', image])
        self.assertEqual(resolve['args'][0], 'run')
        self.assertEqual(build['cwd'], str(ENDPOINT))
        self.assertEqual(build['args'][:3], ['build', '--tag', image])
        self.assertIn('ENDPOINT_VERSION=2.0.0', build['args'])
        self.assertIn('FAOSTAT_VERSION=1.0.0', build['args'])
        self.assertEqual(push['args'], ['push', image])


if __name__ == '__main__':
    unittest.main()
