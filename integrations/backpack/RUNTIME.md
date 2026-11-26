# Reboot-safe DAWN runtime

See [event history, mode policy, service preferences and restart handoff](EVENTS.md) for the new unified continuity layer.

The optional [resident YOLO service](YOLO.md) runs alongside DAWN and Ollama, keeps its GPU model warm, and accepts owner-only on-demand camera detection plus streamed Goggles 3 frames. Its November 9 workload peaked at 11.1 GB against the working decimal 12 GB ceiling; that measurement predates continuous drone capture.

The native backpack runtime is opt-in through `DAWN_BACKPACK_SOCKET`. The service installation enables four user services: `backpack-mqtt-dev`, `backpack-power-sim-dev`, `backpack-runtime`, and `backpack-dawn-dev`. User lingering must remain enabled for startup without a desktop login. This is still a development deployment with simulated battery telemetry.

## Host diagnostics, control and acceptance cues

See [host tools](HOST_TOOLS.md) for actual uptime/memory/CPU/disk/temperature readings, the OS-confined general diagnostic CLI, confirmed shutdown/reboot/dawn-or-yolo restarts, and eight randomly selected native acceptance cues. Real host statistics are separate from the simulated battery feed. Host changes use attended confirmation; the CLI cannot bypass it.

## Conversation continuity

The local microphone conversation is checkpointed at completed turns and before submitting a power change. A private SQLite store at `~/jetson-backpack-dev/run/backpack.db` retains up to 32 user/assistant text messages, bounded to 4,000 characters per stored message. Provider system prompts, raw tool protocol rows, images and audio are not restored. Checkpoints are keyed by the local session's effective owner (default voice user 1). Resetting the local conversation clears its saved checkpoint. This is bounded conversational continuity, not a long-term semantic-memory implementation; DAWN's optional memory extraction remains disabled.

DAWN's existing authenticated web conversations continue to use its original auth database. No administrator account or password is created by these scripts.

## Direct battery status

Common local questions such as “what is the battery status?” and “what's the battery status?” read the current STAT telemetry snapshot and speak a brief aggregate answer without model inference. The route runs after the existing Victor engagement gate, preserves simulated-data labeling and battery freshness, and reports unavailable/stale data instead of remembered readings. Historical and slot-specific questions still use the model path. A live AirPods turn completed in 7.0 seconds including the question; see [validation](VALIDATION.md).

## Drone feed

**ASTRA is the canonical aerial workflow name and model tool (`astra`).** Recon and Icarus are its only mode/status keyword aliases. Say **“Victor, start ASTRA mode”** or **“Victor, initiate ASTRA.”** The native voice worker starts YOLO and headless LiveView, then verifies a goggles frame decoded after the command, a completed inference and current sampling metrics. Only then does it report **“ASTRA is ready. Goggles connected, YOLO online”**, followed by the target and measured rates. Missing video, sampling or inference produces a waiting/failure response rather than announcing readiness.

Say **“Victor, ASTRA stats”** or **“Victor, ASTRA status”** for service state, feed freshness, measured sampling and inference rates, and the explicit ArduPilot-not-configured status. **“Victor, stop ASTRA mode”** or **“Victor, terminate ASTRA”** stops capture first, then stops the YOLO process to release its CUDA/model resources. It verifies both process IDs are zero before clearing cached frames, detections and metrics and announcing termination. Partial shutdown is reported as incomplete. A concurrent termination cancels pending readiness waits and suppresses a delayed scene description.

Substitute **recon** or **Icarus** for ASTRA in these start/stop/mode/status/stats forms. For example: “start recon mode,” “stop Icarus,” and “Icarus stats.” All responses retain the primary ASTRA name. The existing “drone recon” wording remains a qualified recon form. Names such as Astro, Hermes and Sentinel are not lifecycle aliases. Merely discussing a name or asking how to start it does not match the direct command grammar. The older “pull up the drone feed” wording is no longer a direct lifecycle keyword command.

Follow with **“What's on the eye in the sky?”** within the existing two-minute engagement window, or include Victor again. The direct route also accepts “What on the eye in the sky?” and “What is on the eye in the sky?” The model-selectable `astra` tool exposes `start`, `stop`, `status` and `describe`. Drone requests never fall back to the CSI camera. Internal runtime operations and service names are retained for compatibility; they do not determine the spoken workflow keyword.

The observed Whisper transcription “What's on the iron sky?” is also a direct alias. Leading and trailing transcription whitespace is trimmed before matching; the native test covers both cases. “Describe the drone view” is another direct phrase.

`DroneFeed` waits for a source-tagged frame decoded after each question, verifies its age is at most two seconds, and sends it to the local Qwen vision model. YOLO detections accompany the runtime result; Qwen produces the spoken description. This describes the current point-in-time view, not movement across multiple frames. DAWN/Piper speaks through the existing audio routes and suppresses an interrupted reply. Continuous unsolicited spoken alerts are not enabled.

**PiP pauses LiveView sharing.** Missing fresh frames produce an unavailable/paused response. Scene requests wait at most eight seconds for a new frame, then use a 90-second local vision timeout. Private snapshot files are never stale fallback. While a recon session is active, headless capture retries without a UI. Both recon services are disabled at boot and started on command; the native installer preserves this policy without stopping an active session. The desktop test service remains disabled. DAWN, Qwen, Bluetooth audio and the ordinary backpack camera remain independent of recon termination. ArduPilot is not installed or managed by these commands.

## Camera look

Say **“Vic, are you seeing this?”**, **“Victor, what do you see?”**, or **“Hey Victor, can you see this?”**. Vic is a whole-word local microphone nickname for Victor and opens the same 120-second engagement window. It does not change the prefix-only gate for other input surfaces.

