"""Emit simulated DAWN STAT messages. No hardware commands; stdout by default."""

import argparse
import json
import math
import subprocess
import time


SCENARIOS = ("normal", "low-battery", "hot-swap", "battery-silence", "disconnect", "recovery")
TOPIC = "backpack/sim/stat/telemetry"
STATUS_TOPIC = "backpack/sim/stat/status"


def pack(slot, level, supplying=True, present=True):
    result = {"id": slot, "present": present, "supplying": supplying if present else False}
    if present:
        voltage = round(16.0 + level * 0.04, 2)
        watts = 30.0 if supplying else 0.0
        result.update(voltage=voltage, current=round(watts / voltage, 3), power=watts,
                      battery_level=level, temperature=30.0)
    return result


def sample(scenario, step):
    """Return one complete atomic snapshot; values are illustrative, not a battery model."""
    if scenario == "disconnect" and step >= 2:
        return STATUS_TOPIC, {"device": "stat", "msg_type": "status", "status": "offline",
                              "simulated": True}
    if scenario == "battery-silence" and step >= 2:
        return TOPIC, {"device": "stat", "msg_type": "telemetry", "type": "SystemMetrics",
                       "cpu_usage": 10, "memory_usage": 25, "system_temp": 40,
                       "simulated": True}
    if scenario == "recovery" and 2 <= step < 5:
        return sample("disconnect", 2)
    level = max(5, 25 - step * 5) if scenario == "low-battery" else 75
    swapped = scenario == "hot-swap" and step >= 2
    packs = [pack("A", level, supplying=not swapped, present=not (swapped and step < 5)),
             pack("B", 80, supplying=swapped)]
    # Headline values are supplied explicitly by the future bridge/board.
    # Never add parallel-pack voltages or assume an unweighted mean is total charge.
    active = packs[1] if swapped else packs[0]
    return TOPIC, {
        "device": "stat", "msg_type": "telemetry", "type": "BatteryStatus",
        "simulated": True, "voltage": active["voltage"], "current": active["current"],
        "power": active["power"], "battery_level": level, "temperature": 30,
        "charging_state": "discharging", "battery_status": "WARNING" if level <= 15 else "OK",
        "status_reason": "SIMULATION: illustrative combined charge; not a capacity estimate",
        "critical_fault_count": 0, "warning_fault_count": int(level <= 15),
        "info_fault_count": 0, "packs": packs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--publish", action="store_true", help="publish using mosquitto_pub")
    parser.add_argument("--port", type=int, default=1883, help="local test broker port")
    args = parser.parse_args()
    if args.count < 1 or not math.isfinite(args.interval) or args.interval < 0:
        parser.error("count must be positive and interval must be finite and nonnegative")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        for step in range(args.count):
            topic, payload = sample(args.scenario, step)
            payload["timestamp"] = int(time.time())
            print(json.dumps({"topic": topic, "payload": payload}, allow_nan=False), flush=True)
            if args.publish:
                # Explicit opt-in, localhost only, isolated topics, no retained fake values.
                subprocess.run(["mosquitto_pub", "-h", "127.0.0.1", "-p", str(args.port),
                                "-t", topic, "-m", json.dumps(payload, allow_nan=False)],
                               check=True, timeout=5)
            if step + 1 < args.count:
                time.sleep(args.interval)
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Simulation publication failed: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
