#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REMIX_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PROJECT_ROOT=$(cd "$REMIX_ROOT/.." && pwd)

HOST=${BS_MEDIA_ALGO_HOST:-127.0.0.1}
ASR_PORT=${BS_MEDIA_ASR_SERVICE_PORT:-7000}
TTS_PORT=${BS_MEDIA_TTS_SERVICE_PORT:-7001}
COMFY_PORT=${BS_MEDIA_COMFY_SERVICE_PORT:-7002}
PID_DIR=${BS_MEDIA_ALGO_PID_DIR:-"$PROJECT_ROOT/run/algorithms"}
LOCAL_NO_PROXY=${BS_MEDIA_LOCAL_NO_PROXY:-127.0.0.1,localhost}

export NO_PROXY="${NO_PROXY:+$NO_PROXY,}$LOCAL_NO_PROXY"
export no_proxy="${no_proxy:+$no_proxy,}$LOCAL_NO_PROXY"

check_service() {
  local name="$1"
  local port="$2"
  local ready_key="$3"
  local pid_file="$PID_DIR/${name}.pid"
  local pid="missing"
  local health="down"
  local ready="down"

  if [ -f "$pid_file" ]; then
    pid=$(cat "$pid_file")
  fi

  if python - "$HOST" "$port" <<'PY'
import json
import sys
import urllib.request

host = sys.argv[1]
port = int(sys.argv[2])
try:
    with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") == "ok":
        sys.exit(0)
except Exception:
    pass
sys.exit(1)
PY
  then
    health="ok"
  fi

  if python - "$HOST" "$port" "$ready_key" <<'PY'
import json
import sys
import urllib.request

host = sys.argv[1]
port = int(sys.argv[2])
ready_key = sys.argv[3]
try:
    with urllib.request.urlopen(f"http://{host}:{port}/ready", timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") == "ready" and payload.get(ready_key) is True:
        sys.exit(0)
except Exception:
    pass
sys.exit(1)
PY
  then
    ready="ok"
  fi

  printf '%s\tport=%s\tpid=%s\thealth=%s\tready=%s\n' "$name" "$port" "$pid" "$health" "$ready"
}

check_service "asr" "$ASR_PORT" "model_loaded"
check_service "tts" "$TTS_PORT" "model_loaded"
check_service "comfyui" "$COMFY_PORT" "comfyui_reachable"