The local `camera_look` tool takes a fresh IMX477 frame using Argus, warms exposure over 15 frames, applies `nvvidconv flip-method=2` for the physical 180-degree mounting correction, and sends a 640 × 360 JPEG to the resident Qwen model through loopback Ollama. Exact common camera questions invoke this tool's capture/description path directly on the voice worker, avoiding an extra model round trip for tool selection. Other local questions can select `camera_look` through normal tool calling. Vision runs independently of the normal text-only conversation settings; no cloud service or helmet MQTT camera is used.

The camera accepts one request at a time, limits questions to 500 characters and images to 1 MiB, bounds capture to 20 seconds and inference to 90 seconds, and never substitutes an old image after capture failure. The microphone processing loop remains active while the worker waits. An interrupted turn does not speak its delayed description. Temporary frames are removed; one owner-only `run/camera-latest.jpg` is overwritten for orientation review and is never used as capture fallback. Conversation checkpoints retain the spoken text, not an image. Captured writing is treated as scene content rather than instructions. The still frame is a point-in-time view; subsequent camera questions take another picture.

## Verified power changes

Clear local power questions (for example “check the wattage”) and explicit “change the power mode to 10 watts” requests use a small native command route before the LLM. Status is read from the runtime and spoken as a short template. The same runtime validation/confirmation applies to both this route and LLM-selected requests.

The local `jetson_power` tool has `status` and `set` actions. `set` only prepares a request and speaks: “You requested N watts. Swapping power modes requires a reboot. Please confirm.” It requires an integer wattage matching an installed `/etc/nvpmodel.conf` profile. Unsupported/ambiguous profiles and concurrent pending changes are rejected. The tool is explicitly enabled only for this development local microphone; it is not a generic shell, remote power endpoint, or schedulable task.

No hardware command runs at preparation. Only an attended local microphone utterance exactly matching a confirmation phrase (such as “yes” or “confirm”) can accept the request, after the Victor engagement gate. “No”, “cancel”, or “never mind” cancels it. Unconfirmed requests expire after 120 seconds and are cancelled across boots. The LLM tool has no confirmation action, so it cannot confirm its own request.

After user confirmation, native code speaks the user's requested exact phrase: **“Standby by for power change, initiating reboot”**. It waits for the TTS queue to complete before asking the runtime to initiate the change. A missing headset, failed announcement, expired request or runtime failure prevents initiation. A disconnect cannot be treated as confirmation.

Before a hardware command can run, the runtime commits an explicitly confirmed action record with the requested wattage, resolved profile ID and kernel boot ID using SQLite WAL and FULL synchronous transactions. A worker waits five seconds for the acknowledgment, applies the profile with `sudo -n /usr/sbin/nvpmodel -m <validated-id>`, and permits nvpmodel's required reboot. If the command returns successfully without rebooting, it schedules a reboot in one minute. Existing passwordless sudo authorization is used; no new sudoers grant is installed. The tool never reports a queued request as verified success.

On startup, only a different boot ID can complete an in-flight reboot request. The runtime queries `nvpmodel -q` and compares both profile ID and named wattage. A match is recorded as verified; a mismatch becomes a failed result describing the actual mode. Read failures leave verification pending for retry. It does not automatically retry a hardware change after a service crash. Power-action records survive process restarts and remain available after spoken delivery.

## Web status and audio

The DAWN account menu links to `/backpack.html`. Its `/api/backpack/status` endpoint requires an administrator login and returns current power state and persisted action results. It is read-only. The development web server uses HTTPS on LAN port 3001; see [browser access and certificate setup](DEV_SETUP.md#browser-access). The current NX has an administrator account; fresh installations still require separate enrollment.

DAWN captures `backpack_capture.monitor` and plays to `backpack_playback`, stable PipeWire/PulseAudio null devices maintained by the runtime. When exactly one Bluetooth microphone and output appear, owned loopbacks route them to those devices. Disconnecting the headset removes those loopbacks; DAWN and its web UI stay running. Reconnecting recreates them without restarting DAWN. Headset playback is set to the user's requested 90% when connected. The runtime does not pair devices or guarantee unattended Bluetooth reconnection; the headset must actually connect to the NX.

Verified/failed action notices wait in the database while audio is unavailable. DAWN speaks them when a headset route is ready and no local LLM turn is busy; the exact confirmation comes from the verification record, not an LLM. The notice is marked delivered only after the TTS queue reports completion and the route is still ready. Interruptions/disconnects may cause a repeated announcement; physical hearing is not provable in software. Shutdown joins the notification worker before TTS/session teardown.

The two-minute Victor engagement window gates new user commands. A previously requested post-reboot confirmation can be delivered outside that window without starting a new LLM/tool turn.

## Operation and checks

```sh
bash ~/jetson-backpack-dev/backpack/start_dev.sh
systemctl --user status backpack-runtime backpack-dawn-dev
systemctl --user stop backpack-dawn-dev backpack-runtime backpack-power-sim-dev backpack-mqtt-dev
```

`start_dev.sh` idempotently installs/enables the native user services. It no longer requires a headset. Runtime starts before DAWN, and model warmup runs independently so loading Qwen cannot block the web startup. To disable boot startup, use `systemctl --user disable --now` on the four units. Existing state is preserved.

Tests: `python -B -m unittest discover -s software/jetson/backpack -p test_runtime.py -v`. The state-machine tests replace hardware commands and never reboot or alter power. They cover durable intent, actual-state mismatch, unreadable verification, owner isolation, delivery acknowledgment, no-op/rejected changes, and audio reconnect/partial-route cleanup. Real-device validation is recorded in [VALIDATION.md](VALIDATION.md).
