"""Reboot recovery tests: no real power changes or reboot commands are executed."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime import Audio, Store


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.db'
        self.calls = []
        self.mode = (3, '25W')
        self.fail_read = False
        self.fail_apply = False
        self.store = self.open('boot-a')

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, args, **kwargs):
        self.calls.append(args)
        if args[-1] == '-q':
            if self.fail_read:
                return subprocess.CompletedProcess(args, 1, '', 'unavailable')
            return subprocess.CompletedProcess(args, 0,
                                               f'NV Power Mode: {self.mode[1]}\n{self.mode[0]}\n', '')
        return subprocess.CompletedProcess(args, int(self.fail_apply), '', '')

    def open(self, boot):
        store = Store(self.path, boot, self.runner)
        store.modes = lambda: {10: 1, 25: 3}
        return store

    def pending(self, watts=10):
        # Suppress the hardware worker; verify the pre-command durable transaction.
        result = self.store.request_power(watts)
        self.store.audio_ready = True
        with patch('runtime.threading.Thread') as worker:
            self.store.confirm_power(result['id'])
            worker.return_value.start.assert_called_once()
        return result['id']

    def test_request_only_prepares_and_never_changes_hardware_without_confirmation(self):
        with patch('runtime.threading.Thread') as worker:
            prepared = self.store.request_power(10)
            worker.assert_not_called()
        self.assertEqual(self.row()['state'], 'awaiting_confirmation')
        self.assertEqual(self.store.confirmation()['id'], prepared['id'])
        self.assertIn('requires a reboot', prepared['message'])
        self.assertFalse(any('-m' in call for call in self.calls))

    def test_confirmation_expiry_disconnect_and_cancel_do_not_change_power(self):
        prepared = self.store.request_power(10)
        with self.assertRaises(RuntimeError):
            self.store.confirm_power(prepared['id'])  # headset unavailable
        self.store.dispatch({'operation': 'cancel_power', 'id': prepared['id']})
        with self.assertRaises(RuntimeError):
            self.store.confirm_power(prepared['id'])
        second = self.store.request_power(10)
        with self.store.connect() as db:
            db.execute('UPDATE actions SET created=0 WHERE id=?', (second['id'],))
        self.store.audio_ready = True
        with self.assertRaises(RuntimeError):
            self.store.confirm_power(second['id'])
        self.assertEqual(self.row()['state'], 'cancelled')
        self.assertFalse(any('-m' in call for call in self.calls))

    def test_unconfirmed_request_does_not_survive_reboot_as_an_authorization(self):
        self.store.request_power(10)
        restored = self.open('boot-b')
        restored.reconcile()
        self.assertEqual(self.row(restored)['state'], 'cancelled')
        self.assertIsNone(restored.confirmation())

    def row(self, store=None):
        with (store or self.store).connect() as db:
            return dict(db.execute('SELECT * FROM actions ORDER BY id DESC LIMIT 1').fetchone())

    def test_history_survives_service_and_boot_restart_with_owner_isolation(self):
        self.store.dispatch({'operation': 'save_history', 'owner': 7, 'messages': [
            {'role': 'system', 'content': 'Do not retain provider instructions'},
            {'role': 'user', 'content': 'Change to 10 watts'},
            {'role': 'assistant', 'content': 'I will verify after reboot.'},
            {'role': 'tool', 'content': 'do not restore tool protocol fragments'}]})
        restored = self.open('boot-b')
        messages = restored.dispatch({'operation': 'load_history', 'owner': 7})['messages']
        self.assertEqual([m['role'] for m in messages], ['user', 'assistant'])
        self.assertEqual(messages[0]['content'], 'Change to 10 watts')
        self.assertEqual(restored.dispatch({'operation': 'load_history', 'owner': 8})['messages'], [])

    def test_request_is_durable_before_hardware_worker(self):
        self.pending()
        self.assertEqual(self.row(self.open('boot-a'))['state'], 'pending')
        self.assertFalse(any('-m' in call for call in self.calls))

    def test_same_boot_never_claims_post_reboot_success(self):
        self.pending()
        self.mode = (1, '10W')
        self.store.reconcile()
        self.assertEqual(self.row()['state'], 'pending')

    def test_new_boot_verifies_actual_mode_and_retains_notice_until_audio(self):
        action = self.pending()
        self.mode = (1, '10W')
        restored = self.open('boot-b')
        restored.reconcile()
        self.assertEqual(self.row(restored)['state'], 'verified')
        self.assertIn('10-watt mode is active', self.row(restored)['message'])
        self.assertIsNone(restored.dispatch({'operation': 'notice'})['notice'])
        restored.audio_ready = True
        self.assertEqual(restored.dispatch({'operation': 'notice'})['notice']['id'], action)
        restored.dispatch({'operation': 'ack', 'id': action})
        self.assertEqual(self.row(self.open('boot-c'))['delivered'], 1)

    def test_mismatched_actual_mode_is_failure(self):
        self.pending()
        restored = self.open('boot-b')
        restored.reconcile()
        self.assertEqual(self.row(restored)['state'], 'failed')
        self.assertIn('reports 25W', self.row(restored)['message'])

    def test_read_error_preserves_pending_then_recovers(self):
        self.pending()
        restored = self.open('boot-b')
        self.fail_read = True
        with self.assertRaises(RuntimeError):
            restored.reconcile()
        self.assertEqual(self.row(restored)['state'], 'pending')
        self.fail_read = False
        self.mode = (1, '10W')
        restored.reconcile()
        self.assertEqual(self.row(restored)['state'], 'verified')

    def test_apply_failure_does_not_reboot_or_claim_success(self):
        action = self.pending()
        self.fail_apply = True
        with patch('runtime.time.sleep'):
            self.store.apply(action, 1)
        self.assertEqual(self.row()['state'], 'failed')
        self.assertFalse(any('/usr/sbin/shutdown' in call for call in self.calls))

    def test_apply_reboots_only_after_recording_intent(self):
        action = self.pending()
        with patch('runtime.time.sleep'):
            self.store.apply(action, 1)
        self.assertEqual(self.row()['state'], 'rebooting')
        self.assertIn(['sudo', '-n', '/usr/sbin/nvpmodel', '-m', '1'], self.calls)
        self.assertIn(['sudo', '-n', '/usr/sbin/shutdown', '-r', '+1'], self.calls)

    def test_existing_mode_is_noop(self):
        response = self.store.request_power(25)
        self.assertIn('No reboot needed', response['message'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM actions').fetchone()[0], 0)

    def test_invalid_and_duplicate_requests_do_not_change_hardware(self):
        for value in [True, '25; reboot', 99, 25.0]:
            with self.assertRaises(ValueError):
                self.store.request_power(value)
        self.pending()
        with self.assertRaises(RuntimeError):
            self.store.request_power(10)
        self.assertFalse(any('-m' in call for call in self.calls))

    def test_mode_parser_reads_installed_profiles(self):
        config = Path(self.temp.name) / 'nvpmodel.conf'
        config.write_text('< POWER_MODEL ID=0 NAME=MAXN >\n'
                          '< POWER_MODEL ID=1 NAME=10W >\n< POWER_MODEL ID=3 NAME=25W >\n')
        self.assertEqual(Store.modes(self.store, config), {10: 1, 25: 3})


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.connected = False
        self.modules = {77: 'source=unrelated sink=unrelated'}
        self.next_id = 100
        self.fail_output = False
        self.audio = Audio(self.runner)

    def runner(self, args, **kwargs):
        args = args[1:]
        output, code = '', 0
        if args == ['list', 'short', 'modules']:
            output = '\n'.join(f'{key}\tmodule-loopback\t{value}\t' for key, value in self.modules.items())
        elif args == ['list', 'short', 'sinks']:
            output = '1\tbackpack_capture\tPipeWire\n2\tbackpack_playback\tPipeWire\n'
            if self.connected:
                output += '3\tbluez_output.airpods\tPipeWire\n'
        elif args == ['list', 'short', 'sources']:
            output = '4\tbackpack_capture.monitor\tPipeWire\n'
            if self.connected:
                output += '5\tbluez_input.airpods\tPipeWire\n'
        elif args[:2] == ['load-module', 'module-loopback']:
            if self.fail_output and 'source=backpack_playback.monitor' in args:
                code = 1
            else:
                self.modules[self.next_id] = ' '.join(args[2:])
                output = str(self.next_id)
                self.next_id += 1
        elif args[0] == 'unload-module':
            self.modules.pop(int(args[1]), None)
        return subprocess.CompletedProcess(args, code, output, '')

    def test_no_headset_start_and_reconnect_without_duplicate_loopbacks(self):
        self.assertFalse(self.audio.update())
        self.connected = True
        self.assertTrue(self.audio.update())
        self.assertEqual(len(self.modules), 3)  # two owned, one unrelated
        self.assertTrue(self.audio.update())
        self.assertEqual(len(self.modules), 3)
        self.connected = False
        self.assertFalse(self.audio.update())
        self.assertEqual(self.modules, {77: 'source=unrelated sink=unrelated'})
        self.connected = True
        self.assertTrue(self.audio.update())
        self.assertEqual(len(self.modules), 3)
        # A runtime restart removes only its stale links and can recreate them.
        restarted = Audio(self.runner)
        self.assertEqual(self.modules, {77: 'source=unrelated sink=unrelated'})
        self.assertTrue(restarted.update())

    def test_partial_connection_failure_removes_owned_link(self):
        self.connected, self.fail_output = True, True
        with self.assertRaises(RuntimeError):
            self.audio.update()
        self.assertIsNone(self.audio.routes)
        self.assertEqual(self.modules, {77: 'source=unrelated sink=unrelated'})


if __name__ == '__main__':
    unittest.main()
