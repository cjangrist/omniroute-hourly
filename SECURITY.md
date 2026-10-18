# Supply-chain security and verification

## What new releases prove

The workflow records two distinct revisions: this repository's automation commit,
and the upstream OmniRoute source commit actually exported into the Docker build.
It does **not** claim that upstream application code lives in this automation repo.

- Exact upstream commit/tree, Dockerfile/lockfile hashes and exported-context hash.
- A clean tracked-source export, with no `.git` credentials or untracked build inputs;
  unsupported submodules fail closed. The context hash is checked again after build.
- Separate ephemeral GitHub-hosted build and publish jobs. The build cannot mint
  signing tokens or publish packages/releases; the publish job does not execute
  upstream application scripts. The tested image is transferred as a checksummed artifact.
- Full-commit action pins and StepSecurity runner/network auditing (audit mode,
  not an outbound-network allowlist).
- Bounded container boot/health check; image secret detections block publication.
- SPDX SBOM and a complete Trivy vulnerability report. CVEs are disclosed, not
  hidden or equated with a failed upstream release qualification.
- Keyless Cosign image signature using GitHub OIDC, a short-lived certificate and
  public Sigstore transparency log. No long-lived signing key is stored.
- GitHub/Sigstore attestations for build provenance, explicit upstream provenance,
  the SPDX SBOM and release-asset checksums. Image attestations are published to
  GitHub and GHCR; portable verification bundles are release assets.
- Verification pins the signer workflow, `refs/heads/main`, exact automation SHA,
  GitHub OIDC issuer and hosted runner, then checks the signed upstream/source/image binding.
- All evidence is uploaded to a draft release before publication. GitHub immutable
  release policy locks published assets and the release tag; `gh release verify`
  checks GitHub's own signed release attestation before `latest` moves.
- Version-tag collisions fail rather than overwrite. **GHCR tags themselves are
  not server-enforced immutable**; consumers must pin the signed image digest.

The workflow summary and release notes expose check marks only after their steps
pass. The status badge is the actual workflow result, not a static security rating.
The old release predating these changes has no retroactive security guarantees.

## Verify a release yourself

Install current GitHub CLI and Cosign. Authenticate `gh` to GitHub for attestation
retrieval. Public GHCR images do not require stored registry credentials.

```bash
repo=cjangrist/omniroute-hourly
# Select the exact release you intend to trust, not an untrusted supplied image tag.
tag=$(gh api "repos/$repo/releases/latest" --jq .tag_name)
gh release verify "$tag" --repo "$repo"
mkdir -p verification/evidence
cd verification
gh release download "$tag" --repo "$repo" --dir evidence
commit=$(jq -r .automation_commit evidence/build-metadata.json)
image="ghcr.io/$repo@$(jq -r .digest evidence/build-metadata.json)"
identity="https://github.com/$repo/.github/workflows/build.yml@refs/heads/main"
# Authenticate the checksum list BEFORE trusting its checksums.
gh attestation verify evidence/SHA256SUMS --repo "$repo" \
  --cert-identity "$identity" --source-digest "$commit" \
  --source-ref refs/heads/main --deny-self-hosted-runners \
  --bundle evidence/checksums.sigstore.json
(cd evidence && sha256sum --check SHA256SUMS)
cosign verify "$image" --certificate-identity "$identity" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
gh attestation verify "oci://$image" --repo "$repo" \
  --cert-identity "$identity" --source-digest "$commit" \
  --source-ref refs/heads/main --deny-self-hosted-runners
# Verify the explicit upstream-source claim, not just this builder's source revision.
gh attestation verify "oci://$image" --repo "$repo" \
  --cert-identity "$identity" --source-digest "$commit" \
  --source-ref refs/heads/main --deny-self-hosted-runners \
  --predicate-type https://github.com/cjangrist/omniroute-hourly/upstream-build/v1 \
  --format json > evidence/verified-source.json
```

Compare the verified predicate's `source.commit`, `source.tree`, context/Dockerfile/
lockfile hashes, `builder.commit`, and `image.digest` with `build-metadata.json`.
For automated checks, review this repository at the attested automation commit,
then run its `scripts/verify.sh` and `scripts/verify-policy.py` from that checkout
with the downloaded `evidence/` directory. Do not blindly execute a script merely
because an untrusted artifact includes it. Pin an independently reviewed automation
commit if you need a stronger policy than trusting whoever can update `main`.

To verify the SBOM binding, repeat `gh attestation verify` with
`--predicate-type https://spdx.dev/Document`. To consume the exact artifact:

```bash
docker pull "$image"
```

## Boundaries, not marketing

A valid signature establishes the authorized builder identity and artifact digest;
it is not a proof that source code is safe. A compromised trusted workflow/runner
can lie in a predicate. Repository administrators remain part of the trust boundary.
No independent SLSA level certification, formal proof, zero-CVE guarantee, or
bit-for-bit reproducible build is claimed. Upstream's unchanged Dockerfile downloads
base images, npm and other network dependencies; those inputs are not fully
hermetic. BuildKit metadata and the SBOM improve inspection but do not remove that
boundary. `latest` is intentionally mutable. Pin digests and verify signatures.

Scans must execute successfully. Vulnerability findings are reported without blocking
rolling snapshots; secret detections and missing/invalid security evidence fail closed.
An image uploaded before signing fails may remain under its unique version tag, but
it is not promoted to `latest` and has no successful locked release.
