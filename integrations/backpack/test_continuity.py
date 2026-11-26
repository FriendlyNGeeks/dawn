"""Behavior tests using temporary SQLite stores and fake service control only."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime import Store
from continuity import Continuity, DAY
from meshtastic_bridge import Frames, packet_event
import service_logs


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'state.db'
        self.now = 1800000000.
        self.calls = []
        self.store = Store(self.path, 'boot-a', self.runner)
        self.c = self.store.continuity
        self.c.clock = lambda: self.now
        self.c.set('history_floor', self.now - 100 * DAY)

    def tearDown(self):
        self.directory.cleanup()

    def runner(self, args, **kwargs):
        self.calls.append(args)
        return subprocess.CompletedProcess(args, 0, '', '')

    def event(self, **fields):
        event = {'source': 'meshtastic', 'type': 'message.received',
                 'category': 'communication', 'data': {'text': 'hello'}}
        event.update(fields)
        return self.c.publish(event)

    def test_message_deduplication_pagination_and_parameter_binding(self):
        first = self.event(external_id='node:1')
        self.assertEqual(self.event(external_id='node:1')['id'], first['id'])
        self.event(external_id='node:2')
        result = self.c.query(self.now - 100, limit=1)
        self.assertTrue(result['more'])
        self.assertEqual(len(self.c.query(self.now - 100, after=result['next_after'])['events']), 1)
        self.assertEqual(self.c.query(self.now - 100, source="' OR 1=1 --")['events'], [])

    def test_silent_collects_and_explicit_read_does_not_change_mode(self):
        self.c.voice('silent mode')
        self.event()
        self.store.audio_ready = True
        self.now += 5
        self.assertIsNone(self.store.dispatch({'operation': 'notice'})['notice'])
        response = self.c.voice('read me out the messages from the last two hours')
        self.assertTrue(response['handled'])
        self.assertIn('hello', response['message'])
        self.assertEqual(self.c.get('mode'), 'silent')
        restored = Store(self.path, 'boot-b', self.runner)
        self.assertEqual(restored.continuity.get('mode'), 'silent')

    def test_read_discloses_gaps_even_after_receiver_recovers(self):
        self.event(source='sdr', type='service.waiting', category='fault')
        self.event(source='sdr', type='service.ready', category='activity')
        self.assertIn('availability gap', self.c.report(2, True))

    def test_retention_preserves_saved_events_and_messages_for_ninety_days(self):
        first = self.event()
        self.event(category='activity', type='scan.detected', external_id='activity')
        pinned = self.event(external_id='saved')
        self.c.dispatch({'operation': 'pin_event', 'id': pinned['id'], 'pinned': True})
        self.now += 15 * DAY
        self.c.cleanup()
        self.assertEqual(len(self.c.query(0)['events']), 2)
        self.now += 76 * DAY
        self.c.cleanup()
        self.assertEqual([e['id'] for e in self.c.query(0)['events']], [pinned['id']])
        self.assertIn('incomplete', self.c.report(2, True))

    def test_old_observation_is_not_immediately_expired_on_arrival(self):
        self.event(observed_at=self.now - 100 * DAY)
        self.c.cleanup()
        self.assertEqual(len(self.c.query(0)['events']), 1)

    def test_unmanaged_services_are_never_stopped(self):
        self.c.reconcile_services()
        self.assertEqual(self.calls, [])

    def test_preferences_survive_reboot_but_session_override_does_not(self):
        self.c.desired('meshtastic', True, True)
        self.c.desired('meshtastic', False)
        self.assertFalse(next(s for s in self.c.services() if s['name'] == 'meshtastic')['enabled'])
        restored = Store(self.path, 'boot-b', self.runner).continuity
        self.assertTrue(next(s for s in restored.services() if s['name'] == 'meshtastic')['enabled'])
        self.assertFalse(next(s for s in restored.services() if s['name'] == 'meshtastic')['ready'])

    def test_process_start_is_not_verified_readiness_and_health_expires(self):
        self.c.desired('meshtastic', True, True)
        self.c.reconcile_services()
        self.assertIn('meshtasticd.service', self.calls[0])
        self.assertFalse(self.c.services()[0]['ready'])
        self.c.health('meshtastic', True, 'API connected')
        self.assertTrue(self.c.services()[0]['ready'])
        self.now += 31
        self.assertFalse(self.c.services()[0]['ready'])

    def test_no_arbitrary_services_or_shell_commands(self):
        for name in ('meshtastic; reboot', 'sshd', '../service'):
            with self.assertRaises(ValueError):
                self.c.desired(name, True)
        self.assertEqual(self.calls, [])

    def test_expected_shutdown_does_not_announce_failure(self):
        self.c.desired('meshtastic', True)
        self.c.health('meshtastic', True, 'API connected')
        self.c.reconcile_services()
        self.c.desired('meshtastic', False)
        self.c.reconcile_services()
        self.store.audio_ready = True
        self.assertIsNone(self.c.notice())

    def test_startup_is_once_per_boot_and_not_a_power_action_replacement(self):
        self.assertEqual(self.c.startup()['reason'], 'startup')
        self.now += 16
        self.c.tick()
        self.store.audio_ready = True
        notice = self.c.notice()
        self.assertEqual(notice['kind'], 'runtime')
        self.c.ack('runtime', notice['id'])
        self.assertEqual(self.c.startup()['reason'], 'service_restart')
        self.c.tick()
        self.assertIsNone(self.c.notice())

    def test_delivery_acknowledged_after_speech_and_mode_can_mute_power_notice(self):
        with self.store.connect() as db:
            db.execute("INSERT INTO actions(boot,watts,mode_id,state,message,created) "
                       "VALUES('old',10,1,'verified','Verified power mode.',?)", (self.now,))
        self.store.audio_ready = True
        self.c.set('mode', 'silent')
        self.assertIsNone(self.store.dispatch({'operation': 'notice'})['notice'])
        self.c.set('mode', 'normal')
        self.assertEqual(self.store.dispatch({'operation': 'notice'})['notice']['message'], 'Verified power mode.')
        self.assertEqual(self.c.startup()['reason'], 'action_handoff')

    def test_announcements_require_ack_and_deduplicate(self):
        self.event()
        self.now += 3
        self.store.audio_ready = True
        notice = self.c.notice()
        self.assertEqual(notice, self.c.notice())
        self.c.ack(notice['kind'], notice['id'])
        self.assertIsNone(self.c.notice())

    def test_periodic_summary_stays_muted_in_silent_mode(self):
        self.c.voice('silent mode')
        self.c.voice('summaries every 5 minutes')
        self.event()
        self.now += 301
        self.c.tick()
        self.store.audio_ready = True
        self.assertIsNone(self.c.notice())

    def test_event_validation(self):
        for fields in ({'source': '../bad'}, {'data': {'x': float('nan')}},
                       {'data': {'text': 'a' * 17000}}, {'observed_at': self.now + 301},
                       {'observed_at': True}, {'category': 'made_up'}):
            with self.assertRaises(ValueError):
                self.event(**fields)

    def test_meshtastic_filters_keys_and_non_text_and_deduplicates_by_sender(self):
        event = packet_event({'id': 12, 'fromId': '!a', 'channelKey': 'private',
                              'decoded': {'portnum': 'TEXT_MESSAGE_APP', 'text': 'hello'}})
        self.assertEqual(event['external_id'], '!a:12')
        self.assertNotIn('private', json.dumps(event))
        self.assertIsNone(packet_event({'decoded': {'portnum': 'POSITION_APP'}}))
        delayed = packet_event({'rxTime': 1700000000, 'id': 0, 'fromId': '!b',
                                'decoded': {'portnum': 'TEXT_MESSAGE_APP', 'text': 'earlier'}})
        self.assertEqual(delayed['observed_at'], 1700000000)
        self.assertNotIn('external_id', delayed)

    def test_meshtastic_stream_handles_fragmentation_noise_and_oversized_frames(self):
        frames = Frames()
        wire = b'noise\x94\xc3\xff\xffignored\x94\xc3\x00\x03abc\x94\xc3\x00\x02de'
        payloads = []
        for byte in wire:
            payloads.extend(frames.feed(bytes([byte])))
        self.assertEqual(payloads, [b'abc', b'de'])
        self.assertLessEqual(len(frames.buffer), 3)

    def test_log_rotation_keeps_active_inode_and_respects_cap(self):
        path = Path(self.directory.name) / 'dawn.log'
        path.write_bytes(b'x' * (service_logs.LIMIT + 10))
        inode = path.stat().st_ino
        service_logs.maintain(path.parent, self.now)
        self.assertEqual(path.stat().st_ino, inode)
        self.assertEqual(path.stat().st_size, 0)
        backup = path.with_name('dawn.log.1')
        self.assertLessEqual(backup.stat().st_size, service_logs.LIMIT)
        service_logs.maintain(path.parent, backup.stat().st_mtime + 8 * DAY)
        self.assertFalse(backup.exists())

    def test_parallel_duplicate_arrivals_count_once_and_cleanup_updates_usage(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.event(external_id='duplicate'), range(12)))
        self.assertEqual(len({r['id'] for r in results}), 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT rows FROM event_usage').fetchone()[0], 1)
        self.now += 91 * DAY
        self.c.cleanup()
        with self.store.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT rows,bytes FROM event_usage').fetchone()), (0, 0))

    def test_operation_results_and_action_outcomes_enter_history_once(self):
        self.c.record_operation({'operation': 'camera_describe'}, {'fresh': True, 'source': 'camera'})
        self.c.record_operation({'operation': 'drone_start'}, {'error': 'No feed'})
        with self.store.connect() as db:
            db.execute("INSERT INTO actions(boot,watts,mode_id,state,message,created) "
                       "VALUES('old',10,1,'verified','Verified power mode.',?)", (self.now,))
        self.c.record_actions()
        self.c.record_actions()
        self.assertEqual(len(self.c.query(0)['events']), 3)
        self.now += 15 * DAY
        self.c.cleanup()
        self.c.record_actions()
        self.assertEqual(len(self.c.query(0)['events']), 1)  # only the fault remains

    def test_unmanaged_receiver_is_observed_but_not_controlled(self):
        self.c.health('meshtastic', True, 'API connected')
        self.c.reconcile_services()
        self.now += 31
        self.c.reconcile_services()
        self.assertEqual(self.calls, [])
        self.assertIn('service.waiting', [e['type'] for e in self.c.query(0)['events']])

    def test_silent_startup_notice_uses_current_readiness_when_later_delivered(self):
        self.c.set('mode', 'silent')
        self.c.health('meshtastic', True, 'API verified')
        self.c.startup()
        self.c.tick()
        self.now += 31
        self.store.audio_ready = True
        self.c.set('mode', 'normal')
        self.assertIn('waiting for verified readiness', self.c.notice()['message'])

    def test_collection_interruption_is_reported_after_reboot(self):
        self.c.resume()
        self.c.set('runtime_last_seen', {'boot': 'old-boot', 'at': self.now - 120})
        self.c.resume()
        self.assertIn('availability gap', self.c.report(2, True))

    def test_full_pinned_history_does_not_block_modes_preferences_or_maintenance(self):
        event = self.event()
        self.c.dispatch({'operation': 'pin_event', 'id': event['id'], 'pinned': True})
        with patch('continuity.MAX_EVENTS', 1):
            self.assertTrue(self.c.voice('silent mode')['handled'])
            self.c.desired('meshtastic', True, True)
            self.c.tick()
            self.assertEqual(self.c.get('mode'), 'silent')
            self.assertTrue(self.c.get('storage_pressure'))
            self.assertTrue(self.calls)  # recovery still attempts the allowlisted service
            with self.assertRaises(RuntimeError):
                self.event(external_id='cannot-fit')
        self.assertEqual(self.c.query(0)['events'][0]['id'], event['id'])

    def test_restart_cancels_an_old_pending_introduction(self):
        self.c.startup()
        self.assertIsNotNone(self.c.get('startup_due'))
        self.assertEqual(self.c.startup()['reason'], 'service_restart')
        self.assertIsNone(self.c.get('startup_due'))

    def test_supervisor_diagnostics_are_separate_from_event_payloads(self):
        self.c.resume()
        self.c.health('meshtastic', True, 'API verified')
        self.c.reconcile_services()
        path = self.path.parent / 'services.log'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertTrue(any(r['service'] == 'meshtastic' and r['state'] == 'ready' for r in rows))
        self.assertTrue(any(r['service'] == 'runtime' and r['state'] == 'started' for r in rows))


if __name__ == '__main__':
    unittest.main()
