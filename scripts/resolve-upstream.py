#!/usr/bin/env python3
"""Resolve one atomic upstream source snapshot; never depend on upstream releases."""
import base64
import json
import os
import re
import subprocess
from urllib.parse import quote


def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def version_tag(version, sha):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", version):
        raise ValueError(f"Unsupported upstream version: {version!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid upstream commit")
    # Docker disallows '+' in tags. Fail rather than silently change version.
    tag = f"{version}-{sha[:12]}"
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
        raise ValueError("Upstream version cannot be represented exactly as a Docker tag")
    return tag


def main():
    repo = os.environ.get("UPSTREAM", "diegosouzapw/OmniRoute")
    branch = api(f"repos/{repo}")["default_branch"]
    sha = api(f"repos/{repo}/commits/{quote(branch, safe='')}")["sha"]
    content = api(f"repos/{repo}/contents/package.json?ref={sha}")
    version = json.loads(base64.b64decode(content["content"]))["version"]
    values = {"branch": branch, "sha": sha, "upstream_version": version,
              "version": version_tag(version, sha),
              "image": f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"}
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError("Invalid multiline metadata")
            output.write(f"{key}={value}\n")
    print(json.dumps(values, indent=2))


if __name__ == "__main__":
    main()
