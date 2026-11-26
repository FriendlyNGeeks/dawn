"""Drone source, freshness, and spoken readiness contracts; no hardware used."""
import base64
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from drone_feed import DroneFeed


class DroneTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        self.runner = Mock(return_value=subprocess.CompletedProcess([], 0))
        self.opener = Mock(return_value=io.BytesIO(
            b'{"message":{"content":"A person is beside a car."}}'))
        self.feed = DroneFeed(self.state, self.runner, self.opener, clock=lambda: 100.)
        self.feed.unit_state = Mock(return_value={'state': 'active', 'pid': 123})

    def frame(self, **changes):
        header = dict(source='goggles3', decoded_at=100., frame_id=3, detections=[])
        header.update(changes)
        (self.state / 'goggles-frame.bin').write_bytes(
            json.dumps(header).encode() + b'\n\xff\xd8drone-frame\xff\xd9')
        self.telemetry()

    def telemetry(self, stamp=100., inference_fps=12.5):
        (self.state / 'goggles-yolo.json').write_text(json.dumps({
            'source': 'goggles3', 'status': 'live', 'fresh': True,
            'result': dict(source='goggles3', fresh=True, decoded_at=stamp, frame_id=3)}))
        (self.state / 'goggles-yolo.json.metrics').write_text(json.dumps({
            'status': 'metrics', 'timestamp': stamp, 'target_fps': 15,
            'decoded_fps': 30., 'submitted_fps': 15., 'inference_fps': inference_fps}))

    def test_start_confirms_only_after_a_post_request_frame(self):
        self.frame()
        result = self.feed.start()
        self.assertTrue(result['fresh'])
        self.assertIn('connected', result['description'])
        self.assertTrue(result['description'].startswith('ASTRA is ready.'))
        self.assertEqual(['systemctl', '--user', 'start', 'backpack-yolo.service', 'goggle-yolo.service'],
                         self.runner.call_args.args[0])
        self.feed.wait_frame = Mock(side_effect=RuntimeError('paused'))
        with self.assertRaisesRegex(RuntimeError, 'paused'):
            self.feed.start()

    def test_service_failure_never_announces_ready(self):
        self.runner.return_value = subprocess.CompletedProcess([], 1)
        with self.assertRaisesRegex(RuntimeError, 'could not start'):
            self.feed.start()

    def test_scene_question_uses_goggles_bytes_and_local_model(self):
        self.frame()
        result = self.feed.describe('What is on the eye in the sky?')
        self.assertEqual('goggles3', result['source'])
        request = self.opener.call_args.args[0]
        self.assertEqual('http://127.0.0.1:11434/api/chat', request.full_url)
        body = json.loads(request.data)
        self.assertEqual(b'\xff\xd8drone-frame\xff\xd9',
                         base64.b64decode(body['messages'][1]['images'][0]))
        self.assertIn('paused-sharing', body['messages'][0]['content'])

    def test_stale_wrong_source_and_pre_question_frames_are_rejected(self):
        for change in (dict(decoded_at=90.), dict(source='camera'),
                       dict(decoded_at=99.9), dict(decoded_at=float('nan'))):
            with self.subTest(change=change):
                self.frame(**change)
                with self.assertRaises(ValueError):
                    self.feed.snapshot(since=100.)
        self.feed.wait_frame = Mock(side_effect=RuntimeError('paused'))
        with self.assertRaisesRegex(RuntimeError, 'paused'):
            self.feed.describe('What is there?')
        self.opener.assert_not_called()

    def test_missing_answer_and_invalid_question_fail(self):
        self.frame()
        self.opener.return_value = io.BytesIO(b'{"message":{"content":""}}')
        with self.assertRaisesRegex(RuntimeError, 'could not describe'):
            self.feed.describe('What is there?')
        with self.assertRaises(ValueError):
            self.feed.describe('')

    def test_status_distinguishes_ready_stale_and_stopped(self):
        self.frame()
        report = self.feed.status()
        self.assertEqual('ready', report['phase'])
        self.assertIn('inference 12.5', report['description'])
        self.assertEqual('not_configured', report['ardupilot'])
        self.telemetry(stamp=90.)
        self.assertEqual('degraded', self.feed.status()['phase'])
        self.feed.unit_state.return_value = {'state': 'inactive', 'pid': 0}
        report = self.feed.status()
        self.assertEqual('stopped', report['phase'])
        self.assertFalse(report['fresh'])

    def test_stop_unloads_in_order_and_clears_cached_frames_idempotently(self):
        self.frame()
        self.feed.unit_state.return_value = {'state': 'inactive', 'pid': 0}
        report = self.feed.stop()
        self.assertEqual('stopped', report['phase'])
        self.assertTrue(report['description'].startswith('ASTRA terminated.'))
        self.assertEqual(['goggle-yolo.service', 'backpack-yolo.service'],
                         [call.args[0][-1] for call in self.runner.call_args_list])
        self.assertFalse(list(self.state.iterdir()))
        self.feed.stop()

    def test_partial_shutdown_never_claims_unloaded_or_clears_cache(self):
        self.frame()
        self.runner.side_effect = [subprocess.CompletedProcess([], 1),
                                   subprocess.CompletedProcess([], 0)]
        with self.assertRaisesRegex(RuntimeError, 'shutdown is incomplete'):
            self.feed.stop()
        self.assertEqual(2, self.runner.call_count)
        self.assertTrue((self.state / 'goggles-frame.bin').exists())

    def test_termination_cancels_old_wait_and_suppresses_delayed_description(self):
        self.frame()
        epoch = self.feed.epoch
        self.feed.epoch += 1
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.feed.wait_frame(100., 1, epoch)
        def interrupted_model(*args, **kwargs):
            self.feed.epoch += 1
            return io.BytesIO(b'{"message":{"content":"An obsolete scene."}}')
        self.feed.opener = interrupted_model
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.feed.describe('What is there?')

    def test_start_requires_completed_inference_and_sampling(self):
        self.frame()
        self.telemetry(inference_fps=0)
        # Expire the readiness wait deterministically; no hardware or real sleep.
        with patch('drone_feed.time.monotonic', side_effect=[0, 1, 100]):
            self.feed.wait_frame = Mock(return_value=({}, b'jpeg'))
            with self.assertRaisesRegex(RuntimeError, 'not ready'):
                self.feed.start()

    def test_reinstall_keeps_yolo_on_demand_without_stopping_active_session(self):
        import install_services
        root = self.state / 'dev'
        engine = root / 'deps/yolo/yolo26n.engine'
        engine.parent.mkdir(parents=True)
        engine.touch()
        units = self.state / '.config/systemd/user'
        units.mkdir(parents=True)
        (units / 'goggle-yolo.service').touch()
        with patch.object(Path, 'home', return_value=self.state), \
                patch.object(install_services.subprocess, 'run') as runner:
            install_services.install(root)
        commands = [call.args[0] for call in runner.call_args_list]
        enable = next(command for command in commands if 'enable' in command)
        self.assertNotIn('backpack-yolo.service', enable)
        self.assertIn(['systemctl', '--user', 'disable', 'backpack-yolo.service'], commands)
        self.assertIn(['systemctl', '--user', 'disable', 'goggle-yolo.service'], commands)
        self.assertFalse(any('stop' in command for command in commands))
