#!/usr/bin/env bash
# Verify exact signer identity, automation revision, subjects, and upstream binding.
set -euo pipefail
image=${1:?digest-qualified image required}
commit=${2:?expected automation commit required}
repo=cjangrist/omniroute-hourly
identity="https://github.com/$repo/.github/workflows/build.yml@refs/heads/main"
[[ "$image" =~ ^ghcr.io/cjangrist/omniroute-hourly@sha256:[0-9a-f]{64}$ ]]
cosign verify "$image" --certificate-identity "$identity" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com > /dev/null
policy=(--repo "$repo" --cert-identity "$identity" --source-ref refs/heads/main
        --source-digest "$commit" --deny-self-hosted-runners)
gh attestation verify "oci://$image" "${policy[@]}" --format json > evidence/verified-provenance.json
gh attestation verify "oci://$image" "${policy[@]}" \
  --predicate-type https://github.com/cjangrist/omniroute-hourly/upstream-build/v1 \
  --format json > evidence/verified-source.json
gh attestation verify "oci://$image" "${policy[@]}" \
  --predicate-type https://spdx.dev/Document --format json > evidence/verified-sbom.json
gh attestation verify evidence/SHA256SUMS "${policy[@]}" \
  --bundle evidence/checksums.sigstore.json > /dev/null
python3 scripts/verify-policy.py "$image" "$commit"
