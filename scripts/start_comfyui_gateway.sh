#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}/metahuman_platform${PYTHONPATH:+:${PYTHONPATH}}"

exec conda run -n AIGC python -m uvicorn algorithm_services.comfy_gateway_service:app \
  --host 127.0.0.1 \
  --port "${BS_MEDIA_COMFY_SERVICE_PORT:-7002}"

