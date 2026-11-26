#!/usr/bin/env python3
"""Private backpack state, verified power actions and reconnectable audio.

The socket is owner-only. No shell commands or model-provided mode IDs are used.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import sqlite3
import struct
import subprocess
import threading
import time
import urllib.request

from camera_look import CameraLook
from drone_feed import DroneFeed
from host_tools import DiagnosticShell, host_snapshot
from host_actions import HostActions
from continuity import Continuity, OPERATIONS
import service_logs

MAX_REQUEST = 1048576


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, timeout=30, **kwargs)


class Store:
    def __init__(self, path, boot_id, runner=run):
        self.path, self.boot_id, self.runner = Path(path), boot_id, runner
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS history (
                    owner INTEGER PRIMARY KEY, messages TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY, boot TEXT NOT NULL, watts INTEGER NOT NULL,
                    mode_id INTEGER NOT NULL, state TEXT NOT NULL,
                    message TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0,
                    created REAL NOT NULL);
            """)
        os.chmod(self.path, 0o600)
        self.audio_ready = False
        self.host_actions = HostActions(self)
        self.continuity = Continuity(self)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def power(self):
        result = self.runner(['sudo', '-n', '/usr/sbin/nvpmodel', '-q'])
        if result.returncode:
            raise RuntimeError('Cannot read current Jetson power mode')
        match = re.search(r'NV Power Mode:\s*([^\n]+)\n\s*(\d+)', result.stdout)
        if not match:
            raise RuntimeError('Unrecognized nvpmodel status; no mode inferred')
        name, mode_id = match[1].strip(), int(match[2])
        watts = re.fullmatch(r'(\d+)W', name, re.IGNORECASE)
        return {'mode_id': mode_id, 'name': name,
                'watts': int(watts[1]) if watts else None}

    def modes(self, config='/etc/nvpmodel.conf'):
        matches = re.findall(r'^\s*<\s*POWER_MODEL\s+ID=(\d+)\s+NAME=(\d+)W\s*>',
                             Path(config).read_text(), re.MULTILINE | re.IGNORECASE)
        modes = {}
        for mode_id, watts in matches:
            if int(watts) in modes:
                raise RuntimeError('Ambiguous power profiles; no change made')
            modes[int(watts)] = int(mode_id)
        return modes

    def reconcile(self):
        """Only a different kernel boot can complete an in-flight reboot action."""
        self.host_actions.reconcile()
        with self.lock, self.connect() as db:
            db.execute("UPDATE actions SET state='cancelled',message='Confirmation expired; "
                       "no power change was initiated.' WHERE state='awaiting_confirmation' "
                       "AND (boot != ? OR created < ?)", (self.boot_id, time.time() - 120))
            rows = db.execute("SELECT * FROM actions WHERE state IN ('pending','applying',"
                              "'rebooting') AND boot != ?", (self.boot_id,)).fetchall()
            if not rows:
                return
            actual = self.power()  # failure leaves requests pending, never claims success
            for row in rows:
                success = actual['mode_id'] == row['mode_id'] and actual['watts'] == row['watts']
                message = (f"The reboot completed. Your requested {row['watts']}-watt mode "
                           "is active." if success else
                           f"The reboot completed, but your requested {row['watts']}-watt "
                           f"mode is not active. The Jetson reports {actual['name']}.")
                db.execute('UPDATE actions SET state=?,message=? WHERE id=?',
                           ('verified' if success else 'failed', message, row['id']))

    def request_power(self, watts):
        if type(watts) is not int:
            raise ValueError('watts must be an integer from the installed power profiles')
        modes = self.modes()
        if watts not in modes:
            raise ValueError(f'Unsupported wattage. Available: {sorted(modes)}')
        actual = self.power()
        with self.lock, self.connect() as db:
            if db.execute("SELECT 1 FROM host_actions WHERE state IN "
                          "('awaiting_confirmation','pending','executing','issued')").fetchone():
                raise RuntimeError('Another host action is pending')
            if db.execute("SELECT 1 FROM actions WHERE state IN ('awaiting_confirmation','pending','applying',"
                          "'rebooting')").fetchone():
                raise RuntimeError('A power change is already pending; no second change made')
            if actual['watts'] == watts and actual['mode_id'] == modes[watts]:
                return {'message': f"The Jetson is already in {watts}-watt mode. No reboot needed."}
            message = (f"You requested {watts} watts. Swapping power modes requires a reboot. "
                       "Please confirm.")
            cursor = db.execute('INSERT INTO actions(boot,watts,mode_id,state,message,created) '
                                "VALUES(?,?,?,'awaiting_confirmation',?,?)",
                                (self.boot_id, watts, modes[watts], message, time.time()))
            action_id = cursor.lastrowid
        return {'id': action_id, 'message': message}

    def confirmation(self):
        self.reconcile()
        with self.connect() as db:
            row = db.execute("SELECT id,watts FROM actions WHERE state='awaiting_confirmation' "
                             'AND boot=? ORDER BY id DESC LIMIT 1', (self.boot_id,)).fetchone()
        return dict(row) if row else self.host_actions.pending()

    def confirm_power(self, action_id):
        pending = self.confirmation()
        if not pending or pending.get('kind') == 'host' or pending['id'] != action_id:
            raise RuntimeError('Power confirmation expired or is no longer pending; nothing changed')
        if not self.audio_ready:
            raise RuntimeError('Headset disconnected; power change was not initiated')
        with self.lock, self.connect() as db:
            row = db.execute("SELECT mode_id FROM actions WHERE id=? AND "
                             "state='awaiting_confirmation'", (action_id,)).fetchone()
            if not row:
                raise RuntimeError('Power request is no longer awaiting confirmation')
            db.execute("UPDATE actions SET state='pending',message='Power change confirmed; "
                       "reboot verification pending.' WHERE id=?", (action_id,))
            mode_id = row['mode_id']
        # Explicit confirmation is committed before any hardware command.
        threading.Thread(target=self.apply, args=(action_id, mode_id), daemon=True).start()
        return {'id': action_id, 'message': 'Power change confirmed; reboot verification pending.'}

    def apply(self, action_id, mode_id):
        time.sleep(5)  # allow the caller to acknowledge and checkpoint the conversation
        with self.lock, self.connect() as db:
            db.execute("UPDATE actions SET state='applying' WHERE id=?", (action_id,))
        try:
            result = self.runner(['sudo', '-n', '/usr/sbin/nvpmodel', '-m', str(mode_id)],
                                 input='YES\n')
            if result.returncode:
                raise RuntimeError('nvpmodel failed; requested mode was not confirmed')
            # nvpmodel may itself reboot; the pre-existing pending record survives that.
            result = self.runner(['sudo', '-n', '/usr/sbin/shutdown', '-r', '+1'])
            if result.returncode:
                raise RuntimeError('Power change attempted, but reboot scheduling failed')
            with self.lock, self.connect() as db:
                db.execute("UPDATE actions SET state='rebooting' WHERE id=?", (action_id,))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            with self.lock, self.connect() as db:
                db.execute("UPDATE actions SET state='failed',message=? WHERE id=?",
                           (str(exc), action_id))

    def dispatch(self, request):
        operation = request.get('operation')
        with self.lock:
            if operation in OPERATIONS:
                return self.continuity.dispatch(request)
            if operation == 'set_power':
                return self.request_power(request.get('watts'))
            if operation == 'confirmation':
                return {'confirmation': self.confirmation()}
            if operation == 'confirm_power':
                return self.confirm_power(request.get('id'))
            if operation == 'cancel_power':
                with self.connect() as db:
                    db.execute("UPDATE actions SET state='cancelled',message='Power change "
                               "cancelled; nothing changed.' WHERE id=? AND "
                               "state='awaiting_confirmation'", (int(request['id']),))
                return {'ok': True}
            if operation == 'prepare_host':
                return self.host_actions.prepare(request.get('action'), request.get('service'))
            if operation == 'confirm_host':
                return self.host_actions.confirm(request.get('id'))
            if operation == 'cancel_host':
                return self.host_actions.cancel(request.get('id'))
            if operation == 'status':
                with self.connect() as db:
                    rows = db.execute('SELECT id,watts,state,message,delivered,created FROM '
                                      'actions ORDER BY id DESC LIMIT 20').fetchall()
                try:
                    power, error = self.power(), None
                except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                    power, error = None, str(exc)
                return {'power': power, 'error': error, 'audio_ready': self.audio_ready,
                        'actions': [dict(row) for row in rows]}
            if operation == 'notice':
                if self.continuity.get('mode') == 'silent':
                    return {'notice': None}
                with self.connect() as db:
                    row = db.execute("SELECT id,message FROM actions WHERE delivered=0 AND "
                                     "state IN ('verified','failed') ORDER BY id LIMIT 1").fetchone()
                if row and self.audio_ready:
                    return {'notice': dict(row)}
                with self.connect() as db:
                    row = db.execute("SELECT id,message FROM host_actions WHERE delivered=0 AND "
                                     "state IN ('verified','failed','unverified') ORDER BY id LIMIT 1").fetchone()
                if row and self.audio_ready:
                    return {'notice': dict(row, kind='host')}
                return {'notice': self.continuity.notice()}
            if operation == 'ack':
                if request.get('kind') in ('runtime', 'events'):
                    return self.continuity.ack(request['kind'], request.get('id'))
                with self.connect() as db:
                    if request.get('kind') == 'host':
                        db.execute('UPDATE host_actions SET delivered=1 WHERE id=? AND state IN '
                                   "('verified','failed','unverified')", (int(request['id']),))
                    else:
                        db.execute('UPDATE actions SET delivered=1 WHERE id=? AND state IN '
                                   "('verified','failed')", (int(request['id']),))
                return {'ok': True}
            if operation in ('save_history', 'load_history'):
                owner = request.get('owner', 0)
                if type(owner) is not int or owner < 0:
                    raise ValueError('Invalid conversation owner')
                with self.connect() as db:
                    if operation == 'load_history':
                        row = db.execute('SELECT messages FROM history WHERE owner=?',
                                         (owner,)).fetchone()
                        return {'messages': json.loads(row[0]) if row else []}
                    messages = request.get('messages')
                    if not isinstance(messages, list):
                        raise ValueError('Expected messages array')
                    clean = []
                    for message in messages[-32:]:
                        if (isinstance(message, dict) and message.get('role') in ('user', 'assistant')
                                and isinstance(message.get('content'), str)):
                            clean.append({'role': message['role'], 'content': message['content'][:4000]})
                    db.execute('INSERT OR REPLACE INTO history VALUES(?,?)',
                               (owner, json.dumps(clean)))
                return {'ok': True}
        raise ValueError('Unknown backpack operation')


