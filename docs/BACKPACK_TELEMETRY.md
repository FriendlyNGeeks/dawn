# Backpack battery telemetry extension

The backpack integration branch consumes the existing `BatteryStatus` messages on
the configured STAT telemetry topic. It adds optional per-slot details, receiver-side
battery freshness, and explicit simulation labeling. Existing complete aggregate-only
publishers do not need an extension field.

## Packet

```json
{
  "device": "stat",
  "msg_type": "telemetry",
  "type": "BatteryStatus",
  "simulated": true,
  "voltage": 19.5,
  "current": 2.0,
  "power": 39.0,
  "battery_level": 70,
  "temperature": 30,
  "charging_state": "discharging",
  "battery_status": "OK",
  "packs": [
    {"id": "A", "present": true, "supplying": true, "voltage": 19.5,
     "current": 2.0, "power": 39.0, "battery_level": 70, "temperature": 30},
    {"id": "B", "present": false, "supplying": false}
  ]
}
```

Units are volts, amperes, watts, charge percent, and degrees Celsius. Headline
measurements are supplied by the publisher, not inferred from pack entries. Never
add parallel-pack voltages or average charge percentages without capacity information.

Packets are atomic snapshots. Headline voltage, current, power, charge, and temperature
must all be finite JSON numbers; voltage must be nonnegative and charge must be 0–100.
Optional `packs` is an array of at most two entries with distinct IDs `A` and `B`.
Presence and supplying flags must be booleans. Present packs require the same five
measurements; removed packs cannot supply power. Invalid packets leave both the old
snapshot and its age unchanged. An omitted array clears per-slot details; omitted
slots are unknown, not presumed absent. Runtime remains unknown if not supplied.

## Freshness and watches

Battery age is measured with `CLOCK_MONOTONIC` at receipt, independently of system,
fan, and network messages. Stale or offline battery data is withheld from live battery
text and battery metric watch readers. The `stat.battery.telemetry` absence metric
can watch battery-feed age independently of `stat.telemetry`; it becomes available
after the first valid battery packet. Attention and the desired watch must be enabled
by the operator. Controller-level protection remains independent of all these watches.

Simulation uses separate configured topics and a separate database. Simulated readings
are labeled in live battery text. History remains aggregate-only; do not mix simulated
history with real measurements. USB transport framing, individual pack history, and
a dedicated live web dashboard are outside this extension.

## Verification

The STAT unit suite checks valid dual slots, removal, legacy aggregate-only fallback,
malformed slots, and battery expiry despite continued CPU updates. The attention suite
checks that stale/offline battery metrics are unavailable while battery age remains
readable. The companion backpack simulator is tested against the real parser and
battery renderer with temporary databases. This does not establish a full DAWN build,
MQTT broker delivery, model tool-call behavior, or speech output.
