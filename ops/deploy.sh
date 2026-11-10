#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

compose=(docker compose -f compose.deploy.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" up -d --wait db redis
# 구 API·worker가 새 활성 프롬프트를 읽지 않도록 먼저 배출·중지한다.
"${compose[@]}" stop api worker
"${compose[@]}" up --no-deps --force-recreate --exit-code-from migrate migrate
"${compose[@]}" up --no-deps --force-recreate --exit-code-from runtime-prompts runtime-prompts
# migration 또는 등록이 실패하면 set -e로 종료하여 새 소비자를 시작하지 않는다.
"${compose[@]}" up -d --remove-orphans

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
