# AnyDesk OSINT Monitor

Track online/offline status of AnyDesk IDs using disposable Docker/Podman containers as probes. Each probe gets a fresh AnyDesk identity, queries one target through the AnyDesk relay network, and self-destructs — leaving no persistent footprint on your machine or the target.

**Platform:** Linux
**Tested with:** AnyDesk 7.1.4, Docker / Podman

---

## Quick Start

```bash
pip install rich          # optional — enables live dashboard
python3 monitor.py
```

The script handles everything interactively:

1. Verifies Docker/Podman is running
2. Auto-builds the probe image on first run (~3 minutes)
3. Prompts for target IDs, polling interval, timeout, and display mode
4. Shows a config summary, confirms, then starts monitoring
5. Ctrl+C for a clean shutdown with per-ID summary stats

CSV results are always written regardless of display mode.

---

## Requirements

| Requirement | Notes |
|-------------|-------|
| Linux | `--network=host` is Linux-only |
| Docker or Podman | Daemon must be running |
| Python 3.6+ | No other dependencies for log mode |
| `rich` | Optional — enables live dashboard (`pip install rich`) |

---

## How It Works

### Probe Architecture

Each poll cycle, for each target ID:

1. `docker run` spins up a fresh Ubuntu 22.04 container with Xvfb and AnyDesk 7.x
2. AnyDesk starts in **standalone mode** (`anydesk TARGET_ID`) — this auto-starts a local relay service, connects to the AnyDesk relay network, and immediately sends a connection request to the target ID
3. `probe.sh` monitors `anydesk.trace` for definitive result patterns (see below)
4. As soon as a result is detected, AnyDesk is killed and the container outputs one JSON line and exits

Each container gets a unique, ephemeral AnyDesk identity generated at runtime. No identity is reused between probes.

### Detection Patterns (AnyDesk 7.x)

The relay responds within ~1-2 seconds of the connection request:

| Status | Log pattern matched |
|--------|---------------------|
| **Online** | `anynet.any_socket - Connect request accepted, tunnel route created.` |
| **Offline** | `anynet.any_socket - Client appears to be offline.` |

