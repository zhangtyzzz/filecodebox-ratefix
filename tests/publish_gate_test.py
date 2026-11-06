"""Exercise publication sequencing without Docker, credentials or network calls."""
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('maintenance_publish', ROOT / 'scripts/publish.py')
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class PublicationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = pathlib.Path.cwd()
        self.addCleanup(os.chdir, self.cwd)
        os.chdir(self.temp.name)
        pathlib.Path('build').mkdir()
        self.revision = 'a' * 40
        self.base = 'sha256:' + 'b' * 64
        self.configs = {'amd64': 'sha256:' + 'c' * 64, 'arm64': 'sha256:' + 'd' * 64}
        self.manifests = {'amd64': 'sha256:' + 'e' * 64, 'arm64': 'sha256:' + 'f' * 64}
        plan = {'maintenance_revision': self.revision, 'base_digest': self.base,
                'base_image': 'lanol/filecodebox@' + self.base,
                'image_repository': 'fixture/filecodebox-ratefix'}
        pathlib.Path('build/preparation.json').write_text(json.dumps(plan))
        for arch in ['amd64', 'arm64']:
            folder = pathlib.Path('build/candidates/candidate-' + arch)
            folder.mkdir(parents=True)
            content = ('synthetic image archive ' + arch).encode()
            (folder / ('filecodebox-' + arch + '.tar')).write_bytes(content)
            result = {'architecture': arch, 'maintenance_revision': self.revision,
                      'upstream_digest': self.base, 'unit_tests_passed': True,
                      'fresh_boot_passed': True, 'image_id': self.configs[arch],
                      'archive_sha256': hashlib.sha256(content).hexdigest()}
            (folder / 'result.json').write_text(json.dumps(result))
        self.calls = []
        self.bad_remote_config = False
        self.bad_index = False
        self.fail_push = False

    def run_command(self, args):
        self.calls.append(args)
        if args[:3] == ['docker', 'image', 'inspect']:
            arch = args[-1].split(':')[-1]
            return json.dumps([{'Architecture': arch, 'Id': self.configs[arch],
                                'Config': {'Labels': {'io.filecodebox.maintenance.base.digest': self.base,
                                                      'org.opencontainers.image.revision': self.revision}}}]).encode()
        if self.fail_push and args[:2] == ['docker', 'push']:
            raise RuntimeError('synthetic registry push failure')
        return b''

    def registry(self, *args):
        outer = self

        class FakeRegistry:
            def manifest(self, reference):
                if reference.endswith(('-amd64', '-arm64')):
                    arch = reference.rsplit('-', 1)[-1]
                    return outer.manifests[arch], {'config': {'digest': 'wrong' if outer.bad_remote_config else outer.configs[arch]}}
                values = [] if outer.bad_index else [{'digest': outer.manifests[arch], 'platform': {'os': 'linux', 'architecture': arch}} for arch in ['amd64', 'arm64']]
                return 'sha256:' + '1' * 64, {'manifests': values}

            def platforms(self, index):
                return {v['platform']['architecture']: v['digest'] for v in index['manifests']}

        return FakeRegistry()

    def invoke(self):
        env = {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_ACTOR': 'fixture',
               'GHCR_TOKEN': 'synthetic-not-a-real-credential', 'GITHUB_STEP_SUMMARY': 'build/summary.txt'}
        with patch.object(publish, 'run', self.run_command), patch.object(publish, 'Registry', self.registry), patch.dict(os.environ, env), patch.object(sys, 'argv', ['publish.py']):
            publish.main()

    def latest_calls(self):
        return [v for v in self.calls if any(arg.endswith(':latest') for arg in v)]

    def test_validated_index_is_the_last_mutation(self):
        self.invoke()
        self.assertEqual(len(self.latest_calls()), 1)
        self.assertEqual(self.latest_calls()[0], self.calls[-1])
        self.assertEqual(sum(v[:2] == ['docker', 'push'] for v in self.calls), 2)

    def test_failed_second_architecture_does_not_publish_any_image(self):
        path = pathlib.Path('build/candidates/candidate-arm64/result.json')
        data = json.loads(path.read_text())
        data['fresh_boot_passed'] = False
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'required checks'):
            self.invoke()
        self.assertFalse(self.latest_calls())
        self.assertFalse(any(v[:2] == ['docker', 'push'] for v in self.calls))

    def test_archive_corruption_never_promotes_latest(self):
        pathlib.Path('build/candidates/candidate-arm64/filecodebox-arm64.tar').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.invoke()
        self.assertFalse(self.latest_calls())

    def test_registry_config_mismatch_never_promotes_latest(self):
        self.bad_remote_config = True
        with self.assertRaisesRegex(ValueError, 'Published architecture'):
            self.invoke()
        self.assertFalse(self.latest_calls())

    def test_incomplete_index_never_promotes_latest(self):
        self.bad_index = True
        with self.assertRaisesRegex(ValueError, 'Multi-platform index'):
            self.invoke()
        self.assertFalse(self.latest_calls())

    def test_push_failure_never_promotes_latest(self):
        self.fail_push = True
        with self.assertRaisesRegex(RuntimeError, 'synthetic registry push failure'):
            self.invoke()
        self.assertFalse(self.latest_calls())


if __name__ == '__main__':
    unittest.main()
