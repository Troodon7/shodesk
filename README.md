# AnyDesk OSINT Monitor

Track online/offline status of AnyDesk IDs using disposable Docker/Podman containers as probes. Each probe gets a fresh AnyDesk identity, queries one target through the AnyDesk relay network, and self-destructs — leaving no persistent footprint on your machine or the target.

When a target is confirmed online, the tool automatically runs a deeper recon probe to extract the target's public IP, device fingerprint, relay assignment, and all advertised LAN/VPN endpoints.

**Platform:** Linux  
**Tested with:** AnyDesk 7.1.4, Docker / Podman

---

## Installation

### 1. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Linux | `--network=host` is Linux-only |
| Docker or Podman | Daemon must be running |
| Python 3.6+ | Standard library only for log mode |
| `rich` | Optional — enables live dashboard |

### 2. Clone and install Python dependencies

```bash
git clone https://github.com/Troodon7/anydesk-monitor.git
cd anydesk-monitor
pip install -r requirements.txt
```

> `rich` is optional. The tool runs in log mode without it.

### 3. Docker / Podman setup

**Docker** — if your user gets a permission error:
```bash
sudo usermod -aG docker $USER && newgrp docker
```

**Podman** — install the Docker compatibility shim:
```bash
sudo apt install podman-docker   # Debian/Ubuntu
```

The `"Emulate Docker CLI using podman"` message in output is normal.

### 4. Build the probe image (first run only, ~3 minutes)

The monitor builds it automatically on first run. To build manually:
```bash
docker build -t anydesk-probe docker/
```

---

## Usage

### Monitor — online/offline polling

```bash
python3 monitor.py
```

You will be prompted for:

| Prompt | Description | Default |
|--------|-------------|---------|
| Target ID(s) | Comma-separated AnyDesk IDs to monitor | — |
| Interval | Seconds between poll cycles | 30s |
| Timeout | Max seconds per probe before giving up | 10s |
| Display mode | `1` = live dashboard (requires rich), `2` = scrolling log | 1 |
| CSV output file | Path for results CSV | `anydesk_monitor.csv` |

> **Tip:** Run without `sudo` if using Podman rootless. Use an absolute path for the CSV (e.g. `~/anydesk_monitor.csv`) if the working directory is not writable.

**Stop monitoring:** `Ctrl+C` — cleanly kills all in-flight probe containers and prints a summary.

**Output files:**
- `anydesk_monitor.csv` — timestamped poll results (all cycles)
- `anydesk_monitor_recon.jsonl` — OSINT data extracted on first online detection per session

### Recon scanner — on-demand deep probe

Run a deep OSINT probe on one or more IDs without starting the full monitor:

```bash
python3 recon/ip_scan.py 123456789
python3 recon/ip_scan.py 123456789,987654321
```

**Output per online ID:**
```
  [RECON] 123456789
    Public IP  : 203.0.113.42:49677
    Relay      : 7360779b (93.184.216.34)
    FPR        : 9a77906597c8
    Endpoint   : 10.0.0.5:443
    Endpoint   : 203.0.113.42:49677
    Endpoint   : 203.0.113.42:443
```

Results saved to `~/anydesk_recon.json`.

### Debug shell — inspect a probe container manually

```bash
python3 monitor.py --debug 123456789
```

Drops into a bash shell inside a running probe container. Useful for inspecting the AnyDesk trace log directly:

```bash
# Inside the container:
bash /probe.sh                                     # run the probe manually
tail -f /home/probeuser/.anydesk/anydesk.trace    # watch live trace output
```

---

## Output Reference

### CSV columns

| Column | Description |
|--------|-------------|
| `timestamp` | ISO 8601 timestamp of the probe |
| `anydesk_id` | Target AnyDesk ID |
| `status` | `online`, `offline`, `unknown`, or `error` |
| `remote_os` | Target OS (blank in 7.x standalone mode) |
| `remote_version` | Target AnyDesk version (blank in 7.x standalone mode) |
| `detail` | Raw log line that triggered the result |
| `elapsed_ms` | Time from probe start to result |

### Recon JSONL fields

