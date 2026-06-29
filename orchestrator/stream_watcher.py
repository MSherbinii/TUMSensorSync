import threading
import time
from dataclasses import dataclass
from typing import Dict
import pylsl
import config as _config

DROPOUT_TIMEOUT = _config.dropout_timeout()
POLL_INTERVAL   = 1.0

@dataclass
class StreamStatus:
    name: str
    required: bool = True
    connected: bool = False
    last_seen: float = 0.0

    @property
    def dropped(self) -> bool:
        return self.last_seen > 0 and not self.connected

class StreamWatcher:
    def __init__(self):
        self._expected = {spec["label"]: spec for spec in _config.expected_streams()}
        self._statuses: Dict[str, StreamStatus] = {
            label: StreamStatus(name=label, required=spec.get("required", True))
            for label, spec in self._expected.items()
        }
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def all_connected(self) -> bool:
        with self._lock:
            return all(s.connected for s in self._statuses.values() if s.required)

    @property
    def any_dropped(self) -> bool:
        with self._lock:
            return any(s.dropped for s in self._statuses.values() if s.required)

    def get_statuses(self) -> Dict[str, StreamStatus]:
        with self._lock:
            return {k: StreamStatus(v.name, v.required, v.connected, v.last_seen)
                    for k, v in self._statuses.items()}

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            results = pylsl.resolve_streams(wait_time=0.5)
            visible_names = {s.name() for s in results}
            visible_types = {s.type() for s in results}
            with self._lock:
                for label, status in self._statuses.items():
                    spec = self._expected[label]
                    if spec["match"] == "type":
                        matched = spec["value"] in visible_types
                    else:
                        matched = spec["value"] in visible_names
                    if matched:
                        status.connected = True
                        status.last_seen = now
                    elif status.last_seen > 0 and (now - status.last_seen) > DROPOUT_TIMEOUT:
                        status.connected = False
            time.sleep(POLL_INTERVAL)
