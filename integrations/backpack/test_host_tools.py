"""Host observations, sandbox launch contract, and stubbed host-action transitions."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from host_tools import DiagnosticShell, host_snapshot
from runtime import Store


class HostSnapshotTests(unittest.TestCase):
    def test_live_memory_uses_available_and_does_not_expose_process_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 250 kB\n'
                                         'SwapTotal: 100 kB\nSwapFree: 90 kB\n')
            (root / 'uptime').write_text('617.5 25\n')
            (root / 'loadavg').write_text('0.1 0.2 0.3 1/20 123\n')
            (root / 'stat').write_text('cpu 10 0 20 70 0 0 0 0\n')
            process = root / '123'
            process.mkdir()
            (process / 'status').write_text('VmRSS: 42 kB\n')
            (process / 'comm').write_text('dawn\n')
            (process / 'cmdline').write_text('private-token')
            with patch('host_tools.time.sleep'):
                result = host_snapshot(root, root, root)
            self.assertEqual(75, result['memory']['used_percent'])
            self.assertEqual(750 * 1024, result['memory']['used_bytes'])
            self.assertEqual(617.5, result['uptime_seconds'])
            self.assertFalse(result['simulated'])
            self.assertNotIn('private-token', json.dumps(result))
            self.assertEqual('dawn', result['top_processes'][0]['name'])

    def test_general_command_is_an_argument_and_confinement_is_fixed(self):
        command = 'free -b | awk "NR==2 {print $3}"; uname -m'
        args = DiagnosticShell.launch(command)
        self.assertEqual(command, args[-1])
        self.assertEqual(['/bin/bash', '--noprofile', '--norc', '-c'], args[-5:-1])
        self.assertIn('NoNewPrivileges=yes', args)
        self.assertIn('ProtectSystem=strict', args)
        self.assertIn('PrivateNetwork=yes', args)
        self.assertIn('RuntimeMaxSec=8', args)
        self.assertIn('--expand-environment=no', args)
        for invalid in ('', None, 'x' * 2049, 'x\0y'):
            with self.assertRaises(ValueError):
                DiagnosticShell.launch(invalid)

    def test_output_is_bounded_and_control_codes_removed(self):
        def runner(args, **kwargs):
            kwargs['stdout'].write(b'\x1b[31mhello\x1b[0m\x00' + b'x' * 9000)
            return subprocess.CompletedProcess(args, 0)
        result = DiagnosticShell(runner).execute('printf test')
        self.assertTrue(result['truncated'])
        self.assertNotIn('\x1b', result['output'])
        self.assertNotIn('\0', result['output'])
        self.assertTrue(result['output'].startswith('hello'))


class HostActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.db'
        self.calls = []
        self.store = self.open('boot-a')
        self.store.audio_ready = True

    def open(self, boot):
        result = Store(self.path, boot, self.runner)
        result.modes = lambda: {10: 1, 25: 3}
        return result

    def runner(self, args, **kwargs):
        self.calls.append(args)
        text = 'NV Power Mode: 25W\n3\n' if args[-1] == '-q' else (
            'active\n' if 'is-active' in args else '')
        return subprocess.CompletedProcess(args, 0, text, '')

    def row(self):
        with self.store.connect() as db:
            return dict(db.execute('SELECT * FROM host_actions ORDER BY id DESC LIMIT 1').fetchone())

    def prepare(self, action='reboot', service=None):
        return self.store.dispatch({'operation': 'prepare_host', 'action': action, 'service': service})

    def confirm(self, identifier):
        with patch('host_actions.threading.Thread') as worker:
            self.store.dispatch({'operation': 'confirm_host', 'id': identifier})
            worker.return_value.start.assert_called_once()

    def test_proposal_does_not_execute_and_model_cannot_confirm(self):
        with patch('host_actions.threading.Thread') as worker:
            result = self.prepare()
            worker.assert_not_called()
        self.assertFalse(self.calls)
        self.assertEqual('awaiting_confirmation', self.row()['state'])
        self.assertEqual('host', self.store.confirmation()['kind'])
        with self.assertRaises(ValueError):
            self.prepare('confirm')
        with self.assertRaises(RuntimeError):
            self.store.confirm_power(result['id'])

    def test_cancel_expiry_and_disconnect_never_execute(self):
        for identifier in (True, '1', None, 0):
            with self.assertRaises(ValueError):
                self.store.host_actions.cancel(identifier)
        result = self.prepare()
        self.store.dispatch({'operation': 'cancel_host', 'id': result['id']})
        with self.assertRaises(RuntimeError):
            self.confirm(result['id'])
        result = self.prepare()
        with self.store.connect() as db:
            db.execute('UPDATE host_actions SET created=0 WHERE id=?', (result['id'],))
        with self.assertRaises(RuntimeError):
            self.confirm(result['id'])
        result = self.prepare()
        self.store.audio_ready = False
        with self.assertRaises(RuntimeError):
            self.confirm(result['id'])
        self.assertEqual('cancelled', self.row()['state'])
        self.assertFalse(self.calls)

    def test_pending_cannot_be_replayed_or_changed_and_survives_restart(self):
        result = self.prepare()
        self.confirm(result['id'])
        self.assertEqual('pending', self.row()['state'])
        with self.assertRaises(RuntimeError):
            self.confirm(result['id'])
        with patch('host_actions.time.sleep'):
            self.store.host_actions.apply(result['id'], 'shutdown', '')
        self.assertFalse(self.calls)
        restored = self.open('boot-a')
        restored.reconcile()
        self.assertEqual('pending', self.row()['state'])

    def test_confirmed_reboot_is_issued_then_verified_only_on_new_boot(self):
        result = self.prepare()
        self.confirm(result['id'])
        with patch('host_actions.time.sleep'):
            self.store.host_actions.apply(result['id'], 'reboot', '')
        self.assertEqual([['sudo', '-n', '/usr/sbin/shutdown', '-r', 'now']], self.calls)
        self.assertEqual('issued', self.row()['state'])
        self.store.reconcile()
        self.assertEqual('issued', self.row()['state'])
        restored = self.open('boot-b')
        restored.reconcile()
        self.assertEqual('verified', self.row()['state'])

    def test_shutdown_is_not_falsely_verified_after_next_boot(self):
        result = self.prepare('shutdown')
        self.confirm(result['id'])
        with patch('host_actions.time.sleep'):
            self.store.host_actions.apply(result['id'], 'shutdown', '')
        self.open('boot-b').reconcile()
        self.assertEqual('unverified', self.row()['state'])

    def test_only_supported_services_and_real_active_state(self):
        with self.assertRaises(ValueError):
            self.prepare('restart_service', 'dawn; reboot')
        with self.assertRaises(ValueError):
            self.prepare('restart_service', 'backpack-runtime')
        result = self.prepare('restart_service', 'yolo')
        self.confirm(result['id'])
        with patch('host_actions.time.sleep'):
            self.store.host_actions.apply(result['id'], 'restart_service', 'backpack-yolo')
        self.assertEqual('verified', self.row()['state'])
        self.assertEqual([['systemctl', '--user', 'restart', 'backpack-yolo'],
                          ['systemctl', '--user', 'is-active', 'backpack-yolo']], self.calls)

    def test_power_and_host_proposals_are_mutually_exclusive(self):
        result = self.prepare()
        with self.assertRaises(RuntimeError):
            self.store.request_power(10)
        self.store.dispatch({'operation': 'cancel_host', 'id': result['id']})
        self.store.request_power(10)
        with self.assertRaises(RuntimeError):
            self.prepare()


if __name__ == '__main__':
    unittest.main()
