# DAWN development instance on the NX

The development workspace is `~/jetson-backpack-dev` on the NX. `dawn/` is the fork's source checkout with our integration changes; `backpack/` contains the simulator and launch/configuration files. `deps/` holds private speech libraries, and `run/` holds private development state and logs. These are separate from any production deployment.

## Build configuration

- Jetson Linux R39.2, Ubuntu 24.04 ARM64.
- Vendor `nvidia-cuda-dev` provides CUDA toolkit 13.2; Whisper builds for Orin's compute capability 8.7.
- At the user's request, the NX was switched from 10 W to 25 W (profile 3), rebooted, and verified with all eight CPU cores online. Builds use the online core count.
- Whisper base model is downloaded into `dawn/models/whisper.cpp`.
- Piper phonemization release `2023.11.14-4` is rebuilt against ONNX Runtime 1.19.2 so the process does not load two conflicting ONNX versions. Its eSpeak fork is private; the matching speech data is installed at `/usr/share/espeak-ng-data` only if that directory does not exist.
- Web UI and local audio are compiled. Terminal dashboard, optional code-project/MCP bridge, document search, and WebRTC echo cancellation are disabled for this development build.
- The email code is compiled because the current web UI fails its unused-function check with email disabled. No email accounts are configured. Local model tools are explicitly limited to simulated system/battery status, camera capture, Jetson power modes, actual host status, confined diagnostics, and confirmed host-action proposals; see [host tools](HOST_TOOLS.md).

Prepare private speech dependencies, then build the prepared checkout:

```bash
bash ~/jetson-backpack-dev/backpack/prepare_speech_deps.sh
bash ~/jetson-backpack-dev/backpack/build_dev.sh
```

Core distro build dependencies include CMake/Ninja, ALSA/PulseAudio, sndfile/FLAC, libmosquitto, curl/OpenSSL, libwebsockets, Opus, sodium, samplerate, ical, stemmer, XML, spdlog, GMime, JSON-C, and SQLite development packages. `mosquitto`, `mosquitto-clients`, and `pulseaudio-utils` support the isolated runtime. The distro-wide Mosquitto service is disabled; the development broker is a user service bound only to loopback.

The eSpeak-only prefix in the preparation script matters: pointing at the whole upstream phonemizer bundle silently selects its ONNX 1.14 library ahead of 1.19. The prepared library's dynamic dependencies were checked to resolve to ONNX 1.19 only.

## Local model

The development alias uses Qwen3.5 4B Q4_K_M. The original 9B model remains on disk for rollback:

```bash
ollama pull qwen3.5:4b-q4_K_M
ollama create backpack-dev-qwen -f ~/jetson-backpack-dev/backpack/Modelfile.dev
```

The alias limits context to 8192 tokens, uses temperature zero, and defaults to 256 output tokens; DAWN requests cap output at 128. Startup loads it with indefinite residency. Stop the previous alias before recreating it so only the selected model remains resident.

DAWN's Ollama chat-compatibility requests now send `reasoning_effort` rather than the native API's `think` flag. This matches [Ollama's compatibility documentation](https://docs.ollama.com/api/openai-compatibility). Live requests verified that `none` suppresses reasoning and preserves the battery tool call. Initial measurements were made during compilation in the NX's existing 10 W mode and are not final latency benchmarks.

## Start and stop

### Local headset engagement

The local microphone requires a whole-word, case-insensitive mention of the configured assistant name (`Victor`) to open a 120-second response window. A greeting is optional. Subsequent utterances can dispatch commands during that window, but do not extend it; only another name mention does. At exactly 120 seconds, new voice commands are rejected before direct tools or LLM dispatch. Expiry is checked again when a recorded or queued command reaches dispatch. Work already started is not cancelled by expiry.

Passive VAD/transcription remains necessary to detect the name while disengaged. Follow-ups without the name are ignored while a reply is busy; explicit name mentions retain interruption behavior. Browser, satellite, and typed input policies are unchanged. The native build and 51 wake-word tests pass on the NX; the two-minute timeout still needs a timed microphone test.

Start or install the persistent native user services (a headset is optional):

```bash
bash ~/jetson-backpack-dev/backpack/start_dev.sh
```

The runtime maintains stable virtual capture/playback devices and links exactly one connected Bluetooth microphone/output when available. DAWN and its web UI start without a headset. Connected headset output is set to the user's requested 90%.

Four persistent user services are enabled at boot: `backpack-mqtt-dev`, `backpack-power-sim-dev`, `backpack-runtime`, and `backpack-dawn-dev`. Lingering is enabled. The power simulator remains explicitly simulated. The web UI uses HTTPS on LAN port 3001 and the broker remains on loopback port 18884. Web account enrollment is separate; the current NX has an administrator account. First-run enrollment-token lines remain filtered from logs.

### Browser access

Open [DAWN on the NX](https://192.168.2.236:3001/). No SSH tunnel is required on the LAN. HTTP on a LAN IP cannot retain DAWN's `Secure` authentication cookie; successful password validation otherwise redirects straight back to login. Browsers make an exception for localhost, which explains why the previous HTTP SSH tunnel worked.

The private runtime directory contains `run/ssl/dawn.crt` and `run/ssl/dawn.key`. The certificate is self-signed, valid for one year from November 24, 2026 (Eastern time), and covers the current LAN IP, loopback, localhost, and the Jetson names. Trust the public certificate on each client, or explicitly accept its certificate warning for this device. Keep the private key on the NX; never copy it into this repository. Renew the certificate before expiry or when the LAN IP changes. An SSH tunnel still works with `https://127.0.0.1:3001/`.

On a fresh development installation, provision those certificate files before starting DAWN with the HTTPS-enabled configuration. They are deliberately absent from source control. For an installation using DAWN's private CA generator instead, configure its certificate chain and key paths as described in [DAWN's HTTPS setup](../dawn/docs/GETTING_STARTED_SERVER.md).

```bash
systemctl --user is-active backpack-mqtt-dev backpack-power-sim-dev backpack-runtime backpack-dawn-dev
systemctl --user stop backpack-dawn-dev backpack-runtime backpack-power-sim-dev backpack-mqtt-dev
```

See [reboot-safe runtime behavior](RUNTIME.md) for conversation checkpoints, the explicit power-change confirmation, actual-mode verification, queued speech and the authenticated status page.

The voice test phrase is **“Hey Victor, what is the battery status?”** Expect a short response explicitly labeled simulated. The direct spoken summary reports the illustrative combined level of 75%; per-slot data remains available through the full telemetry tool. None of these readings come from a real battery board.

See [validation results](VALIDATION.md) for what has actually been verified. A running service alone does not prove end-to-end speech intelligibility or tool-call accuracy.
