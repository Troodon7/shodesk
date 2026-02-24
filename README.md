# Shodesk

Track online/offline status of AnyDesk IDs using disposable Docker containers as probes. Each probe gets a fresh AnyDesk identity, queries one target through the AnyDesk relay network, and self-destructs — leaving no persistent footprint on your machine or the target.

When a target is confirmed online, the tool automatically runs a deeper recon probe to extract the target's public IP, device fingerprint, relay assignment, and all advertised LAN/VPN endpoints.

**Platform:** Linux, macOS (Docker Desktop 4.29+)

## Tested Versions

| Environment | Version | Notes |
|-------------|---------|-------|
| Parrot Security (Linux) | 7.1 "echo" | Podman rootless; primary dev/test environment |
| Ubuntu 22.04 LTS (Linux) | 22.04 | Docker; also used as container base image |
| macOS | *(not yet tested — placeholder)* | Docker Desktop 4.29+ required |
| BlackArch (Lite / Full) | *(untested)* | Arch-based; Docker via `pacman -S docker`; AppArmor not present but flag is safely ignored |
| AnyDesk | 7.1.4 | Probe target; patterns may differ on other versions |

---

## Installation

### 1. Prerequisites

| Requirement | Linux | macOS |
|-------------|-------|-------|
| Docker | Daemon running, user in `docker` group | Docker Desktop 4.29+ |
| Python 3.6+ | Standard library only for log mode | Same |
| `rich` | **Bundled** — no install needed (`packages/` ships with repo) | Same |

**macOS additional requirement:** Docker Desktop's beta host networking feature must be enabled for the recon probe to capture real P2P/IP data:

> Docker Desktop → Settings → Resources → Network → **Enable host networking** → Apply & Restart

Without it, regular online/offline polling still works, but the recon probe will return empty IP/FPR fields.

### 2. Clone

```bash
git clone https://github.com/Troodon7/shodesk.git
cd shodesk
```

> No dependencies to install. `rich` is bundled in `packages/` and loaded automatically at startup.

### 3. Docker setup

**Linux** — if your user gets a permission error:
```bash
sudo usermod -aG docker $USER && newgrp docker
```

**macOS** — open Docker Desktop and verify it shows "Engine running" in the menu bar.

### 4. Build the probe image (first run only, ~3 minutes)

The monitor builds it automatically on first run. To build manually:
```bash
docker build -t shodesk-probe docker/
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
| Target ID(s) or file path | Comma-separated AnyDesk IDs **or** path to a `.txt` file (one ID per line) | — |
| Interval | Seconds between poll cycles | 30s |
| Timeout | Max seconds per probe before giving up | 10s |
| Display mode | `1` = live dashboard (requires rich), `2` = scrolling log | 1 |
| CSV output file | Path for results CSV | `shodesk.csv` |

**Importing IDs from a file:**
```
# targets.txt — lines starting with # are ignored
123456789
987654321

555666777
```
```bash
  Target ID(s) or file path: ~/targets.txt
  [+] Loaded 3 ID(s) from /home/user/targets.txt
```

**Stop monitoring:** `Ctrl+C` — cleanly kills all in-flight probe containers and prints a summary.

**Output files:**
- `shodesk.csv` — timestamped poll results (all cycles)
- `shodesk_recon.jsonl` — OSINT data extracted on first online detection per session

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

Results saved to `~/shodesk_recon.json`.

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
| `target_id` | Target AnyDesk ID |
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

### Linux

All containers use `--network=host`. AnyDesk requires outbound TLS to `relay-*.net.anydesk.com` on port 443. For offline targets, the relay responds immediately — no traffic ever reaches the target device. For online targets, the connection request reaches the target relay endpoint but is killed before any session is accepted.

### macOS

Docker Desktop's gVisor network stack isolates containers from the Mac's real network interfaces. To work around this, two different networking modes are used:

| Probe | Network mode | Why |
|-------|-------------|-----|
| Regular poll (`probe.sh`) | Bridge (default) | Relay-based online/offline detection works through Docker Desktop NAT — no host port conflicts |
| Recon (`recon_probe.sh`) | `--network=host` | Requires Docker Desktop host networking (beta) to participate in P2P NAT negotiation and capture the target's real public IP and fingerprint |

Using bridge for the regular probe avoids port conflicts caused by Docker Desktop's gVisor proxy holding onto AnyDesk's ports (7070, ephemeral) between sequential container runs.

---

## Troubleshooting

### "Permission denied" when running docker (Linux)

Add your user to the docker group:
```bash
sudo usermod -aG docker $USER && newgrp docker
```

### macOS: recon returns empty IP/FPR fields

The recon probe uses `--network=host` to participate in P2P NAT negotiation. Without Docker Desktop's beta host networking enabled, the container sees the Linux VM's network instead of the Mac's real interfaces, so P2P fails and no OSINT data is captured.

Enable it: Docker Desktop → Settings → Resources → Network → **Enable host networking** → Apply & Restart

### macOS: "Docker daemon is not running"

Open Docker Desktop from your Applications folder and wait for the engine to start before re-running `monitor.py`.

### Checking and removing the probe image

The probe image persists on disk between runs — containers are destroyed after each probe but the image stays until you delete it. To check if it exists:
```bash
docker images shodesk-probe
```

To remove it from disk:
```bash
docker rmi shodesk-probe
```

The next run of `monitor.py` will rebuild it automatically (~3 minutes).

### All probes return `unknown`

AnyDesk may have updated its trace log format. Signs:
- The `detail` field shows `No pattern (Ns). Log: ...` with unfamiliar log lines

Update the `grep` patterns in `docker/probe.sh` then force a clean image rebuild:
```bash
docker rmi shodesk-probe
docker build -t shodesk-probe docker/
```

### `/etc/anydesk` error in container logs

Do a clean image rebuild:
```bash
docker rmi shodesk-probe
docker build -t shodesk-probe docker/
```

---

## Project Structure

```
shodesk/
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
├── docs/
│   └── CHANGELOG.md            # Version history
└── reference_material/         # Local only — not committed to repo
```

---

## Roadmap / TODO

- [ ] **TeamViewer support** — explore TeamViewer as a monitoring target alongside AnyDesk
- [ ] **Test on macOS** — Docker Desktop 4.29+; verify recon P2P/IP capture with host networking enabled
- [ ] **Test on BlackArch** — Lite and Full; confirm Docker setup and `apparmor=unconfined` no-op behaviour

---

## Changelog

See [docs/CHANGELOG.md](docs/CHANGELOG.md) for full version history.

---

## Legal

This tool is for authorized security research and OSINT in controlled environments only. Only monitor systems you own or have explicit written permission to monitor. The authors are not responsible for misuse.
