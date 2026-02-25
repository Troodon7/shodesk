# Shodesk

Active reconnaissance tool for AnyDesk IDs. Probes targets through the AnyDesk relay network using disposable Docker containers — each probe gets a fresh ephemeral identity, makes one connection attempt, and self-destructs.

**This is active recon, with a targeted OSINT tool as an option.** Confirming a target is online requires establishing a live relay tunnel to their device. When a target is first seen online, a deeper probe extracts their public IP, device fingerprint, relay assignment, and all advertised LAN/VPN endpoints from that live connection.

The only OSINT component is `harvest.py`, which discovers AnyDesk IDs passively from public scam reports on Reddit and GitHub — you can do this before any probing begins to get a list for testing but that is risky given the nature of the discovery, use at your own risk.

**Platform:** Linux, macOS (Docker Desktop 4.29+)

## Monitor Tested Versions

| Environment | Version | Notes |
|-------------|---------|-------|
| Parrot Security (Linux) | 7.1 "echo" | Podman rootless; primary dev/test environment |
| Ubuntu 22.04 LTS (Linux) | 22.04 | Docker; also used as container base image |
| macOS | *(Apple silicon 26.3)* | Docker Desktop 4.29+ required |
| BlackArch (Lite / Full) | *(untested)* | Arch-based; Docker via `pacman -S docker`; AppArmor not present but flag is safely ignored |
| AnyDesk | 7.1.4 | Probe target; patterns may differ on other versions |

## Harvestor

| Environment | Version | Notes |
|-------------|---------|-------|
| Parrot Security (Linux) | 7.1 "echo" | Podman rootless; primary dev/test environment |
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

### Harvester — discover scammer IDs (optional first step)

```bash
python3 harvest.py
```

Searches Reddit scam communities (r/scambait, r/Scams, r/techsupport) and GitHub issues for publicly posted AnyDesk IDs associated with scam reports. Results are written to `~/targets.txt` ready for `monitor.py` to consume.

| Flag | Default | Description |
|------|---------|-------------|
| `--cap N` | 100 | Stop after N unique IDs |
| `--out PATH` | `~/targets.txt` | Output file |
| `--sources reddit github` | both | Limit to specific sources |

```bash
python3 harvest.py --cap 200 --sources reddit     # Reddit only, up to 200 IDs
python3 harvest.py --out ~/scammer_ids.txt         # custom output path
```

**Ctrl+C** at any point saves whatever has been collected so far and exits cleanly.

> **Note:** This pulls from public posts where victims or scambaiters have documented scammer IDs. IDs are not verified — some may be stale or reassigned. The monitor will quickly establish which are currently online.

---

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

**Output files** (in `~/shodesk-logs/`):
- `shodesk_YYYYMMDD_HHMMSS.csv` — timestamped poll results (all cycles)
- `shodesk_YYYYMMDD_HHMMSS_recon.jsonl` — recon data extracted on first online detection per session

### Recon scanner — on-demand deep probe

Run a deep recon probe on one or more IDs without starting the full monitor:

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

Results saved to `~/shodesk-logs/recon_YYYYMMDD_HHMMSS.json`.

### Deep IP Scan — Shodan lookup at exit (opt-in)

When you stop monitoring with `Ctrl+C`, if any targets came online during the session, you will be prompted:

```
  Deep scan 2 discovered IP(s)?
    [P] Passive — Shodan API lookup
    [A] Active  — nmap port scan (sends packets)
    [N] Skip
  Choice [P/A/N]:
```

> **Active vs. passive warning:** Neither mode is fully passive. The public IPs were obtained by actively connecting to the target through the AnyDesk relay — a live tunnel was established to extract them. Shodan lookup (`P`) is a read-only query against Shodan's pre-existing scan database and sends no packets to the target. nmap (`A`) sends packets directly to the target's IP and is fully active. Use both with appropriate authorization.

**Setting up a Shodan API key (optional):**

Create `recon/shodan-api.txt` with your key on a single line:
```bash
cp recon/shodan-api.txt.example recon/shodan-api.txt
# Edit the file and replace YOUR_KEY_HERE with your actual key
```

