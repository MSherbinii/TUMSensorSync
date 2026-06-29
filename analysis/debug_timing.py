#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
"""
debug_timing.py
===============
Shows exactly how LSL clock correction works and validates all alignment
assumptions for a given XDF + JSON pair.

Usage:
    python Tools/analysis/debug_timing.py Data/Recordings/P001_combined_aligned.csv
    python Tools/analysis/debug_timing.py Data/Recordings/P001.xdf
    python Tools/analysis/debug_timing.py Data/Recordings/P001.xdf Data/SessionLogs/new/participant_1.json

What it shows:
    1. Raw clock offsets per stream BEFORE correction
    2. Clock offsets AFTER correction (should be near zero)
    3. Timing of every event: how long each phase took
    4. Inter-sample gaps (validates no data loss)
    5. JSON ↔ XDF structural alignment check (if JSON provided)
    6. Pipeline latency from SyncFlash (if present)
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pyxdf
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
except ImportError as e:
    print(f"Missing: {e}\npip install pyxdf pandas numpy matplotlib")
    sys.exit(1)

from marker_utils import find_marker_stream_key, MARKER_STREAM_NAME


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def load_xdf_raw(path):
    """Load XDF returning both corrected and raw (uncorrected) timestamps."""
    # Load with clock correction (default)
    streams_corrected, header = pyxdf.load_xdf(path)

    # Load without clock correction for comparison
    streams_raw, _ = pyxdf.load_xdf(path, synchronize_clocks=False)

    corrected = {s["info"]["name"][0]: s for s in streams_corrected}
    raw       = {s["info"]["name"][0]: s for s in streams_raw}
    return corrected, raw, header


def show_clock_offsets(corrected, raw):
    section("1. CLOCK CORRECTION — what LSL fixed")
    print(f"  {'Stream':45} {'Raw offset (ms)':>18} {'After correction':>18}")
    print(f"  {'-'*45} {'-'*18} {'-'*18}")

    for name in corrected:
        ts_raw  = raw[name]["time_stamps"]
        ts_corr = corrected[name]["time_stamps"]
        if len(ts_raw) < 2:
            continue

        # Offset = mean difference between corrected and raw timestamps
        if len(ts_raw) == len(ts_corr):
            offsets_ms = (ts_corr - ts_raw) * 1000
            raw_offset_ms  = offsets_ms.mean()
            # After correction the residual should be tiny
            # Measure residual jitter (std of the offset, not mean)
            residual_ms = offsets_ms.std()
        else:
            raw_offset_ms = float("nan")
            residual_ms   = float("nan")

        print(f"  {name:45} {raw_offset_ms:>+17.1f}ms {residual_ms:>17.3f}ms std")

    print("""
  Interpretation:
  - Raw offset = how far this device's clock was from PC clock (hours/days is normal)
  - After correction std = residual jitter remaining (should be < 1ms)
  - pyxdf.load_xdf() applies correction automatically on every load
