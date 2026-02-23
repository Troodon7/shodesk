#!/usr/bin/env python3
# Author: troodon7 (https://github.com/troodon7)
"""
Shodesk Recon Scanner — OSINT extraction for confirmed-online IDs

Runs a separate recon probe that waits past initial connection to capture:
  - Target's public IP and port
  - Device fingerprints (short FPR + full hash)
  - Relay server assignment (ID + IP → rough geolocation)
  - All advertised P2P connection endpoints (LAN IPs, VPN ranges, public)

Usage:
    python3 ip_scan.py
    python3 ip_scan.py 123456789
    python3 ip_scan.py 123456789 987654321
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RECON_PROBE = Path(__file__).parent.parent / "docker" / "recon_probe.sh"
IMAGE = "shodesk-probe"
TIMEOUT = 20


def run_recon(target_id: str) -> dict:
    """Run recon probe container for a single AnyDesk ID."""
    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network=host",
                "--security-opt", "apparmor=unconfined",
                "-v", f"{RECON_PROBE}:/recon_probe.sh:ro",
                "-e", f"TARGET_ID={target_id}",
                "-e", f"TIMEOUT={TIMEOUT}",
                "--entrypoint", "/recon_probe.sh",
                IMAGE,
            ],
            capture_output=True, text=True,
            timeout=TIMEOUT + 30,
        )

        stdout = result.stdout.strip()
        if not stdout:
            stderr_snip = result.stderr.strip()[-200:] if result.stderr else ""
            return {"id": target_id, "status": "error", "detail": f"No output — {stderr_snip}"}

        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue

        return {"id": target_id, "status": "error", "detail": f"No JSON: {stdout[:200]}"}

    except subprocess.TimeoutExpired:
        return {"id": target_id, "status": "error", "detail": "Container timed out"}
    except Exception as e:
        return {"id": target_id, "status": "error", "detail": str(e)}


def print_result(r: dict):
    ts = datetime.now().strftime("%H:%M:%S")
    status = r.get("status", "unknown").upper()
    aid = r.get("id", "?")

    if status != "ONLINE":
        print(f"  [{ts}] {aid}  {status}")
        if "detail" in r:
            print(f"           {r['detail']}")
        return

    print(f"\n  [{ts}] {aid}  ONLINE")
    print(f"    Public IP   : {r.get('public_ip','?')}:{r.get('public_port','?')}")
    print(f"    Relay       : {r.get('relay_id','?')}  ({r.get('relay_ip','?')})")
    print(f"    FPR (short) : {r.get('fpr_short','?')}")
    print(f"    FPR (full)  : {r.get('fpr_full','?')}")
    candidates = r.get("connection_candidates", [])
    if candidates:
        print(f"    Endpoints   :")
        for ep in candidates:
            print(f"      {ep}")
    print(f"    Elapsed     : {r.get('elapsed_ms',0)}ms")
    print()


def main():
    ids = sys.argv[1:] if len(sys.argv) > 1 else []

    if not ids:
        print("\n  Shodesk Recon Scanner")
        print("  Enter IDs to probe (comma-separated):")
        raw = input("  > ").strip()
        ids = [x.strip() for x in raw.split(",") if x.strip()]

    if not ids:
        print("  No IDs provided.")
        sys.exit(1)

    print(f"\n  Probing {len(ids)} ID(s) — timeout {TIMEOUT}s each\n")
    print(f"  {'─' * 60}")

    results = []
    for aid in ids:
        print(f"  Probing {aid}...", flush=True)
        r = run_recon(aid)
        print_result(r)
        results.append(r)

    # Save JSON
    out = Path.home() / "shodesk_recon.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Results saved to: {out}")


if __name__ == "__main__":
    main()
