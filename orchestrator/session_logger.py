
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "Data", "Logs")

def _log_path() -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    return os.path.join(LOG_DIR, f"session_{datetime.now().strftime('%Y-%m-%d')}.log")

def log(event: str) -> None:
    """Append a timestamped event line to today's log file."""
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {event}\n"
    with open(_log_path(), "a", encoding="utf-8") as f:
        f.write(line)
