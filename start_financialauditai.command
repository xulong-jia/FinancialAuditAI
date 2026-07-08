#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="FinancialAuditAI"
FRONTEND_URL="http://localhost:5173"
HEALTH_URL="http://localhost:8000/health"
CONFIG_URL="http://localhost:8000/api/v1/config"

echo "Starting ${APP_NAME} local demo..."
echo "This is a local public-acceptance demo, not a production deployment."
echo

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required tool: $1"
    echo "Install it first, then run this script again."
    exit 1
  fi
}

require_cmd docker
require_cmd python3
require_cmd node
require_cmd npm

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but not running."
  echo "Open Docker Desktop, wait until it is ready, then run this script again."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is not available through 'docker compose'."
  echo "Update Docker Desktop, then run this script again."
  exit 1
fi

if [ ! -f ".env" ]; then
  if [ ! -f ".env.example" ]; then
    echo "Missing .env.example; cannot create local demo .env."
    exit 1
  fi
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "This is local demo configuration only. Do not put real secrets in committed files."
  echo
fi

check_port() {
  local port="$1"
  local name="$2"
  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use ($name)."
    echo "Stop the process using that port, or run stop_financialauditai.command if this stack is already running."
    exit 1
  fi
}

check_port 8000 "backend"
check_port 5173 "frontend"
check_port 5432 "postgres"

echo "Validating Docker Compose config..."
docker compose config >/dev/null

echo "Building and starting local stack..."
docker compose up --build -d

echo
echo "Waiting for backend health..."
for _ in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo
echo "${APP_NAME} local demo is starting."
echo "Frontend:       ${FRONTEND_URL}"
echo "Backend health: ${HEALTH_URL}"
echo "API config:     ${CONFIG_URL}"
echo
echo "If this is the first run and you want synthetic demo data, run:"
echo "  docker compose exec backend python ../scripts/seed_demo_data.py"
echo
echo "To stop the local stack, double-click stop_financialauditai.command."
echo "Recent logs:"
docker compose logs --tail=60
