#!/usr/bin/env bash
set -euo pipefail

LISTEN_PORT="${PORT:-80}"

unitd --no-daemon &
UNIT_PID=$!

for _ in $(seq 1 100); do
  [[ -S /var/run/control.unit.sock ]] && break
  sleep 0.1
done
if [[ ! -S /var/run/control.unit.sock ]]; then
  echo "Timed out waiting for NGINX Unit control socket" >&2
  exit 1
fi

cat > /tmp/unit.json <<EOF
{
  "listeners": {
    "*:${LISTEN_PORT}": {
      "pass": "applications/api"
    }
  },
  "applications": {
    "api": {
      "type": "python 3.11",
      "processes": 1,
      "working_directory": "/app",
      "home": "/app/.venv",
      "path": ["/app"],
      "module": "main",
      "callable": "app",
      "protocol": "asgi",
      "user": "app",
      "group": "app"
    }
  }
}
EOF

# Do not use curl -f: Unit returns 4xx/5xx with a JSON body when app load fails.
# With set -e, a failed curl would exit the script and stop the container with no visible reason.
HTTP_CODE="$(
  curl -sS -o /tmp/unit_response.txt -w "%{http_code}" -X PUT --data-binary @/tmp/unit.json \
    --unix-socket /var/run/control.unit.sock \
    http://localhost/config
)"
if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "Unit /config failed: HTTP ${HTTP_CODE}" >&2
  cat /tmp/unit_response.txt >&2 || true
  exit 1
fi

echo "NGINX Unit ASGI on *:${LISTEN_PORT} (main:app, workers user app)"

wait "$UNIT_PID"
