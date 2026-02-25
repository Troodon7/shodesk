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
                "recon_data": None,
                "elapsed_ms": 0,
                "last_checked": None,
                "last_online": None,
                "checks": 0,
                "online_count": 0,
            }

    def set_recon(self, aid, recon):
        """Store recon data dict for colored rendering in the detail pane."""
        self.state[aid]["recon_data"] = recon

    def _clean_detail(self, status, detail):
        """Reduce raw probe detail to a single readable line for display."""
        if not detail:
            return ""
        if status == "unknown":
            # "No pattern (10s). Log: ..." — drop the log dump entirely
            if detail.startswith("No pattern"):
                idx = detail.find(".")
                return detail[:idx] if idx != -1 else detail[:30]
            return detail[:50]
        if status in ("offline", "online", "error"):
            # AnyDesk log lines: "info TIMESTAMP ... module - Message."
            # Extract just the message after the last " - "
            if " - " in detail:
                clean = detail.rsplit(" - ", 1)[-1].strip().rstrip("|").strip()
                return clean[:60] if len(clean) > 60 else clean
        return detail[:60] if len(detail) > 60 else detail

    def _recon_text(self, recon_data):
        """Build a colored Rich Text block from recon data dict."""
        t = Text()
        ip = recon_data.get("public_ip", "?")
        port = recon_data.get("public_port", "?")
        t.append("Public IP  : ")
        t.append(ip, style="green")
        t.append(":")
        t.append(str(port), style="cyan")
        relay_id = recon_data.get("relay_id", "?")
        relay_ip = recon_data.get("relay_ip", "?")
        t.append(f"\nRelay      : {relay_id} (")
        t.append(relay_ip, style="green")
        t.append(")")
        t.append(f"\nFPR        : {recon_data.get('fpr_short', '?')}")
        for ep in recon_data.get("connection_candidates", []):
            t.append("\nEndpoint   : ")
            last_colon = ep.rfind(":")
            if last_colon != -1:
                t.append(ep[:last_colon], style="green")
                t.append(":")
                t.append(ep[last_colon + 1:], style="cyan")
            else:
                t.append(ep, style="green")
        return t

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

            recon_data = s.get("recon_data")
            if recon_data:
                cell_detail = self._recon_text(recon_data)
                cell_detail.append("\n" + "─" * 30 + "\n")
                cell_detail.append(s["detail"])
            else:
                cell_detail = self._clean_detail(s["status"], s["detail"])

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