| Field | Description |
|-------|-------------|
| `public_ip` / `public_port` | Target's public IP and port as seen by the relay |
| `relay_id` / `relay_ip` | AnyDesk relay node the target is assigned to |
| `fpr_short` | Short device fingerprint (12 hex chars) |
| `fpr_full` | Full device fingerprint hash (40 hex chars, stable across reboots) |
| `connection_candidates` | All P2P endpoints advertised by target (LAN IPs, VPN ranges, public IP) |
| `timestamp` | ISO 8601 timestamp of the recon probe |

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

### Auto-Recon on First Online Detection

When an ID is first seen online, `monitor.py` fires `recon_probe.sh` which waits an additional 1.5s past the initial connection to capture P2P negotiation data. This exposes the target's full network topology without any additional connection attempts.

---

## Timing

| Phase | Duration |
|-------|----------|
| Container startup | ~1–2s |
| AnyDesk → relay connection | ~1.5s |
| Offline detection | ~2.5s total |
| Online detection | ~2.5s total |
| **Total per ID** | **~3–4s** |

With 3 IDs at a 30s interval: ~10–12s probing, ~18–20s idle.

---

## Networking

Containers use `--network=host`. AnyDesk requires outbound TLS to `relay-*.net.anydesk.com` on port 443. For offline targets, the relay responds immediately — no traffic ever reaches the target device. For online targets, the connection request reaches the target relay endpoint but is killed before any session is accepted.

---

## Troubleshooting

### "Permission denied" when running docker

Add your user to the docker group:
```bash
sudo usermod -aG docker $USER && newgrp docker
```

### Probe image not found after reboot

Podman images in rootless mode may not persist across reboots. `monitor.py` detects this and auto-rebuilds. To rebuild manually:
```bash
docker build -t anydesk-probe docker/
```

### All probes return `unknown`

AnyDesk may have updated its trace log format. Signs:
- The `detail` field shows `No pattern (Ns). Log: ...` with unfamiliar log lines

Update the `grep` patterns in `docker/probe.sh` then force a clean image rebuild:
```bash
docker rmi anydesk-probe
docker build -t anydesk-probe docker/
```

### `/etc/anydesk` error in container logs

Do a clean image rebuild:
```bash
docker rmi anydesk-probe
docker build -t anydesk-probe docker/
```

---

## Project Structure

```
anydesk_monitor/
├── monitor.py                  # Interactive setup + probe loop
├── requirements.txt            # pip dependencies
├── docker/
│   ├── Dockerfile              # Ubuntu 22.04 + AnyDesk from official APT repo
│   ├── probe.sh                # Container entrypoint: Xvfb → AnyDesk → trace parser → JSON
│   └── recon_probe.sh          # Deep recon probe: waits for P2P negotiation data
├── display/
│   ├── dashboard.py            # Rich Live table display
│   └── logger.py               # CSV logger + log-mode line printer
├── recon/
│   └── ip_scan.py              # Standalone OSINT scanner (on-demand recon)
└── reference_material/         # Local only — not committed to repo
    └── recon_20260223_000129/  # Trace data from initial recon session
```

---

## Changelog

### 2026-02-23 — Recon probe + auto-OSINT

- Added `docker/recon_probe.sh`: deep probe that captures public IP, device fingerprints, relay info, and P2P connection candidates
- `monitor.py` now auto-fires recon probe on first online detection per session
- Graceful shutdown with container cleanup on Ctrl+C
- Added `recon/ip_scan.py` for standalone on-demand OSINT scans

### 2026-02-23 — AnyDesk 7.1.4 compatibility

AnyDesk 7.x introduced two breaking changes from the 6.x probe approach:

1. **`/etc/anydesk` required** — Fixed by adding `mkdir -p /etc/anydesk && chmod 777 /etc/anydesk` to the Dockerfile.
2. **Auto-connect removed from CLI** — Fixed by switching to standalone mode: `anydesk TARGET_ID` without pre-starting `--service`.

New detection patterns for 7.x:
- **Online:** `Connect request accepted, tunnel route created.`
- **Offline:** `Client appears to be offline.`

---

## Legal

This tool is for authorized security research and OSINT in controlled environments only. Only monitor systems you own or have explicit written permission to monitor. The authors are not responsible for misuse.
