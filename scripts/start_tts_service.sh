#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}/metahuman_platform${PYTHONPATH:+:${PYTHONPATH}}"

exec conda run -n tts python -m uvicorn algorithm_services.tts_service:app \
  --host 127.0.0.1 \
  --port "${BS_MEDIA_TTS_SERVICE_PORT:-7001}"

