# Power telemetry validation

## Synced upstream integration — 2026-11-25

Integrated upstream `04a25f2c` with the versioned Backpack bridge and companion runtime on `codex/backpack-upstream-20261125`. The deployed product-code commit is `a6032875`. The six previously untracked Dawn files and the companion deployment/test sources are now committed.

The native ARM64/CUDA Release candidate and the build in the deployed workspace passed, including the build-time source invariants. The Backpack harness passed 36 telemetry tests (one existing ignored case), 12 attention tests, the native acknowledgment/fake-socket collector, and all 78 Python tests. The WebUI-enabled CI test build completed: 264 suites passed initially; the remaining document-extraction suite passed after its MIME expectations were made conditional on compiled PDF/DOCX support. Thus all 265 selected CI suites passed across the run and the focused rerun. Two GCC truncation failures were also corrected: the repository-import confirmation wording and bounded test-failure excerpts.

A separate network namespace kept the candidate's HTTP listener and abstract admin socket isolated from the running daemon. Against copies of the actual databases, the final candidate migrated auth schema to v117 and preserved the original account/password-hash records. Generated test credentials stayed in memory and applied only to the copied database. Checks passed for invalid-password rejection, successful HTTPS login, Secure/HttpOnly/SameSite cookies, authenticated UI/session status, administrator-only Backpack access, and non-admin rejection. No real operator password was requested or reset.

Chromium checked the merged wrapping header at widths 320, 375, 393, 402, 430, 480, 500 and 600 pixels with optional controls visible. WebKit checked the 402-pixel mobile layout. No toolbar controls extended beyond the viewport. Scoped clang-format-14 and Prettier checks, companion Python syntax checks, a GCC analyzer run on the C bridge, and focused secret-pattern/source review passed. The npm lockfile audit reported no advisories. The pinned clang-tidy tool, CodeQL, sanitizer builds and physical microphone/camera/drone/radio tests were not run in this task; optional PDF/DOCX extraction cases remain skipped when their libraries are absent.

Private pre-upgrade source, binaries, configuration, units, certificates and consistent database snapshots were retained under `run/upstream-integration-20261125-before`. A fresh checkpoint with DAWN stopped is under `run/upstream-integration-20261125-final`; its `source-recovery.json` records the original branch and source stash. The live configuration and companion service code were preserved. The running service reports `a6032875`, auth schema is v117, account records/configuration compare unchanged, and music/queue databases pass SQLite integrity checks. DAWN and its runtime, MQTT, simulator and Meshtastic adapter services are active; DAWN reported zero automatic restarts at acceptance. LAN HTTPS login returns HTTP 200, while unauthenticated Backpack API access redirects to login.

For rollback, stop DAWN before restoring its matching source/binary and auth/music snapshots. Preserve post-upgrade data separately first. Do not restore the independently running Backpack/STAT databases while their writers remain active. See [integration and recovery guidance](INTEGRATION.md).



## Unified events and restart continuity — 2026-11-23

Implemented the [event and continuity contract](EVENTS.md): additive SQLite event tables,
90-day communications/fault retention, 14-day activity retention, protected saved events,
bounded ingestion and diagnostic log rotation. Silent mode persists across restarts and
explicit history readouts retain that mode. Service preferences separate autostart from
same-boot overrides and do not take control of existing unmanaged peripherals.

On the physical ARM64 NX, the full native build passed. The Linux validation harness passed
78 Python tests, 36 telemetry tests (one existing ignored case), 12 attention tests, and the
native fake-socket/collector tests including startup handoff and filesystem/abstract watchdog
notification addresses. Scoped clang-format checks passed. The existing build invariant
checks also passed. No automated secret scanner or Python security linter is configured;
focused review found no new secrets, shell execution or external transmission of stored data.

The installed Meshtastic SDK reproduced its documented heartbeat broken-pipe issue.
The new adapter instead uses its protobuf definitions with the documented framed TCP protocol.
A 45-second live probe retained verified readiness across repeated configuration exchanges;
an installed-protobuf packet fixture also passed decoding without any radio transmission.
Channel configuration snapshots remain transient and are not logged. Actual second-node
message delivery and physical microphone recognition of the new commands remain unverified.

