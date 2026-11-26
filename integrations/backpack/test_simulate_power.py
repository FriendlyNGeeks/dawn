"""Scenario contract tests; no network or hardware required."""
import json
import os
import subprocess
import tempfile
import unittest

from simulate_power import SCENARIOS, TOPIC, STATUS_TOPIC, sample


class SimulationTests(unittest.TestCase):
    def test_scenarios_are_serializable_and_explicitly_simulated(self):
        for scenario in SCENARIOS:
            for step in range(8):
                topic, payload = sample(scenario, step)
                self.assertIn(topic, (TOPIC, STATUS_TOPIC))
                self.assertTrue(payload["simulated"])
                json.dumps(payload, allow_nan=False)

    def test_hot_swap_removes_a_and_moves_load_to_b_then_reinserts_a(self):
        before = sample("hot-swap", 0)[1]["packs"]
        removed = sample("hot-swap", 3)[1]["packs"]
        restored = sample("hot-swap", 6)[1]["packs"]
        self.assertTrue(before[0]["supplying"])
        self.assertFalse(removed[0]["present"])
        self.assertNotIn("voltage", removed[0])
        self.assertTrue(removed[1]["supplying"])
        self.assertTrue(restored[0]["present"])
        self.assertFalse(restored[0]["supplying"])

    def test_silence_does_not_emit_battery_updates(self):
        self.assertEqual("BatteryStatus", sample("battery-silence", 0)[1]["type"])
        self.assertEqual("SystemMetrics", sample("battery-silence", 3)[1]["type"])

    def test_low_battery_and_recovery(self):
        self.assertEqual("WARNING", sample("low-battery", 4)[1]["battery_status"])
        self.assertEqual("offline", sample("recovery", 3)[1]["status"])
        self.assertEqual("BatteryStatus", sample("recovery", 6)[1]["type"])

    @unittest.skipUnless(os.environ.get("BACKPACK_STAT_REPLAY"), "Linux DAWN replay harness required")
    def test_generated_messages_pass_through_real_dawn_parser_and_renderer(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                messages = [dict(zip(("topic", "payload"), sample(scenario, step)))
                            for step in range(8)]
                result = subprocess.run(
                    [os.environ["BACKPACK_STAT_REPLAY"], os.path.join(directory, "history.db")],
                    input="".join(json.dumps(message) + "\n" for message in messages),
                    text=True, capture_output=True, check=True, timeout=15)
                snapshots = [line for line in result.stdout.splitlines()
                             if line.startswith("SNAPSHOT ")]
                self.assertEqual(8, len(snapshots))
                self.assertIn("SIMULATED", snapshots[0])
                self.assertIn("Slot A:", snapshots[0])
                if scenario == "hot-swap":
                    self.assertIn("Slot A: removed", snapshots[3])
                    self.assertIn("Slot B: 80%", snapshots[3])
                if scenario in ("disconnect", "recovery"):
                    self.assertIn("unavailable", snapshots[3])
                    self.assertNotIn("75%", snapshots[3])
                if scenario == "recovery":
                    self.assertIn("SIMULATED", snapshots[6])


if __name__ == "__main__":
    unittest.main()
