#!/usr/bin/env python3
"""
TUMSensorSync — Session Orchestrator
Run this once before each experiment session.
"""
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

import pylsl
from rich.live import Live
from rich.prompt import Prompt
from rich.console import Console

import config as _config
from stream_watcher import StreamWatcher
from recorder import Recorder
from relay_launcher import RelayLauncher
from session_logger import log
from display import build_panel

console = Console()
MARKER_STREAM_NAME = _config.marker_stream_name()
SESSION_END_MARKER = "SessionEnd"
AUTO_STOP_DELAY = _config.auto_stop_delay()


def ask_participant_id() -> str:
    console.print("\n[bold]THESIS VR — Session Orchestrator[/bold]\n")
    pid = Prompt.ask("Participant ID").strip()
    if not pid:
        pid = f"P{datetime.now().strftime('%Y%m%d%H%M%S')}"
        console.print(f"[dim]No ID entered — using {pid}[/dim]")
    return pid


def open_marker_inlet() -> Optional[pylsl.StreamInlet]:
    """Try to open an inlet on UnityMarkers stream. Returns None if not found."""
    results = pylsl.resolve_streams(wait_time=1.0)
    results = [s for s in results if s.name() == MARKER_STREAM_NAME]
    if not results:
        return None
    return pylsl.StreamInlet(results[0])


def _auto_align(participant_id: str, recorder, con) -> None:
    """
    After session ends, find all XDF part files, run alignment on each,
    and merge into one combined CSV saved alongside the recordings.
    Works whether session ended via SessionEnd marker or manual Q-stop.
    """
    import glob, importlib.util

    # Find all XDF files that belong to this session (same participant_id prefix)
    data_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "Data", "Recordings"))
    pattern  = os.path.join(data_dir, f"{participant_id}_*.xdf")
    xdf_files = sorted(glob.glob(pattern))

    if not xdf_files:
        con.print("[dim]No XDF files found to align.[/dim]")
        return

    # Import validate_and_align without subprocess
    analysis_path = os.path.join(os.path.dirname(__file__), "..", "analysis", "validate_and_align.py")
    analysis_path = os.path.normpath(analysis_path)
    if not os.path.exists(analysis_path):
        con.print("[yellow]validate_and_align.py not found — skipping auto-alignment.[/yellow]")
        return

    try:
        spec = importlib.util.spec_from_file_location("validate_and_align", analysis_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        con.print(f"[yellow]Could not load alignment module: {e}[/yellow]")
        return

    con.print(f"\n[bold]Auto-aligning {len(xdf_files)} XDF file(s)...[/bold]")
    log(f"AUTO-ALIGN starting for {len(xdf_files)} files")

    part_dfs = []
    for xdf in xdf_files:
        try:
            streams = mod.load_streams(xdf)
            markers = mod.get_markers(streams)
            df = mod.build_aligned_dataframe(streams, markers)
            part_dfs.append(df)
            n = len(df)
            dur = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]) / 60 if n > 1 else 0
            con.print(f"  [green]✓[/green] {os.path.basename(xdf):50} {n:6} rows  {dur:.1f}min")
        except Exception as e:
            con.print(f"  [red]✗[/red] {os.path.basename(xdf)} — {e}")

    if not part_dfs:
        con.print("[yellow]No data frames produced.[/yellow]")
        return

    # Merge all parts, collect all markers across parts
    import pandas as pd
    all_markers = []
    for xdf in xdf_files:
        try:
            streams = mod.load_streams(xdf)
            all_markers.extend(mod.get_markers(streams))
        except Exception:
            pass
    all_markers = sorted(set(all_markers), key=lambda x: x[0])

    combined = pd.concat(part_dfs, ignore_index=True).sort_values("timestamp").reset_index(drop=True)

    # Auto-enrich with message text if session JSON exists
    session_log_dirs = [
        os.path.normpath(os.path.join(data_dir, "..", "SessionLogs", "new")),
        os.path.normpath(os.path.join(data_dir, "..", "SessionLogs")),
    ]
    json_path = None
    for d in session_log_dirs:
        candidate = os.path.join(d, f"participant_{participant_id}.json")
        if os.path.exists(candidate):
            json_path = candidate
            break

    if json_path and all_markers:
        try:
            combined = mod.enrich_with_text(combined, all_markers, json_path)
            con.print(f"  [green]✓[/green] Text enrichment applied from {os.path.basename(json_path)}")
            log(f"AUTO-ALIGN enriched with text from {os.path.basename(json_path)}")
        except Exception as e:
            con.print(f"  [yellow]Text enrichment skipped: {e}[/yellow]")
    elif not json_path:
        con.print(f"  [dim]No session JSON found for {participant_id} — connect Quest via USB to enrich with text[/dim]")

    # Add time_s column (time from session start = 0)
    session_start = combined["timestamp"].iloc[0]
    combined.insert(1, "time_s", combined["timestamp"] - session_start)

    # Save combined CSV
    out_name = f"{participant_id}_combined_aligned.csv"
    out_path = os.path.join(data_dir, out_name)
    combined.to_csv(out_path, index=False, encoding="utf-8")

    total_dur = combined["time_s"].iloc[-1] / 60
    log(f"AUTO-ALIGN complete: {len(combined)} rows, {total_dur:.1f}min → {out_name}")

    con.print(f"\n[bold green]Aligned CSV saved:[/bold green] {out_path}")
    con.print(f"  {len(combined):,} rows  |  {total_dur:.1f} min  |  {len(combined.columns)} columns")
    con.print(f"  Columns: {', '.join(combined.columns.tolist())}\n")


