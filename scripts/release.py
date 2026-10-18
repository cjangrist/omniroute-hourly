#!/usr/bin/env python3
"""Publish a release per timestamped build, preserving exact upstream provenance."""
import datetime
import json
import os
import pathlib
import subprocess


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)


def main():
    env = os.environ
    repo, version = env["GITHUB_REPOSITORY"], env["VERSION"]
    tag = f"v{version}"
    run = f"https://github.com/{repo}/actions/runs/{env['GITHUB_RUN_ID']}"
    metadata = {
        "upstream_repository": "diegosouzapw/OmniRoute",
        "upstream_branch": env["UPSTREAM_BRANCH"],
        "upstream_commit": env["UPSTREAM_SHA"],
        "upstream_version": env["UPSTREAM_VERSION"],
        "version": version,
        "build_timestamp": int(env["BUILD_TIMESTAMP"]),
        "image": f"{env['IMAGE']}:{version}",
        "latest": f"{env['IMAGE']}:latest",
        "digest": env["IMAGE_DIGEST"],
        "platform": "linux/amd64",
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "workflow_run": run,
        "automation_commit": env["GITHUB_SHA"],
    }
    pathlib.Path("build-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    notes = f"""## Unofficial upstream snapshot: {version}

Built from [{env['UPSTREAM_BRANCH']} @ {env['UPSTREAM_SHA']}](https://github.com/diegosouzapw/OmniRoute/commit/{env['UPSTREAM_SHA']}).

- Upstream package version: `{env['UPSTREAM_VERSION']}`
- Unix build timestamp: `{env['BUILD_TIMESTAMP']}`
- Image: `{env['IMAGE']}:{version}`
- Moving channel: `{env['IMAGE']}:latest`
- Digest: `{env['IMAGE_DIGEST']}`
- Platform: `linux/amd64`
- [Successful build and container boot smoke check]({run})

Uses the upstream Dockerfile (`runner-base`) and its build scripts unchanged.
This is **not an official or release-qualified upstream release**. Upstream release-green,
lint, unit/integration and vulnerability gates are intentionally not prerequisites.
GitHub tag identifies this builder's automation revision; the upstream source is the SHA above.
Every build gets a timestamped release, even when upstream source is unchanged.
Retrying publication for the same resolved build refreshes its release and metadata.
"""
    pathlib.Path("release-notes.md").write_text(notes)
    releases = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/releases"))
    exists = any(r["tag_name"] == tag for page in releases for r in page)
    if exists:
        gh("release", "edit", tag, "--repo", repo, "--title", tag,
           "--notes-file", "release-notes.md", "--latest")
    else:
        gh("release", "create", tag, "--repo", repo, "--target", env["GITHUB_SHA"],
           "--title", tag, "--notes-file", "release-notes.md", "--latest")
    gh("release", "upload", tag, "build-metadata.json", "--repo", repo, "--clobber")
    release = json.loads(gh("api", f"repos/{repo}/releases/tags/{tag}"))
    assert not release["draft"] and not release["prerelease"]
    assert any(a["name"] == "build-metadata.json" for a in release["assets"])
    print(release["html_url"])


if __name__ == "__main__":
    main()
