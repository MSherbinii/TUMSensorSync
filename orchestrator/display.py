
from datetime import datetime, timedelta
from typing import Dict, Optional
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.console import Group
from rich import box

from stream_watcher import StreamStatus


def build_panel(
    participant_id: str,
    statuses: Dict[str, StreamStatus],
    status_line: str,
    recording_file: str,
    elapsed: Optional[timedelta],
    start_time: Optional[datetime],
) -> Panel:
    """Build the rich Panel rendered each tick by the Live display."""

    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column(width=4)
    table.add_column(width=32)
    table.add_column(width=12)

    for name, s in statuses.items():
        if s.connected:
            icon = Text("✓", style="bold green")
            state = Text("connected", style="green")
        elif s.last_seen > 0:
            icon = Text("⚠", style="bold yellow")
            state = Text("dropped", style="yellow")
        else:
            icon = Text("✗", style="bold red")
            state = Text("waiting", style="red")
        table.add_row(icon, Text(name), state)

    elapsed_str = str(elapsed).split(".")[0] if elapsed else "--:--:--"
    status_text = Text(f"\n{status_line}", style="bold")
    if elapsed:
        status_text.append(f"   {elapsed_str}", style="dim")

    file_text = Text()
    if recording_file:
        short = recording_file.split("\\")[-1].split("/")[-1]
        file_text = Text(f"  {short}", style="dim")

    content = Group(table, status_text, file_text)

    time_str = datetime.now().strftime("%H:%M:%S")
    title = f"THESIS VR — Session Orchestrator   [dim]{participant_id}   {time_str}[/dim]"
    return Panel(content, title=title, box=box.HEAVY)