These patterns were discovered through controlled recon experiments — see the [Research](#research) section below.

### Probe Output (JSON)

```json
{"id":"123456789","status":"online","detail":"... Connect request accepted, tunnel route created.","elapsed_ms":2223}
{"id":"123456789","status":"offline","detail":"... Client appears to be offline.","elapsed_ms":2662}
{"id":"111111111","status":"error","detail":"No output (exit 1) — stderr: ...","elapsed_ms":0}
```

---

## Display Modes

### Dashboard (requires `rich`)

Live terminal table with per-ID status, detail text, last online timestamp, and last checked time. Refreshes in real time as probes complete.

### Log Mode (plain text)

One line per probe result to stdout. Useful for piping or when `rich` is not installed.

```
  [08:42:01] 123456789   ONLINE     2223ms  ... tunnel route created.
  [08:42:05] 123456789   OFFLINE    2662ms  ... Client appears to be offline.
```

Both modes always append to the CSV file.

### CSV Output

Default filename: `anydesk_monitor.csv`

Columns: `timestamp, anydesk_id, status, remote_os, remote_version, detail, elapsed_ms`

> **Note:** In AnyDesk 7.x standalone mode, `remote_os` and `remote_version` are not present in the trace log for normal connection probes. These columns will be blank. The `detail` column contains the raw log line that triggered the detection.

---

## Timing

| Phase | Duration |
|-------|----------|
| Container startup | ~1–2s |
| AnyDesk → relay connection | ~1.5s |
| Offline detection | ~2.5s total |
| Online detection | ~2.5s total |
| **Total per ID** | **~3–4s** |

With 3 IDs at a 30s interval: ~10–12s probing, ~18–20s idle. Comfortable margin.

> **vs. earlier versions:** AnyDesk 6.x used a two-process approach (`--service` + GUI trigger) that took 8–15s per probe. The 7.x standalone mode is significantly faster.

---

## Networking

Containers use `--network=host`. AnyDesk requires outbound TLS to `relay-*.net.anydesk.com` on port 443. For offline targets, the relay responds immediately — no traffic ever reaches the target device. For online targets, the connection request reaches the target relay endpoint but is killed before any session is accepted.

---

## Troubleshooting

### Probe image not found after reboot

Podman images in rootless mode may not persist across reboots. `monitor.py` detects this and auto-rebuilds. If the build fails, rebuild manually:

```bash
docker build -t anydesk-probe docker/
```

### AnyDesk version update breaks probes (`unknown` result)

If AnyDesk updates its trace log format, the detection patterns will need to be updated. Signs:
- All probes return `status: unknown`
- The `detail` field shows `No pattern (Ns). Log: ...` with unfamiliar log lines

To re-derive patterns, use the recon tools (see [Research](#research)). Then update the `grep` patterns in `docker/probe.sh`.

Force a clean image rebuild after updating `probe.sh`:

```bash
docker rmi anydesk-probe
docker build -t anydesk-probe docker/
```

### `/etc/anydesk` error in container logs

AnyDesk 7.x requires `/etc/anydesk` to exist with write permissions inside the container. The Dockerfile creates this directory. If you see `Cannot access /etc/anydesk` in probe stderr, the image was built without this fix — do a clean rebuild:

```bash
docker rmi anydesk-probe
docker build -t anydesk-probe docker/
```

### Running as root inside container

The container runs AnyDesk as a non-root user (`probeuser`) because AnyDesk 7.x blocks startup when run as root. This is handled automatically by `probe.sh`.

### Podman vs Docker

This tool works with both. If you have Podman installed with the `docker` compatibility shim (`podman-docker`), no changes are needed — `monitor.py` calls `docker` which Podman intercepts. The `"Emulate Docker CLI using podman"` message in stderr is normal.

---

## Research

### Why This Approach?

AnyDesk doesn't expose online/offline status via any public API on the free tier. The initial idea was passive trace log monitoring — but recon proved that AnyDesk logs **nothing** at idle. The only way to detect status is to actively attempt a connection and parse the result.

The Docker probe approach solves the privacy problem: each connection attempt would normally expose your AnyDesk ID to the target. Disposable containers mean a fresh, ephemeral identity every probe.

### Recon Tools

`recon/` contains two scripts for re-deriving detection patterns if AnyDesk changes its trace format:

**`capture.py`** — Guided capture tool. Walks you through four test scenarios with AnyDesk open on your local machine, recording trace log lines, file changes, network connections, and process state for each:

| Scenario | What it captures |
|----------|-----------------|
| Baseline | AnyDesk idle — proves nothing is logged passively |
| Known online | Connect to a previously-seen online ID |
| New online | Connect to a never-seen online ID |
| Offline/invalid | Connect to a dead or fake ID |

Requires AnyDesk installed locally (not the Docker probe).

```bash
cd recon
python3 capture.py
```

**`analyze.py`** — Diffs captured scenarios to find messages unique to each, highlighting reliable detection candidates:

```bash
python3 analyze.py ../learning_material/recon_YYYYMMDD_HHMMSS/
python3 analyze.py ../learning_material/recon_YYYYMMDD_HHMMSS/ --verbose
python3 analyze.py ../learning_material/recon_YYYYMMDD_HHMMSS/ -o report.txt
```

### Captured Data

`learning_material/recon_20260223_000129/` contains trace data captured during the initial recon phase (AnyDesk 6.x behavior). Key findings from that session:

- **Baseline:** 0 trace lines. Passive monitoring is impossible.
- **Offline** (~270ms in 6.x): `Showing the disconnect dialog (This desk is not available.` — relay rejects instantly.
- **Online — new ID** (~1.2s in 6.x): `Remote OS: ...`, `Remote version: ...` — rich metadata.
- **Online — known ID** (~0.9s in 6.x): `Received wait for accept request`

> **Note:** These 6.x patterns are **not** used by the current probe (which targets 7.x). They are preserved as reference for the research methodology. If you need to revert to 6.x support or analyze what changed, this data is your baseline.

---

## Project Structure

```
anydesk_monitor/
├── monitor.py                  # Interactive setup + probe loop
├── requirements.txt            # pip dependencies (just rich)
├── docker/
│   ├── Dockerfile              # Ubuntu 22.04 + AnyDesk from official APT repo
│   └── probe.sh                # Container entrypoint: Xvfb → AnyDesk → trace parser → JSON
├── display/
│   ├── __init__.py
│   ├── dashboard.py            # Rich Live table display
│   └── logger.py               # CSV logger + log-mode line printer
├── recon/
│   ├── capture.py              # Guided recon capture (requires local AnyDesk)
│   └── analyze.py              # Scenario diff and pattern analyzer
└── learning_material/
    └── recon_20260223_000129/  # Trace data from initial 6.x recon session
        ├── 00_baseline/
        ├── known_online/
        ├── new_online/
        ├── offline_invalid/
        └── static_files/       # AnyDesk config snapshots from recon machine
```

---

## Changelog

### 2026-02-23 — AnyDesk 7.1.4 compatibility

AnyDesk 7.x introduced two breaking changes from the 6.x probe approach:

1. **`/etc/anydesk` required** — The post-install script is bypassed in the Dockerfile (to avoid systemd dependency errors), which meant this directory was never created. AnyDesk 7.x crashes on startup without it. Fixed by adding `mkdir -p /etc/anydesk && chmod 777 /etc/anydesk` to the Dockerfile.

2. **Auto-connect removed from CLI** — The old approach (`anydesk --service` + `anydesk TARGET_ID`) relied on the second command triggering an automatic connection. In 7.x, that command only opens the GUI with the ID pre-filled, waiting for a user click. Fixed by switching to **standalone mode**: running `anydesk TARGET_ID` directly (without pre-starting `--service`) causes 7.x to launch a local relay service, connect, and send the connection request automatically — no GUI interaction needed.

New detection patterns for 7.x (derived from trace analysis):
- **Online:** `Connect request accepted, tunnel route created.`
- **Offline:** `Client appears to be offline.`

Probe speed improved from ~8–15s to ~3s per ID as a side effect.

---

## Legal

This tool is for authorized security research and OSINT in controlled environments only. Only monitor systems you own or have explicit written permission to monitor. The authors are not responsible for misuse.