class Audio:
    def __init__(self, runner=run):
        self.runner, self.links = runner, []
        self.routes = None
        # Remove only this runtime's reserved loopbacks after a service restart.
        for line in self.call('list', 'short', 'modules').splitlines():
            fields = line.split('\t')
            if len(fields) >= 3 and fields[1] == 'module-loopback':
                args = fields[2].split()
                if ('sink=backpack_capture' in args or
                        'source=backpack_playback.monitor' in args):
                    self.runner(['pactl', 'unload-module', fields[0]])

    def call(self, *args):
        result = self.runner(['pactl', *args])
        if result.returncode:
            raise RuntimeError('PipeWire/PulseAudio operation failed')
        return result.stdout.strip()

    def update(self):
        sinks = self.call('list', 'short', 'sinks')
        for name, rate in [('backpack_capture', 16000), ('backpack_playback', 48000)]:
            if name not in [line.split()[1] for line in sinks.splitlines()]:
                self.call('load-module', 'module-null-sink', f'sink_name={name}',
                          f'rate={rate}', 'channels=1')
        sources = [line.split()[1] for line in self.call('list', 'short', 'sources').splitlines()
                   if line.split()[1].startswith('bluez_input.')]
        outputs = [line.split()[1] for line in self.call('list', 'short', 'sinks').splitlines()
                   if line.split()[1].startswith('bluez_output.')]
        routes = (sources[0], outputs[0]) if len(sources) == len(outputs) == 1 else None
        if routes != self.routes:
            for module in self.links:
                self.runner(['pactl', 'unload-module', module])
            self.links, self.routes = [], None
            if routes:
                try:
                    self.call('set-source-mute', routes[0], '0')
                    self.call('set-sink-mute', routes[1], '0')
                    self.call('set-sink-volume', routes[1], '90%')
                    for source, sink in [(routes[0], 'backpack_capture'),
                                         ('backpack_playback.monitor', routes[1])]:
                        self.links.append(self.call('load-module', 'module-loopback',
                                                    f'source={source}', f'sink={sink}',
                                                    'latency_msec=30'))
                    self.routes = routes
                except RuntimeError:
                    for module in self.links:
                        self.runner(['pactl', 'unload-module', module])
                    self.links = []
                    raise
        return self.routes is not None


