#!/usr/bin/env bash
set -euo pipefail

: "${AUTO_TUNNEL:=1}"
: "${TUNNEL_PROVIDER:=cloudflare}"
: "${BARTENDER_TELEGRAM_ID:=1}"
: "${DEV_TELEGRAM_USER_ID:=1}"
: "${UVICORN_HOST:=0.0.0.0}"
: "${UVICORN_PORT:=8000}"
export AUTO_TUNNEL BARTENDER_TELEGRAM_ID DEV_TELEGRAM_USER_ID UVICORN_HOST UVICORN_PORT

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p /tmp/homebar
NPM="$(command -v npm)"
PYTHON="$ROOT/.venv/bin/python"

ensure_cloudflared() {
  if command -v cloudflared >/dev/null; then
    return 0
  fi
  local dest="/usr/local/bin/cloudflared"
  if [[ ! -x "$dest" ]]; then
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" -o /tmp/cloudflared
    chmod +x /tmp/cloudflared
    sudo install -m 755 /tmp/cloudflared "$dest"
  fi
}
ensure_cloudflared

if [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  (cd "$ROOT/frontend" && "$NPM" run build)
fi

cat > /tmp/homebar/api.sh << LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
export AUTO_TUNNEL=$(printf '%q' "$AUTO_TUNNEL")
export TUNNEL_PROVIDER=$(printf '%q' "${TUNNEL_PROVIDER:-auto}")
export BOT_UPDATES_MODE=$(printf '%q' "${BOT_UPDATES_MODE:-auto}")
export BARTENDER_TELEGRAM_ID=$(printf '%q' "$BARTENDER_TELEGRAM_ID")
export DEV_TELEGRAM_USER_ID=$(printf '%q' "$DEV_TELEGRAM_USER_ID")
export BOT_TOKEN=$(printf '%q' "${BOT_TOKEN:-}")
export WEBAPP_URL=$(printf '%q' "${WEBAPP_URL:-}")
cd $(printf '%q' "$ROOT/backend")
exec $(printf '%q' "$PYTHON") -m uvicorn app.main:app --host $(printf '%q' "$UVICORN_HOST") --port $(printf '%q' "$UVICORN_PORT")
LAUNCHER
cat > /tmp/homebar/web.sh << LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
cd $(printf '%q' "$ROOT/frontend")
exec $(printf '%q' "$NPM") run dev
LAUNCHER
chmod 700 /tmp/homebar/api.sh /tmp/homebar/web.sh

if ! curl -sf "http://127.0.0.1:${UVICORN_PORT}/api/health" >/dev/null 2>&1; then
  tmux kill-session -t homebar-api 2>/dev/null || true
  tmux new-session -d -s homebar-api "exec /bin/bash /tmp/homebar/api.sh >> /tmp/homebar/api.log 2>&1"
fi

if ! curl -sf "http://127.0.0.1:5173" >/dev/null 2>&1; then
  tmux kill-session -t homebar-web 2>/dev/null || true
  tmux new-session -d -s homebar-web "exec /bin/bash /tmp/homebar/web.sh >> /tmp/homebar/web.log 2>&1"
fi

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${UVICORN_PORT}/api/health" >/dev/null 2>&1 \
    && curl -sf "http://127.0.0.1:5173" >/dev/null 2>&1; then
    exit 0
  fi
  sleep 1
done

echo "Djinn Antonic did not become ready" >&2
echo "--- api.log ---" >&2
tail -n 80 /tmp/homebar/api.log >&2 || true
echo "--- web.log ---" >&2
tail -n 80 /tmp/homebar/web.log >&2 || true
exit 1
