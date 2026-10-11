#!/usr/bin/env bash
# Expose the local API (docker compose, 127.0.0.1:5055) to a phone over HTTPS with a
# Cloudflare quick tunnel: free, no account, no ATS exceptions. The URL changes every run:
# paste the printed URL into the app's Debug "API base URL" setting.
# Usage: scripts/demo_tunnel.sh [port]     (Ctrl-C stops the tunnel)
set -euo pipefail
# http2 (TCP 443) by default: QUIC (UDP 7844) is blocked on many networks, including this one
# ("tls: no application protocol"). Override with TUNNEL_PROTOCOL=quic|auto.
PORT="${1:-${API_PORT:-5055}}"
LOCAL="http://localhost:${PORT}"

command -v cloudflared >/dev/null || { echo "cloudflared not found: brew install cloudflared" >&2; exit 1; }
curl -fsS "${LOCAL}/health" >/dev/null || { echo "API not reachable at ${LOCAL}/health - run: docker compose up -d" >&2; exit 1; }

LOG="$(mktemp -t fwr-tunnel)"
cloudflared tunnel --no-autoupdate --protocol "${TUNNEL_PROTOCOL:-http2}" --url "${LOCAL}" >"${LOG}" 2>&1 &
PID=$!
trap 'kill ${PID} 2>/dev/null || true; rm -f "${LOG}"' EXIT INT TERM

URL=""
for _ in $(seq 1 60); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "${LOG}" | head -1 || true)"
  [ -n "${URL}" ] && break
  kill -0 "${PID}" 2>/dev/null || { echo "cloudflared exited:" >&2; cat "${LOG}" >&2; exit 1; }
  sleep 1
done
[ -n "${URL}" ] || { echo "no tunnel URL after 60 s:" >&2; cat "${LOG}" >&2; exit 1; }

# Wait for the edge connection to register, then give DNS a moment: querying the brand-new
# hostname too early gets a cached NXDOMAIN from the OS resolver for a while.
for _ in $(seq 1 60); do
  grep -q "Registered tunnel connection" "${LOG}" && break
  sleep 1
done
sleep 8
for _ in $(seq 1 30); do
  if curl -fsS "${URL}/health" >/dev/null 2>&1; then
    echo
    echo "Tunnel up:   ${URL}"
    echo "Health:      $(curl -fsS "${URL}/health")"
    echo "On the phone: Debug settings -> API base URL -> ${URL}"
    echo "Ctrl-C to stop."
    wait "${PID}"
    exit 0
  fi
  sleep 2
done
echo "tunnel ${URL} is up but ${URL}/health did not answer within 60 s" >&2
exit 1