Sources, native binaries, user units and a consistent SQLite backup were retained privately
under the NX run/continuity-20261123.KEwzR6/before directory before applying the change.
Runtime, DAWN and the adapter were restarted successfully; all were active with zero automatic
restarts at acceptance. DAWN reported notify readiness and a five-minute watchdog heartbeat,
its health endpoint returned HTTP 200, SQLite integrity was OK, and Meshtastic had fresh API
readiness. SDR remained unconfigured and did not claim ready. No host reboot, radio transmission,
SDR scanner installation or S3 upload was performed. Cold-boot behavior is covered by simulated
boot-ID tests rather than a physical reboot in this task.

## ASTRA primary keyword — 2026-11-14

Promoted ASTRA to the primary aerial workflow name, registered model tool and spoken report name. Recon and Icarus are the two mode/status keyword aliases. The direct grammar accepts start/initiate and stop/terminate with optional mode, plus status/stats and question forms. Existing qualified “drone recon” phrases remain supported. Removed the older descriptive feed-start phrases from direct lifecycle matching; eye-in-the-sky scene questions retain their existing route.

All 11 focused Python lifecycle tests passed, including canonical ready/terminated wording. The actual native phrase/fake-socket harness passed case/punctuation/whitespace, all three names, action/status forms, unsupported-name rejection and discussion/negation rejection. The native DAWN rebuild passed. Physical recognition of the expanded ASTRA/recon/Icarus command set remains to test; the earlier single Astra transcription was successful.

## Drone recon lifecycle — 2026-11-14

Added the direct “start recon mode” and “stop recon mode” aliases. Both passed the native phrase/request harness, including punctuation, whitespace and rejection of a how-to question; the DAWN rebuild passed. Physical speech recognition of these new aliases remains to test.

Added native initiate/terminate/status phrases and tool actions. Startup gates readiness on fresh post-command video, a completed inference and current positive sampling metrics. Status reports actual service PIDs, freshness, sampling and inference rates, with ArduPilot explicitly not configured. Shutdown stops capture before YOLO, verifies both process IDs are zero, and removes private frame/result/metric caches. Termination cancels pending readiness/description results. Both services now start on demand; reinstalling native services disables their boot startup without interrupting an active session.

Thirty-seven focused Python tests passed initially; after the final lifecycle/installer adjustments, all 27 affected drone/runtime tests passed. The viewer's 24 .NET tests passed, and the ARM64 recon build and native DAWN build succeeded. The native collector/fake-Unix-socket harness compiled with warnings as errors and checked exact phrase routing, operation mapping, refusal of stale readiness/wrong-source descriptions, and acceptance of a verified stopped status without a fresh frame. Three relevant CTest suites passed.

Two real runtime-socket start/stop cycles passed against the physical goggles. Readiness reported approximately 15 submitted FPS and 12 completed inferences per second. Stop reported both MainPIDs zero; cached images/results and `yolo.sock` were gone, and the second start used a new model PID. DAWN health and both AirPods routes remained active. Recon was left stopped for the user's voice test. ArduPilot installation was not attempted. Sustained performance and exact spoken initiate/terminate/status recognition remain unverified.

## Headless drone feed and Victor requests — 2026-11-14

