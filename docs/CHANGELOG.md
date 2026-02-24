# Changelog

---

## v1.3 — Security hardening + session log files

**Security fixes**
- `ip_scan.py`: added ID validation (9–10 digits) matching monitor.py — was missing entirely
- `monitor.py`: validate `--debug` ID argument before passing to container
- `probe.sh` / `recon_probe.sh`: quote `${TARGET_ID}` in anydesk invocation
- `probe.sh`: escape newlines, carriage returns, and tabs in JSON output
- Output files now created with permissions 600 (no longer world-readable)
- Fixed timeout error message: reported +20s, actual was +40s

**Session log files**
- Each run creates new timestamped files — no more appending to a single growing CSV
- Default output directory: `~/shodesk-logs/`
- CSV: `~/shodesk-logs/shodesk_YYYYMMDD_HHMMSS.csv`
- Recon JSONL: `~/shodesk-logs/shodesk_YYYYMMDD_HHMMSS_recon.jsonl`
- `ip_scan.py` recon output: `~/shodesk-logs/recon_YYYYMMDD_HHMMSS.json`
- Directory created automatically on first run

---

## v1.2 — Vendored dependencies; no pip required

- **`rich` bundled in `packages/`** — loaded automatically at startup via `sys.path`, no install step needed
- **`requirements.txt` removed** — modern distros (Arch, Debian, Ubuntu 23+) enforce PEP 668 externally-managed environments, which blocks system-wide `pip install` and demands `--break-system-packages` to override. Rather than fight the package manager, the dependency ships with the repo. Clone and run.

---

## v1.1 — CSV target file support

- **Target file input** — `.csv` files now accepted alongside `.txt`; first column is used, header rows and non-numeric values silently skipped
- `.txt` behavior unchanged — one ID per line, `#` comments supported

---

## v1.0 — Initial release

**Core monitor**
- Online/offline polling loop with configurable interval and timeout
- Disposable Docker/Podman probe containers — fresh AnyDesk identity per probe, zero persistent footprint
- Live dashboard (requires `rich`) and scrolling log mode
- CSV output with timestamped poll results
- Comma-separated IDs or `.txt` file import (one ID per line, `#` comments)
- Ctrl+C graceful shutdown with container cleanup and session summary

**Recon probe**
- Auto-fires on first online detection per session
- Extracts public IP, relay ID/IP, short and full device fingerprint, all P2P connection candidates
- Standalone `recon/ip_scan.py` for on-demand OSINT without starting the full monitor
- Output saved to `shodesk_recon.jsonl`

**AnyDesk 7.x compatibility**
- Switched to standalone mode (`anydesk TARGET_ID`) — auto-connect via `--service` removed in 7.x
- Added `/etc/anydesk` directory creation to Dockerfile (required by 7.x)
- Detection patterns: `Connect request accepted, tunnel route created.` (online) / `Client appears to be offline.` (offline)
- Tested with AnyDesk 7.1.4

**macOS compatibility**
- Docker Desktop 4.29+ supported (host networking beta required for recon)
- Regular poll probe uses bridge networking on macOS — avoids gVisor port conflicts on AnyDesk ports
- Recon probe uses `--network=host` on macOS for real P2P/IP capture
- Preflight check warns if Docker Desktop host networking is disabled
- AppArmor flags dropped on macOS (Linux-only)

---

## TODO

- [ ] **TeamViewer support** — explore TeamViewer as a monitoring target alongside AnyDesk
- [ ] **Test on macOS** — Docker Desktop 4.29+; verify recon P2P/IP capture with host networking enabled
- [ ] **Test on BlackArch** — Lite and Full; confirm Docker setup and `apparmor=unconfined` no-op behaviour
