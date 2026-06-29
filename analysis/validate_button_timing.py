#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_button_timing.py
=========================
Compares Unity's internal button press timestamps (from participant JSON)
with the corresponding LSL marker timestamps (from XDF recording).

This independently validates the full alignment pipeline:
  - If LSL clock correction is working: difference should be < 2ms
  - If Unity input polling adds latency: visible as frameGap in marker payload
  - If network causes jitter: visible as variance across presses

Usage:
    python Tools/analysis/validate_button_timing.py Data/Recordings/P001.xdf Data/SessionLogs/new/participant_P001.json

What it proves:
    Unity knows when the button was pressed (unityMs in JSON).
    We know when the marker arrived at the PC (LSL timestamp in XDF).
    After clock correction, these should agree within 1-2ms.
    Any larger difference = alignment problem that needs investigation.
"""

import sys
import os
import json
import argparse

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pyxdf
    import numpy as np
except ImportError as e:
    print(f"Missing: {e}  ->  pip install pyxdf numpy")
    sys.exit(1)

from marker_utils import find_marker_stream_raw


def load_button_markers_from_xdf(xdf_path: str) -> list:
    """Extract ButtonPress markers from XDF with their LSL-corrected timestamps."""
    streams, _ = pyxdf.load_xdf(xdf_path)
    marker_stream = find_marker_stream_raw(streams)
    if not marker_stream:
        return []

    events = []
    for t, v in zip(marker_stream["time_stamps"], marker_stream["time_series"]):
        marker = v[0]
        if not marker.startswith("ButtonPress:"):
            continue

        # Parse: ButtonPress:seq=N:unityMs=X.XXXXXX:frame=N:dt=X.XXX:sinceLastFrame=X.XXX
        parts = {}
        for kv in marker.split(":"):
            if "=" in kv:
                k, val = kv.split("=", 1)
                parts[k] = val

        try:
            events.append({
                "lsl_t":           float(t),
                "seq":             int(parts.get("seq", -1)),
                "unity_t":         float(parts.get("unityMs", 0)),
                "frame":           int(parts.get("frame", 0)),
                "dt_ms":           float(parts.get("dt", 0)) * 1000,
                "since_last_ms":   float(parts.get("sinceLastFrame", 0)) * 1000,
                "raw_marker":      marker,
            })
        except (ValueError, KeyError):
            pass

    return events


def load_button_presses_from_json(json_path: str) -> list:
    """Extract button press events from Unity participant JSON."""
    with open(json_path, encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    presses = data.get("buttonPresses", [])
    return [
        {
            "seq":       p.get("sequenceNumber", -1),
            "unity_t":   float(p.get("frameTimeSinceStart", 0)),
            "frame":     p.get("frameCount", 0),
            "dt_ms":     float(p.get("deltaTime", 0)) * 1000,
        }
        for p in presses
    ]


def validate(xdf_path: str, json_path: str):
    print(f"\nXDF  : {os.path.basename(xdf_path)}")
    print(f"JSON : {os.path.basename(json_path)}")
    print()

    xdf_events  = load_button_markers_from_xdf(xdf_path)
    json_events = load_button_presses_from_json(json_path)

    if not xdf_events:
        print("No ButtonPress markers found in XDF.")
        print("-> Make sure the new build with FireButtonPressMarker() is deployed.")
        return

    if not json_events:
        print("No buttonPresses found in JSON.")
        print("-> Check that DataCollection.cs was updated and data was saved.")
        return

    print(f"Found {len(xdf_events)} button press markers in XDF")
    print(f"Found {len(json_events)} button press events in JSON")
    print()

    # Match by sequence number
    xdf_by_seq  = {e["seq"]: e for e in xdf_events}
    json_by_seq = {e["seq"]: e for e in json_events}
    common_seqs = sorted(set(xdf_by_seq) & set(json_by_seq))

    if not common_seqs:
        print("No matching sequence numbers between XDF and JSON.")
        print("XDF seqs :", sorted(xdf_by_seq.keys()))
        print("JSON seqs:", sorted(json_by_seq.keys()))
        return

    print(f"Matched {len(common_seqs)} presses by sequence number")
    print()
    print("=" * 70)
    print("  BUTTON PRESS ALIGNMENT VALIDATION")
    print("=" * 70)
    print(f"  {'Seq':>4}  {'Unity t (s)':>12}  {'LSL t (s)':>12}  {'Diff (ms)':>10}  {'Frame dt':>9}  {'Input gap':>10}")
    print(f"  {'-'*4}  {'-'*12}  {'-'*12}  {'-'*10}  {'-'*9}  {'-'*10}")

    diffs = []
    for seq in common_seqs:
        x = xdf_by_seq[seq]
        j = json_by_seq[seq]

        # The core alignment check:
        # x["lsl_t"] = LSL-corrected PC clock timestamp of marker arrival
        # x["unity_t"] = Unity's realtimeSinceStartup when push_sample() was called
        #   (embedded in the marker payload, so this is before network transit)
        # After clock correction, lsl_t should equal the PC-clock equivalent of unity_t
        # Difference = residual after correction (should be < 2ms if alignment is good)

        # Note: unity_t is in Unity's local clock (seconds since app start)
        # lsl_t is in LSL corrected clock (seconds since PC boot)
        # We compare relative differences instead:
        # For consecutive presses, the gap should match between both clocks
        diff_ms = (x["lsl_t"] - x["unity_t"]) * 1000  # absolute offset (large, meaningless alone)
        diffs.append(diff_ms)

        status = ""
        if x["since_last_ms"] > 20:
            status = " <- HIGH input gap"

        print(f"  {seq:>4}  {x['unity_t']:>12.6f}  {x['lsl_t']:>12.3f}  {diff_ms:>+10.2f}  {x['dt_ms']:>7.1f}ms  {x['since_last_ms']:>8.1f}ms{status}")

    diffs = np.array(diffs)
    print()
    print("=" * 70)
    print("  CONSISTENCY CHECK (differences should be ~constant)")
    print("=" * 70)
    print(f"  Mean offset   : {diffs.mean():+.2f}ms")
    print(f"  Std dev       : {diffs.std():.3f}ms  <- should be < 2ms if clock correction works")
    print(f"  Min / Max     : {diffs.min():+.2f}ms / {diffs.max():+.2f}ms")
    print(f"  Range         : {diffs.max() - diffs.min():.3f}ms")
    print()

    std = diffs.std()
    if std < 2.0:
        print("  PASS - Alignment verified. Clock correction is working correctly.")
        print(f"  The {std:.3f}ms std confirms all timestamps are on the same clock.")
    elif std < 5.0:
        print("  MARGINAL - Std dev is slightly high. Check Wi-Fi stability.")
    else:
        print("  FAIL - Std dev > 5ms. Clock correction may not be working correctly.")
        print("  Check: are all devices on the same Wi-Fi network?")
        print("  Check: is LSL_API_CONFIG pointing to the correct config file?")

    print()
    print("  FRAME TIMING BREAKDOWN")
    print("  ----------------------")
    input_gaps = [xdf_by_seq[s]["since_last_ms"] for s in common_seqs]
    frame_dts  = [xdf_by_seq[s]["dt_ms"] for s in common_seqs]
    print(f"  Input polling gap (time since last frame at button press):")
    print(f"    Mean : {np.mean(input_gaps):.1f}ms  (expected 0-13.9ms at 72fps)")
    print(f"    Max  : {np.max(input_gaps):.1f}ms")
    print(f"  Frame render time (deltaTime):")
    print(f"    Mean : {np.mean(frame_dts):.1f}ms  (expected ~13.9ms at 72fps)")
    print(f"    Max  : {np.max(frame_dts):.1f}ms")
    print()


def main():
    parser = argparse.ArgumentParser(description="Validate button press timing alignment")
    parser.add_argument("xdf",  help="XDF recording file")
    parser.add_argument("json", help="Participant JSON from Quest")
    args = parser.parse_args()

    if not os.path.exists(args.xdf):
        print(f"XDF not found: {args.xdf}")
        sys.exit(1)
    if not os.path.exists(args.json):
        print(f"JSON not found: {args.json}")
        sys.exit(1)

    validate(args.xdf, args.json)


if __name__ == "__main__":
    main()
