#!/usr/bin/env bash
set -euo pipefail
image=${1:?image required}
container="omniroute-smoke-${GITHUB_RUN_ID:-local}"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker run --detach --name "$container" "$image"
for ((attempt=0; attempt<90; attempt++)); do
  state=$(docker inspect --format '{{.State.Status}}' "$container")
  health=$(docker inspect --format '{{.State.Health.Status}}' "$container")
  if [[ "$health" == healthy ]]; then
    docker exec "$container" node healthcheck.mjs
    echo "Container boot and upstream /healthz check passed"
    exit 0
  fi
  if [[ "$state" == exited || "$state" == dead || "$health" == unhealthy ]]; then
    break
  fi
  sleep 2
done
docker logs "$container"
docker inspect --format '{{json .State}}' "$container"
exit 1
