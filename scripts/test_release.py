"""Hermetic regression tests for snapshot naming and release publication."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = load("resolver", "resolve-upstream.py")
release = load("release", "release.py")
SHA = "0123456789abcdef0123456789abcdef01234567"
TIMESTAMP = 1792155103
VERSION = f"3.8.52-{TIMESTAMP}-{SHA[:12]}"


class NamingTests(unittest.TestCase):
    def test_timestamp_precedes_hash(self):
        self.assertEqual(resolver.version_tag("3.8.52", SHA, TIMESTAMP), VERSION)

    def test_alphabetical_order_is_time_order_not_hash_order(self):
        tags = [resolver.version_tag("3.8.52", sha * 40, stamp)
                for sha, stamp in [("f", TIMESTAMP), ("0", TIMESTAMP + 1),
                                   ("a", TIMESTAMP + 2)]]
        self.assertEqual(sorted(reversed(tags)), tags)
        self.assertEqual(sorted(["v" + tag for tag in reversed(tags)]),
                         ["v" + tag for tag in tags])

    def test_same_source_rebuild_gets_a_new_tag(self):
        self.assertNotEqual(resolver.version_tag("3.8.52", SHA, TIMESTAMP),
                            resolver.version_tag("3.8.52", SHA, TIMESTAMP + 1))

    def test_fixed_width_and_boundaries(self):
        self.assertEqual(resolver.version_tag("1.0.0", SHA, 0),
                         f"1.0.0-0000000000-{SHA[:12]}")
        self.assertLess(resolver.version_tag("1.0.0", SHA, 999999999),
                        resolver.version_tag("1.0.0", SHA, 1000000000))
        self.assertIn("-9999999999-", resolver.version_tag("1.0.0", SHA, 9999999999))

    def test_invalid_inputs(self):
        cases = [("bad", SHA, TIMESTAMP), ("1.0.0", "bad", TIMESTAMP),
                 ("1.0.0+build", SHA, TIMESTAMP), ("1.0.0", SHA, -1),
                 ("1.0.0", SHA, 10**10), ("1.0.0", SHA, True),
                 ("1.0.0", SHA, "1792155103"), ("1.0.0", SHA, 1.5),
                 ("1.0.0-" + "a" * 110, SHA, TIMESTAMP)]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                resolver.version_tag(*args)

    def test_prerelease_version_is_preserved(self):
        self.assertEqual(resolver.version_tag("1.0.0-rc.1", SHA, TIMESTAMP),
                         f"1.0.0-rc.1-{TIMESTAMP}-{SHA[:12]}")

    def test_real_resolver_entrypoint_outputs_one_coherent_snapshot(self):
        replies = [{"default_branch": "release/v3.8.52"}, {"sha": SHA},
                   {"content": base64.b64encode(b'{"version":"3.8.52"}').decode()}]
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            output = Path(tmp) / "output"
            env = {"GITHUB_REPOSITORY": "Example/Builder", "GITHUB_OUTPUT": str(output)}
            with patch.dict(os.environ, env), patch.object(resolver, "api", side_effect=replies) as api, \
                    patch.object(resolver.time, "time", return_value=TIMESTAMP + 0.9) as clock, \
                    contextlib.redirect_stdout(io.StringIO()):
                resolver.main()
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertEqual(values["version"], VERSION)
        self.assertEqual(values["build_timestamp"], str(TIMESTAMP))
        self.assertEqual(values["sha"], SHA)
        self.assertEqual(values["image"], "ghcr.io/example/builder")
        clock.assert_called_once()
        self.assertTrue(api.call_args_list[1].args[0].endswith("release%2Fv3.8.52"))
        self.assertTrue(api.call_args_list[2].args[0].endswith("ref=" + SHA))


class PublicationTests(unittest.TestCase):
    def test_draft_assets_then_publish_and_require_lock(self):
        env = {"GITHUB_REPOSITORY": "example/builder", "VERSION": VERSION,
               "IMAGE": "ghcr.io/example/builder", "GITHUB_SHA": "b" * 40}
        metadata = {"version": VERSION, "automation_commit": "b" * 40,
                    "upstream_commit": SHA, "digest": "sha256:" + "a" * 64,
                    "workflow_run": "https://example.com/build"}
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            with contextlib.chdir(tmp), patch.dict(os.environ, env):
                Path("evidence").mkdir()
                Path("evidence/build-metadata.json").write_text(json.dumps(metadata))
                Path("evidence/vulnerabilities.json").write_text('{"Results": []}')
                assets = [{"name": "build-metadata.json"}, {"name": "vulnerabilities.json"}]
                replies = [{"enabled": True}, [[]], "", {"draft": True, "assets": assets},
                           "", {"draft": False, "prerelease": False, "immutable": True,
                                "assets": assets, "html_url": "https://example.com/release"}]
                with patch.object(release, "gh", side_effect=[json.dumps(r) for r in replies]) as gh, \
                        contextlib.redirect_stdout(io.StringIO()):
                    release.main()
                self.assertIn("--draft", gh.call_args_list[2].args)
                self.assertIn("--draft=false", gh.call_args_list[4].args)
                self.assertFalse(any("--clobber" in c.args for c in gh.call_args_list))

    def test_disabled_immutability_fails_closed(self):
        env = {"GITHUB_REPOSITORY": "example/builder", "VERSION": VERSION, "GITHUB_SHA": "b" * 40}
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            with contextlib.chdir(tmp), patch.dict(os.environ, env):
                Path("evidence").mkdir()
                Path("evidence/build-metadata.json").write_text(json.dumps(
                    {"version": VERSION, "automation_commit": "b" * 40}))
                with patch.object(release, "gh", return_value='{"enabled": false}') as gh, \
                        self.assertRaises(SystemExit):
                    release.main()
                gh.assert_called_once()

    def test_existing_release_cannot_be_overwritten(self):
        env = {"GITHUB_REPOSITORY": "example/builder", "VERSION": VERSION, "GITHUB_SHA": "b" * 40}
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            with contextlib.chdir(tmp), patch.dict(os.environ, env):
                Path("evidence").mkdir()
                Path("evidence/build-metadata.json").write_text(json.dumps(
                    {"version": VERSION, "automation_commit": "b" * 40}))
                with patch.object(release, "gh", side_effect=[
                        '{"enabled": true}', json.dumps([[{"tag_name": "v" + VERSION}]])]) as gh, \
                        self.assertRaises(SystemExit):
                    release.main()
                self.assertEqual(gh.call_count, 2)


if __name__ == "__main__":
    unittest.main()
