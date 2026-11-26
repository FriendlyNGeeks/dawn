# Victor host tools and spoken acknowledgments

Victor's local microphone has three additional tools: `host_status`, `diagnostic_cli`, and `host_control`. They are enabled only in the development local-tool list; remote tools remain restricted to the existing system-status tool.

## Fast actual host readings

`host_status` reads Linux `/proc`, thermal sysfs, and the system disk directly. It returns an observation timestamp, actual boot uptime, memory percentage and bytes, swap, sampled CPU usage, load averages, disk capacity, temperatures, and the eight largest process names/RSS values. It never returns process environments or command-line arguments. Memory used is `MemTotal - MemAvailable`, with decimal GB used in spoken totals. These values are explicitly real host data and are separate from the simulated battery/STAT feed.

Common local questions have a direct route without model inference:

- “Vic, what is the memory usage?”
- “Hey Victor, what is your uptime?”
- “Victor, check CPU usage.”
- “Vic, how much disk space is left?”
- “Victor, what is your temperature?”

More involved questions, such as “why is memory usage high?”, reach Qwen with fresh host tools available. The system prompt instructs it to fetch actual readings instead of using remembered or simulated values.

## General diagnostic CLI

`diagnostic_cli(command)` accepts a general bash command, including pipes and ordinary command composition. It is not a fixed command vocabulary. The runtime launches an immutable, transient system service with a dynamic unprivileged UID. The model controls only bash's final command argument, never the launcher, service properties, unit name, environment, or privilege configuration.

Linux/systemd enforces:

- Read-only host filesystem and inaccessible home, application state, mount/media, and other private paths.
- Empty private `/run` and masked `/etc` with only read-only public alternatives/OS-release bindings, a private 16 MiB `/tmp`, private devices and network, hidden other users' processes, no capabilities, no new privileges, and restricted address families/namespaces.
- Eight-second runtime limit, one-second stop grace, whole-control-group cleanup, 128 MiB memory ceiling, no swap, 16 tasks, 25% of one CPU, limited file descriptors and 64 KiB file/output writes.
- One diagnostic request at a time, at most 2,048 command characters, 8 KiB of returned output, and removal of terminal escape/control codes.

Examples include `uptime; free -b`, `df -h /`, `uname -a`, and sysfs inspection with shell loops/awk. This confined environment deliberately cannot read the host account's files, connect to its service bus, use its network, or become root with sudo. Some commands therefore see a restricted view: use `host_status` for actual top host processes rather than sandbox `ps`. Failed confinement setup fails the request; there is no unsandboxed fallback. The parent runtime uses the host account's existing noninteractive sudo authorization solely to launch this fixed sandbox. No new sudoers grant or password was created.

Live tests on the NX verified ordinary commands, blocked host writes, hidden home and host bus, blocked IPv4 sockets, denied sudo, isolated temporary files, bounded excessive output, and termination of `sleep 20` in approximately 8.5 seconds. Systemd 255 could not hide all of `/run` using `InaccessiblePaths`; a read-only empty tmpfs over `/run` worked with the full remaining constraints. No unsafe fallback was used.

Systemd environment expansion is disabled so bash/awk expressions arrive unchanged. Public `/etc/alternatives` is bound read-only because Debian's `awk` executable resolves through it; masking all of `/etc` without that binding made the otherwise-installed utility unavailable. A real awk pipeline and the private HOME value were verified after this adjustment.

## Confirmed host actions

`host_control` can **propose** `shutdown`, `reboot`, or `restart_service`. Service restarts are limited to `dawn` and `yolo`. Unsupported service names and arbitrary commands are rejected; file changes and general administrative commands are not introduced by this tool.

“Vic, reboot the Jetson” and “Vic, shut down the Jetson” prepare proposals directly. Qwen can also propose actions on explicit requests. Preparation speaks what would happen and requests **confirm or cancel**; it performs no host operation. There is no model-callable confirmation action.

Only an attended local microphone utterance after the existing Victor/Vic engagement gate can confirm. The native path speaks an explicit shutdown, reboot, or service-restart announcement and waits for speech completion before committing confirmation. Disconnected audio, expired/cancelled proposals, failed speech completion, conflicting pending power actions and replayed confirmations prevent initiation. Proposals expire after 120 seconds and are cancelled across boots or an observed disconnected headset. Confirmation and cancellation do not receive an extra “checking” cue.

Confirmed actions are committed to private SQLite state before a worker waits five seconds and issues the fixed command. Reboot completion is reported only after a changed kernel boot ID. A prior shutdown cannot be established merely by booting again, so that result remains explicitly unverified. Restart completion requires a successful `systemctl --user restart` and a subsequent active state. No completion is claimed merely because an action was queued. Verified/failed/unverified notices wait for connected audio. The original wattage-change confirmation and verification path remains in place, and power-mode/host proposals are mutually exclusive.

`host_actions` is an additive table in the existing private `run/backpack.db`; existing conversations and power-action rows are preserved. Sources and a SQLite-consistent backup were saved under `run/before-host-tools-20261109.tar` and `run/before-host-tools.db`. The previous runtime can ignore the added table when source rollback is needed; restoring the database would discard newer history, so do not restore it casually.

## Spoken acceptance cue

Every accepted local request selects one of eight cues using libsodium's thread-safe uniform random generator, regardless of whether it concerns host statistics, batteries, power, the camera, or general questions:

- “Checking that now.”
- “Taking a look.”
- “On it.”
- “Let me check.”
- “One moment.”
- “Let me look into that.”
- “I'll check the details.”
- “Give me a moment.”

Each cue has an equal chance on each request; consecutive repeats are possible. Cues are generated natively and queued immediately; they do not wait for Qwen to compose an acknowledgment. Work proceeds while the short cue is synthesized/played. A cue confirms acceptance, not successful data retrieval or action completion. It is not added as a conversation answer/checkpoint row.

Cancellation, confirmation, ignored speech outside the engagement window, remote inputs and tool-internal followups do not get a second cue. A compiled speech-collector test drives every possible random selection and verifies all eight phrases, with no random draws for suppressed requests. The user confirmed hearing the acknowledgment and actual memory reading clearly through the AirPods. Exact audible-start latency and physical playback of every newly added phrase were not separately measured. Background speech or a misrecognized trigger name is not evidence that a request was accepted.

## Verification

The native DAWN build and four focused CTest suites passed: telemetry, wake word, frozen tool schemas, and prompt construction. The actual C acknowledgment code passed a collector-based test, including opt-out, host/camera cues, cancellation and confirmation suppression. Ten new Python host tests and all 16 existing runtime tests passed on the PC and ARM64. Host shutdown, reboot and service execution were replaced by stubs in state-machine tests; no real shutdown/reboot was performed during implementation. Backend status and diagnostics were checked against the running NX after deployment; DAWN health and both AirPods routes remained active.

No package dependency was added. There is no configured automated secret scanner in this repository; a focused review of the changed source/configuration and generated launch arguments found no embedded credentials or secret-file contents. See [validation](VALIDATION.md) for the live-test outcome and remaining limitations.
