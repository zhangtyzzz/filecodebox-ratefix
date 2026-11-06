"""The release gate must refuse unreviewed source or a changed replacement."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('guard', ROOT / 'scripts/check_upstream.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = pathlib.Path(self.temp.name)
        self.upstream = self.folder / 'upstream.py'
        self.patch = self.folder / 'patch.py'
        self.policy = self.folder / 'policy.json'
        self.upstream.write_text('upstream-reviewed\n')
        self.patch.write_text('replacement-reviewed\n')
        self.data = {'allowed_upstream_sha256': [guard.hashlib.sha256(self.upstream.read_bytes()).hexdigest()],
                     'patched_file_sha256': guard.hashlib.sha256(self.patch.read_bytes()).hexdigest()}
        self.write_policy()

    def write_policy(self):
        self.policy.write_text(json.dumps(self.data))

    def test_reviewed_source_and_patch_pass(self):
        self.assertEqual(guard.check(self.upstream, self.patch, self.policy)['status'], 'PASS')

    def test_new_upstream_function_blocks_overlay(self):
        self.upstream.write_text('upstream-reviewed\ndef new_security_check(): pass\n')
        with self.assertRaisesRegex(ValueError, 'UPSTREAM_MODULE_CHANGED'):
            guard.check(self.upstream, self.patch, self.policy)

    def test_even_a_whitespace_change_requires_review(self):
        self.upstream.write_text('upstream-reviewed\n\n')
        with self.assertRaisesRegex(ValueError, 'UPSTREAM_MODULE_CHANGED'):
            guard.check(self.upstream, self.patch, self.policy)

    def test_missing_module_fails(self):
        self.upstream.unlink()
        with self.assertRaises(OSError):
            guard.check(self.upstream, self.patch, self.policy)

    def test_changed_patch_fails(self):
        self.patch.write_text('unexpected replacement\n')
        with self.assertRaisesRegex(ValueError, 'patch differs'):
            guard.check(self.upstream, self.patch, self.policy)

    def test_reviewed_policy_pins_current_patch(self):
        real = json.loads((ROOT / 'upstream-policy.json').read_text())
        self.assertEqual(real['patched_file_sha256'], guard.hashlib.sha256((ROOT / 'dependencies.py').read_bytes()).hexdigest())
        self.assertEqual(real['expected_test_count'], 15)


if __name__ == '__main__':
    unittest.main()