If the file is absent or empty, the tool will prompt for a key at runtime. Get a free key at [account.shodan.io](https://account.shodan.io).

> `recon/shodan-api.txt` is in `.gitignore` and will never be committed.

**Output:** Results are printed as a table and appended to the session `_recon.jsonl` file as records with `"type": "deep_scan"`.

---

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

### monitor.py flags

| Flag | Description |
|------|-------------|
| *(none)* | Interactive setup — prompts for targets, interval, timeout, display mode, and output path |
| `--online` | Poll online/offline status only — skips deep recon on first detection and the Shodan exit prompt |
| `--debug ID` | Drop into a bash shell inside a probe container for the given ID (for development/inspection) |

---

## Output Reference

### CSV columns

| Column | Description |
|--------|-------------|
| `timestamp` | ISO 8601 timestamp of the probe |
| `target_id` | Target AnyDesk ID |
| `status` | `online` — relay confirmed target is reachable; `offline` — relay confirmed unreachable; `unknown` — no relay response before timeout (ID likely stale or unregistered); `error` — AnyDesk failed to initialize |
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

**Deep scan records** (appended at exit, `"type": "deep_scan"`):

| Field | Description |
|-------|-------------|
| `type` | Always `"deep_scan"` |
| `ip` | The scanned public IP |
| `mode` | `"passive"` (Shodan) or `"active"` (nmap) |
| `timestamp` | ISO 8601 timestamp of the scan |
| `data` | Full Shodan host object, or `{"error": "..."}` on failure |

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
| **Unknown** | No matching pattern before timeout — see below |
| **Error** | AnyDesk failed to initialize (no trace log produced) |

#### Understanding Unknown

`unknown` means the probe timed out without receiving a definitive relay response. The AnyDesk client initialized successfully (license sync, relay registration), but the relay never confirmed the target ID's status within the timeout window.

Common causes:
- **ID doesn't exist or was never registered** — the relay has no record of it and simply doesn't respond
- **Stale ID** — the ID existed but the AnyDesk install behind it is gone; the relay eventually drops it but may not respond immediately
- **Relay congestion** — occasional slow relay response; the same ID may resolve cleanly on the next cycle
- **ID in a transitional state** — device is mid-boot or AnyDesk is restarting

A persistent stream of `unknown` results for an ID (across multiple cycles) almost always means the ID is dead. IDs harvested from public scam reports go stale quickly — the detail column will show `No pattern (Ns)` to indicate how long the probe waited.

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
├── harvest.py                  # ID harvester: discovers scammer AnyDesk IDs → targets.txt
├── requirements.txt            # pip dependencies
├── docker/
│   ├── Dockerfile              # Ubuntu 22.04 + AnyDesk from official APT repo
│   ├── probe.sh                # Container entrypoint: Xvfb → AnyDesk → trace parser → JSON
│   └── recon_probe.sh          # Deep recon probe: waits for P2P negotiation data
├── display/
│   ├── dashboard.py            # Rich Live table display
│   └── logger.py               # CSV logger + log-mode line printer
├── recon/
│   ├── ip_scan.py              # Standalone recon scanner (on-demand deep probe)
│   ├── ip_deep_scan.py         # Deep IP scan: Shodan lookup + nmap stub (opt-in at exit)
│   └── shodan-api.txt.example  # API key placeholder (copy to shodan-api.txt, never committed)
├── docs/
│   └── CHANGELOG.md            # Version history
└── reference_material/         # Local only — not committed to repo
```

---

## Changelog

See [docs/CHANGELOG.md](docs/CHANGELOG.md) for full version history.

---

## Legal

This tool is for authorized security research in controlled environments only. Only monitor systems you own or have explicit written permission to monitor. The authors are not responsible for misuse.

**On the "OSINT" label:** Despite the `_recon.jsonl` filename and prior references to "OSINT," the core probe is **active reconnaissance**, not passive intelligence gathering. Every probe that confirms a target is online does so by establishing a live AnyDesk relay tunnel to the target device. IP addresses, fingerprints, and P2P endpoints are extracted from that active connection — not from public data sources. The Shodan lookup added in the deep scan feature is the only genuinely passive element (querying a pre-existing scan database), but it operates on IPs already obtained through active means. Use this tool accordingly.
