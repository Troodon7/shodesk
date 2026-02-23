#!/usr/bin/env python3
# Author: troodon7 (https://github.com/troodon7)
"""
Shodesk — Docker Probe Architecture

Monitors AnyDesk IDs for online/offline status using disposable Docker
containers. Each probe gets a fresh container (new AnyDesk ID), makes one
connection attempt, parses the trace log, and dies.

Just run it:
    python3 monitor.py
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import readline
    _HAS_READLINE = True
except ImportError:
    _HAS_READLINE = False


def _path_completer(text, state):
    """Tab-completion for file paths, honouring ~ expansion."""
    expanded = os.path.expanduser(text)
    matches = glob.glob(expanded + "*")
    matches = [m + "/" if os.path.isdir(m) else m for m in matches]
    if text.startswith("~"):
        home = os.path.expanduser("~")
        matches = ["~" + m[len(home):] if m.startswith(home) else m for m in matches]
    try:
        return matches[state]
    except IndexError:
        return None


# ── Preflight ────────────────────────────────────────────────────────────

def check_docker():
    """Verify Docker is available and running."""
    if not shutil.which("docker"):
        print("  [!] Docker not found. Install it first:")
        print("      https://docs.docker.com/engine/install/")
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return True
        stderr = result.stderr.decode(errors="replace").lower()
        if "permission denied" in stderr or "connect: permission denied" in stderr:
            print("  [!] Permission denied — current user cannot access Docker.")
            print("      Fix: add your user to the docker group then re-login:")
            print(f"      sudo usermod -aG docker $USER && newgrp docker")
            print("      Or run monitor.py with sudo.")
        elif "cannot connect" in stderr or "is the docker daemon running" in stderr:
            print("  [!] Docker daemon is not running. Start it:")
            print("      sudo systemctl start docker")
        else:
            print(f"  [!] Docker error: {result.stderr.decode(errors='replace').strip()[:200]}")
        return False
    except subprocess.TimeoutExpired:
        print("  [!] Docker daemon timed out — may be starting up, try again.")
        return False


def ensure_image(image_name):
    """Build probe image automatically if it doesn't exist."""
    result = subprocess.run(
        ["docker", "image", "inspect", image_name],
        capture_output=True, timeout=10,
    )
    if result.returncode == 0:
        print(f"  [+] Probe image '{image_name}' ready")
        return True

    docker_dir = Path(__file__).parent / "docker"
    if not docker_dir.exists():
        print(f"  [!] Docker build directory not found: {docker_dir}")
        return False

    print(f"  [*] Building probe image (first run — this takes a few minutes)...")
    try:
        subprocess.run(
            ["docker", "build", "-t", image_name, str(docker_dir)],
            check=True, timeout=600,
        )
        print(f"  [+] Image '{image_name}' built successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [!] Docker build failed (exit code {e.returncode})")
        return False


def check_rich():
    """Check if Rich is available, offer to install."""
    try:
        import rich  # noqa: F401
        return True
    except ImportError:
        return False


# ── Interactive Setup ────────────────────────────────────────────────────

def prompt(text, default=None):
    """Prompt with optional default value."""
    if default is not None:
        suffix = f" [{default}]: "
    else:
        suffix = ": "
    val = input(f"  {text}{suffix}").strip()
    if not val and default is not None:
        return str(default)
    return val


