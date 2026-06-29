#!/usr/bin/env python3
"""
preflight.py -- Run this before starting a session.

Checks that all required LSL streams (configured in config.json) are
visible and healthy. Also shows stream details to help diagnose
connection issues.

Usage:
    python preflight.py
    python preflight.py --wait 30    # wait up to 30s for streams (default 10)
"""
import sys
import os
import time
import argparse

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pylsl
except ImportError:
    print("pylsl not installed. Run: pip install pylsl")
    sys.exit(1)

try:
    import config as _config
    EXPECTED = _config.expected_streams()
except Exception as e:
    print(f"Warning: could not load config.json ({e}). Using defaults.")
    EXPECTED = [
        {"label": "UnityMarkers", "match": "name", "value": "UnityMarkers", "required": True,
         "hint": "Start the VR app on the Quest"},
        {"label": "Neon Gaze", "match": "type", "value": "Gaze", "required": True,
         "hint": "Enable LSL in Neon Companion app on phone"},
        {"label": "HR Polar H10 1339173B", "match": "name", "value": "HR Polar H10 1339173B", "required": True,
         "hint": "Open RRStreamer -> connect Polar H10 -> serial must be 1339173B"},
        {"label": "RR Polar H10 1339173B", "match": "name", "value": "RR Polar H10 1339173B", "required": True,
         "hint": "Same as HR -- RRStreamer must show 'Streaming'"},
    ]

REQUIRED_SPECS = [s for s in EXPECTED if s.get("required", True)]
OPTIONAL_SPECS = [s for s in EXPECTED if not s.get("required", True)]


def scan(wait_s: float) -> list:
    return pylsl.resolve_streams(wait_time=wait_s)


def check_streams(streams: list) -> dict:
    found_names = {s.name() for s in streams}
    found_types = {s.type() for s in streams}
    results = {}
    for spec in EXPECTED:
        if spec["match"] == "name":
            results[spec["label"]] = spec["value"] in found_names
        else:  # type
            results[spec["label"]] = spec["value"] in found_types
    return results


def print_all_streams(streams: list):
    if not streams:
        print("  (no streams found on network)")
        return
    for s in streams:
        print(f"  {s.name()!r:45}  type={s.type()!r:12}  Hz={s.nominal_srate():.0f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", type=float, default=10.0, help="Seconds to wait for streams (default 10)")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  TUMSensorSync Pre-flight Check")
    print("=" * 60)
    print(f"\nScanning for LSL streams ({args.wait:.0f}s)...\n")

    streams = scan(args.wait)

    print("All streams visible on network:")
    print_all_streams(streams)
    print()

    results = check_streams(streams)

    print("Required stream status:")
    all_ok = True
    for spec in REQUIRED_SPECS:
        ok = results[spec["label"]]
        all_ok = all_ok and ok
        status = "OK  " if ok else "MISS"
        icon   = "+" if ok else "!"
        print(f"  [{icon}] {status}  {spec['label']}")
        if not ok:
            print(f"         Fix: {spec['hint']}")

    if OPTIONAL_SPECS:
        print("\nOptional stream status (recorded if present, never blocks):")
        for spec in OPTIONAL_SPECS:
            ok = results[spec["label"]]
            icon = "+" if ok else "-"
            status = "OK    " if ok else "absent"
            print(f"  [{icon}] {status}  {spec['label']}")

    print()
    if all_ok:
        print("  ALL REQUIRED STREAMS READY")
        print("  You can now run: python run_session.py")
        return 0
    else:
        missing = sum(1 for v in results.values() if not v) - len(
            [s for s in OPTIONAL_SPECS if not results[s["label"]]]
        )
        print(f"  {missing} required stream(s) missing. Fix the issues above and re-run preflight.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
