#!/bin/bash
# Author: troodon7 (https://github.com/troodon7)
# AnyDesk Probe — runs inside disposable Docker container
# Starts Xvfb + AnyDesk in standalone mode (auto-connects to target),
# parses trace log, outputs JSON.
#
# v7.x behavior: passing TARGET_ID directly starts a local-service,
# connects to the relay, and sends the connection request automatically —
# no separate --service process or GUI interaction required.
#
# Environment:
#   TARGET_ID  — AnyDesk ID to probe (required)
#   TIMEOUT    — max seconds to wait for result (default: 15)

set -euo pipefail

TARGET_ID="${TARGET_ID:?TARGET_ID environment variable is required}"
TIMEOUT="${TIMEOUT:-15}"

PROBE_USER="probeuser"
ANYDESK_DIR="/home/${PROBE_USER}/.anydesk"
TRACE_LOG="$ANYDESK_DIR/anydesk.trace"
DISPLAY_NUM=99

# --- Helpers ---

json_result() {
    local status="$1" detail="$2" elapsed="$3"
    detail="${detail//\\/\\\\}"
    detail="${detail//\"/\\\"}"
    detail="${detail//$'\n'/\\n}"
    detail="${detail//$'\r'/\\r}"
    detail="${detail//$'\t'/\\t}"
    echo "{\"id\":\"${TARGET_ID}\",\"status\":\"${status}\",\"detail\":\"${detail}\",\"elapsed_ms\":${elapsed}}"
}

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

su "$PROBE_USER" -c "DISPLAY=\":${DISPLAY_NUM}\" anydesk \"${TARGET_ID}\"" &>/dev/null &

# Wait up to 10s for trace log to appear
INIT_WAIT=0
while [ ! -f "$TRACE_LOG" ] && [ "$INIT_WAIT" -lt 20 ]; do
    sleep 0.5
    INIT_WAIT=$((INIT_WAIT + 1))
done

if [ ! -f "$TRACE_LOG" ]; then
    json_result "error" "AnyDesk failed to initialize (no trace log after 10s)" 0
    exit 1
fi

# --- Monitor trace log for result patterns ---

START_MS=$(date +%s%N | cut -b1-13)
ELAPSED=0
RESULT=""
DETAIL=""

while [ "$ELAPSED" -lt "$((TIMEOUT * 1000))" ]; do
    sleep 0.2

    LOG_CONTENT=$(cat "$TRACE_LOG" 2>/dev/null || true)

    # OFFLINE: relay confirmed the desk is not reachable
    if echo "$LOG_CONTENT" | grep -qi "Client appears to be offline\|desk not found\|connection refused"; then
        NOW_MS=$(date +%s%N | cut -b1-13)
        ELAPSED=$((NOW_MS - START_MS))
        MATCH=$(echo "$LOG_CONTENT" | grep -i "offline\|not found\|connection refused" | tail -1 | sed 's/^[[:space:]]*//' || true)
        RESULT="offline"
        DETAIL="${MATCH:-Client offline}"
        break
    fi

    # ONLINE: relay confirmed desk is reachable and connection is proceeding
    if echo "$LOG_CONTENT" | grep -qi "Connect request accepted\|tunnel route created\|Net connection established\|Received wait for accept"; then
        NOW_MS=$(date +%s%N | cut -b1-13)
        ELAPSED=$((NOW_MS - START_MS))
        MATCH=$(echo "$LOG_CONTENT" | grep -i "Connect request accepted\|tunnel route created\|Net connection established\|wait for accept" | head -1 | sed 's/^[[:space:]]*//' || true)
        RESULT="online"
        DETAIL="${MATCH:-Connection established}"
        break
    fi

    NOW_MS=$(date +%s%N | cut -b1-13)
    ELAPSED=$((NOW_MS - START_MS))
done

# --- Output result ---

if [ -z "$RESULT" ]; then
    RESULT="unknown"
    LOG_SNIP=$(tail -c 400 "$TRACE_LOG" 2>/dev/null \
               | tr '\n' '|' | tr '\t' ' ' || true)
    if [ -n "$LOG_SNIP" ]; then
        DETAIL="No pattern (${TIMEOUT}s). Log: ${LOG_SNIP}"
    else
        DETAIL="No definitive pattern within ${TIMEOUT}s (no log entries)"
    fi
fi

json_result "$RESULT" "$DETAIL" "$ELAPSED"
