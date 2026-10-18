"""Fail-closed supply-chain regression checks; no remote operations."""
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


def load(filename):
    spec = importlib.util.spec_from_file_location(filename, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source = load('source-evidence.py')
policy = load('verify-policy.py')
registry = load('require-new-tag.py')
prepare = load('prepare-release.py')


class SecurityTests(unittest.TestCase):
    def test_context_hash_detects_content_mode_and_symlink_changes(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            root = Path(tmp)
            file = root / 'Dockerfile'
            file.write_text('FROM scratch\n')
            original = source.context_digest(root)
            file.write_text('FROM malicious\n')
            self.assertNotEqual(original, source.context_digest(root))
            file.write_text('FROM scratch\n')
            file.chmod(0o755)
            self.assertNotEqual(original, source.context_digest(root))
            file.unlink()
            file.symlink_to('other')
            self.assertNotEqual(original, source.context_digest(root))

    def test_actual_git_export_and_tampering_rejection(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
            with contextlib.chdir(tmp):
                Path('upstream').mkdir()
                def git(*args):
                    return subprocess.check_output(['git', '-C', 'upstream', *args], text=True).strip()
                git('init', '-q')
                git('config', 'user.name', 'Test')
                git('config', 'user.email', 'test@example.invalid')
                Path('upstream/Dockerfile').write_text('FROM scratch\n')
                Path('upstream/package-lock.json').write_text('{}')
                git('add', '.')
                git('commit', '-qm', 'fixture')
                with patch.dict(os.environ, {'UPSTREAM_SHA': git('rev-parse', 'HEAD')}), \
                        patch('sys.argv', ['source-evidence.py']):
                    source.main()
                self.assertFalse(Path('build-context/.git').exists())
                with patch('sys.argv', ['source-evidence.py', '--verify']):
                    source.main()
                    Path('build-context/Dockerfile').write_text('changed')
                    with self.assertRaises(SystemExit):
                        source.main()

    def test_verified_predicate_must_match_digest_source_and_builder(self):
        metadata = {'digest': 'sha256:' + 'a' * 64, 'automation_commit': 'b' * 40,
                    'upstream_commit': 'c' * 40, 'source': {'commit': 'c' * 40},
                    'version': '1.0.0-1792155103-cccccccccccc'}
        predicate = {'source': metadata['source'], 'builder': {'commit': 'b' * 40},
                     'image': {'name': 'ghcr.io/example/image', 'digest': metadata['digest'],
                               'version': metadata['version']}}
        verified = [{'verificationResult': {'statement': {
            'subject': [{'digest': {'sha256': 'a' * 64}}], 'predicate': predicate}}}]
        image = 'ghcr.io/example/image@' + metadata['digest']
        policy.validate(image, 'b' * 40, metadata, verified)
        for field in ['source', 'builder', 'image']:
            altered = copy.deepcopy(verified)
            altered[0]['verificationResult']['statement']['predicate'][field] = {}
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                policy.validate(image, 'b' * 40, metadata, altered)
        with self.assertRaises(ValueError):
            policy.validate(image.replace('a' * 64, 'd' * 64), 'b' * 40, metadata, verified)

    def test_registry_network_errors_are_not_absence(self):
        token = unittest.mock.MagicMock()
        token.__enter__.return_value.read.return_value = b'{"token":"test"}'
        env = {'IMAGE': 'ghcr.io/example/image', 'VERSION': '1.0.0'}
        for status in [401, 403, 429, 500]:
            error = urllib.error.HTTPError('https://example.invalid', status, 'error', {}, None)
            with self.subTest(status=status), patch.dict(os.environ, env), \
                    patch.object(registry.urllib.request, 'urlopen', side_effect=[token, error]), \
                    self.assertRaises(urllib.error.HTTPError):
                registry.main()
        missing = urllib.error.HTTPError('https://example.invalid', 404, 'missing', {}, None)
        with patch.dict(os.environ, env), \
                patch.object(registry.urllib.request, 'urlopen', side_effect=[token, missing]):
            registry.main()

    def test_workflow_least_privilege_and_pinned_actions(self):
        text = (Path(__file__).parents[1] / '.github/workflows/build.yml').read_text()
        build, publish = text.split('\n  publish:\n')
        self.assertNotIn('id-token: write', build)
        self.assertNotIn('packages: write', build)
        self.assertNotIn('contents: write', build)
        self.assertIn('id-token: write', publish)
        self.assertLess(publish.index('bash scripts/verify.sh'), publish.index('python3 scripts/release.py'))
        self.assertLess(publish.index('gh release verify'), publish.index('Promote verified release to latest'))
        import re
        for action in re.findall(r'uses: ([^\s]+)', text):
            self.assertRegex(action, r'^[^@]+@[0-9a-f]{40}$')


if __name__ == '__main__':
    unittest.main()
