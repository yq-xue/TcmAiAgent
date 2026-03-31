#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PY_BIN="${PY_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-0}"

is_port_free() {
  local p="$1"
  "$PY_BIN" - "$p" <<'PY' >/dev/null 2>&1
import socket, sys
p = int(sys.argv[1])
s = socket.socket()
try:
    s.bind(("127.0.0.1", p))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}

if [ ! -d "$VENV_DIR" ]; then
  "$PY_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python -m pip install -U pip
python -m pip install -r requirements.txt

if ! is_port_free "$PORT"; then
  echo "Port $PORT is in use; searching for a free port..." >&2
  p="$PORT"
  while true; do
    p=$((p+1))
    if is_port_free "$p"; then
      PORT="$p"
      break
    fi
  done
fi

echo "Starting server on ${HOST}:${PORT}" >&2
if [ "$RELOAD" = "1" ]; then
  exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
fi
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"

