#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FUNCTION_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
LOG_DIR="${BS_MEDIA_PLATFORM_LOG_DIR:-$FUNCTION_ROOT/logs/platform}"
LOG_FILE="${BS_MEDIA_PLATFORM_LOG_FILE:-$LOG_DIR/uvicorn-7028.log}"

mkdir -p "$LOG_DIR"

exec env \
  PYTHONUNBUFFERED=1 \
  BS_MEDIA_ASR_MODE=service \
  BS_MEDIA_TTS_MODE=service \
  BS_MEDIA_COMFY_MODE=service \
  python -m uvicorn server:app --host 0.0.0.0 --port 7028 >>"$LOG_FILE" 2>&1