def main() -> None:
    participant_id = ask_participant_id()
    log(f"SESSION START participant={participant_id}")

    relay = RelayLauncher()
    launched = relay.launch()
    if launched:
        log("RELAY launched PupilLSLRelay.exe")
        console.print("[dim]Pupil LSL Relay launched.[/dim]")
    else:
        console.print("[dim]PupilLSLRelay.exe not found in bin/ — assuming relay already running.[/dim]")

    watcher = StreamWatcher()
    watcher.start()

    recorder = Recorder(participant_id)
    recording_started = False
    start_time: Optional[datetime] = None

    marker_inlet: Optional[pylsl.StreamInlet] = None

    session_end_detected = threading.Event()
    quit_requested = threading.Event()

    import msvcrt

    def keyboard_listener():
        """Background thread: watch for Q keypress."""
        while not quit_requested.is_set():
            if msvcrt.kbhit():
                ch = msvcrt.getch().decode("utf-8", errors="ignore").upper()
                if ch == "Q":
                    quit_requested.set()
            time.sleep(0.1)

    kb_thread = threading.Thread(target=keyboard_listener, daemon=True)
    kb_thread.start()

    status_line = "Waiting for all streams..."
    dropout_streams: set = set()

    try:
        with Live(refresh_per_second=2, console=console) as live:
            while True:
                statuses = watcher.get_statuses()
                elapsed = (datetime.now() - start_time) if start_time else None

                live.update(build_panel(
                    participant_id=participant_id,
                    statuses=statuses,
                    status_line=status_line,
                    recording_file=recorder.current_file,
                    elapsed=elapsed,
                    start_time=start_time,
                ))

                # Detect new dropouts
                for name, s in statuses.items():
                    if s.dropped and s.required and name not in dropout_streams:
                        dropout_streams.add(name)
                        log(f"DROPOUT {name}")
                        if name == MARKER_STREAM_NAME:
                            marker_inlet = None
                        if recorder.is_recording:
                            recorder.stop()
                            log("RECORDING PAUSED due to dropout")
                            status_line = f"⚠  STREAM LOST: {name} — PAUSED"
                            recording_started = False
                            start_time = None

                # Clear dropout flag when stream returns
                for name in list(dropout_streams):
                    if statuses[name].connected:
                        dropout_streams.discard(name)
                        log(f"STREAM RESTORED {name}")

                # Auto-start recording once all streams present
                if watcher.all_connected and not recorder.is_recording:
                    try:
                        path = recorder.start()
                        recording_started = True
                        start_time = datetime.now()
                        log("ALL STREAMS READY — recording started")
                        log(f"RECORDING {path}")
                        status_line = "● RECORDING"
                        for name in watcher.get_statuses():
                            log(f"STREAM ONLINE {name}")
                    except FileNotFoundError as e:
                        status_line = f"ERROR: {e.args[0].splitlines()[0]}"
                        log(f"ERROR {e.args[0].splitlines()[0]}")

                # Open marker inlet once UnityMarkers is visible
                if statuses.get(MARKER_STREAM_NAME) and statuses[MARKER_STREAM_NAME].connected:
                    if marker_inlet is None:
                        marker_inlet = open_marker_inlet()

                # Poll for SessionEnd marker
                if marker_inlet and recording_started:
                    try:
                        sample, _ = marker_inlet.pull_sample(timeout=0.0)
                        if sample and SESSION_END_MARKER in sample[0]:
                            log("SESSION END marker received")
                            session_end_detected.set()
                    except Exception:
                        pass

                # Handle stop conditions
                if session_end_detected.is_set() or quit_requested.is_set():
                    reason = "SessionEnd marker" if session_end_detected.is_set() else "Q key"
                    status_line = f"Session complete ({reason}). Stop recording? [Y/n]  auto-stops in {AUTO_STOP_DELAY}s"
                    live.update(build_panel(
                        participant_id=participant_id,
                        statuses=statuses,
                        status_line=status_line,
                        recording_file=recorder.current_file,
                        elapsed=elapsed,
                        start_time=start_time,
                    ))
                    deadline = time.time() + AUTO_STOP_DELAY
                    confirmed = True
                    import msvcrt
                    while time.time() < deadline:
                        time.sleep(0.1)
                        if msvcrt.kbhit():
                            ch = msvcrt.getch().decode("utf-8", errors="ignore").upper()
                            if ch == "N":
                                confirmed = False
                                session_end_detected.clear()
                                quit_requested.clear()
                                status_line = "● RECORDING (continued by researcher)"
                                break
                            elif ch in ("Y", "\r"):
                                break
                    if confirmed:
                        break

                time.sleep(0.5)

    finally:
        quit_requested.set()
        duration = (datetime.now() - start_time) if start_time else timedelta(0)
        recorder.stop()
        watcher.stop()
        relay.stop()

        dur_str = str(duration).split(".")[0]
        log("RECORDING STOPPED")
        log(f"SESSION COMPLETE duration={dur_str} file={recorder.current_file}")

        console.print(f"\n[bold green]Session complete.[/bold green]")
        console.print(f"Duration : {dur_str}")
        console.print(f"File     : {recorder.current_file}")
        console.print(f"Log      : Data/Logs/session_{datetime.now().strftime('%Y-%m-%d')}.log\n")

        # Auto-align all XDF parts for this session into one combined CSV
        _auto_align(participant_id, recorder, console)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        log("SESSION INTERRUPTED by keyboard")
