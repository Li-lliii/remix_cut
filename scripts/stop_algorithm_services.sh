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

stop_pid() {
  local pid="$1"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$pid" 2>/dev/null; then
        return 0
      fi
      sleep 0.2
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
}

find_pid_by_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$port" 2>/dev/null | head -n 1
    return 0
  fi
  ps -eo pid=,args= | awk -v pattern="--port $port" '$0 ~ /uvicorn/ && $0 ~ pattern {print $1; exit}'
}

stop_service() {
  local name="$1"
  local port="$2"
  local pid_file="$PID_DIR/${name}.pid"
  local pid=""
  local stopped_by_pid=0
  local stopped_by_port=0

  if [ -f "$pid_file" ]; then
    pid=$(cat "$pid_file")
    stop_pid "$pid"
    rm -f "$pid_file"
    stopped_by_pid=1
  fi

  while true; do
    pid=$(find_pid_by_port "$port" || true)
    if [ -z "$pid" ]; then
      break
    fi
    stop_pid "$pid"
    stopped_by_port=1
  done

  if [ "$stopped_by_pid" -eq 1 ] && [ "$stopped_by_port" -eq 1 ]; then
    echo "$name stopped by pid file and port fallback"
  elif [ "$stopped_by_pid" -eq 1 ]; then
    echo "$name stopped by pid file"
  elif [ "$stopped_by_port" -eq 1 ]; then
    echo "$name stopped by port fallback"
  else
    echo "$name not running"
  fi
}

stop_service "asr" "$ASR_PORT"
stop_service "tts" "$TTS_PORT"
stop_service "comfyui" "$COMFY_PORT"
