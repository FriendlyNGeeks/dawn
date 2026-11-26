# Backpack power telemetry simulator

This is a development-only feed into DAWN's existing STAT telemetry service. It does not talk to the power board or send hardware commands. The future USB reader will translate validated board frames into the same messages. The USB wire protocol is not selected or implemented yet.

## Run without hardware

From this directory, Python 3.10+ needs no third-party packages:

```bash
python3 simulate_power.py --scenario hot-swap --count 8 --interval 1
python3 -B -m unittest discover -s . -p 'test_simulate_power.py' -v
```

Scenarios: normal, low-battery, hot-swap (remove A, supply from B, reinsert A), battery-silence (CPU messages continue), disconnect (offline status), and recovery (offline then battery readings resume). Every payload is marked simulated. Values and thresholds are illustrative test data, not a calibrated battery or electrical model.

Each stdout line is an envelope with `topic` and `payload`. Only `payload` goes on MQTT. No network connection is made unless `--publish` is supplied. Publication uses an installed `mosquitto_pub` client, connects only to a localhost broker, and never retains fake values:

```bash
python3 simulate_power.py --scenario battery-silence --count 40 --publish
```

For manual integration, use a separate DAWN test configuration and history database:

```toml
[stat]
enabled = true
telemetry_topic = "backpack/sim/stat/telemetry"
status_topic = "backpack/sim/stat/status"
db_path = "/tmp/backpack-sim-stat.db"
stale_after_sec = 3
```

The section matches DAWN's `dawn.toml.example`. Do not attach simulated topics or a simulated history DB to a production session. The later [development installation](DEV_SETUP.md) uses a separate local broker and DAWN instance; the offline replay tests themselves need neither.

## Wire contract

The existing aggregate `BatteryStatus` headline fields remain authoritative; DAWN does not calculate combined charge or add pack voltages. A complete valid battery sample supplies finite numeric `voltage`, `current`, `power`, `battery_level` (0–100), and `temperature`; voltage must be nonnegative. `time_remaining_min` is optional and unknown when omitted. Existing complete aggregate-only publishers remain supported.

Optional `packs` holds up to two entries, identified by physical slot `A` or `B`. Each entry requires boolean `present` and `supplying`. Present entries require the same five finite measurements as above. Removed entries must not be supplying and need no measurements. Duplicate slots, unknown slots, invalid measurements, and oversized arrays reject the entire packet without refreshing the cache. Missing slots are unknown, not assumed absent. Each valid aggregate-only packet clears prior per-slot details.

The optional `simulated` flag is surfaced in the spoken/text battery result. Headline charge values in this simulator are explicitly illustrative; actual aggregation needs pack capacity/calibration and power-path information from the board.

Battery freshness uses receiver-side monotonic time independently of CPU/network updates. Stale/offline battery data is withheld by the live battery renderer and battery watch readers. The optional `stat.battery.telemetry` absence watch exposes battery age after a sample has been received. Watches still require DAWN attention to be enabled and a watch configured; this is not a substitute for controller-level battery protection.

History remains aggregate-only. A dedicated live battery dashboard, per-pack history, USB transport parsing, sequence handling, and firmware agreement are future work.

## Focused Linux/ARM64 validation

With a C compiler, `libjson-c-dev`, and `libsqlite3-dev` installed:

```bash
sh validate.sh
```

This builds DAWN's real telemetry and alert unit tests with warnings as errors, then runs generated scenarios through the actual C parser and renderer using an offline replay harness. Temporary test databases are isolated from application data. This does not build or deploy the complete voice assistant.

See [recorded validation results and limitations](VALIDATION.md).
