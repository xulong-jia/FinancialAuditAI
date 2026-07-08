#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Stopping FinancialAuditAI local demo..."

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required tool: docker"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is not available through 'docker compose'."
  exit 1
fi

docker compose down

echo
echo "FinancialAuditAI local demo stopped."
