"""Commit gating: no change succeeds, failures retry, and API errors stay visible."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('check', Path(__file__).with_name('check-upstream.py'))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class CommitGateTests(unittest.TestCase):
    def setUp(self):
        self.release = {'draft': False, 'prerelease': False, 'immutable': True,
                        'published_at': '2026-10-18T18:00:00Z',
                        'assets': [{'name': 'build-metadata.json'}]}
        self.metadata = Mock(return_value={'upstream_commit': 'a' * 40,
                                          'workflow_run': 'https://example.com/runs/123'})
        self.run = Mock(return_value={'status': 'completed', 'conclusion': 'success'})

    def test_unchanged_success_skips(self):
        self.assertFalse(check.should_build('a' * 40, [self.release], self.metadata, self.run))

    def test_new_commit_builds(self):
        self.assertTrue(check.should_build('b' * 40, [self.release], self.metadata, self.run))
        self.run.assert_not_called()

    def test_failed_or_incomplete_publication_retries(self):
        for status, conclusion in [('completed', 'failure'), ('in_progress', None), ('completed', 'cancelled')]:
            self.run.return_value = {'status': status, 'conclusion': conclusion}
            self.assertTrue(check.should_build('a' * 40, [self.release], self.metadata, self.run))

    def test_drafts_prereleases_and_unlocked_releases_do_not_suppress(self):
        for key, value in [('draft', True), ('prerelease', True), ('immutable', False)]:
            release = dict(self.release, **{key: value})
            self.assertTrue(check.should_build('a' * 40, [release], self.metadata, self.run))
        self.metadata.assert_not_called()

    def test_empty_repository_builds(self):
        self.assertTrue(check.should_build('a' * 40, [], self.metadata, self.run))

    def test_release_order_does_not_depend_on_version_or_hash(self):
        older = dict(self.release, published_at='2026-10-17T18:00:00Z', assets=[])
        self.assertFalse(check.should_build('a' * 40, [older, self.release], self.metadata, self.run))

    def test_api_failures_are_not_no_change_success(self):
        self.metadata.side_effect = RuntimeError('API unavailable')
        with self.assertRaises(RuntimeError):
            check.should_build('a' * 40, [self.release], self.metadata, self.run)

    def test_build_is_gated_before_upstream_execution(self):
        text = (Path(__file__).parents[1] / '.github/workflows/build.yml').read_text()
        self.assertIn("if: needs.check.outputs.build == 'true'", text)
        self.assertEqual(text.count('python3 scripts/resolve-upstream.py'), 1)
        self.assertIn('ref: ${{ needs.check.outputs.sha }}', text)


if __name__ == '__main__':
    unittest.main()
