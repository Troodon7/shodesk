# Changelog

## 2026-02-23 — macOS compatibility

- **Platform support extended to macOS** (Docker Desktop 4.29+ with host networking beta)
- Regular poll probe switches to bridge networking on macOS — eliminates gVisor port conflicts on ports 7070 and ephemeral AnyDesk ports; relay-based detection still works
- Recon probe retains `--network=host` on macOS for real P2P/IP data capture
- Preflight on macOS checks Docker Desktop host networking setting and prints setup instructions if disabled
- macOS-specific error messages for Docker not found and daemon not running
- Dropped `--security-opt apparmor=unconfined` on macOS (AppArmor is Linux-only)
- `recon_probe.sh` now invoked via `bash` entrypoint — resilient to missing execute permission after `git clone`

## 2026-02-23 — Recon probe + auto-OSINT

- Added `docker/recon_probe.sh`: deep probe that captures public IP, device fingerprints, relay info, and P2P connection candidates
- `monitor.py` now auto-fires recon probe on first online detection per session
- Graceful shutdown with container cleanup on Ctrl+C
- Added `recon/ip_scan.py` for standalone on-demand OSINT scans

## 2026-02-23 — AnyDesk 7.1.4 compatibility

AnyDesk 7.x introduced two breaking changes from the 6.x probe approach:

1. **`/etc/anydesk` required** — Fixed by adding `mkdir -p /etc/anydesk && chmod 777 /etc/anydesk` to the Dockerfile.
2. **Auto-connect removed from CLI** — Fixed by switching to standalone mode: `anydesk TARGET_ID` without pre-starting `--service`.

New detection patterns for 7.x:
- **Online:** `Connect request accepted, tunnel route created.`
- **Offline:** `Client appears to be offline.`
