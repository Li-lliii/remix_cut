#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REMIX_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
METAHUMAN_ROOT="$REMIX_ROOT/metahuman_platform"
PROJECT_ROOT=$(cd "$REMIX_ROOT/.." && pwd)

HOST=${BS_MEDIA_ALGO_HOST:-127.0.0.1}
ASR_PORT=${BS_MEDIA_ASR_SERVICE_PORT:-7000}
TTS_PORT=${BS_MEDIA_TTS_SERVICE_PORT:-7001}
COMFY_PORT=${BS_MEDIA_COMFY_SERVICE_PORT:-7002}
LOG_DIR=${BS_MEDIA_ALGO_LOG_DIR:-"$PROJECT_ROOT/logs/algorithms"}
PID_DIR=${BS_MEDIA_ALGO_PID_DIR:-"$PROJECT_ROOT/run/algorithms"}
CONFIG_PATH=${BS_MEDIA_CONFIG_PATH:-"$REMIX_ROOT/config.yaml"}
LOCAL_NO_PROXY=${BS_MEDIA_LOCAL_NO_PROXY:-127.0.0.1,localhost}

mkdir -p "$LOG_DIR" "$PID_DIR"

export PYTHONPATH="$METAHUMAN_ROOT:$REMIX_ROOT:${PYTHONPATH:-}"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}$LOCAL_NO_PROXY"
export no_proxy="${no_proxy:+$no_proxy,}$LOCAL_NO_PROXY"
export BS_MEDIA_ALGO_HOST="$HOST"
export BS_MEDIA_ASR_SERVICE_HOST="${BS_MEDIA_ASR_SERVICE_HOST:-$HOST}"
export BS_MEDIA_TTS_SERVICE_HOST="${BS_MEDIA_TTS_SERVICE_HOST:-$HOST}"
export BS_MEDIA_COMFY_SERVICE_HOST="${BS_MEDIA_COMFY_SERVICE_HOST:-$HOST}"
export BS_MEDIA_ASR_SERVICE_PORT="$ASR_PORT"
export BS_MEDIA_TTS_SERVICE_PORT="$TTS_PORT"
export BS_MEDIA_COMFY_SERVICE_PORT="$COMFY_PORT"
export BS_MEDIA_ASR_SERVICE_BASE_URL="${BS_MEDIA_ASR_SERVICE_BASE_URL:-http://$HOST:$ASR_PORT}"
export BS_MEDIA_TTS_SERVICE_BASE_URL="${BS_MEDIA_TTS_SERVICE_BASE_URL:-http://$HOST:$TTS_PORT}"

eval "$(
python - "$CONFIG_PATH" <<'PY'
import shlex
import sys

from platform_app.services.gpu_binding import load_algorithm_service_env

service_env = load_algorithm_service_env(sys.argv[1])
for key, value in service_env.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"

port_in_use() {
  local port="$1"
  python - "$HOST" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    sock.connect((host, port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
sys.exit(0)
PY
}

wait_for_json_status() {
  local url="$1"
  local expected="$2"
  local field="${3:-status}"
  local attempts="${4:-60}"
  local delay="${5:-1}"
  local attempt=0
  while [ "$attempt" -lt "$attempts" ]; do
    if python - "$url" "$expected" "$field" <<'PY'
import json
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
expected = sys.argv[2]
field = sys.argv[3]
try:
    with urllib.request.urlopen(url, timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception:
    sys.exit(1)
value = payload.get(field)
if str(value) != expected:
    sys.exit(1)
sys.exit(0)
PY
    then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep "$delay"
  done
  return 1
}

wait_for_ready() {
  local url="$1"
  local ready_key="$2"
  local attempts="${3:-60}"
  local delay="${4:-1}"
  local attempt=0
  while [ "$attempt" -lt "$attempts" ]; do
    if python - "$url" "$ready_key" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
ready_key = sys.argv[2]
try:
    with urllib.request.urlopen(url, timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception:
    sys.exit(1)
if payload.get("status") != "ready":
    sys.exit(1)
if payload.get(ready_key) is not True:
    sys.exit(1)
sys.exit(0)
PY
    then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep "$delay"
  done
  return 1
}

start_service() {
  local name="$1"
  local module="$2"
  local gpu="$3"
  local port="$4"
  local env_name="$5"
  local ready_key="$6"
  local device_env="$7"
  local log_file="$LOG_DIR/${name}.log"
  local pid_file="$PID_DIR/${name}.pid"

  if port_in_use "$port"; then
    echo "端口已被占用: $name -> $HOST:$port" >&2
    exit 1
  fi

  if [ -n "$gpu" ]; then
    nohup env PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES="$gpu" $device_env conda run --no-capture-output -n "$env_name" python -m uvicorn "$module:app" --host "$HOST" --port "$port" >"$log_file" 2>&1 &
  else
    nohup env PYTHONUNBUFFERED=1 $device_env conda run --no-capture-output -n "$env_name" python -m uvicorn "$module:app" --host "$HOST" --port "$port" >"$log_file" 2>&1 &
  fi
  local pid=$!
  echo "$pid" > "$pid_file"

  if ! wait_for_json_status "http://$HOST:$port/health" "ok"; then
    echo "$name 健康检查失败，查看日志: $log_file" >&2
    exit 1
  fi

  if ! wait_for_ready "http://$HOST:$port/ready" "$ready_key"; then
    echo "$name 就绪检查失败，查看日志: $log_file" >&2
    exit 1
  fi

  echo "$name started on $HOST:$port (pid $pid)"
}

start_service "asr" "algorithm_services.asr_service" "$ASR_GPU" "$ASR_PORT" "tts" "model_loaded" "BS_MEDIA_ASR_DEVICE=$ASR_DEVICE"
start_service "tts" "algorithm_services.tts_service" "$TTS_GPU" "$TTS_PORT" "tts" "model_loaded" "BS_MEDIA_TTS_ASR_DEVICE=$TTS_ASR_DEVICE BS_MEDIA_TTS_DEVICE=$TTS_DEVICE"
start_service "comfyui" "algorithm_services.comfy_gateway_service" "" "$COMFY_PORT" "AIGC" "comfyui_reachable" ""

echo "all algorithm services started"
