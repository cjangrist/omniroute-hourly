#!/usr/bin/env python3
"""Apply semantic policy only to cryptographically verified statements."""
import json
from pathlib import Path
import sys


def validate(image, commit, metadata, verified):
    name, digest = image.split('@sha256:')
    if metadata['digest'] != 'sha256:' + digest or metadata['automation_commit'] != commit:
        raise ValueError('Unexpected image or automation revision')
    for result in verified:
        statement = result['verificationResult']['statement']
        subjects = statement['subject']
        if not any(s['digest'].get('sha256') == digest for s in subjects):
            continue
        predicate = statement['predicate']
        if (predicate['source'] == metadata['source']
                and predicate['source']['commit'] == metadata['upstream_commit']
                and predicate['builder']['commit'] == commit
                and predicate['image']['name'] == name
                and predicate['image']['digest'] == metadata['digest']
                and predicate['image']['version'] == metadata['version']):
            return
    raise ValueError('No verified source attestation matches the release')


def main():
    validate(sys.argv[1], sys.argv[2],
             json.loads(Path('evidence/build-metadata.json').read_text()),
             json.loads(Path('evidence/verified-source.json').read_text()))
    print('Verified source attestation matches exact release image and revisions')


if __name__ == '__main__':
    main()
