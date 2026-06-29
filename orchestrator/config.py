import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

_LEGACY_DEFAULT_DEVICES = [
    {"label": "Neon Gaze", "match": "type", "value": "Gaze", "required": True,
     "nominal_hz": 200, "hint": "Enable LSL in Neon Companion app on phone",
     "channels": {"gaze_x": 0, "gaze_y": 1, "pupil_left_mm": 7, "pupil_right_mm": 8}},
    {"label": "Neon Event", "match": "type", "value": "Event", "required": False,
     "hint": "Neon internal event stream (optional, recorded if present)"},
]


def load() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(
            f"config.json not found at {_CONFIG_PATH}\n"
            f"Copy config.json.template to config.json and edit it for your devices."
        )
    with open(_CONFIG_PATH) as f:
        return json.load(f)


_cfg = None


def _raw():
    global _cfg
    if _cfg is None:
        _cfg = load()
    return _cfg


def get(key, default=None):
    cfg = _raw()
    # Support nested keys via "recording.data_dir" style
    if "." in key:
        parts = key.split(".")
        node = cfg
        for p in parts:
            if isinstance(node, dict):
                node = node.get(p)
            else:
                return default
        return node if node is not None else default
    return cfg.get(key, default)


def marker_stream_name() -> str:
    return get("marker_stream_name", "UnityMarkers")


def devices() -> list:
    explicit = get("devices")
    if explicit is not None:
        return explicit

    # Legacy fallback for old configs with only polar_serial
    serial = get("polar_serial", "UNKNOWN")
    hr_name = f"HR Polar H10 {serial}"
    rr_name = f"RR Polar H10 {serial}"
    return _LEGACY_DEFAULT_DEVICES + [
        {"label": hr_name, "match": "name", "value": hr_name, "required": True,
         "nominal_hz": 1, "hint": f"Open RRStreamer -> serial must be {serial}"},
        {"label": rr_name, "match": "name", "value": rr_name, "required": True,
         "nominal_hz": 1, "hint": "Same as HR -- RRStreamer must show 'Streaming'"},
    ]


def expected_streams() -> list:
    marker = {
        "label": marker_stream_name(), "match": "name", "value": marker_stream_name(),
        "required": True, "hint": "Start the VR app on the Quest",
    }
    return [marker] + devices()


def device_by_label(label: str) -> dict | None:
    for d in devices():
        if d["label"] == label:
            return d
    return None


def gaze_device() -> dict | None:
    for d in devices():
        if d.get("match") == "type" and d.get("value") == "Gaze":
            return d
    return None


def gaze_channels() -> dict:
    dev = gaze_device()
    if dev and "channels" in dev:
        return dev["channels"]
    return {"gaze_x": 0, "gaze_y": 1, "pupil_left_mm": 7, "pupil_right_mm": 8}


def recording_dir() -> str:
    return get("recording.data_dir", get("data_dir", "../../Data/Recordings"))


def session_log_dir() -> str:
    return get("recording.session_log_dir", get("session_log_dir", "../../Data/SessionLogs/new"))


def labrecorder_cli() -> str:
    return get("recording.labrecorder_cli", get("labrecorder_cli", "bin/LabRecorderCLI.exe"))


def dropout_timeout() -> float:
    return get("timing.dropout_timeout_s", get("dropout_timeout_s", 3.0))


def auto_stop_delay() -> float:
    return get("timing.auto_stop_delay_s", get("auto_stop_delay_s", 10))