Added `--yolo --yolo-fps 15`, bounded raw-frame IPC to resident YOLO, automatic USB retries, and the direct spoken start/eye-in-the-sky routes. Fresh source-tagged frames are required after each command; no CSI or stale-frame fallback is allowed. PiP sharing pauses are documented. See [operation](YOLO.md#headless-drone-input) and [voice workflow](RUNTIME.md#drone-feed).

On ARM64, 24 .NET tests passed, including a real Unix-socket payload/oversized-response test and sysfs regression tests. Thirty-one focused Python tests passed across YOLO, drone freshness/readiness, existing CSI descriptions and runtime behavior. The native DAWN build and wake-word, frozen-schema and prompt-builder CTest suites passed. The actual C drone phrase matcher passed in the acknowledgment collector harness compiled with warnings as errors. The native build retained its existing ccache and real-time audio scheduling warnings.

The live runtime socket returned readiness only after a post-command goggles frame, then returned a local Qwen description with source `goggles3`. Snapshot, latest-result and socket modes were verified as 0600. The running process has no DISPLAY or WAYLAND_DISPLAY and no Xvfb/preview. Both AirPods loopbacks were active, and DAWN health returned ok. Short samples measured 30 decoded FPS, approximately 15 submitted FPS and 12–13 completed inferences per second; sustained memory/thermal performance and the physical microphone-to-spoken-drone-answer workflow remain unverified pending user testing.

Scoped changed-file whitespace checks passed. A broader pre-existing CRLF whitespace issue in `include/core/wake_word.h` was left untouched. No new dependency was introduced; no automated secret scanner or Python security linter is configured in this workspace. A focused source review found no new credentials or external image transmission; vision remains on loopback.

During the user's first microphone test, Whisper produced “What's on the iron sky?” and a subsequent “What on the eye in the sky?” with leading whitespace. The latter reached `drone_feed` through model selection and completed a source-specific description, but tool selection added roughly 26 seconds. Added the observed alias and whitespace trimming to the native direct matcher; rebuilt and reran the actual matcher harness. DAWN was reloaded after the active turn completed. Direct-route spoken latency and audibility still need the user's retest. Quiet inference samples were 12–13 FPS; compilation and Qwen contention reduced sampled inference throughput to approximately 6 FPS while capture/submission continued.

## Eight randomized acknowledgment cues — 2026-11-09

Kept the two existing cue phrases and added “On it”, “Let me check”, “One moment”, “Let me look into that”, “I'll check the details”, and “Give me a moment”. All accepted local request types now use the same eight-entry pool, selected with libsodium `randombytes_uniform(8)`. Each has an equal chance; natural consecutive repeats remain possible. Confirmations, cancellations, null input and the opt-out path do not consume a random draw or queue speech.

The native DAWN build passed, and the actual acknowledgment function passed its updated collector harness compiled with `-Wall -Wextra -Werror`. The harness supplies every possible random result in turn and checks the exact eight phrases across alternating host/camera questions, then verifies suppression without additional draws. This is deterministic coverage of the random-selection wiring, not an assertion about a short random sample's distribution. The production executable links the existing libsodium runtime; the test RNG override is only in the separate harness. Scoped diff whitespace and clang-format checks passed. No dependency was added.

The user confirmed the baseline spoken cue and actual memory reading were clear through the AirPods. Physical playback of all six new phrases and their individual audible-start timing were not separately measured.

## Actual host tools and spoken acceptance — 2026-11-09

Added `host_status`, `diagnostic_cli`, and confirmation-only `host_control` to the explicit local tool list. Actual memory/CPU/uptime/disk/temperature observations come directly from Linux, separate from the simulated STAT feed. Native common-question routes avoid model inference. The native local worker/direct routes queue “Checking that now” or camera-specific “Taking a look” before retrieval; confirmation/cancellation does not receive a second cue.

Validation completed on the NX:

- Native DAWN rebuilt. The focused CTest telemetry, wake-word, frozen-schema and prompt-builder targets passed (4/4).
- The actual acknowledgment C code compiled with `-Wall -Wextra -Werror` and section garbage collection, replacing only speech with a collector. Opt-out, host/camera cue selection, cancellation, confirmation and null-input cases passed. It did not perform any real speech or hardware action.
- Ten new Python host tests passed on PC and ARM64; all 16 existing runtime/power/audio tests passed. Host commands and worker execution are stubbed in state-machine tests. Cases cover real memory calculation without process-argument exposure, bounded output, immutable sandbox launch settings, durable confirmation, expired/cancelled/disconnected/replayed proposals, boot verification, unsupported services, and mutual exclusion with power-mode requests.
- Real sandbox commands returned uptime, memory, architecture and a working awk pipeline. Attempts to write `/usr`, access host home/bus, create IPv4 sockets, and escalate with sudo failed or were hidden as intended. Private scratch files did not persist to the next request. Excessive output was bounded/truncated. `sleep 20` was stopped after about 8.5 seconds. The runtime did not fall back to an unrestricted shell.
- Systemd 255 namespace setup required masking `/run` using read-only tmpfs rather than `InaccessiblePaths`. Masked `/etc` retains only read-only public alternatives/OS-release bindings so normal Debian command symlinks work; shell variable expansion remains in bash rather than the systemd launcher.
- Scoped native whitespace/clang-format checks passed. No new dependency was added. No configured project secret scanner was found; focused changed-source/configuration review found no embedded credentials or secret-file contents.
- Sources and a consistent SQLite backup were preserved before the additive `host_actions` table was introduced. Existing histories and wattage-action data remain in the same private store. Old source can ignore the extra table.

After deployment, the real runtime RPC reported uptime 8,131.72 seconds and memory 65.8% (10.757 of 16.356 decimal GB) at that observation; a confined CLI query returned consistent live readings. DAWN health returned `ok`; both AirPods loopbacks, the runtime, DAWN and resident YOLO stayed active. No real shutdown, reboot or service-control action was executed during these checks. The user subsequently confirmed the acknowledgment and memory reading were clear through the AirPods; background speech alone was not treated as a test command. See [host operation and limitations](HOST_TOOLS.md).

## Resident YOLO follow-up — 2026-11-09

Installed YOLO26 nano as the persistent native `backpack-yolo` user service alongside the existing DAWN Whisper base/Piper runtime and resident Qwen. YOLO remains warmed on the GPU and detects only on request. Package installation added TensorRT 10.16.2.10 for CUDA 13.2 and distro OpenCV dependencies (15 packages, no upgrades/removals). PyTorch/Ultralytics were used only in an isolated PC export environment. No reboot, power change, or DAWN restart was needed for the YOLO service installation.

FP16 engine builds reproduced the TensorRT missing-convolution-shader/KTM assertion. FP32 with builder optimization zero, no auxiliary streams and a 256 MiB workspace built and executed on ARM64 CUDA. Exported ONNX SHA-256 is `22505be30d2a16cdc36e9f532f4fe198171f2c63f1d57042f9638a6b26711780`; target engine SHA-256 is `615625c475f0c0e1e71096a3284348df3cff2c3f6a1020e17e7f356c20481a84`.

Three detection contract tests passed on the PC and NX. They cover letterbox coordinate reversal, image bounds, labels, confidence limits and malformed/nonfinite output rejection. Python source syntax checks passed. Live owner-only socket checks verified readiness, invalid operation rejection, non-object rejection and socket mode 0600. The known bus image produced a bus and four people. Fresh upright-corrected camera detection returned successfully with no objects above the threshold. Quiet GPU inference was 62–66 ms; overlapping Qwen vision increased it to 142 ms. Camera capture plus YOLO detection took 2.5–2.7 seconds.

Available-based whole-system memory was sampled every 200 ms. Before YOLO mean was 10.512 GB; warmed idle mean was 10.721 GB; overlapping Qwen vision and YOLO peaked at 11.112 GB. All four models remained loaded, the work requests exited successfully, and Qwen was still GPU-resident afterward. This left 0.888 GB under the explicit decimal 12 GB ceiling. YOLO's own warmed process RSS was approximately 0.700 GB, including shared pages. Approximately 1.3 MB of swap remained used without growth in the overlap test. Whisper/Piper were resident, not intentionally exercised through simultaneous speech inference. Short sampling does not establish sustained/worst-case usage.

`pip-audit` reported no known vulnerabilities for the six pinned direct PC export requirements, with transitive resolution disabled; this was not a full transitive or distro-package security audit. Service enablement, continued DAWN health, and model residency were verified. See [YOLO operation, reproduction and memory results](YOLO.md) for commands and limits. YOLO is available through its local on-demand service; Victor's spoken camera descriptions continue using Qwen.

Verified November 7, 2026 on the ARM64 Jetson NX, using a temporary source copy and temporary databases.

DAWN baseline: `2bed9a3004e0988189e3c519bc0b205549999dfd`, with the local `backpack-integration` modifications. Changes are not committed or pushed.

## Checks

- `sh validate.sh`: 49 tests passed; one existing network contract fixture test was ignored because `STAT_NET_FIXTURE` was not defined. The sibling STAT repository is not checked out.
- STAT suite: 33 tests total, zero failures, one ignored. Includes dual-pack parsing/removal, aggregate-only fallback, malformed packet rejection, and battery staleness with continuing CPU telemetry.
- Attention suite: 12 tests passed. Includes stale/offline battery reading rejection and independent battery-feed age.
- Python suite: five tests passed, including all six generated scenarios replayed through DAWN's actual C parser and battery renderer.
- C compilation used `-Wall -Wextra -Werror`; the modified tool also passed a separate syntax-only check.
- Modified DAWN C/header files passed `clang-format-14 --dry-run --Werror`.
- `git diff --check` passed for the DAWN checkout.

The first alert-suite run exposed an accidentally overbroad freshness condition in the general telemetry-age reader. It was corrected; the final network and battery alert regression checks passed.

## Environment changes and limits

Installed `libjson-c-dev`, `libsqlite3-dev`, and `clang-format-14` on the NX for compilation/formatting. Apt also updated the SQLite runtime dependency. Tests did not install or start DAWN, a broker, an LLM, or a USB hardware service.

At the time of the initial simulator checks, the complete DAWN build and live runtime had not been tested. The development-install results below supersede that limitation for the checks explicitly listed. History remains aggregate-only. Simulation values are illustrative.

## Development installation follow-up

- Installed the vendor CUDA 13.2 toolkit and built the complete DAWN development executable plus `dawn-admin` with CUDA Whisper enabled.
- Changed to the user-requested 25 W profile, rebooted, and verified mode 3 with CPU IDs 0–7 online. Resumed the cached build successfully using all online cores.
- Verified the phonemizer resolves ONNX Runtime 1.19 only; the upstream bundled ONNX 1.14 is not loaded into DAWN.
- DAWN's native CMake targets `test_stat_service`, `test_attention_gate`, and `test_llm_capabilities` built and passed through CTest. The sibling-STAT network fixture remains unavailable.
- All three transient development services were active: broker, power simulator, and DAWN.
- Published/subscribed simulated battery messages over the isolated loopback broker; DAWN logged subscription to the configured simulated telemetry and status topics.
- Whisper initialized the CUDA0 backend successfully. Piper loaded the voice, Silero VAD initialized, and DAWN completed its boot greeting. No startup ERROR/WARNING lines were found in the development log at the check.
- The local HTTP health endpoint returned 200; `dawn-admin ping` reported a responsive daemon.
- The normal user's audio services were active after reboot. Explicit trusted-device reconnection restored both AirPods routes; unattended reconnection is not yet tested.
- An initial running-system reading showed approximately 5.3 GiB available memory. This is an idle development snapshot, not a peak-load benchmark.
- Local Qwen API requests selected `system_status` with action `battery`. Compatibility-endpoint tests verified `reasoning_effort: none` removed reasoning output; DAWN's request writer was corrected accordingly.

Still unverified: the live microphone question → DAWN tool execution → intelligible spoken battery answer, dedicated battery dashboard, real USB board readings, sustained combined load, and battery safety behavior. The developer instance is ready for the user's voice test.

See [usage and the telemetry contract](README.md). The real controller must retain power protection independently of the assistant.

### Voice retry preparation

### Local engagement window (not deployed)

Built the actual `test_wake_word.c`, `wake_word.c`, common logging, and Unity sources under local Ubuntu WSL using GCC with `-Wall -Wextra -Werror`: 51 tests passed, none failed or ignored. Added cases cover initially disengaged speech, whole-word/case-insensitive name detection, rejected name substrings, follow-ups without timer extension, exact 120-second expiry, renewal, and backwards-time rejection. Formatted the four affected C/header files with clang-format 14. The local microphone state machine now routes accepted follow-ups and rechecks expiry before dispatch. Full DAWN compilation, NX deployment, and microphone verification remain pending because the NX is powered off.

The user requested a smaller model. Installed `qwen3.5:4b-q4_K_M` and recreated the development alias with the same context, deterministic sampling, and disabled thinking. Two API checks using the existing system prompt and real battery-tool schema both selected `system_status` / `battery` without reasoning output. First request including model loading took 31.11 seconds; the repeated cached request took 3.73 seconds. These are tool-selection API timings, not end-to-end voice latency. Ollama reported one resident alias, 100% GPU, approximately 3.4 GB. The 9B weights remain on disk.

The first microphone battery question was transcribed correctly but produced a false unavailable answer after approximately 33 seconds. Request tracing revealed 42 advertised tools (about 85 KB of schemas) despite the one-tool execution whitelist. Local requests now filter frozen definitions to executable tools and use concise availability guidance. Cloud schema behavior is preserved. Development output is capped at 128 tokens and the model alias uses temperature zero.

The native executable rebuilt successfully. CTest passed `test_session_prefix`, `test_llm_tools_frozen`, and `test_prompt_builder` (3/3). The diagnostic proxy and virtual audio sinks were removed from the running setup; normal AirPods routing was restored, the boot greeting completed, and health returned `ok`. The corrected spoken battery response and its latency still require a voice retry.


## Reboot-safe runtime — 2026-11-08

- Native DAWN build completed on the NX, including the backpack bridge and local Friday engagement gate. Native `test_wake_word` passed (51 Unity cases).
- Runtime state/audio tests passed locally and on ARM64. The final confirmation-aware suite contains 16 tests, including no hardware operation before explicit confirmation, expired/cancelled/disconnected confirmations, state mismatch/read failure, history ownership, and audio reconnect/cleanup. All hardware commands are replaced in those tests.
- Live owner-only Unix RPC reported the actual 25 W profile. Requesting the already-active 25 W profile was a no-op; malformed wattage was rejected. No test changed the device's wattage.
- A real reboot verified that all four persistent user services started without a headset and `/health` returned `ok`. User lingering and startup enablement were checked. An isolated diagnostic database retained the intent across a changed kernel boot ID and verified the actual 25 W mode after reboot; it never issued a power-change command or inserted a pretend request into the user's action history.
- Native restoration logged one temporary local conversation message for the configured default voice owner (1). The diagnostic message was removed and DAWN restarted with the original empty checkpoint before voice testing.
- The authenticated status endpoint redirected an unauthenticated request to login. Its JavaScript passed syntax checking and a DOM test displaying a verified action and disconnected-headset state. No web account exists yet; authenticated browser testing remains pending account enrollment.
- AirPods were reconnected explicitly over SSH. The runtime linked microphone/speaker routes without restarting DAWN. The initial spoken power-status questions were misrecognized as “paramotor” / “power motor” and Qwen answered without using the tool. Clear power status/change commands are therefore routed directly; final microphone validation is in progress.
- Power changes now prepare a request and speak the reboot/confirmation prompt. Only a matching attended local confirmation can proceed; the model has no confirmation tool action. The native path speaks the exact requested “Standby by for power change, initiating reboot” announcement and waits for TTS completion before committing/starting the hardware change. End-to-end spoken confirmation, cancellation and a real mode-changing reboot remain to be checked with the user.

## Live battery speech and latency — 2026-11-09

Connected the paired AirPods over SSH and verified both runtime-owned loopbacks. All four user services were active, DAWN health was `ok`, and the Qwen development alias was already resident on the GPU.

The first spoken battery question was recognized correctly in 518 ms. The model took 15.13 seconds to its first token and 19.88 seconds from dispatch to completion, with 3,586 input tokens. It answered 92% without a fresh battery tool call; the simulator actually reported 75%. The user confirmed intelligibility, but this turn failed accuracy and latency validation.

Added a direct local route for exact common battery-status questions after the existing engagement/attended-input gate. It reads the same mutex-protected STAT snapshot as the tool and speaks a short aggregate answer, preserving simulation labeling, battery-specific freshness, offline/unavailable handling, and warning/critical status. Other questions, including slot-specific or historical queries, retain the model path. This improves the battery route; it does not establish faster general Qwen inference or validate model-selected battery tool execution.

The native DAWN build and CTest targets `test_stat_service` and `test_wake_word` passed. Three added telemetry-rendering cases cover live/simulated answers, all unavailable/stale conditions, warnings/critical faults, and output bounds. Scoped diff whitespace and clang-format checks passed. A repository-wide diff check encountered pre-existing CRLF whitespace in unrelated wake-word files; those files were preserved.

On the corrected live turn, NX log timestamps were:

- Speech detected: 00:16:28.813 UTC on November 10 (November 9 local).
- Pause detected: 00:16:31.021; transcription completed at 00:16:31.519 (497 ms).
- Direct fresh battery snapshot and speech request: 00:16:31.726, battery age zero seconds.
- Speech completed: 00:16:35.808.

The user confirmed hearing “Simulated reading. Battery is at 75 percent.” within ten seconds. Total time from speech detection through completed answer was 6.995 seconds, including the question; dispatch through completed speech was 4.082 seconds. Exact audible-start latency was not instrumented. This single live turn meets the ten-second target; sustained/repeated-turn performance remains unmeasured. No microphone recording was retained.

### Read-only power-mode latency

The first question, “Hey Friday, what power mode are we running?”, was transcribed as “Hey, fight it. What power motor are we running?” and fell through to Qwen. It answered 25 watts, which matched the actual mode, but no fresh tool call was logged. Model time to first token was 15.30 seconds; dispatch to model completion was 18.25 seconds. The user confirmed the answer was correct but slow. A subsequent “No” had a 1.14-second time to first token and 95% prompt-cache coverage, evidence that prefix reuse can materially reduce model delay on this workload, without proving a sustained general latency target.

The clearer retry, “Hey Friday, check the wattage”, used the existing direct read-only power route. Speech was detected at 00:18:25.478 UTC; transcription finished at 00:18:27.823 (297 ms); dispatch was 00:18:28.230; TTS completed at 00:18:31.573. Total detected-speech-to-answer-completion time was 6.095 seconds, including the question; dispatch-to-completion was 3.343 seconds. The user confirmed the correct 25 watt answer within ten seconds. A separate `nvpmodel -q` confirmed 25W/profile 3. No power change or reboot was performed. Spoken power changes and queued post-reboot confirmations remain unverified; “power mode” recognition remains unreliable. AirPods and DAWN remained connected and running.

### Configurable trigger word

Changed general.ai_name from friday to victor in the PC and NX development configuration. After restarting DAWN, both native wake-word initializers logged victor, health returned ok, and both AirPods loopbacks remained active. No source rebuild was required for that configuration change. Later camera tests below verify live Victor and Vic microphone recognition.

## Local camera descriptions — 2026-11-09

Added the local `camera_look` tool and direct handling of common camera questions on the existing voice worker. The configured Victor assistant accepts whole-word Vic mentions locally, including the correct command offset after the three-letter nickname. The prefix-only matcher used by other surfaces remains configured-name-only. Both names retain the existing two-minute local engagement rules.

The IMX477/A603 Argus pipeline captured fresh JPEGs at 640 × 360 with `flip-method=2`. Qwen's installed model inspection reported vision support, and a standalone fresh-image request returned a concrete scene description. The first standalone capture took 2.417 seconds and inference took 30.177 seconds. Subsequent live requests were faster; this is not a sustained benchmark.

Validation completed:

- Native DAWN build, `test_wake_word` CTest target, scoped diff whitespace, and clang-format checks passed. The added nickname case covers Vic/Victor, whole-word boundaries, expiry, and preservation of the separate prefix gate.
- Four camera contract tests passed locally and on ARM64, covering upright pipeline arguments, fresh bytes reaching loopback inference, failed capture without old-image reuse, busy/timeout handling, invalid questions, and missing model output.
- All 16 existing runtime/audio/power tests passed on ARM64; hardware commands are stubbed in those tests.
- DAWN and the runtime restarted successfully with the local camera tool enabled. Health returned `ok`; both AirPods loopbacks remained active. No packages, model downloads, power changes, or reboots were required.

Live “Hey Victor, are you seeing this?” was transcribed correctly. The camera request began at 00:39:14.973 UTC on November 10 (November 9 local). Capture took 2.429 seconds, vision took 7.014 seconds, and the response text was ready at 00:39:24.469. TTS finished at 00:39:35.786. The user confirmed a correct scene description. After speech finished, the exact captured frame was transferred for visual QA: the figure was upright on the plastic cases with the desk below, consistent with the scene description. Lighting remains dim/hazy; no image-quality enhancement was applied.

The final “Vic, are you seeing this?” turn was transcribed exactly, recognized the nickname, and started a new capture at 00:40:47.831. Capture took 2.426 seconds and vision took 8.515 seconds; response text was ready at 00:40:58.784 and TTS finished at 00:41:12.922. The user confirmed Vic worked. The exact second frame was inspected after that reply and was also upright. Total capture-plus-analysis was 10.941 seconds; exact audible-start latency was not instrumented, and the full spoken answer takes longer. The earlier ten-second battery-status result does not establish the same bound for vision.

Recognition is not perfectly reliable: an earlier attempt became “Did I hear you saying this?” and did not engage. Another became “Rick, are you seeing this?” during the open engagement window and went through ordinary text inference; it did not capture a new image and its assertion of seeing the scene is not a verified camera result. A correctly transcribed Victor/Vic request uses the explicit capture path and cannot reuse the preview after capture failure. The general model-selected tool path is registered and enabled but was not separately exercised live. Images are sent only to loopback Ollama. One private `run/camera-latest.jpg` remains for review and is overwritten by the next successful capture; temporary frame directories are removed.