def setup():
    """Interactive setup — gather all config, return dict."""
    config = {}

    # Target IDs
    print()
    print("  Enter AnyDesk IDs to monitor (comma-separated)")
    print("  Or enter a path to a .txt file (one ID per line)")
    print("  Example: 123456789,987654321  or  ~/targets.txt")
    while True:
        if _HAS_READLINE:
            readline.set_completer(_path_completer)
            readline.set_completer_delims(" \t\n;")
            readline.parse_and_bind("tab: complete")
        raw = prompt("Target ID(s) or file path")
        if _HAS_READLINE:
            readline.set_completer(None)
        raw_expanded = str(Path(raw).expanduser()) if raw else raw
        if raw and Path(raw_expanded).is_file():
            try:
                lines = Path(raw_expanded).read_text().splitlines()
                ids = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
                print(f"  [+] Loaded {len(ids)} ID(s) from {raw_expanded}")
            except OSError as e:
                print(f"  [!] Could not read file: {e}")
                continue
        else:
            ids = [x.strip() for x in raw.split(",") if x.strip()]
        bad = [x for x in ids if not re.match(r"^\d{9,10}$", x)]
        if bad:
            print(f"  [!] Invalid ID(s): {', '.join(bad)} — must be 9-10 digits")
            continue
        if not ids:
            print("  [!] Enter at least one ID")
            continue
        config["ids"] = ids
        break

    # Interval
    print()
    while True:
        val = prompt("Seconds between probe cycles", 30)
        try:
            interval = int(val)
            if interval < 5:
                print("  [!] Minimum interval is 5 seconds")
                continue
            config["interval"] = interval
            break
        except ValueError:
            print("  [!] Enter a number")

    # Timeout
    print()
    while True:
        val = prompt("Per-probe timeout (seconds)", 10)
        try:
            timeout = int(val)
            if timeout < 3:
                print("  [!] Minimum timeout is 3 seconds")
                continue
            config["timeout"] = timeout
            break
        except ValueError:
            print("  [!] Enter a number")

    # Display mode
    print()
    has_rich = check_rich()
    if has_rich:
        print("  Display mode:")
        print("    1) dashboard — live Rich table (recommended)")
        print("    2) log       — scrolling text + CSV file")
        while True:
            val = prompt("Mode", "1")
            if val in ("1", "dashboard"):
                config["mode"] = "dashboard"
                break
            elif val in ("2", "log"):
                config["mode"] = "log"
                break
            else:
                print("  [!] Enter 1 or 2")
    else:
        print("  [*] Rich not installed — using log mode")
        print("      (pip install rich for the live dashboard)")
        config["mode"] = "log"

    # CSV output path (always, useful for both modes)
    print()
    config["output"] = prompt("CSV output file", str(Path.home() / "shodesk.csv"))

    config["image"] = "shodesk-probe"

    return config


# ── Probe Runner ─────────────────────────────────────────────────────────

def run_probe(aid, image_name, timeout):
    """Run a single Docker probe container and return the parsed result."""
    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-e", f"TARGET_ID={aid}",
                "-e", f"TIMEOUT={timeout}",
                "--network=host",
                "--security-opt", "apparmor=unconfined",
                image_name,
            ],
            capture_output=True, text=True,
            timeout=timeout + 40,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if not stdout:
            detail = f"No output (exit {result.returncode})"
            if stderr:
                # Show last 200 chars of stderr so the actual error is visible
                detail += f" — stderr: {stderr[-200:]}"
            return {
                "id": aid,
                "status": "error",
                "detail": detail,
                "elapsed_ms": 0,
            }

        # Parse last JSON line (container may emit startup noise)
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue

        return {
            "id": aid,
            "status": "error",
            "detail": f"No JSON in output: {stdout[:200]}",
            "elapsed_ms": 0,
        }

    except subprocess.TimeoutExpired:
        return {
            "id": aid,
            "status": "error",
            "detail": f"Container timed out after {timeout + 20}s",
            "elapsed_ms": 0,
        }
    except Exception as e:
        return {
            "id": aid,
            "status": "error",
            "detail": str(e),
            "elapsed_ms": 0,
        }



def run_recon_probe(aid, image_name, recon_script, timeout=20):
    """Run recon probe to extract OSINT on first online detection.

    Waits 1.5s past initial connection to capture P2P negotiation data:
    public IP, device fingerprints, relay info, and all LAN/VPN endpoints.
    Returns a dict with the parsed fields.
    """
    if not recon_script.exists():
        return {
            "id": aid,
            "status": "error",
            "detail": f"recon_probe.sh not found: {recon_script}",
        }
    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network=host",
                "--security-opt", "apparmor=unconfined",
                "-v", f"{recon_script}:/recon_probe.sh:ro",
                "-e", f"TARGET_ID={aid}",
                "-e", f"TIMEOUT={timeout}",
                "--entrypoint", "/recon_probe.sh",
                image_name,
            ],
            capture_output=True, text=True,
            timeout=timeout + 30,
        )
        stdout = result.stdout.strip()
        if not stdout:
            return {"id": aid, "status": "error", "detail": "No output from recon probe"}
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {"id": aid, "status": "error", "detail": f"No JSON: {stdout[:200]}"}
    except subprocess.TimeoutExpired:
        return {"id": aid, "status": "error", "detail": "Recon probe timed out"}
    except Exception as e:
        return {"id": aid, "status": "error", "detail": str(e)}



def cleanup_containers(image_name):
    """Kill any probe containers still running for this image."""
    try:
        r = subprocess.run(
            ["docker", "ps", "-q", "--filter", f"ancestor={image_name}"],
            capture_output=True, text=True, timeout=10,
        )
        ids = [c for c in r.stdout.strip().splitlines() if c]
        if ids:
            subprocess.run(["docker", "kill"] + ids,
                           capture_output=True, timeout=15)
    except Exception:
        pass


# ── Main ─────────────────────────────────────────────────────────────────

