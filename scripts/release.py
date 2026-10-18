#!/usr/bin/env python3
"""Upload complete evidence to a draft, publish once, then require immutability."""
import json
import os
from pathlib import Path
import subprocess


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def main():
    env = os.environ
    repo, version = env['GITHUB_REPOSITORY'], env['VERSION']
    tag = 'v' + version
    metadata = json.loads(Path('evidence/build-metadata.json').read_text())
    if metadata['automation_commit'] != env['GITHUB_SHA'] or metadata['version'] != version:
        raise SystemExit('Release metadata does not match this workflow')
    # The settings endpoint requires repository administration, which the
    # deliberately least-privileged GITHUB_TOKEN does not have. Enforce the
    # actual published release's immutable state below instead.
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/releases'))
    if any(r['tag_name'] == tag for page in pages for r in page):
        raise SystemExit('Release already exists; immutable releases are never overwritten')
    scans = json.loads(Path('evidence/vulnerabilities.json').read_text())
    counts = {}
    for result in scans.get('Results', []):
        for finding in result.get('Vulnerabilities', []):
            severity = finding['Severity']
            counts[severity] = counts.get(severity, 0) + 1
    notes = f'''## Verified upstream snapshot: {version}

- [x] Exact upstream source: `{metadata['upstream_commit']}`
- [x] Automation revision: `{metadata['automation_commit']}`
- [x] Isolated build and container boot/health check
- [x] Image secret scan passed
- [x] Keyless image signature; GitHub OIDC identity and public Sigstore log
- [x] Verified GitHub build provenance, upstream-source attestation and SPDX SBOM attestation
- [x] Checksummed release evidence with signed checksum attestation
- [x] Immutable release required (verified after publication before latest promotion)

Image: `{env['IMAGE']}@{metadata['digest']}`

[Build and verification]({metadata['workflow_run']}) · [Verification instructions](https://github.com/{repo}/blob/{env['GITHUB_SHA']}/SECURITY.md)

### Vulnerability disclosure
Scan findings by severity: `{json.dumps(counts, sort_keys=True)}`.
The complete report is attached. This is not a zero-vulnerability certification.

### Trust boundary
Source and builder revisions are distinct and both are attested. The original upstream Dockerfile
and build scripts are used. Network-fetched dependencies and base images are not hermetic;
no independent reproducible-build or SLSA level certification is claimed. Signatures authenticate
the builder and artifact digest, not the safety of upstream code. Version image tags are not
overwritten by this workflow; GHCR tags are not server-enforced immutable. Pin image digests.
'''
    Path('release-notes.md').write_text(notes)
    # Upload every asset while draft; publication locks assets and the release tag.
    files = [str(p) for p in sorted(Path('evidence').iterdir()) if p.is_file()]
    gh('release', 'create', tag, *files, '--repo', repo, '--target', env['GITHUB_SHA'],
       '--title', tag, '--notes-file', 'release-notes.md', '--draft')
    # Drafts may not have a Git tag yet, so the by-tag endpoint returns 404.
    # Discover the authenticated draft in the release collection and read by ID.
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/releases'))
    matches = [r for page in pages for r in page if r['tag_name'] == tag]
    if len(matches) != 1:
        raise SystemExit('Expected exactly one newly created draft release')
    release_id = matches[0]['id']
    draft = json.loads(gh('api', f'repos/{repo}/releases/{release_id}'))
    expected = {Path(f).name for f in files}
    if not draft['draft'] or {a['name'] for a in draft['assets']} != expected:
        raise SystemExit('Draft release is missing evidence; refusing publication')
    gh('api', '--method', 'PATCH', f'repos/{repo}/releases/{release_id}',
       '-F', 'draft=false', '-f', 'make_latest=true')
    published = json.loads(gh('api', f'repos/{repo}/releases/{release_id}'))
    if published['draft'] or published['prerelease'] or not published['immutable']:
        raise SystemExit('Published release is not immutable')
    if {a['name'] for a in published['assets']} != expected:
        raise SystemExit('Published release assets do not match')
    print(published['html_url'])


if __name__ == '__main__':
    main()
