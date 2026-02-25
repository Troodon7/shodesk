#!/usr/bin/env python3
"""
harvest.py — Harvest known scammer AnyDesk IDs from public sources.

Searches Reddit scam communities and GitHub for publicly posted AnyDesk IDs
associated with scam reports. Outputs a targets.txt file compatible with
monitor.py.

Usage:
    python3 harvest.py                           # interactive, cap=100
    python3 harvest.py --cap 50                  # stop after 50 IDs
    python3 harvest.py --out ~/targets.txt       # custom output path
    python3 harvest.py --sources reddit          # Reddit only
    python3 harvest.py --sources github          # GitHub only

    Ctrl+C at any time saves collected IDs and exits cleanly.
"""

import argparse
import json
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# AnyDesk IDs are 9 digits — sometimes spaced or dashed (123 456 789 / 123-456-789)
_ID_PLAIN   = re.compile(r'\b(\d{9,10})\b')
_ID_SPACED  = re.compile(r'\b(\d{3}[\s\-]\d{3}[\s\-]\d{3,4})\b')

REDDIT_SUBREDDITS = ["scambait", "Scams", "techsupport"]
REDDIT_UA = "shodesk-harvest/1.0 (github.com/Troodon7/shodesk; scammer-research)"
GITHUB_UA = "shodesk-harvest/1.0"

_stop = False


def _handle_signal(sig, frame):
    global _stop
    _stop = True
    print("\n\n  [!] Interrupted — saving what we have...")


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_ids(text: str) -> set:
    """Extract all plausible AnyDesk IDs from a text block."""
    ids = set()
    for m in _ID_PLAIN.finditer(text or ""):
        ids.add(m.group(1))
    for m in _ID_SPACED.finditer(text or ""):
        ids.add(re.sub(r"[\s\-]", "", m.group(1)))
    return ids


def fetch_json(url: str, headers: dict = None, pause: float = 0.0):
    """Fetch a URL and return parsed JSON, or None on any error."""
    if pause:
        time.sleep(pause)
    if _stop:
        return None
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("  [!] Rate-limited — waiting 60s ...")
            time.sleep(60)
        elif e.code not in (403, 404):
            print(f"  [!] HTTP {e.code} — {url}")
        return None
    except Exception as e:
        print(f"  [!] Fetch error: {e}")
        return None


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def harvest_reddit(found: set, cap: int) -> int:
    """
    Search scam subreddits for posts containing AnyDesk IDs.
    Paginates up to 5 pages (500 posts) per subreddit.
    """
    headers = {"User-Agent": REDDIT_UA}
    added = 0

    for sub in REDDIT_SUBREDDITS:
        if _stop or len(found) >= cap:
            break

        print(f"  → Reddit  r/{sub} ...")
        after = None

        for page in range(1, 6):  # max 5 pages per subreddit
            if _stop or len(found) >= cap:
                break

            url = (
                f"https://www.reddit.com/r/{sub}/search.json"
                f"?q=anydesk&restrict_sr=1&sort=new&limit=100"
                + (f"&after={after}" if after else "")
            )

            data = fetch_json(url, headers=headers, pause=2.5)
            if not data:
                break

            posts = data.get("data", {}).get("children", [])
            if not posts:
                break

            for post in posts:
                if _stop or len(found) >= cap:
                    break
                pd = post.get("data", {})
                text = f"{pd.get('title', '')} {pd.get('selftext', '')}"
                for nid in extract_ids(text) - found:
                    if len(found) >= cap:
                        break
                    found.add(nid)
                    added += 1
                    print(f"    [+] {nid:<12}  r/{sub}  (total: {len(found)})")

            after = data.get("data", {}).get("after")
            if not after:
                break

    return added


def harvest_github(found: set, cap: int) -> int:
    """
    Search GitHub issues for scam reports mentioning AnyDesk IDs.
    GitHub unauthenticated: 10 req/min, so we pause 7s between requests.
    """
    headers = {
        "User-Agent": GITHUB_UA,
        "Accept": "application/vnd.github.v3+json",
    }
    added = 0

    queries = [
        "anydesk scam",
        "anydesk scammer",
        "anydesk fraud",
    ]

    for q in queries:
        if _stop or len(found) >= cap:
            break

        print(f"  → GitHub   issues: \"{q}\" ...")

        for page in range(1, 4):  # max 3 pages per query
            if _stop or len(found) >= cap:
                break

            url = (
                f"https://api.github.com/search/issues"
                f"?q={urllib.parse.quote(q)}&per_page=100&page={page}&sort=created"
            )

            data = fetch_json(url, headers=headers, pause=7.0)
            if not data:
                break

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                if _stop or len(found) >= cap:
                    break
                text = f"{item.get('title', '')} {item.get('body', '')}"
                for nid in extract_ids(text) - found:
                    if len(found) >= cap:
                        break
                    found.add(nid)
                    added += 1
                    print(f"    [+] {nid:<12}  github  (total: {len(found)})")

    return added


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def load_existing(path: Path) -> set:
    """Read IDs already in the output file so we don't write duplicates."""
    existing = set()
    if not path.exists():
        return existing
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and re.match(r"^\d{9,10}$", line):
            existing.add(line)
    return existing


def save_targets(found: set, path: Path, sources: list, existing: set):
    new_ids = sorted(found - existing)
    if not new_ids:
        print("  No new IDs to write (all already in file or none found).")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(f"\n# Harvested {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
        f.write(f" — sources: {', '.join(sources)}\n")
        f.write(f"# {len(new_ids)} new ID(s)\n")
        for nid in new_ids:
            f.write(nid + "\n")

    print(f"  Wrote {len(new_ids)} new ID(s) → {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Harvest scammer AnyDesk IDs from public sources into targets.txt."
    )
    parser.add_argument(
        "--cap", type=int, default=100,
        help="Stop after this many unique IDs (default: 100)",
    )
    parser.add_argument(
        "--out", default="~/targets.txt",
        help="Output file (default: ~/targets.txt)",
    )
    parser.add_argument(
        "--sources", nargs="+", choices=["reddit", "github"],
        default=["reddit", "github"],
        help="Which sources to search (default: both)",
    )
    args = parser.parse_args()

    out_path = Path(args.out).expanduser()

    print(f"\n  Shodesk — ID Harvester")
    print(f"  Sources : {', '.join(args.sources)}")
    print(f"  Cap     : {args.cap} unique IDs")
    print(f"  Output  : {out_path}")
    print(f"  Ctrl+C saves and exits at any time.\n")

    existing = load_existing(out_path)
    if existing:
        print(f"  [{len(existing)} IDs already in file — duplicates will be skipped]\n")

    found: set = set()

    if "reddit" in args.sources and not _stop:
        harvest_reddit(found, args.cap)

    if "github" in args.sources and not _stop:
        harvest_github(found, args.cap)

    status = "cap reached" if len(found) >= args.cap else ("interrupted" if _stop else "complete")
    print(f"\n  {len(found)} unique ID(s) found this session  [{status}]")
    save_targets(found, out_path, args.sources, existing)
    print()


if __name__ == "__main__":
    main()
