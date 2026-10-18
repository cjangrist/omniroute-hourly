# OmniRoute hourly Docker builds

[![Latest build attempt](https://github.com/cjangrist/omniroute-hourly/actions/workflows/build.yml/badge.svg)](https://github.com/cjangrist/omniroute-hourly/actions/workflows/build.yml)
[![Published release](https://img.shields.io/github/v/release/cjangrist/omniroute-hourly?label=published%20snapshot&sort=date)](https://github.com/cjangrist/omniroute-hourly/releases/latest)
[![Supply-chain verification](https://img.shields.io/badge/supply_chain-verifiable-blue?logo=sigstore)](SECURITY.md)
[![Public GHCR image](https://img.shields.io/badge/GHCR-public%20image-blue?logo=docker)](https://github.com/cjangrist/omniroute-hourly/pkgs/container/omniroute-hourly)

Unofficial, automated builds of the **current default branch** of
[diegosouzapw/OmniRoute](https://github.com/diegosouzapw/OmniRoute).
The branch is resolved dynamically every run: currently a `release/v…` branch,
not the latest published GitHub release or npm package. When upstream changes its
default branch, these builds follow it automatically.

## Use

```sh
docker pull ghcr.io/cjangrist/omniroute-hourly:latest
docker run -d --name omniroute \
  -p 127.0.0.1:20128:20128 \
  -v omniroute-data:/app/data \
  ghcr.io/cjangrist/omniroute-hourly:latest
```

Open <http://localhost:20128>. Follow [upstream configuration and security documentation](https://github.com/diegosouzapw/OmniRoute).
The upstream image defaults, entrypoint, non-root user, API-key requirement,
port and volume layout are preserved. **Platform: Linux amd64.**

## Schedule, versions, and status

- Runs every hour at minute **17 UTC**, on builder changes, and manually from Actions.
  GitHub schedules are best-effort and can be delayed. GitHub may disable scheduled
  workflows after 60 days of repository inactivity; re-enable from Actions if needed.
- Rebuilds every run, even if upstream source is unchanged, using BuildKit layer caching.
- Uses the upstream `package.json` version, a **10-digit Unix build timestamp**
  (UTC seconds since the epoch), then a **12-character upstream commit hash**:
  image `3.8.52-1792155103-0123456789ab`, release
  `v3.8.52-1792155103-0123456789ab` (format examples only). The timestamp is
  captured once when resolving the build, so names sort chronologically within
  the same upstream version, independently of hash order. Alphabetical ordering
  across different upstream versions is not semantic-version ordering.
- Every successful build publishes a matching GitHub release containing
  upstream branch, full SHA, image digest, Unix build timestamp and workflow link
  in `build-metadata.json`. Rebuilding the same source gets a new timestamped
  release. Published releases and assets are immutable; existing versions are never overwritten.
- Release naming and publication regression tests run before each build. Run
  locally with `python3 -m unittest discover -s scripts -p 'test_*.py' -v`.
- `:latest` always points to the newest successfully built and boot-checked image;
  promotion happens only after signing, provenance verification and immutable-release publication.
  Earlier failures leave the previous `:latest` in place. Serialized publishing
  prevents overlapping jobs from racing the tag.
- **Latest build attempt** badge is green/red for the latest workflow result.
  **Published snapshot** separately identifies the most recent successful release.
  Green is build/publish success, **not** a claim that upstream's entire test suite passes.

## Same build path, without release gating

Checks out an exact upstream SHA, then builds its **unmodified `Dockerfile`,
`runner-base` target**, which runs upstream `npm ci`, native-dependency checks,
`npm run build` and standalone assembly. Matches upstream's webpack build arguments
(`OMNIROUTE_USE_TURBOPACK=0`, 12288 MB V8 heap, two build workers).
Uses standard **GitHub-hosted `ubuntu-24.04` public/free runners**, with swap for
build headroom. No self-hosted or paid larger runners, Docker Hub credentials,
or long-lived publishing tokens. Publication uses the repository's `GITHUB_TOKEN`.

Does **not** import upstream release-green, lint, policy, unit/integration,
mutation, release-acceptance, semver-promotion or vulnerability-scan gates.
See [upstream issue #15306](https://github.com/diegosouzapw/OmniRoute/issues/15306)
for the release-cadence problem this bypasses. A bounded container boot and
upstream `/healthz` probe, image secret scan, signatures, attestations and immutable
release verification must pass. Vulnerability findings are disclosed in the attached
report rather than recreating upstream release gating. See [security guarantees and verification](SECURITY.md).
Actual Docker compilation/native checks still have to succeed; no errors are hidden.

This is an **unofficial rolling snapshot**, potentially containing upstream bugs
or vulnerabilities, not an endorsement of production readiness. This repository
contains build automation, not an independent fork of upstream application source.
Upstream OmniRoute is MIT-licensed; its notices remain in the unchanged source
build context. Automation here is also MIT-licensed.
