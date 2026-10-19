#!/usr/bin/env python3
"""Skip only when the current source already has a successfully completed release."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def should_build(sha, releases, read_metadata, read_run):
    published = [r for r in releases if not r['draft'] and not r['prerelease']
                 and r.get('immutable')]
    if not published:
        return True
    latest = max(published, key=lambda r: r['published_at'])
    asset = next(a for a in latest['assets'] if a['name'] == 'build-metadata.json')
    metadata = read_metadata(asset)
    if metadata['upstream_commit'] != sha:
        return True
    # A release can exist before latest promotion fails. Never treat that as success.
    run_id = metadata['workflow_run'].rsplit('/', 1)[1]
    run = read_run(run_id)
    return not (run['status'] == 'completed' and run['conclusion'] == 'success')


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    # Resolver writes this exact snapshot; do not resolve the moving branch twice.
    values = dict(line.split('=', 1) for line in Path(os.environ['RESOLVED_OUTPUT']).read_text().splitlines())
    pages = json.loads(subprocess.check_output(
        ['gh', 'api', '--paginate', '--slurp', f'repos/{repo}/releases?per_page=100'], text=True))
    releases = [release for page in pages for release in page]
    def metadata(asset):
        with urllib.request.urlopen(asset['browser_download_url'], timeout=30) as response:
            return json.load(response)
    build = should_build(values['sha'], releases, metadata,
                         lambda run: api(f'repos/{repo}/actions/runs/{run}'))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'build={str(build).lower()}\n')
    message = ('New or not-yet-successful upstream commit: build required.' if build else
               'No upstream change since the last successful publication; skipped successfully.')
    print(message)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(f'## Upstream commit check\n{message}\n\nCommit: `{values["sha"]}`\n')


if __name__ == '__main__':
    main()
