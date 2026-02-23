"""CSV logger for Shodesk."""

import csv
import os
from datetime import datetime


HEADERS = [
    "timestamp",
    "target_id",
    "status",
    "remote_os",
    "remote_version",
    "detail",
    "elapsed_ms",
]


class CSVLogger:
    """Append-mode CSV logger for probe results."""

    def __init__(self, path):
        self.path = path
        self._write_header_if_needed()

    def _write_header_if_needed(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            with open(self.path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(HEADERS)

    def log(self, aid, result):
        """Append one probe result to CSV."""
        detail = result.get("detail", "")

        # Parse remote OS and version from detail string
        remote_os = ""
        remote_version = ""
        if "Remote OS: " in detail:
            parts = detail.split(", ")
            for part in parts:
                if part.startswith("Remote OS: "):
                    remote_os = part.replace("Remote OS: ", "")
                elif part.startswith("Version: "):
                    remote_version = part.replace("Version: ", "")

        row = [
            datetime.now().isoformat(),
            aid,
            result.get("status", "unknown"),
            remote_os,
            remote_version,
            detail,
            result.get("elapsed_ms", 0),
        ]

        with open(self.path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)

    def print_line(self, aid, result):
        """Print a summary line to stdout (for log mode)."""
        status = result.get("status", "unknown").upper()
        detail = result.get("detail", "")
        elapsed = result.get("elapsed_ms", 0)
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] {aid}  {status:8s}  {elapsed:5d}ms  {detail}")
