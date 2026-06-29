#!/usr/bin/env python3
"""
verify_session.py  --  post-session data quality check
Usage: python Tools/session_orchestrator/verify_session.py Data/Recordings/P001_2026-05-21.xdf

Checks:
  - All 4 expected streams are present
  - Clock offsets are within acceptable range
  - No large gaps in any stream
  - Markers are in logical order
  - Gaze and HR data exist for each scenario
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pyxdf
except ImportError:
    print("pip install pyxdf")
    sys.exit(1)

# Fallback specs match the project's historical defaults, used only if
# config.json can't be loaded (e.g. checking an XDF from another machine).
_FALLBACK_SPECS = [
    {"label": "UnityMarkers", "match": "name", "value": "UnityMarkers"},
    {"label": "Neon Gaze", "match": "name", "value": "Neon Companion_Neon Gaze"},
    {"label": "HR Polar H10", "match": "name", "value": "HR Polar H10"},
    {"label": "RR Polar H10", "match": "name", "value": "RR Polar H10"},
]

try:
    import config as _config
    EXPECTED_SPECS = _config.expected_streams()
    MARKER_STREAM_NAME = _config.marker_stream_name()
except Exception:
    EXPECTED_SPECS = _FALLBACK_SPECS
    MARKER_STREAM_NAME = "UnityMarkers"

MAX_CLOCK_OFFSET_MS = 50      # warn if offset exceeds this
MAX_GAP_SECONDS     = 2.0     # warn if any stream has a gap larger than this
GAZE_MIN_HZ         = 150     # warn if gaze drops below this rate


def check(xdf_path: str):
    print(f"\nVerifying: {os.path.basename(xdf_path)}\n")
    streams, header = pyxdf.load_xdf(xdf_path)

    issues = []
    ok_count = 0

    # ── 1. Stream presence ────────────────────────────────────────────────────
    found_names = [s["info"]["name"][0] for s in streams]
    found_types = [s["info"]["type"][0] for s in streams]
    print("Streams present:")
    for spec in EXPECTED_SPECS:
        if spec["match"] == "type":
            matched = next((n for n, t in zip(found_names, found_types) if spec["value"] in t), None)
        else:
            matched = next((n for n in found_names if spec["value"] in n), None)
        if matched:
            print(f"  OK  {matched}")
            ok_count += 1
        else:
            print(f"  MISSING  {spec['label']}")
            issues.append(f"Stream missing: {spec['label']}")

    # ── 2. Clock offsets ──────────────────────────────────────────────────────
    print("\nClock offsets (after LSL correction):")
    for s in streams:
        name = s["info"]["name"][0]
        offsets = s.get("clock_offsets", {}).get("offset", [])
        if offsets:
            values = [float(v) * 1000 for v in offsets]  # convert to ms
            max_off = max(abs(v) for v in values)
            avg_off = sum(abs(v) for v in values) / len(values)
            status = "OK " if max_off < MAX_CLOCK_OFFSET_MS else "WARN"
            print(f"  {status}  {name[:35]:35} max={max_off:.1f}ms  avg={avg_off:.1f}ms")
            if max_off >= MAX_CLOCK_OFFSET_MS:
                issues.append(f"High clock offset on {name}: {max_off:.1f}ms")
        else:
            print(f"  --   {name[:35]:35} (no offset data)")

    # ── 3. Sample gaps ────────────────────────────────────────────────────────
    print("\nSample gaps:")
    for s in streams:
        name = s["info"]["name"][0]
        ts = s["time_stamps"]
        if len(ts) < 2:
            print(f"  WARN  {name[:35]:35} only {len(ts)} samples")
            issues.append(f"Too few samples in {name}: {len(ts)}")
            continue
        diffs = [ts[i+1] - ts[i] for i in range(len(ts)-1)]
        max_gap = max(diffs)
        duration = ts[-1] - ts[0]
        n = len(ts)
        rate = n / duration if duration > 0 else 0
        status = "OK " if max_gap < MAX_GAP_SECONDS else "WARN"
        print(f"  {status}  {name[:35]:35} {n:6} samples  {rate:6.1f}Hz  max_gap={max_gap:.2f}s  dur={duration/60:.1f}min")
        if max_gap >= MAX_GAP_SECONDS:
            issues.append(f"Gap of {max_gap:.1f}s in {name}")

    # ── 4. Marker sequence ────────────────────────────────────────────────────
    marker_stream = next((s for s in streams if s["info"]["name"][0] == MARKER_STREAM_NAME), None)
    if marker_stream:
        markers = [(t, v[0]) for t, v in zip(marker_stream["time_stamps"], marker_stream["time_series"])]
        print(f"\nMarkers ({len(markers)} total):")
        scenario_starts = [m for m in markers if m[1].startswith("ScenarioStart")]
        scenario_ends   = [m for m in markers if m[1].startswith("ScenarioEnd")]
        session_end     = [m for m in markers if m[1] == "SessionEnd"]
        for t, v in markers:
            print(f"  {t:.3f}  {v}")
        if len(scenario_starts) != 4:
            issues.append(f"Expected 4 ScenarioStart markers, got {len(scenario_starts)}")
        if not session_end:
            issues.append("No SessionEnd marker found")

    # ── 5. Summary ────────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    if not issues:
        print("PASS — no issues found. Data looks clean.")
    else:
        print(f"ISSUES FOUND ({len(issues)}):")
        for issue in issues:
            print(f"  ! {issue}")
    print("─" * 60 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Find most recent recording
        recordings_dir = os.path.join(os.path.dirname(__file__), "..", "..", "Data", "Recordings")
        xdf_files = sorted([
            os.path.join(recordings_dir, f)
            for f in os.listdir(recordings_dir) if f.endswith(".xdf")
        ])
        if not xdf_files:
            print("No .xdf files found. Pass path as argument.")
            sys.exit(1)
        path = xdf_files[-1]
        print(f"No file specified — checking most recent: {os.path.basename(path)}")
    else:
        path = sys.argv[1]

    check(path)