def serve(root):
    os.umask(0o077)
    state = root / 'run'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    store = Store(state / 'backpack.db', Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    store.continuity.resume()
    camera = CameraLook(state)
    drone = DroneFeed(state)
    diagnostics = DiagnosticShell()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(3)
            _, uid, _ = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET,
                                                                  socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                return
            request = {}
            try:
                line = self.rfile.readline(MAX_REQUEST + 1)
                if len(line) > MAX_REQUEST or not line.endswith(b'\n'):
                    raise ValueError('Request too large or incomplete')
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError('Expected an object')
                if request.get('operation') == 'camera_describe':
                    result = camera.describe(request.get('query', 'What do you see?'))
                elif request.get('operation') == 'drone_start':
                    result = drone.start()
                elif request.get('operation') == 'drone_describe':
                    result = drone.describe(request.get('query', 'What is on the eye in the sky?'))
                elif request.get('operation') == 'drone_stop':
                    result = drone.stop()
                elif request.get('operation') == 'drone_status':
                    result = drone.status()
                elif request.get('operation') == 'host_status':
                    result = host_snapshot()
                elif request.get('operation') == 'diagnostic_cli':
                    result = diagnostics.execute(request.get('command'))
                else:
                    result = store.dispatch(request)
            except (ValueError, KeyError, TypeError, RuntimeError, OSError,
                    sqlite3.Error, subprocess.TimeoutExpired) as exc:
                result = {'error': str(exc)}
            try:
                if isinstance(request, dict):
                    store.continuity.record_operation(request, result)
            except (ValueError, RuntimeError, OSError, sqlite3.Error):
                service_logs.append(state, 'runtime', 'event_write_failed',
                                    'A camera or ASTRA result could not be recorded')
            self.wfile.write(json.dumps(result).encode() + b'\n')

    address = state / 'runtime.sock'
    address.unlink(missing_ok=True)
    server = socketserver.ThreadingUnixStreamServer(str(address), Handler)
    server.daemon_threads = True
    os.chmod(address, 0o600)

    def maintain():
        audio = None
        while True:
            try:
                if audio is None:
                    audio = Audio()
                store.audio_ready = audio.update()
            except (RuntimeError, OSError, subprocess.TimeoutExpired):
                store.audio_ready = False
                audio = None
            for maintenance in (store.reconcile, store.continuity.record_actions,
                                store.continuity.tick, lambda: service_logs.maintain(state)):
                try:
                    maintenance()
                except (RuntimeError, OSError, subprocess.TimeoutExpired, sqlite3.Error):
                    pass  # one failed subsystem must not prevent cleanup or recovery
            time.sleep(3)

    threading.Thread(target=maintain, daemon=True).start()

    def warm_model():
        for attempt in range(5):
            try:
                request = urllib.request.Request(
                    'http://127.0.0.1:11434/api/generate',
                    data=json.dumps({'model': 'backpack-dev-qwen', 'stream': False,
                                     'keep_alive': -1}).encode(),
                    headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=180) as response:
                    json.load(response)
                return
            except (OSError, ValueError):
                time.sleep(10)

    threading.Thread(target=warm_model, daemon=True).start()
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home() / 'jetson-backpack-dev')
    args = parser.parse_args()
    serve(args.root)
