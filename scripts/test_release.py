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
    def check_publication(self, exists):
        env = {"GITHUB_REPOSITORY": "example/builder", "VERSION": VERSION,
               "GITHUB_RUN_ID": "123", "UPSTREAM_BRANCH": "release/v3.8.52",
               "UPSTREAM_SHA": SHA, "UPSTREAM_VERSION": "3.8.52",
               "BUILD_TIMESTAMP": str(TIMESTAMP), "IMAGE": "ghcr.io/example/builder",
               "IMAGE_DIGEST": "sha256:" + "a" * 64, "GITHUB_SHA": "b" * 40}
        tag = "v" + VERSION
        published = {"draft": False, "prerelease": False,
                     "assets": [{"name": "build-metadata.json"}],
                     "html_url": "https://example.com/release"}
        pages = [[], [{"tag_name": tag}]] if exists else [[]]
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            with contextlib.chdir(tmp), patch.dict(os.environ, env), \
                    patch.object(release, "gh", side_effect=[json.dumps(pages), "", "", json.dumps(published)]) as gh, \
                    contextlib.redirect_stdout(io.StringIO()):
                release.main()
                metadata = json.loads(Path("build-metadata.json").read_text())
                notes = Path("release-notes.md").read_text()
        self.assertEqual(metadata["version"], VERSION)
        self.assertEqual(metadata["build_timestamp"], TIMESTAMP)
        self.assertEqual(metadata["upstream_commit"], SHA)
        self.assertEqual(metadata["image"], env["IMAGE"] + ":" + VERSION)
        self.assertEqual(metadata["digest"], env["IMAGE_DIGEST"])
        self.assertIn(str(TIMESTAMP), notes)
        command = gh.call_args_list[1].args
        self.assertEqual(command[:3], ("release", "edit" if exists else "create", tag))
        self.assertIn("--latest", command)
        if not exists:
            self.assertEqual(command[command.index("--target") + 1], env["GITHUB_SHA"])
        self.assertEqual(gh.call_args_list[2].args[:4],
                         ("release", "upload", tag, "build-metadata.json"))
        self.assertEqual(gh.call_args_list[3].args,
                         ("api", f"repos/example/builder/releases/tags/{tag}"))

    def test_create_timestamped_release(self):
        self.check_publication(False)

    def test_retry_refreshes_exact_timestamped_release(self):
        self.check_publication(True)


if __name__ == "__main__":
    unittest.main()
