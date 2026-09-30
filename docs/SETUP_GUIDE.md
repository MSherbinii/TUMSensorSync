# Sensor Setup Guide

Step-by-step for getting every sensor streaming and recording before a session.

**You need:** Samsung phone, Pupil Labs Neon eye tracker, Polar H10 chest strap, Meta Quest headset, Windows PC, one Wi-Fi network.

---

## ⚠️ RULE #1: EVERYTHING ON THE SAME NETWORK

**The Samsung phone, the Quest and the PC must all be connected to the exact same Wi-Fi network.** The sensors talk to the PC over that network (Lab Streaming Layer). If the devices are on different networks, the PC will see nothing.

- Connect all three to the same Wi-Fi **before** opening any app.
- Do not use guest or public networks (university, hotel, etc.). They often block device-to-device traffic. Use a dedicated router or a phone hotspot instead.
- Do not use a VPN on the PC or the phone.
- If you change networks, close and reopen the apps.

---

## Part 1: Before you start

1. Charge the phone, Neon and Quest.
2. Connect **phone, Quest and PC to the same Wi-Fi** (see Rule #1).
3. Turn **Bluetooth ON** on the phone (needed for the Polar H10).
4. Keep the phone screen awake during the session and turn off battery saver.

---

## Part 2: Heart rate (Polar H10 + RRStreamer)

1. **Wet the electrodes.** Water the two electrode patches on the inside of the strap until damp. Dry electrodes give no signal.
2. Put the strap on the participant, snug, just under the chest muscles, Polar logo in the middle facing up.
3. Clip the Polar H10 onto the strap. It switches on when it touches skin.
4. On the phone, open the **RRStreamer** app.
5. Connect to the heart monitor. Select the device named **Polar H10 + serial number** (for example `Polar H10 1339173B`). The serial must match the one in `orchestrator/config.json`.
6. Check that RRStreamer shows **"Streaming"**.

**Streams this creates on the network:** `HR Polar H10 <serial>` and `RR Polar H10 <serial>` (about 1 Hz).

---

## Part 3: Eye tracker (Pupil Labs Neon)

1. Plug the Neon into the phone with the USB cable.
2. Open the **Neon Companion** app and wait until the Neon shows as connected.
3. In the Companion app **Settings**, turn **ON** these:
   - **Stream over LSL** (this starts the LSL streams)
   - **Compute eye state** (needed for pupil diameter, which our data uses)
4. In the same Settings, set **Gaze data rate** to **200 Hz** (the other options are 100 Hz and 33 Hz; we need 200 Hz).
5. Put the Neon into the Quest face gasket and check the eyes show in the live preview.
6. You do not need to press record in the Companion app. The PC records everything over LSL.

**Streams this creates on the network:**
- `<Device name>_Neon Gaze`: gaze position plus pupil diameter (200 Hz)
- `<Device name>_Neon Events`: the names of events the Neon generates, as text. This is automatic once "Stream over LSL" is on.

Our own markers (scenario start, etc.) do **not** go through the Neon. They come from the Quest app as `UnityMarkers`.

---

## Part 4: VR headset (Quest)

1. Make sure the Quest is on the **same Wi-Fi** as the phone and PC.
2. Launch the study app (APK).
3. It sends two streams: `UnityMarkers` (scenario markers) and `SceneLuminance`.

---

## Part 5: PC

1. Confirm the PC is on the **same Wi-Fi** as the phone and Quest.
2. Check `orchestrator/config.json` exists (copy from `config.json.template` if not) and the Polar serial matches the strap you are using.
3. Check all streams are visible:
   ```
   python orchestrator/preflight.py
   ```
   All required streams must show as found.
4. Start the session:
   ```
   python orchestrator/run_session.py
   ```
   Enter the **Participant ID** when asked. Recording starts automatically once all streams are connected.
5. Run the experiment.
6. The session ends on the `SessionEnd` marker, or press **Q** to stop manually.
7. Recordings (`.xdf`) are saved in the Data/Recordings folder.

---

## Checklist

- [ ] Phone, Quest and PC on the **SAME Wi-Fi network**
- [ ] Bluetooth ON on the phone
- [ ] Electrodes wet, strap on, Polar H10 clipped in
- [ ] RRStreamer open, Polar connected, says "Streaming"
- [ ] Neon plugged into the phone, Neon Companion open
- [ ] Neon Companion: **Stream over LSL** ON
- [ ] Neon Companion: **Compute eye state** ON
- [ ] Neon Companion: **Gaze data rate** = 200 Hz
- [ ] Study app running on the Quest
- [ ] `preflight.py` shows all streams found
- [ ] `run_session.py` started, Participant ID entered

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No streams on the PC at all | Devices are not on the same network. Check all three. Avoid guest networks and VPNs. |
| Heart rate missing | Re-wet electrodes, tighten strap, reconnect in RRStreamer, check Bluetooth. |
| Polar connects but PC does not find it | Serial in `config.json` does not match the strap. |
| No Neon gaze stream | "Stream over LSL" is off in Neon Companion, or the Neon is not connected. |
| Pupil data missing or empty | "Compute eye state" is off in Neon Companion. |
| `UnityMarkers` missing | Study app is not running on the Quest yet. |
| Streams drop mid-session | Phone went to sleep, battery saver, or weak Wi-Fi. |
