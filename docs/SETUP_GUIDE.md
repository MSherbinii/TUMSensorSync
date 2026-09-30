# Sensor Setup Guide (Plain English)

A simple step-by-step for getting all sensors running and recording before a session.

**What you need:** Samsung phone, Pupil Labs Neon eye tracker, Polar H10 chest strap, Meta Quest headset, Windows PC, one Wi-Fi network.

> **Golden rule:** Phone, Quest and PC must all be on the **same Wi-Fi network**. If they are not, nothing will show up on the PC.

---

## Part 1 – Before you start (5 min)

1. Charge everything: phone, Neon, Quest. Polar H10 needs a working battery too.
2. Connect the **phone, Quest and PC** to the same Wi-Fi.
3. Turn **Bluetooth ON** on the phone.
4. Turn off any battery saver on the phone (it can kill the apps mid-session).

---

## Part 2 – Heart rate (Polar H10 + RRStreamer)

1. **Wet the electrodes.** Water the two flat rubber/fabric patches on the inside of the strap until damp. Dry electrodes = no signal.
2. Put the strap on the participant, snug, just under the chest muscles. The Polar logo sits in the middle, facing up.
3. Clip the Polar H10 sensor onto the strap. It wakes up automatically once it has skin contact.
4. On the phone, open the **RRStreamer** app.
5. Connect to the heart monitor. Choose the device named **Polar H10 + its serial number** (example: `Polar H10 1339173B`).
   - Serial must match the one in the config (see Part 5).
6. Check the app says **"Streaming"**.
7. You should see a heart rate number updating. If it shows nothing, re-wet the electrodes and tighten the strap.

**Stream names that appear on the network:** `HR Polar H10 <serial>` and `RR Polar H10 <serial>` (about 1 Hz).

---

## Part 3 – Eye tracker (Pupil Labs Neon)

1. Plug the Neon into the phone (USB cable).
2. Open the **Neon Companion** app on the phone. Wait until it shows the glasses as connected.
3. Open the app **Settings** and look for the **LSL / "Stream over LSL"** option. **Turn it ON.**
   - If the app has an option to stream/enable **LSL markers/events**, turn that ON as well.
4. Check the **gaze sampling rate (Hz)** in the settings. Set it to **200 Hz** (this is what the system expects).
5. Put the Neon into the Quest face gasket and check the eyes are visible in the live preview.
6. Do not start a Neon recording manually unless you want a backup. The PC records everything through LSL.

**Stream that appears on the network:** `Gaze` (about 200 Hz).

---

## Part 4 – VR headset (Quest)

1. Put the headset on the participant (or hold it ready).
2. Launch the **study app (APK)** on the Quest.
3. Once running, it sends a `UnityMarkers` stream (events like scenario start, etc.) and a `SceneLuminance` stream.

---

## Part 5 – PC: check and record

1. Open a terminal in the project folder.
2. Make sure `orchestrator/config.json` exists (copy from `config.json.template` if not) and the **Polar serial number matches** the strap in use.
3. **Check all streams are visible:**
   ```
   python orchestrator/preflight.py
   ```
   Everything required should show as found. If something is missing, see Troubleshooting below.
4. **Start the session:**
   ```
   python orchestrator/run_session.py
   ```
   Enter the **Participant ID** when asked. Recording starts automatically once all streams are connected.
5. Run the experiment.
6. Session ends on the `SessionEnd` marker, or press **Q** to stop manually.
7. Recordings (`.xdf`) are saved in the Data/Recordings folder.

---

## Quick checklist (print this)

- [ ] Phone, Quest, PC on same Wi-Fi
- [ ] Bluetooth ON on phone
- [ ] Electrodes wet, strap on, Polar H10 clipped in
- [ ] RRStreamer open, Polar connected, says "Streaming"
- [ ] Neon plugged in, Neon Companion open
- [ ] LSL streaming ON in Neon Companion (plus markers if available)
- [ ] Gaze set to 200 Hz
- [ ] Study app running on Quest
- [ ] `preflight.py` shows all streams found
- [ ] `run_session.py` started, Participant ID entered

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No streams on PC at all | Not on same Wi-Fi. Check all three devices. Some networks (guest/university) block device-to-device traffic, so use a dedicated router or hotspot. |
| Heart rate missing | Re-wet electrodes, tighten strap, reconnect in RRStreamer, check Bluetooth is on. |
| Polar connects but PC does not see it | Serial in `config.json` does not match the strap. Fix the serial. |
| No `Gaze` stream | LSL not enabled in Neon Companion, or Neon not plugged in. |
| `UnityMarkers` missing | Study app is not running on the Quest yet. |
| Streams drop mid-session | Phone battery saver, phone went to sleep, or weak Wi-Fi. Keep the screen awake and apps in foreground. |
