#!/usr/bin/env python3
"""Export only tracked source; bind the build context to its exact Git snapshot."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def context_digest(root):
    records = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            records.append([relative, 'symlink', os.readlink(path)])
        elif path.is_file():
            records.append([relative, 'file', path.stat().st_mode & 0o777,
                            hashlib.sha256(path.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(records, separators=(',', ':')).encode()).hexdigest()


def main():
    evidence = Path('evidence')
    context = Path('build-context')
    if '--verify' in sys.argv:
        record = json.loads((evidence / 'source.json').read_text())
        if context_digest(context) != record['context_sha256']:
            raise SystemExit('Build context changed after export')
        return
    evidence.mkdir(exist_ok=True)
    sha = run('git', '-C', 'upstream', 'rev-parse', 'HEAD')
    if sha != os.environ['UPSTREAM_SHA']:
        raise SystemExit('Upstream checkout does not match resolved SHA')
    if run('git', '-C', 'upstream', 'status', '--porcelain'):
        raise SystemExit('Upstream checkout is dirty')
    # Reject unsupported source boundaries instead of silently omitting content.
    tree = run('git', '-C', 'upstream', 'ls-tree', '-r', 'HEAD')
    if any(line.startswith('160000 ') for line in tree.splitlines()):
        raise SystemExit('Submodules require explicit source/material handling')
    archive = evidence / 'upstream-source.tar'
    subprocess.run(['git', '-C', 'upstream', 'archive', '--format=tar',
                    '--output', str(archive.resolve()), sha], check=True)
    context.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(context, filter='data')
    record = {
        'repository': 'https://github.com/diegosouzapw/OmniRoute',
        'commit': sha,
        'tree': run('git', '-C', 'upstream', 'rev-parse', 'HEAD^{tree}'),
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'context_sha256': context_digest(context),
        'dockerfile_sha256': hashlib.sha256((context / 'Dockerfile').read_bytes()).hexdigest(),
        'package_lock_sha256': hashlib.sha256((context / 'package-lock.json').read_bytes()).hexdigest(),
    }
    (evidence / 'source.json').write_text(json.dumps(record, indent=2) + '\n')
    # Retain the digest in release evidence, not an unnecessarily large source copy.
    archive.unlink()
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