""")


def show_sample_timing(corrected):
    section("2. SAMPLE TIMING — inter-sample gaps per stream")

    for name, s in corrected.items():
        ts = s["time_stamps"]
        n  = len(ts)
        if n < 2:
            print(f"  {name:45} — only {n} sample(s)")
            continue

        diffs_ms = np.diff(ts) * 1000
        nominal_hz = s["info"]["nominal_srate"][0]
        expected_ms = 1000 / float(nominal_hz) if float(nominal_hz) > 0 else None

        gaps_over_2x = int((diffs_ms > (expected_ms * 2 if expected_ms else 100)).sum()) if expected_ms else "N/A"
        max_gap_ms   = diffs_ms.max()
        mean_gap_ms  = diffs_ms.mean()

        status = "OK " if max_gap_ms < (expected_ms * 3 if expected_ms else 500) else "GAP"
        print(f"  [{status}] {name:42} n={n:6}  mean={mean_gap_ms:7.2f}ms  "
              f"max={max_gap_ms:8.1f}ms  gaps>{('2x' if expected_ms else '100ms')}={gaps_over_2x}")


def show_event_timeline(corrected):
    section("3. EVENT TIMELINE — what happened when")

    marker_key = find_marker_stream_key(corrected)
    if not marker_key:
        print(f"  No {MARKER_STREAM_NAME} stream found.")
        return None

    markers = list(zip(
        corrected[marker_key]["time_stamps"],
        [v[0] for v in corrected[marker_key]["time_series"]]
    ))

    if not markers:
        print(f"  {MARKER_STREAM_NAME} stream present but 0 samples.")
        print("  → Quest screen probably slept during recording.")
        print("  → Fix: set Quest screen timeout to Never before sessions.")
        return None

    t0 = markers[0][0]
    print(f"  {'Time':>8}  {'+offset':>8}  Marker")
    print(f"  {'-'*8}  {'-'*8}  {'-'*50}")
    prev_t = t0
    for t, m in markers:
        elapsed   = t - t0
        since_prev = t - prev_t
        print(f"  {elapsed:>7.2f}s  +{since_prev:>6.2f}s  {m}")
        prev_t = t

    return markers


def show_phase_durations(markers):
    section("4. PHASE DURATIONS — how long each part took")

    if not markers:
        print("  No markers — cannot compute phase durations.")
        return

    phases = {}
    t0 = markers[0][0]
    current_phase = "pre_session"
    current_start = t0

    phase_order = []

    for t, m in markers:
        new_phase = None
        if m.startswith("ScenarioStart:"):
            new_phase = f"scenario_{m.split(':')[1]}_active"
        elif m.startswith("SurveyStart:"):
            new_phase = f"survey_{m.split(':')[1]}"
        elif m.startswith("SurveyEnd:"):
            new_phase = f"between_scenarios"
        elif m == "SessionEnd":
            new_phase = "session_ended"

        if new_phase:
            dur = t - current_start
            phases[current_phase] = phases.get(current_phase, 0) + dur
            phase_order.append((current_phase, dur))
            current_phase = new_phase
            current_start = t

    # Final phase
    last_t = markers[-1][0]
    dur = last_t - current_start
    phases[current_phase] = phases.get(current_phase, 0) + dur
    phase_order.append((current_phase, dur))

    total = sum(phases.values())
    print(f"  {'Phase':35} {'Duration':>10} {'%':>6}")
    print(f"  {'-'*35} {'-'*10} {'-'*6}")
    for phase, dur in phase_order:
        print(f"  {phase:35} {dur:>9.1f}s {dur/total*100:>5.1f}%")
    print(f"  {'TOTAL':35} {total:>9.1f}s {100:>5.0f}%")

    # NPC vs user speaking time
    npc_time = sum(
        markers[i+1][0] - markers[i][0]
        for i in range(len(markers)-1)
        if markers[i][1].startswith("NPCOpening") or markers[i][1].startswith("NPCReply")
    )
    user_time = sum(
        markers[i+1][0] - markers[i][0]
        for i in range(len(markers)-1)
        if markers[i][1].startswith("UserMessage")
    )
    print(f"\n  NPC speaking time  : {npc_time:.1f}s")
    print(f"  User speaking time : {user_time:.1f}s")


def show_json_alignment(markers, json_path):
    section("5. JSON ↔ XDF STRUCTURAL ALIGNMENT")

    with open(json_path, encoding="utf-8", errors="replace") as f:
        session = json.load(f)

    scenarios = session.get("scenarios", [])
    marker_scenarios = {}
    for t, m in markers:
        if m.startswith("ScenarioStart:"):
            snum = int(m.split(":")[1])
            marker_scenarios[snum] = {"start_t": t, "turns": []}
        elif m.startswith("UserMessage:"):
            parts = m.split(":")
            turn  = int(parts[1])
            snum  = int(parts[2].replace("Role", ""))
            if snum in marker_scenarios:
                marker_scenarios[snum]["turns"].append(t)

    print(f"  {'Scenario':10} {'JSON turns':>12} {'XDF turns':>10} {'Match':>8} {'Start time':>12}")
    print(f"  {'-'*10} {'-'*12} {'-'*10} {'-'*8} {'-'*12}")

    all_match = True
    for s in scenarios:
        snum = s["scenarioNumber"]
        json_turns = len([m for m in s.get("chatLog", []) if m["role"] == "user"])
        xdf_turns  = len(marker_scenarios.get(snum, {}).get("turns", []))
        start_t    = marker_scenarios.get(snum, {}).get("start_t")
        match = "✓" if json_turns == xdf_turns else "✗ MISMATCH"
        if json_turns != xdf_turns:
            all_match = False
        t_str = f"{start_t:.2f}s" if start_t else "NOT IN XDF"
        print(f"  {snum:<10} {json_turns:>12} {xdf_turns:>10} {match:>8} {t_str:>12}")

    if all_match:
        print("\n  All turn counts match. JSON ↔ XDF alignment verified.")
    else:
        print("\n  MISMATCH detected. Possible causes:")
        print("  - App crashed and restarted mid-session")
        print("  - Session stopped before all scenarios completed")
        print("  - Recording started after some markers already fired")


def _parse_sync_flash_timing_markers(markers):
    """
    Parse the new multi-marker SyncFlash sequence and return a dict keyed by flash id.
    Supports both new (id-tagged) and legacy (plain "SyncFlash") recordings.

    Returns: { flash_id: { "flash_t": float, "unity_ms": float|None,
                            "cpu_ms": float|None, "gpu_ms": float|None } }
    """
    flashes = {}

    for t, m in (markers or []):
        if m.startswith("SyncFlash:id="):
            fid = int(m.split("=")[1])
            flashes.setdefault(fid, {})["flash_t"] = t
        elif m == "SyncFlash":
            # Legacy marker — assign to id=0 as a fallback bucket
            flashes.setdefault(0, {}).setdefault("flash_t", t)
        elif m.startswith("SyncFlashEndOfFrame:id="):
            parts = {kv.split("=")[0]: kv.split("=")[1]
                     for kv in m.split(":") if "=" in kv}
            fid = int(parts.get("id", 0))
            try:
                flashes.setdefault(fid, {})["unity_ms"] = float(parts.get("unityMs", "nan"))
            except ValueError:
                pass
        elif m.startswith("SyncFlashFrameTiming:id="):
            parts = {kv.split("=")[0]: kv.split("=")[1]
                     for kv in m.split(":") if "=" in kv}
            fid = int(parts.get("id", 0))
            cpu_raw = parts.get("cpuMs", "NA")
            gpu_raw = parts.get("gpuMs", "NA")
            flashes.setdefault(fid, {})["cpu_ms"] = None if cpu_raw == "NA" else float(cpu_raw)
            flashes.setdefault(fid, {})["gpu_ms"] = None if gpu_raw == "NA" else float(gpu_raw)

    return flashes


def show_sync_flash(corrected, markers, out_prefix):
    section("6. SYNC FLASH — stimulus-to-eye-data latency budget")

    flashes = _parse_sync_flash_timing_markers(markers)
    if not flashes:
        print("  No SyncFlash marker found.")
        print("  → This means the recording started before the scene loaded,")
        print("    OR the scene loaded during a dropout (no markers recorded).")
        print("  → Next session: ensure Quest is running the app BEFORE")
        print("    all streams connect and recording starts.")
        return

    gaze_key = next((k for k in corrected if "Gaze" in k), None)
    if not gaze_key:
        print("  No gaze stream found.")
        return

    gaze_ts   = corrected[gaze_key]["time_stamps"]
    gaze_data = np.array(corrected[gaze_key]["time_series"])
    worn_idx  = min(2, gaze_data.shape[1] - 1)
    worn_ch   = gaze_data[:, worn_idx]

    for i, (fid, info) in enumerate(sorted(flashes.items())):
        flash_t = info.get("flash_t")
        if flash_t is None:
            continue

        mask = (gaze_ts >= flash_t - 0.1) & (gaze_ts <= flash_t + 0.5)
        if not np.any(mask):
            print(f"  Flash {i+1} (id={fid}): no gaze samples in window")
            continue

        window_ts   = gaze_ts[mask]
        window_worn = worn_ch[mask]
        baseline    = np.median(worn_ch[(gaze_ts >= flash_t - 0.2) & (gaze_ts < flash_t)])
        delta       = window_worn - baseline
        peak_idx    = np.argmax(np.abs(delta))
        spike_t     = window_ts[peak_idx]
        total_ms    = (spike_t - flash_t) * 1000

        unity_ms = info.get("unity_ms")
        cpu_ms   = info.get("cpu_ms")
        gpu_ms   = info.get("gpu_ms")

        remaining_ms = (total_ms - unity_ms) if unity_ms is not None else None

        print(f"\n  Flash {i+1} (id={fid}) at {flash_t:.3f}s:")
        print(f"  {'─'*55}")
        print(f"    SyncFlash marker             : {flash_t:.6f}s")
        print(f"    Gaze worn-channel spike      : {spike_t:.6f}s")
        print(f"    Total stimulus-to-eye-data   : {total_ms:.1f} ms")

        if unity_ms is not None:
            print(f"    Unity end-of-frame cost      : {unity_ms:.1f} ms  "
                  f"(WaitForEndOfFrame — NOT photon time)")
        else:
            print(f"    Unity end-of-frame cost      : N/A  (old recording — no SyncFlashEndOfFrame marker)")

        if cpu_ms is not None:
            print(f"    Approx. Unity CPU frame time : {cpu_ms:.1f} ms  (~6-frame delay, approximate)")
        if gpu_ms is not None:
            print(f"    Approx. Unity GPU frame time : {gpu_ms:.1f} ms  (~6-frame delay, approximate)")

        if remaining_ms is not None:
            print(f"    Remaining (display+bio+Neon+net): {remaining_ms:.1f} ms")

        print()
        print(f"    Latency pipeline breakdown:")
        print(f"    ┌─────────────────────────────────────────────────────────────────┐")
        if unity_ms is not None:
            print(f"    │  Unity render to end-of-frame    : {unity_ms:>6.1f} ms                │")
            print(f"    │  Quest compositor + display      : ??? ms  (not measurable)     │")
            print(f"    │  Biological pupil reflex         : ~50-200 ms (physiology)      │")
            print(f"    │  Neon acquisition + processing   : ~20-50 ms (camera + LSL)     │")
            print(f"    │  WiFi + LabRecorder delivery     : ~1-5 ms (network)            │")
            print(f"    ├─────────────────────────────────────────────────────────────────┤")
        print(f"    │  TOTAL measured                   : {total_ms:>6.1f} ms                │")
        status = "OK" if total_ms < 300 else "HIGH"
        print(f"    │  Status                           : {status:<28}│")
        print(f"    └─────────────────────────────────────────────────────────────────┘")


def plot_full_session(corrected, markers, out_prefix):
    """Generate a full session overview plot."""
    gaze_key = next((k for k in corrected if "Gaze" in k), None)
    hr_key   = next((k for k in corrected if k.startswith("HR")), None)

    if not gaze_key and not hr_key:
        return

    fig = plt.figure(figsize=(16, 10))
    gs  = gridspec.GridSpec(3, 1, hspace=0.4)

    # Gaze X/Y
    if gaze_key:
        gaze_ts   = corrected[gaze_key]["time_stamps"]
        gaze_data = np.array(corrected[gaze_key]["time_series"])
        t0 = gaze_ts[0]

        ax1 = fig.add_subplot(gs[0])
        ax1.plot(gaze_ts - t0, gaze_data[:, 0], "b-", alpha=0.5, linewidth=0.5, label="Gaze X")
        ax1.plot(gaze_ts - t0, gaze_data[:, 1], "r-", alpha=0.5, linewidth=0.5, label="Gaze Y")
        ax1.set_ylabel("Screen position (px)")
        ax1.set_title("Gaze Position over Session")
        ax1.legend(loc="upper right", fontsize=8)

        ax2 = fig.add_subplot(gs[1])
        pupil_l = gaze_data[:, 7]
        pupil_r = gaze_data[:, 8]
        ax2.plot(gaze_ts - t0, pupil_l, "purple", alpha=0.7, linewidth=0.8, label="Pupil L")
        ax2.plot(gaze_ts - t0, pupil_r, "orange", alpha=0.7, linewidth=0.8, label="Pupil R")
        ax2.set_ylabel("Pupil diameter (mm)")
        ax2.set_title("Pupil Diameter over Session")
        ax2.legend(loc="upper right", fontsize=8)

    # HR
    if hr_key:
        ax3 = fig.add_subplot(gs[2])
        hr_ts  = corrected[hr_key]["time_stamps"]
        hr_val = [float(v[0]) for v in corrected[hr_key]["time_series"]]
        t0_hr  = gaze_ts[0] if gaze_key else hr_ts[0]
        ax3.plot(hr_ts - t0_hr, hr_val, "green", linewidth=1.5, marker="o", markersize=3, label="HR bpm")
        ax3.set_ylabel("Heart Rate (bpm)")
        ax3.set_xlabel("Time (s)")
        ax3.set_title("Heart Rate over Session")
        ax3.legend(loc="upper right", fontsize=8)

    # Add marker lines to all axes
    if markers:
        t0 = gaze_ts[0] if gaze_key else markers[0][0]
        scenario_colors = {1: "red", 2: "blue", 3: "orange", 3: "purple"}
        for t, m in markers:
            rel_t = t - t0
            color = "gray"
            if m.startswith("ScenarioStart"): color = "red"
            elif m.startswith("SurveyStart"):  color = "green"
            elif m == "SessionEnd":            color = "black"
            for ax in fig.get_axes():
                ax.axvline(rel_t, color=color, alpha=0.4, linewidth=0.8)
                if m.startswith("ScenarioStart") or m == "SessionEnd":
                    ax.text(rel_t, ax.get_ylim()[1] * 0.95, m.split(":")[0],
                           fontsize=6, color=color, rotation=90, va="top")

    plt.suptitle(f"Session Overview — {os.path.basename(out_prefix)}", fontsize=12)
    out_path = out_prefix + "_debug_overview.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Saved plot: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Debug LSL timing and alignment")
    parser.add_argument("xdf", help="XDF file or combined aligned CSV")
    parser.add_argument("json", nargs="?", help="Optional participant JSON for structural check")
    args = parser.parse_args()

    if args.xdf.endswith(".csv"):
        print("CSV provided — showing timing stats from aligned data only.")
        df = pd.read_csv(args.xdf)
        section("ALIGNED CSV STATS")
        print(f"  Rows     : {len(df):,}")
        print(f"  Columns  : {list(df.columns)}")
        if "time_s" in df.columns:
            duration = df.time_s.iloc[-1]
        else:
            duration = df.timestamp.iloc[-1] - df.timestamp.iloc[0]
        print(f"  Duration : {duration/60:.1f} min ({duration:.1f}s)")
        print(f"  Time col : {'time_s (starts at 0)' if 'time_s' in df.columns else 'timestamp (raw LSL clock)'}")
        if "hr_bpm" in df.columns:
            print(f"\n  HR stats:")
            print(f"    Mean HR : {df.hr_bpm.mean():.1f} bpm")
            print(f"    Std HR  : {df.hr_bpm.std():.1f} bpm")
            print(f"    Min HR  : {df.hr_bpm.min():.0f} bpm")
            print(f"    Max HR  : {df.hr_bpm.max():.0f} bpm")
        if "gaze_x" in df.columns:
            print(f"\n  Gaze stats:")
            print(f"    Gaze X  : {df.gaze_x.mean():.0f} +/- {df.gaze_x.std():.0f} px")
            print(f"    Gaze Y  : {df.gaze_y.mean():.0f} +/- {df.gaze_y.std():.0f} px")
        if "pupil_right_mm" in df.columns:
            print(f"    Pupil R : {df.pupil_right_mm.mean():.3f} +/- {df.pupil_right_mm.std():.3f} mm")
        if "phase" in df.columns:
            print(f"\n  Phase breakdown:")
            print(df.groupby("phase").size().rename("rows").to_string())
        time_col = "time_s" if "time_s" in df.columns else "timestamp"
        diffs = df[time_col].diff().dropna() * 1000
        print(f"\n  Timestamp gaps:")
        print(f"    Mean    : {diffs.mean():.2f}ms")
        print(f"    Max     : {diffs.max():.0f}ms")
        print(f"    >10ms   : {(diffs>10).sum()} gaps")
        return

    out_prefix = args.xdf.replace(".xdf", "")
    print(f"\nLoading: {os.path.basename(args.xdf)}")
    corrected, raw, header = load_xdf_raw(args.xdf)

    show_clock_offsets(corrected, raw)
    show_sample_timing(corrected)
    markers = show_event_timeline(corrected)
    show_phase_durations(markers)

    if args.json:
        show_json_alignment(markers, args.json)

    show_sync_flash(corrected, markers, out_prefix)
    plot_full_session(corrected, markers, out_prefix)

    print(f"\n{'━'*60}")
    print(f"  Debug complete. Check {os.path.basename(out_prefix)}_debug_overview.png")
    print(f"{'━'*60}\n")


if __name__ == "__main__":
    main()
