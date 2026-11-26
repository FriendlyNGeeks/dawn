# Events, service preferences and reboot continuity

Implemented 2026-11-23. This extends the existing private SQLite runtime; no remote
database, container or new system privilege grant is required.

## Voice behavior

Commands use the existing attended local microphone engagement gate. Include Victor/Vic
outside the two-minute engagement window.

- "Silent mode" / "Normal mode": mute or enable unsolicited reports; collection continues.
- "Read me the messages from the last two hours": read retained communications without
  changing mode. Readouts contain at most 20 records and disclose truncation.
- "Summarize activity from the last two hours": read retained activity, with availability gaps.
- "Summaries every 15 minutes" / "Stop periodic summaries": configure event-count digests.
- "Always start Meshtastic": persist autostart and request it for this boot.
- "Start Meshtastic" / "Stop Meshtastic": change this boot only.
- "Never start Meshtastic": clear autostart and request a stop.
- "Service status": read adapter readiness. SDR / RTL SDR can replace Meshtastic
  in lifecycle commands, but no SDR scanner is currently configured.

Explicit readouts speak in silent mode. Power-action notices also wait while silent.
Automatic communication notices cover only the latest five minutes; history remains queryable.
Times in readouts are UTC.

## Common event contract

Services send newline-delimited JSON to the existing owner-only run/runtime.sock.
The socket verifies caller UID. All same-UID clients are trusted local applications;
these operations are not exposed as remote/model tools.

Example:
    {"operation":"publish_event","event":{"source":"meshtastic","type":"message.received","category":"communication","external_id":"!node:42","data":{"sender":"!node","text":"Camp reached","channel":0}}}

The runtime assigns UUID, database sequence, schema version 1 and recorded timestamp.
Optional observed_at is Unix UTC seconds, nonnegative, finite and at most five minutes ahead.
External IDs are unique per source. Categories: communication, activity, fault.
Severities: info, warning, critical. Data must be a JSON object of at most 16 KiB.
Raw IQ, audio, images and video belong in local files; events can hold their metadata/references.

query_events takes since/until timestamps, optional source/category, limit (1–100), and after
sequence. Results include events, next_after, more, a conservative history completeness boundary,
and storage pressure. Pagination follows sequence; callers can sort complete results by observed
time. Radio text is read through templates and never executed or interpreted as model instructions.

## Retention and delivery

Communications and faults default to 90 days; routine activity to 14 days.
Retention uses arrival time, preserving delayed messages. set_retention accepts category and days
(1–3650). pin_event accepts id and boolean pinned. Pinned events survive automatic cleanup.

Initial event budget: 100,000 rows or 128 MiB of JSON payload, whichever is reached first.
This is a logical budget, not a hard filesystem/database size quota: indexes and WAL need more
space. Each minute maintenance expires at most 500 rows per category, plus up to 500 oldest
unpinned rows when usage exceeds 90 percent. It discloses pressure and conservative history gaps.
At full capacity ingestion rejects new records, including when pinned records fill the budget.
Receivers must retry and disclose acquisition gaps.

Notice acknowledgments are separate from collection. Only completed TTS with a still-connected
audio route acknowledges delivery. Interrupted notices can repeat. Service-state updates
coalesce to the latest undelivered state. Intentional stops do not announce failures.
Communication batches wait two seconds and contain at most five events.

## Service preferences and readiness

Runtime preferences reconcile desired services independently of DAWN. Existing peripherals
remain unmanaged until explicitly selected. Same-boot overrides survive runtime restarts;
a new boot restores autostart. No interrupted hardware action is replayed.

Meshtastic maps to the existing system meshtasticd.service. Control uses fixed argv through
sudo -n systemctl, with no shell or installed sudoers changes. Missing authorization is reported.
Preferences do not rewrite independent administrator systemd enablement; a separately boot-enabled
unit may briefly start before runtime applies a saved stop preference.

The installer adds backpack-meshtastic-events only when deps/meshtastic-cli/bin/python exists.
The adapter uses protobuf definitions from that isolated environment and loopback TCP port 4403.
It records incoming text messages and renews a readiness lease every five seconds, backed by
a successful framed configuration exchange every twenty seconds. The SDK heartbeat path is
avoided after reproducing broken-pipe errors; no configuration keys are logged. Packet receive
timestamps are preserved when valid; recorded_at separately records arrival at the event store.
It sends no radio transmissions and does not currently observe all outgoing clients.
Outgoing clients can publish message.sent events through the common API.

SDR remains explicitly unconfigured. A real scanner needs a reviewed fixed mapping in
continuity.SERVICES and an adapter publishing detections and service_health: name, ready boolean,
detail. Readiness expires after 30 seconds or a boot-ID change. Process existence alone is
insufficient evidence of scanning.

## Restart handoff and watchdog

DAWN requests a startup handoff instead of speaking its generic introduction.
Existing owner-isolated conversation checkpoints remain in place. A fresh-boot summary waits
up to 15 seconds for desired services, then reports verified ready/waiting/unconfigured states.
DAWN stays available as peripherals initialize. Same-boot restarts skip repeated introductions.
Observed peripherals are included in the startup report even when not managed by an autostart
preference. Delayed startup announcements refresh their content against current readiness.
Pending power/host action verification takes priority over generic startup summaries.

DAWN uses Type=notify, a ten-minute initialization timeout and a five-minute systemd watchdog.
The main heartbeat sends READY/WATCHDOG. This detects a stalled main loop, not every worker fault.
Restart=always still covers process exits. Rebuild DAWN and apply the installer together.

## Service logs and media

Diagnostic dawn.log, yolo.log, goggles.log and supervisor services.log rotate above 10 MiB,
with three bounded backups per file. Backups expire after seven days. Maintenance runs about once
a minute; active files can exceed the target between passes. Copy/truncate preserves open append
descriptors but can lose a diagnostic line; authoritative events use SQLite transactions.
Inactive current log files remain bounded but are not age-deleted.
System journal retention remains under the host administrator's journald policy.
Raw Meshtastic daemon logs are not copied because they may contain channel keys.

No SDR recording producer, media archive or S3 uploader is installed by this change.
Existing camera-latest.jpg and goggles cache behavior remains as described in RUNTIME.md.
A future recorder needs its own rolling byte budget and verified optional archival.

## Validation and rollout

Python tests use temporary SQLite stores and fake service control, never real reboots.
Run the Linux validate.sh harness and build_dev.sh before native rollout. Then apply start_dev.sh
and verify watchdog, voice and physical peripheral readiness on the NX.
Back up backpack.db using SQLite's backup API first. Tables extend the database additively;
existing state is preserved. Older runtimes ignore these new tables.
