import os
import subprocess
from datetime import datetime
import config as _config

_BASE = os.path.dirname(__file__)
CLI_EXE  = os.path.join(_BASE, _config.labrecorder_cli())
DATA_DIR = os.path.join(_BASE, _config.recording_dir())

def _build_stream_selectors() -> list:
    # LabRecorderCLI syntax: LabRecorderCLI.exe outputfile.xdf 'pred1' 'pred2' ...
    # One predicate per stream (marker stream + every configured device, required
    # or not -- optional streams are recorded when present but never block startup).
    return [f'{spec["match"]}="{spec["value"]}"' for spec in _config.expected_streams()]

class Recorder:
    def __init__(self, participant_id: str):
        self._participant_id = participant_id
        self._process: subprocess.Popen | None = None
        self._current_file: str = ""
        self._segment = 0

    @property
    def is_recording(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def current_file(self) -> str:
        return self._current_file

    def start(self) -> str:
        """Start a new recording segment. Returns the output file path."""
        if not os.path.exists(CLI_EXE):
            raise FileNotFoundError(
                f"LabRecorderCLI.exe not found at {CLI_EXE}\n"
                f"See Tools/session_orchestrator/setup.md for instructions."
            )

        os.makedirs(DATA_DIR, exist_ok=True)
        self._segment += 1
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        suffix = f"_part{self._segment}" if self._segment > 1 else ""
        filename = f"{self._participant_id}_{timestamp}{suffix}.xdf"
        self._current_file = os.path.join(DATA_DIR, filename)

        # LabRecorderCLI positional syntax: outputfile.xdf ['pred1' 'pred2' ...]
        # No predicates = record all visible LSL streams
        args = [CLI_EXE, self._current_file] + _build_stream_selectors()

        self._process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self._current_file

    def stop(self) -> None:
        """Stop the current recording cleanly."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
