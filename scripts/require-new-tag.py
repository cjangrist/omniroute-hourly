#!/usr/bin/env python3
"""Refuse existing image tags; do not treat registry outages as absence."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def main():
    image = os.environ['IMAGE']
    if not image.startswith('ghcr.io/'):
        raise SystemExit('Only GHCR is supported')
    name = image.removeprefix('ghcr.io/')
    query = urllib.parse.urlencode({'service': 'ghcr.io', 'scope': f'repository:{name}:pull'})
    with urllib.request.urlopen('https://ghcr.io/token?' + query, timeout=30) as response:
        token = json.load(response)['token']
    request = urllib.request.Request(
        f'https://ghcr.io/v2/{name}/manifests/{os.environ["VERSION"]}',
        headers={'Authorization': 'Bearer ' + token,
                 'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}, method='HEAD')
    try:
        with urllib.request.urlopen(request, timeout=30):
            raise SystemExit('Version tag already exists; refusing overwrite')
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    print('Version tag does not exist')


if __name__ == '__main__':
    main()
