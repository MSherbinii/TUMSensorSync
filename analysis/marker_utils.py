#!/usr/bin/env python3
"""
marker_utils.py — shared helper for resolving the configured Unity marker
stream name across all analysis scripts. Reads marker_stream_name from
orchestrator/config.json if available, falls back to "UnityMarkers".
"""
import os
import sys

def _load_marker_stream_name() -> str:
    orchestrator_dir = os.path.join(os.path.dirname(__file__), "..", "orchestrator")
    sys.path.insert(0, orchestrator_dir)
    try:
        import config as _config
        return _config.marker_stream_name()
    except Exception:
        return "UnityMarkers"

MARKER_STREAM_NAME = _load_marker_stream_name()

def find_marker_stream_key(streams: dict):
    """streams: {stream_name: data} dict, as built by load_streams() in
    align_session.py / validate_and_align.py / debug_timing.py."""
    return next((k for k in streams if MARKER_STREAM_NAME in k), None)

def find_marker_stream_raw(streams: list):
    """streams: raw pyxdf.load_xdf() stream list."""
    return next((s for s in streams if MARKER_STREAM_NAME in s["info"]["name"][0]), None)
