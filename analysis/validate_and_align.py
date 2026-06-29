#!/usr/bin/env python3
"""
validate_and_align.py
=====================
Loads an XDF recording, validates sync flash latency, then produces a
single long-format CSV with every gaze sample (200Hz) as a row, with
HR/RR interpolated to the same timebase, and the current conversation
context (scenario, turn, speaker) filled in from LSL markers.

Usage:
    pip install pyxdf pandas numpy scipy matplotlib
    python Tools/analysis/validate_and_align.py Data/Recordings/P001_2026-05-21.xdf

Output:
    Data/Recordings/P001_2026-05-21_aligned.csv
    Data/Recordings/P001_2026-05-21_sync_validation.png
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
    from scipy.interpolate import interp1d
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install pyxdf pandas numpy scipy matplotlib")
    sys.exit(1)

from marker_utils import find_marker_stream_key

# Load channel mappings from config if available, else use Neon defaults
_ORCHESTRATOR_DIR = os.path.join(os.path.dirname(__file__), "..", "orchestrator")
sys.path.insert(0, _ORCHESTRATOR_DIR)
try:
    import config as _config
    GAZE_CHANNELS = _config.gaze_channels()
except (ImportError, FileNotFoundError):
    GAZE_CHANNELS = {
        "gaze_x": 0, "gaze_y": 1,
        "pupil_left_mm": 7, "pupil_right_mm": 8,
    }

# Extended channels always included if present in data
_EXTENDED_GAZE = {"worn": 2, "fixation_id": 3, "blink_id": 4, "azimuth": 5, "elevation": 6}
for k, v in _EXTENDED_GAZE.items():
    if k not in GAZE_CHANNELS:
        GAZE_CHANNELS[k] = v


def load_streams(xdf_path):
    streams, header = pyxdf.load_xdf(xdf_path)
    result = {}
    for s in streams:
        name = s["info"]["name"][0]
        result[name] = s
    return result


def get_markers(streams):
    key = find_marker_stream_key(streams)
    if not key:
        return []
    s = streams[key]
    return list(zip(s["time_stamps"], [v[0] for v in s["time_series"]]))


def _parse_flash_timing_from_markers(markers):
    """
    Build a dict of per-flash timing data from the multi-marker SyncFlash sequence.
    Supports both new (id-tagged) and legacy (plain "SyncFlash") recordings.

    Returns: { flash_id: { "flash_t": float, "unity_ms": float|None,
                            "cpu_ms": float|None, "gpu_ms": float|None } }
    """
    flashes = {}
    for t, m in markers:
        if m.startswith("SyncFlash:id="):
            fid = int(m.split("=")[1])
            flashes.setdefault(fid, {})["flash_t"] = t
        elif m == "SyncFlash":
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


def validate_sync_flash(streams, markers, out_prefix):
    """
    Find SyncFlash markers and corresponding luminance spikes in the Neon gaze
    'worn' channel. Report a full stimulus-to-eye-data latency budget per flash,
    breaking out Unity end-of-frame cost where available.

    Returns mean total latency in ms, or None.
    """
    flashes = _parse_flash_timing_from_markers(markers)
    if not flashes:
        print("  WARNING: No SyncFlash marker found — skipping latency validation")
        return None

    gaze_key = next((k for k in streams if "Gaze" in k), None)
    if not gaze_key:
        print("  WARNING: No gaze stream found")
        return None

    gaze = streams[gaze_key]
    gaze_ts   = np.array(gaze["time_stamps"])
    gaze_data = np.array(gaze["time_series"])
    worn_idx  = GAZE_CHANNELS.get("worn", 2)
    if worn_idx >= gaze_data.shape[1]:
        print("  WARNING: 'worn' channel index exceeds stream channels — using channel 2")
        worn_idx = min(2, gaze_data.shape[1] - 1)
    worn_ch   = gaze_data[:, worn_idx]

    total_latencies = []
    flash_items = sorted(flashes.items())

    for i, (fid, info) in enumerate(flash_items):
        flash_t = info.get("flash_t")
        if flash_t is None:
            continue

        mask = (gaze_ts >= flash_t) & (gaze_ts <= flash_t + 0.5)
        if not np.any(mask):
            print(f"  Flash {i+1} (id={fid}): no gaze samples in window — skipping")
            continue

        window_ts   = gaze_ts[mask]
        window_worn = worn_ch[mask]
        baseline    = np.median(worn_ch[(gaze_ts >= flash_t - 0.2) & (gaze_ts < flash_t)])
        delta       = window_worn - baseline
        peak_idx    = np.argmax(np.abs(delta))
        spike_t     = window_ts[peak_idx]
        total_ms    = (spike_t - flash_t) * 1000
        total_latencies.append(total_ms)

        unity_ms     = info.get("unity_ms")
        cpu_ms       = info.get("cpu_ms")
        gpu_ms       = info.get("gpu_ms")
        remaining_ms = (total_ms - unity_ms) if unity_ms is not None else None

        print(f"\n  Flash {i+1} (id={fid}):")
        print(f"    SyncFlash t                     : {flash_t:.3f}s")
        print(f"    Gaze spike t                    : {spike_t:.3f}s")
        print(f"    Total stimulus-to-eye-data      : {total_ms:.1f} ms")
        if unity_ms is not None:
            print(f"    Unity end-of-frame cost         : {unity_ms:.1f} ms  (NOT photon time)")
        if cpu_ms is not None:
            print(f"    Approx. Unity CPU frame time    : {cpu_ms:.1f} ms  (approx, ~6-frame delay)")
        if gpu_ms is not None:
            print(f"    Approx. Unity GPU frame time    : {gpu_ms:.1f} ms  (approx, ~6-frame delay)")
        if remaining_ms is not None:
            print(f"    Remaining (display+bio+Neon+net): {remaining_ms:.1f} ms")

    if total_latencies:
        mean_lat = float(np.mean(total_latencies))
        print(f"\n  Mean total latency: {mean_lat:.1f}ms  (n={len(total_latencies)} flashes)")
        print(f"  Note: value includes Quest display/compositor latency, biological pupil")
        print(f"        light reflex, Neon processing, and LSL network delivery.")
        print(f"  Acceptable range  : < 80ms  ({'OK' if mean_lat < 80 else 'HIGH — check Wi-Fi / Quest display pipeline'})")

        # Plot
        fig, axes = plt.subplots(len(flash_items), 1,
                                 figsize=(10, 3 * len(flash_items)), squeeze=False)
        lat_iter = iter(total_latencies)
        for i, (fid, info) in enumerate(flash_items):
            flash_t = info.get("flash_t")
            if flash_t is None:
                continue
            lat_ms = next(lat_iter, None)
            ax = axes[i][0]
            mask = (gaze_ts >= flash_t - 0.1) & (gaze_ts <= flash_t + 0.5)
            ax.plot(gaze_ts[mask] - flash_t, worn_ch[mask], "b-", label="worn signal")
            ax.axvline(0, color="red", linestyle="--", label="SyncFlash marker")
            if lat_ms is not None:
                ax.axvline(lat_ms / 1000, color="green", linestyle="--",
                           label=f"gaze spike (+{lat_ms:.0f}ms)")
            unity_ms = info.get("unity_ms")
            if unity_ms is not None:
                ax.axvline(unity_ms / 1000, color="orange", linestyle=":",
                           label=f"Unity end-of-frame (+{unity_ms:.1f}ms)")
            ax.set_xlabel("Time relative to SyncFlash marker (s)")
            ax.set_ylabel("Worn channel")
            title = f"Flash {i+1} (id={fid})"
            if lat_ms is not None:
                title += f" — total={lat_ms:.1f}ms"
            if unity_ms is not None:
                title += f"  unity={unity_ms:.1f}ms"
            ax.set_title(title)
            ax.legend(fontsize=8)

        fig.suptitle("SyncFlash Stimulus-to-Eye-Data Latency Validation")
        fig.tight_layout()
        png_path = out_prefix + "_sync_validation.png"
        fig.savefig(png_path, dpi=150)
        print(f"  Saved: {png_path}")
        plt.close(fig)

        return mean_lat
    return None


def build_aligned_dataframe(streams, markers):
    """
    Build a long-format DataFrame at gaze resolution (200Hz).
    Columns: timestamp, gaze_x, gaze_y, pupil_left_mm, pupil_right_mm,
             blink, fixation_id, worn, azimuth, elevation,
             hr_bpm (interpolated), rr_ms (interpolated),
             scenario_number, scenario_type, turn_index, speaker, phase
    """
    gaze_key = next((k for k in streams if "Gaze" in k), None)
    hr_key   = next((k for k in streams if k.startswith("HR")), None)
    rr_key   = next((k for k in streams if k.startswith("RR")), None)

    if not gaze_key:
        print("ERROR: No gaze stream in XDF")
        sys.exit(1)

    gaze = streams[gaze_key]
    gaze_ts   = np.array(gaze["time_stamps"])
    gaze_data = np.array(gaze["time_series"])

    n = len(gaze_ts)
    n_channels = gaze_data.shape[1] if gaze_data.ndim == 2 else 0

    data = {"timestamp": gaze_ts}

    # Core channels (always present in config)
    for col in ["gaze_x", "gaze_y", "pupil_left_mm", "pupil_right_mm"]:
        if col in GAZE_CHANNELS and GAZE_CHANNELS[col] < n_channels:
            data[col] = gaze_data[:, GAZE_CHANNELS[col]]
        else:
            data[col] = np.full(n, np.nan)

    # Extended channels (optional — included if index is valid)
    if "blink_id" in GAZE_CHANNELS and GAZE_CHANNELS["blink_id"] < n_channels:
        data["blink"] = (gaze_data[:, GAZE_CHANNELS["blink_id"]] >= 0).astype(int)
    else:
        data["blink"] = np.zeros(n, dtype=int)

    for col in ["fixation_id", "worn", "azimuth", "elevation"]:
        if col in GAZE_CHANNELS and GAZE_CHANNELS[col] < n_channels:
            data[col] = gaze_data[:, GAZE_CHANNELS[col]]

    df = pd.DataFrame(data)

    # Interpolate HR onto gaze timebase
    for key, col in [(hr_key, "hr_bpm"), (rr_key, "rr_ms")]:
        if key and len(streams[key]["time_stamps"]) > 1:
            src_ts = np.array(streams[key]["time_stamps"])
            src_v  = np.array([v[0] for v in streams[key]["time_series"]], dtype=float)
            interp = interp1d(src_ts, src_v, kind="linear",
                              bounds_error=False, fill_value=np.nan)
            df[col] = interp(gaze_ts)
        else:
            df[col] = np.nan

    # Fill in conversation context from markers
    df["scenario_number"] = -1
    df["scenario_type"]   = "baseline"
    df["turn_index"]      = -1
    df["speaker"]         = "none"
    df["phase"]           = "baseline"

    SCENARIO_TYPE = {1: "Escalating_Scripted", 2: "Deescalating_Scripted",
                     3: "Escalating_AI",       4: "Deescalating_AI"}

    current_scenario = -1
    current_turn     = -1
    current_speaker  = "none"
    current_phase    = "baseline"

    for t, marker in sorted(markers, key=lambda x: x[0]):
        idx = np.searchsorted(gaze_ts, t)

        if marker.startswith("ScenarioStart:"):
            current_scenario = int(marker.split(":")[1])
            current_phase    = "scenario"
            current_turn     = 0
            current_speaker  = "none"
        elif marker.startswith("NPCOpening:") or (
             marker.startswith("NPCReply:") and ":" in marker):
            current_speaker = "npc"
            current_phase   = "npc_speaking"
        elif marker.startswith("UserMessage:"):
            current_turn   += 1
            current_speaker = "user"
            current_phase   = "user_speaking"
        elif marker.startswith("SurveyStart:"):
            current_phase   = "survey"
            current_speaker = "none"
        elif marker == "SessionEnd":
            current_phase   = "end"

        # Apply state forward from this marker index
        df.loc[idx:, "scenario_number"] = current_scenario
        df.loc[idx:, "scenario_type"]   = SCENARIO_TYPE.get(current_scenario, "unknown")
        df.loc[idx:, "turn_index"]      = current_turn
        df.loc[idx:, "speaker"]         = current_speaker
        df.loc[idx:, "phase"]           = current_phase

    return df


def enrich_with_text(df: "pd.DataFrame", markers, json_path: str) -> "pd.DataFrame":
    """
    Add message_text and message_turn columns to an aligned dataframe.
    Each gaze row gets the exact text being spoken at that timestamp,
    derived by joining XDF markers with the session JSON chat log.
    """
    import json as _json
    with open(json_path, encoding="utf-8", errors="replace") as f:
        session = _json.load(f)

    scenario_chats = {}
    for sc in session.get("scenarios", []):
        chat = [m for m in sc.get("chatLog", []) if m["role"] != "system"]
        scenario_chats[sc["scenarioNumber"]] = chat

    # Walk markers, track current scenario from ScenarioStart
    current_scenario = None
    npc_turn = 0
    user_turn = 0
    events = []  # (timestamp, scenario_num, role, turn_num, text)

    for t, m in sorted(markers, key=lambda x: x[0]):
        if m.startswith("ScenarioStart:"):
            current_scenario = int(m.split(":")[1])
            npc_turn = 0
            user_turn = 0
        elif m.startswith("NPCOpening:") and current_scenario:
            chat = scenario_chats.get(current_scenario, [])
            text = chat[0]["content"] if chat else ""
            events.append((t, current_scenario, "npc", 0, text))
            npc_turn = 1
        elif m.startswith("UserMessage:") and current_scenario:
            user_turn += 1
            chat = scenario_chats.get(current_scenario, [])
            idx = user_turn * 2 - 1
            text = chat[idx]["content"] if idx < len(chat) else ""
            events.append((t, current_scenario, "user", user_turn, text))
        elif m.startswith("NPCReply:") and current_scenario:
            chat = scenario_chats.get(current_scenario, [])
            idx = npc_turn * 2
            text = chat[idx]["content"] if idx < len(chat) else ""
            events.append((t, current_scenario, "npc", npc_turn, text))
            npc_turn += 1

    if not events:
        df["message_text"] = ""
        df["message_turn"] = -1
        return df

    df = df.copy()
    df["message_text"] = ""
    df["message_turn"] = -1

    ts = df["timestamp"].values
    for i, (t_start, snum, role, turn, text) in enumerate(events):
        t_end = events[i + 1][0] if i + 1 < len(events) else ts[-1]
        mask = (ts >= t_start) & (ts < t_end)
        df.loc[mask, "message_text"] = text
        df.loc[mask, "message_turn"] = turn

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xdf", help="Path to .xdf recording file")
    parser.add_argument("--json", default=None, help="Optional session JSON for text enrichment")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    xdf_path = args.xdf
    out_prefix = xdf_path.replace(".xdf", "")

    print(f"\nLoading: {os.path.basename(xdf_path)}")
    streams = load_streams(xdf_path)
    markers = get_markers(streams)

    print(f"\nStreams in file:")
    for name, s in streams.items():
        n = len(s["time_stamps"])
        dur = s["time_stamps"][-1] - s["time_stamps"][0] if n > 1 else 0
        hz = n / dur if dur > 0 else 0
        print(f"  {name:45} {n:6} samples  {hz:7.1f}Hz  {dur/60:.1f}min")

    print(f"\nMarkers ({len(markers)} total):")
    t0 = markers[0][0] if markers else 0
    for t, m in markers:
        print(f"  {t - t0:>8.2f}s  {m}")

    print("\n--- Sync Flash Validation ---")
    latency_ms = None
    if not args.no_plot:
        latency_ms = validate_sync_flash(streams, markers, out_prefix)

    print("\n--- Building aligned dataframe ---")
    df = build_aligned_dataframe(streams, markers)

    # Enrich with message text if JSON provided
    if args.json and os.path.exists(args.json):
        print(f"\n--- Enriching with message text from {os.path.basename(args.json)} ---")
        df = enrich_with_text(df, markers, args.json)
        print(f"  Added message_text and message_turn columns")

    # Add time_s column starting from 0
    session_start = df["timestamp"].iloc[0]
    df.insert(1, "time_s", df["timestamp"] - session_start)

    # Save
    csv_path = out_prefix + "_aligned.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"Saved: {csv_path}  ({len(df)} rows, {len(df.columns)} columns)")

    duration_s = df["time_s"].iloc[-1]
    print("\n--- Summary ---")
    print(f"Duration     : {duration_s/60:.1f} min ({duration_s:.1f}s)")
    print(f"Gaze samples : {len(df)} at ~200Hz")
    print(f"HR coverage  : {df.hr_bpm.notna().sum()} samples ({df.hr_bpm.notna().mean()*100:.0f}%)")
    print(f"Blink rate   : {df.blink.mean()*200*60:.0f} blinks/min")
    if latency_ms:
        print(f"Pipeline lat : {latency_ms:.1f}ms (stimulus-to-eye-data; includes display+bio+Neon+net)")
    print(f"\nPhase breakdown:")
    print(df.groupby("phase")[["time_s"]].count().rename(
        columns={"time_s": "gaze_samples"}))


if __name__ == "__main__":
    main()
