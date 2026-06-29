#!/usr/bin/env python3
"""
align_session.py — merge Unity scene log (JSON) with sensor data (XDF)

Usage:
    python Tools/analysis/align_session.py \
        Data/Recordings/P001_2026-05-21.xdf \
        <path_to_participant_json>

The participant JSON is on the Quest at:
  Internal shared storage/Android/data/com.MSherbinii.ThesisVR/files/SessionLogs/participant_XXX.json

Copy it to your PC first, then run this script.

Output: prints a per-scenario summary table and saves aligned_P001.csv
"""

import sys
import os
import json
import csv
import glob

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pyxdf
except ImportError:
    print("pip install pyxdf")
    sys.exit(1)

from marker_utils import find_marker_stream_key


def load_xdf(path):
    streams, _ = pyxdf.load_xdf(path)
    result = {}
    for s in streams:
        name = s["info"]["name"][0]
        result[name] = {
            "times":  s["time_stamps"],
            "data":   s["time_series"],
        }
    return result


def get_markers(streams):
    """Return list of (timestamp, marker_string) sorted by time."""
    key = find_marker_stream_key(streams)
    if not key:
        return []
    return sorted(
        zip(streams[key]["times"], [v[0] for v in streams[key]["data"]]),
        key=lambda x: x[0]
    )


def mean(values):
    return sum(values) / len(values) if values else None


def samples_between(stream, t_start, t_end):
    """Return all data samples in a stream between t_start and t_end."""
    times = stream["times"]
    data  = stream["data"]
    return [
        (t, d) for t, d in zip(times, data)
        if t_start <= t <= t_end
    ]


def analyse(xdf_path, json_path):
    print(f"\nXDF  : {os.path.basename(xdf_path)}")
    print(f"JSON : {os.path.basename(json_path)}\n")

    streams = load_xdf(xdf_path)
    markers = get_markers(streams)

    with open(json_path, encoding="utf-8") as f:
        session = json.load(f)

    # Find gaze and HR streams (partial name match)
    gaze_key = next((k for k in streams if "Gaze" in k), None)
    hr_key   = next((k for k in streams if k.startswith("HR")), None)
    rr_key   = next((k for k in streams if k.startswith("RR")), None)

    print(f"Streams found: {list(streams.keys())}\n")

    rows = []

    for scenario in session.get("scenarios", []):
        snum = scenario["scenarioNumber"]
        chat = scenario.get("chatLog", [])
        sliders = scenario.get("sliders", {})

        # Find scenario boundaries in markers
        t_start = next((t for t, m in markers if m == f"ScenarioStart:{snum}"), None)
        t_end   = next((t for t, m in markers if m == f"ScenarioEnd:{snum}"), None)

        # Fallback: use SurveyStart as end if ScenarioEnd not found
        if t_end is None:
            t_end = next((t for t, m in markers if m.startswith("SurveyStart")), None)

        # Count turns
        user_turns = [m for m in chat if m["role"] == "user"]
        npc_turns  = [m for m in chat if m["role"] == "assistant"]

        # Message timestamps from markers
        msg_markers = [(t, m) for t, m in markers
                       if f"Role{snum}" in m or f"Role{((snum-1)%4)+1}" in m]

        # Physiology during scenario
        hr_samples  = samples_between(streams[hr_key],  t_start or 0, t_end or 9e9) if hr_key and t_start else []
        rr_samples  = samples_between(streams[rr_key],  t_start or 0, t_end or 9e9) if rr_key and t_start else []
        gaze_samples = samples_between(streams[gaze_key], t_start or 0, t_end or 9e9) if gaze_key and t_start else []

        hr_values  = [float(d[0]) for _, d in hr_samples  if d]
        rr_values  = [float(d[0]) for _, d in rr_samples  if d]

        duration = (t_end - t_start) if t_start and t_end else None

        row = {
            "scenario_number":   snum,
            "scenario_type":     "Escalating" if snum in (1, 3) else "Deescalating",
            "scenario_mode":     "Scripted" if snum in (1, 2) else "AI",
            "t_start":           round(t_start, 3) if t_start else "N/A",
            "t_end":             round(t_end, 3)   if t_end   else "N/A",
            "duration_s":        round(duration, 1) if duration else "N/A",
            "user_turns":        len(user_turns),
            "npc_turns":         len(npc_turns),
            "mean_hr_bpm":       round(mean(hr_values), 1)  if hr_values  else "N/A",
            "mean_rr_ms":        round(mean(rr_values), 1)  if rr_values  else "N/A",
            "gaze_samples":      len(gaze_samples),
            "slider1":           sliders.get("slider1", "N/A"),
            "slider2":           sliders.get("slider2", "N/A"),
            "slider3":           sliders.get("slider3", "N/A"),
        }
        rows.append(row)

        print(f"Scenario {snum}  ({row['scenario_type']}, {row['scenario_mode']})")
        print(f"  Time       : {row['t_start']} → {row['t_end']}  ({row['duration_s']}s)")
        print(f"  Turns      : {row['user_turns']} user / {row['npc_turns']} NPC")
        print(f"  Mean HR    : {row['mean_hr_bpm']} bpm")
        print(f"  Mean RR    : {row['mean_rr_ms']} ms")
        print(f"  Gaze pts   : {row['gaze_samples']}")
        print(f"  Sliders    : {row['slider1']} / {row['slider2']} / {row['slider3']}")
        print()

    # Save CSV
    if rows:
        out_name = "aligned_" + os.path.splitext(os.path.basename(xdf_path))[0] + ".csv"
        out_path = os.path.join(os.path.dirname(xdf_path), out_name)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        analyse(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 2:
        # Auto-find most recent JSON in Downloads or project
        xdf = sys.argv[1]
        candidates = glob.glob(os.path.expanduser("~/Downloads/participant_*.json")) + \
                     glob.glob("participant_*.json")
        if candidates:
            analyse(xdf, sorted(candidates)[-1])
        else:
            print("Pass the participant JSON as second argument:")
            print("  python align_session.py recording.xdf participant_001.json")
    else:
        print("Usage: python align_session.py recording.xdf participant_001.json")
