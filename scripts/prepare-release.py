#!/usr/bin/env python3
"""Create durable, explicit evidence before signing or locking a release."""
import datetime
import json
import os
from pathlib import Path
import re


def main():
    env = os.environ
    source = json.loads(Path('evidence/source.json').read_text())
    if source['commit'] != env['UPSTREAM_SHA']:
        raise SystemExit('Source evidence does not match upstream SHA')
    if not re.fullmatch('sha256:[0-9a-f]{64}', env['IMAGE_DIGEST']):
        raise SystemExit('Invalid image digest')
    version = env['VERSION']
    expected = f"{env['UPSTREAM_VERSION']}-{int(env['BUILD_TIMESTAMP']):010d}-{env['UPSTREAM_SHA'][:12]}"
    if version != expected:
        raise SystemExit('Version is not bound to the source and timestamp')
    metadata = {
        'upstream_repository': source['repository'], 'upstream_branch': env['UPSTREAM_BRANCH'],
        'upstream_commit': env['UPSTREAM_SHA'], 'upstream_version': env['UPSTREAM_VERSION'],
        'version': version, 'build_timestamp': int(env['BUILD_TIMESTAMP']),
        'image': f"{env['IMAGE']}:{version}", 'digest': env['IMAGE_DIGEST'],
        'platform': 'linux/amd64',
        'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'workflow_run': f"https://github.com/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}",
        'automation_commit': env['GITHUB_SHA'], 'source': source,
    }
    predicate = {
        'source': source,
        'builder': {'repository': 'https://github.com/' + env['GITHUB_REPOSITORY'],
                    'commit': env['GITHUB_SHA'], 'workflow': '.github/workflows/build.yml',
                    'run': metadata['workflow_run']},
        'invocation': {'target': 'runner-base', 'platform': 'linux/amd64',
                       'build_args': {'OMNIROUTE_USE_TURBOPACK': '0',
                                      'OMNIROUTE_BUILD_MEMORY_MB': '12288',
                                      'OMNIROUTE_BUILD_WORKERS': '2'}},
        'image': {'name': env['IMAGE'], 'digest': env['IMAGE_DIGEST'], 'version': version},
        'limitations': ['Network-fetched build dependencies are not hermetic.',
                        'Attestation authenticates builder claims, not absence of malicious source.',
                        'No independent reproducible-build or SLSA level certification is claimed.'],
    }
    for filename, value in [('build-metadata.json', metadata), ('source-provenance.json', predicate)]:
        Path('evidence', filename).write_text(json.dumps(value, indent=2) + '\n')


if __name__ == '__main__':
    main()