BANNER = """
    ╔══════════════════════════════════════════════════╗
    ║         Shodesk OSINT Monitor                    ║
    ║         Docker Probe Architecture                ║
    ╚══════════════════════════════════════════════════╝
"""


def debug_shell(image_name, target_id):
    """Drop into a bash shell inside the probe container for manual debugging."""
    print(f"\n  Launching debug shell for ID {target_id}")
    print("  Run probe manually:  bash /probe.sh")
    print("  Watch AnyDesk logs:  tail -f /home/probeuser/.anydesk/anydesk.trace")
    print("  Exit shell to quit.\n")
    subprocess.run([
        "docker", "run", "--rm", "-it",
        "-e", f"TARGET_ID={target_id}",
        "-e", "TIMEOUT=30",
        "--network=host",
        "--security-opt", "apparmor=unconfined",
        "--entrypoint", "bash",
        image_name,
    ])


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--debug", metavar="ID",
                        help="Drop into a bash shell inside the probe container for TARGET_ID")
    args, _ = parser.parse_known_args()

    print(BANNER)

    # Step 1: Preflight
    print("  ── Preflight ──")
    if not check_docker():
        sys.exit(1)
    print("  [+] Docker OK")

    image_name = "shodesk-probe"
    if not ensure_image(image_name):
        sys.exit(1)

    if args.debug:
        debug_shell(image_name, args.debug)
        sys.exit(0)

    # Step 2: Interactive setup
    print("\n  ── Setup ──")
    config = setup()

    # Recon setup
    recon_done = set()
    recon_script = Path(__file__).parent / "docker" / "recon_probe.sh"
    csv_path = Path(config["output"]).expanduser()
    recon_out = csv_path.parent / (csv_path.stem + "_recon.jsonl")

    # Step 3: Confirm and launch
    print(f"\n  ── Config ──")
    print(f"    Targets:  {', '.join(config['ids'])}")
    print(f"    Interval: {config['interval']}s")
    print(f"    Timeout:  {config['timeout']}s per probe")
    print(f"    Mode:     {config['mode']}")
    print(f"    CSV:      {config['output']}")
    print()
    confirm = prompt("Start monitoring? (y/n)", "y")
    if confirm.lower() not in ("y", "yes"):
        print("  Aborted.")
        sys.exit(0)

    # Step 4: Set up display
    display = None
    logger = None

    if config["mode"] == "dashboard":
        from display.dashboard import Dashboard
        display = Dashboard(config["ids"], config["interval"], config["image"])
        display.start()

    from display.logger import CSVLogger
    logger = CSVLogger(config["output"])

    if config["mode"] == "log":
        print(f"\n  Monitoring — Ctrl+C to stop")
        print(f"  {'=' * 70}")

    # Graceful shutdown
    shutdown = False

    def handle_signal(sig, frame):
        nonlocal shutdown
        shutdown = True
        cleanup_containers(image_name)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Step 5: Main probe loop
    cycle = 0
    try:
        while not shutdown:
            cycle += 1

            for aid in config["ids"]:
                if shutdown:
                    break

                result = run_probe(aid, config["image"], config["timeout"])

                # Always log to CSV
                logger.log(aid, result)

                # Auto-recon: run once on first online detection
                if result.get("status") == "online" and aid not in recon_done:
                    recon_done.add(aid)
                    recon = run_recon_probe(aid, config["image"], recon_script)
                    recon["timestamp"] = datetime.now().isoformat()
                    with open(recon_out, "a") as rf:
                        rf.write(json.dumps(recon) + "\n")
                    ip = recon.get("public_ip", "?")
                    fpr = recon.get("fpr_short", "?")
                    candidates = recon.get("connection_candidates", [])
                    recon_lines = [
                        f"  [RECON] {aid}",
                        f"    Public IP  : {ip}:{recon.get('public_port', '?')}",
                        f"    Relay      : {recon.get('relay_id', '?')} ({recon.get('relay_ip', '?')})",
                        f"    FPR        : {fpr}",
                    ] + [f"    Endpoint   : {ep}" for ep in candidates]
                    if display:
                        display.set_recon(aid, recon)
                    else:
                        for line in recon_lines:
                            print(line)

                if display:
                    display.update(aid, result)
                    display.refresh()
                else:
                    logger.print_line(aid, result)

            # Wait for next cycle
            waited = 0
            while waited < config["interval"] and not shutdown:
                time.sleep(1)
                waited += 1

    finally:
        cleanup_containers(image_name)
        if display:
            display.stop()
            display.print_summary()
        else:
            print(f"\n  Stopped after {cycle} cycle(s).")

        print(f"  Results saved to: {config['output']}")
        if recon_out.exists():
            print(f"  Recon data   at: {recon_out}")


if __name__ == "__main__":
    main()
