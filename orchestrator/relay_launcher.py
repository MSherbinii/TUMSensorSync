
import os
import subprocess
import shutil
import config as _config

# lsl_relay is installed via: pip install lsl-relay
# Discovery order:
#   1. lsl_relay_path in config.json (explicit override)
#   2. shutil.which("lsl_relay") — works when pip Scripts folder is on PATH
#   3. None — researcher must start lsl_relay manually (non-fatal)

def _find_relay() -> str | None:
    configured = _config.get("lsl_relay_path")
    if configured and os.path.exists(configured):
        return configured
    found = shutil.which("lsl_relay")
    if found:
        return found
    return None

RELAY_CMD = _find_relay()

class RelayLauncher:
    def __init__(self):
        self._process: subprocess.Popen | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def launch(self) -> bool:
        """
        Launch Pupil LSL Relay (lsl_relay) in the background.
        Returns True if launched, False if not found (non-fatal —
        researcher can start it manually or it may already be running).
        """
        if not RELAY_CMD or not os.path.exists(RELAY_CMD):
            return False
        if self.is_running:
            return True
        self._process = subprocess.Popen(
            [RELAY_CMD],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
