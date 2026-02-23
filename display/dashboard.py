"""Rich Live dashboard for Shodesk."""

from datetime import datetime, timedelta

from rich.live import Live
from rich.table import Table
from rich.text import Text


STATUS_STYLES = {
    "online": "bold green",
    "offline": "bold red",
    "unknown": "bold yellow",
    "error": "bold magenta",
    "pending": "dim",
}


class Dashboard:
    """Real-time terminal dashboard showing target ID status."""

    def __init__(self, ids, interval, image_name):
        self.ids = ids
        self.interval = interval
        self.image_name = image_name
        self.start_time = datetime.now()
        self.live = None

        # Per-ID state
        self.state = {}
        for aid in ids:
            self.state[aid] = {
                "status": "pending",
                "remote_os": "",
                "detail": "",
                "recon": "",
                "elapsed_ms": 0,
                "last_checked": None,
                "last_online": None,
                "checks": 0,
                "online_count": 0,
            }

    def set_recon(self, aid, recon):
        """Store formatted recon data for display in the detail pane."""
        lines = [
            f"Public IP  : {recon.get('public_ip', '?')}:{recon.get('public_port', '?')}",
            f"Relay      : {recon.get('relay_id', '?')} ({recon.get('relay_ip', '?')})",
            f"FPR        : {recon.get('fpr_short', '?')}",
        ]
        for ep in recon.get("connection_candidates", []):
            lines.append(f"Endpoint   : {ep}")
        self.state[aid]["recon"] = "\n".join(lines)

    def update(self, aid, result):
        """Update state for a target ID with a probe result dict."""
        s = self.state[aid]
        s["status"] = result.get("status", "unknown")
        s["detail"] = result.get("detail", "")
        s["elapsed_ms"] = result.get("elapsed_ms", 0)
        s["last_checked"] = datetime.now()
        s["checks"] += 1

        # Extract remote OS from detail if present
        detail = result.get("detail", "")
        if detail.startswith("Remote OS: "):
            s["remote_os"] = detail.split(",")[0].replace("Remote OS: ", "")

        if s["status"] == "online":
            s["last_online"] = datetime.now()
            s["online_count"] += 1

    def _build_table(self):
        runtime = datetime.now() - self.start_time
        runtime_str = str(timedelta(seconds=int(runtime.total_seconds())))

        table = Table(
            title=f"Shodesk  |  interval: {self.interval}s  |  runtime: {runtime_str}",
            title_style="bold cyan",
            show_lines=True,
        )
        table.add_column("Target ID", style="bold", width=14)
        table.add_column("Status", width=10, justify="center")
        table.add_column("Detail", width=40)
        table.add_column("Last Online", width=20)
        table.add_column("Last Checked", width=20)

        for aid in self.ids:
            s = self.state[aid]

            status_text = Text(s["status"].upper(), style=STATUS_STYLES.get(s["status"], ""))

            last_online = ""
            if s["last_online"]:
                last_online = s["last_online"].strftime("%Y-%m-%d %H:%M:%S")

            last_checked = ""
            if s["last_checked"]:
                last_checked = s["last_checked"].strftime("%Y-%m-%d %H:%M:%S")

            recon = s.get("recon", "")
            probe_detail = s["detail"]
            if recon:
                cell_detail = recon + "\n" + "─" * 30 + "\n" + probe_detail
            else:
                cell_detail = probe_detail

            table.add_row(
                aid,
                status_text,
                cell_detail,
                last_online,
                last_checked,
            )

        return table

    def start(self):
        """Start the Live display."""
        self.live = Live(self._build_table(), refresh_per_second=2)
        self.live.start()

    def refresh(self):
        """Refresh the display with current state."""
        if self.live:
            self.live.update(self._build_table())

    def stop(self):
        """Stop the Live display."""
        if self.live:
            self.live.stop()

    def print_summary(self):
        """Print final summary stats after shutdown."""
        runtime = datetime.now() - self.start_time
        print(f"\n  Runtime: {timedelta(seconds=int(runtime.total_seconds()))}")
        print(f"  IDs monitored: {len(self.ids)}")
        for aid in self.ids:
            s = self.state[aid]
            uptime = f"{(s['online_count'] / s['checks'] * 100):.1f}%" if s["checks"] else "N/A"
            print(f"    {aid}: {s['checks']} checks, "
                  f"{s['online_count']} online, uptime {uptime}")
