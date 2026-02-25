"""
Deep IP scan — Shodan passive lookup + nmap active stub. [BETA]
Called interactively at Ctrl+C exit when session_ips is non-empty.

Status:
  - Passive mode (Shodan API lookup): beta
  - Active mode (nmap): not yet implemented (stub only)
"""

import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

try:
    from rich.table import Table
    from rich.console import Console
    _rich = True
except ImportError:
    _rich = False


def load_shodan_key(recon_dir: Path) -> "str | None":
    key_file = recon_dir / "shodan-api.txt"
    if key_file.exists():
        try:
            key = key_file.read_text().strip()
            # Skip comment lines
            for line in key.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
        except OSError:
            pass
    try:
        key = input("  Shodan API key (Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return key if key else None


def passive_scan(ip: str, api_key: str) -> dict:
    url = f"https://api.shodan.io/shodan/host/{ip}?key={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "shodesk/1.3"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"{e.code} {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": str(e.reason)}
    except Exception as e:
        return {"error": str(e)}


def active_scan(ip: str) -> dict:
    raise NotImplementedError("Active scan coming in next release")


def _print_rich_table(results: list):
    console = Console()
    table = Table(title="Deep IP Scan Results", show_lines=True)
    table.add_column("IP", style="green")
    table.add_column("Ports", style="cyan")
    table.add_column("Org/ISP")
    table.add_column("Country")
    table.add_column("Hostnames")
    table.add_column("CVEs")
    table.add_column("Tags")

    for entry in results:
        ip = entry["ip"]
        data = entry.get("data", {})
        error = data.get("error")

        if error:
            table.add_row(f"[green]{ip}[/green]", f"[red]{error}[/red]", "", "", "", "", "")
            continue

        ports = data.get("ports", [])
        port_str = ", ".join(str(p) for p in ports[:10])
        if len(ports) > 10:
            port_str += f" +{len(ports) - 10} more"

        org = data.get("org") or data.get("isp") or "?"
        country = data.get("country_name", "?")
        hostnames = ", ".join(data.get("hostnames", [])[:3]) or "?"
        vulns = data.get("vulns", {})
        cve_count = str(len(vulns)) if vulns else "0"
        tags = ", ".join(data.get("tags", [])) or "—"

        table.add_row(ip, port_str or "—", org, country, hostnames, cve_count, tags)

    console.print(table)


def _print_plain_table(results: list):
    print(f"\n{'IP':<18} {'Ports':<30} {'Org':<25} {'Country':<15} CVEs")
    print("-" * 100)
    for entry in results:
        ip = entry["ip"]
        data = entry.get("data", {})
        error = data.get("error")
        if error:
            print(f"{ip:<18} ERROR: {error}")
            continue
        ports = data.get("ports", [])
        port_str = ",".join(str(p) for p in ports[:10])
        if len(ports) > 10:
            port_str += f"+{len(ports)-10}"
        org = (data.get("org") or data.get("isp") or "?")[:24]
        country = data.get("country_name", "?")[:14]
        vulns = len(data.get("vulns", {}))
        print(f"{ip:<18} {port_str:<30} {org:<25} {country:<15} {vulns}")


def deep_scan(ips: set, mode: str, recon_dir: Path, jsonl_path: Path):
    api_key = None
    if mode == "p":
        api_key = load_shodan_key(recon_dir)
        if not api_key:
            print("  Skipped (no key).")
            return

    results = []
    for ip in sorted(ips):
        print(f"  Scanning {ip} ...")
        try:
            if mode == "p":
                data = passive_scan(ip, api_key)
            else:
                data = active_scan(ip)
        except NotImplementedError as e:
            print(f"  [{ip}] {e}")
            continue
        except Exception as e:
            data = {"error": str(e)}

        record = {
            "type": "deep_scan",
            "ip": ip,
            "timestamp": datetime.now().isoformat(),
            "mode": "passive" if mode == "p" else "active",
            "data": data,
        }
        try:
            with open(jsonl_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            print(f"  Warning: could not write to {jsonl_path}: {e}")

        results.append({"ip": ip, "data": data})

    if not results:
        return

    print()
    if _rich:
        _print_rich_table(results)
    else:
        _print_plain_table(results)
