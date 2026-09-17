#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

docker compose -f compose.deploy.yaml config --quiet
docker compose -f compose.deploy.yaml up -d --build --remove-orphans

for attempt in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/api/health > /dev/null; then
    echo "Deployment health check passed"
    docker compose -f compose.deploy.yaml ps
    exit 0
  fi
  sleep 2
done

echo "Deployment health check failed"
docker compose -f compose.deploy.yaml logs --tail=100 api caddy
exit 1
