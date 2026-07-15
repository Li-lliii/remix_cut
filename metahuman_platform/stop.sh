#!/usr/bin/env bash
# filepath: \zhouzhiboa\bs_media\.worktrees\runtime-refactor-baseline\function\remix_cut\metahuman_platform\stop.sh
set -euo pipefail

PORT="${1:-7028}"

get_pids_by_port() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti :"$PORT"
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp "( sport = :$PORT )" 2>/dev/null \
      | awk -F'pid=|,' 'NR>1 {print $2}' \
      | sort -u
  elif command -v netstat >/dev/null 2>&1; then
    netstat -ano 2>/dev/null \
      | awk -v port=":$PORT" '$4 ~ port {print $5}' \
      | sort -u
  fi
}

PIDS="$(get_pids_by_port || true)"

if [[ -z "${PIDS:-}" ]]; then
  echo "未找到占用端口 ${PORT} 的进程"
  exit 0
fi

echo "找到占用端口 ${PORT} 的进程: ${PIDS}"
kill ${PIDS} 2>/dev/null || true
sleep 1

REMAINING="$(get_pids_by_port || true)"
if [[ -n "${REMAINING:-}" ]]; then
  echo "仍未退出，强制终止: ${REMAINING}"
  kill -9 ${REMAINING} 2>/dev/null || true
fi

echo "端口 ${PORT} 已停止"