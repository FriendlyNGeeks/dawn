"""Durable proposals; only attended voice confirmation permits host actions."""
import subprocess
import threading
import time

SERVICES = {'dawn': 'backpack-dawn-dev', 'yolo': 'backpack-yolo',
            'backpack-dawn-dev': 'backpack-dawn-dev', 'backpack-yolo': 'backpack-yolo'}


class HostActions:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS host_actions ('
                       'id INTEGER PRIMARY KEY, boot TEXT NOT NULL, action TEXT NOT NULL, '
                       'service TEXT NOT NULL, state TEXT NOT NULL, message TEXT NOT NULL, '
                       'delivered INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)')

    def reconcile(self):
        store = self.store
        with store.lock, store.connect() as db:
            db.execute("UPDATE host_actions SET state='cancelled',message='Host action expired or "
                       "headset disconnected; nothing was initiated.' WHERE state='awaiting_confirmation' "
                       'AND (boot != ? OR created < ? OR ?=0)',
                       (store.boot_id, time.time() - 120, int(store.audio_ready)))
            rows = db.execute("SELECT * FROM host_actions WHERE state IN ('pending','executing','issued') "
                              'AND boot != ?', (store.boot_id,)).fetchall()
            for row in rows:
                reboot = row['action'] == 'reboot'
                message = ('The requested reboot completed; the Jetson is back online.' if reboot else
                           'The Jetson is back online after a host action request; its prior completion is unverified.')
                db.execute('UPDATE host_actions SET state=?,message=? WHERE id=?',
                           ('verified' if reboot else 'unverified', message, row['id']))

    def pending(self):
        self.reconcile()
        with self.store.connect() as db:
            row = db.execute("SELECT id,action,service FROM host_actions WHERE "
                             "state='awaiting_confirmation' AND boot=? ORDER BY id DESC LIMIT 1",
                             (self.store.boot_id,)).fetchone()
        return dict(row, kind='host') if row else None

    def prepare(self, action, service=None):
        if action not in ('shutdown', 'reboot', 'restart_service'):
            raise ValueError('Use shutdown, reboot, or restart_service; no model confirmation action exists')
        if action == 'restart_service':
            if not isinstance(service, str) or service not in SERVICES:
                raise ValueError('Only the dawn or yolo service can be restarted')
            service = SERVICES[service]
        elif service not in (None, ''):
            raise ValueError('Service applies only to restart_service')
        else:
            service = ''
        store = self.store
        self.reconcile()
        if not store.audio_ready:
            raise RuntimeError('Connect the headset before requesting a host action')
        with store.lock, store.connect() as db:
            for table in ('actions', 'host_actions'):
                if db.execute(f"SELECT 1 FROM {table} WHERE state IN "
                              "('awaiting_confirmation','pending','applying','rebooting','executing','issued')").fetchone():
                    raise RuntimeError('Another power or host action is pending')
            target = {'shutdown': 'shut down the Jetson', 'reboot': 'reboot the Jetson',
                      'restart_service': f'restart {service}'}[action]
            message = f'You requested that I {target}. Please say confirm or cancel.'
            cursor = db.execute('INSERT INTO host_actions(boot,action,service,state,message,created) '
                                "VALUES(?,?,?,'awaiting_confirmation',?,?)",
                                (store.boot_id, action, service, message, time.time()))
        return {'id': cursor.lastrowid, 'kind': 'host', 'message': message}

    def cancel(self, identifier):
        if type(identifier) is not int or identifier < 1:
            raise ValueError('Invalid host action identifier')
        with self.store.lock, self.store.connect() as db:
            db.execute("UPDATE host_actions SET state='cancelled',message='Host action cancelled; "
                       "nothing changed.' WHERE id=? AND state='awaiting_confirmation'", (identifier,))
        return {'ok': True}

    def confirm(self, identifier):
        pending = self.pending()
        if type(identifier) is not int or not pending or pending['id'] != identifier:
            raise RuntimeError('Host confirmation is expired, cancelled, or unavailable; nothing changed')
        store = self.store
        with store.lock, store.connect() as db:
            row = db.execute("SELECT * FROM host_actions WHERE id=? AND state='awaiting_confirmation'",
                             (identifier,)).fetchone()
            if not row or not store.audio_ready:
                raise RuntimeError('Host confirmation unavailable; nothing changed')
            db.execute("UPDATE host_actions SET state='pending',message='Host action confirmed; "
                       "completion is not yet verified.' WHERE id=?", (identifier,))
        threading.Thread(target=self.apply, args=(identifier, row['action'], row['service']), daemon=True).start()
        return {'id': identifier, 'message': 'Host action queued; completion is not yet verified.'}

    def apply(self, identifier, action, service):
        # Defense in depth: never accept a shell or arbitrary service here.
        if action not in ('shutdown', 'reboot', 'restart_service') or (
                action == 'restart_service' and service not in SERVICES.values()):
            raise ValueError('Unsupported host action')
        time.sleep(5)
        store = self.store
        with store.lock, store.connect() as db:
            row = db.execute("SELECT state,boot,action,service FROM host_actions WHERE id=?", (identifier,)).fetchone()
            if (not row or row['state'] != 'pending' or row['boot'] != store.boot_id or
                    row['action'] != action or row['service'] != service):
                return
            db.execute("UPDATE host_actions SET state='executing' WHERE id=?", (identifier,))
        try:
            args = (['systemctl', '--user', 'restart', service] if action == 'restart_service' else
                    ['sudo', '-n', '/usr/sbin/shutdown', '-r' if action == 'reboot' else '-h', 'now'])
            result = store.runner(args)
            if result.returncode:
                raise RuntimeError('Host action command failed; completion is unverified')
            state, message = 'issued', 'Host command issued; completion is not yet verified.'
            if action == 'restart_service':
                active = store.runner(['systemctl', '--user', 'is-active', service])
                if active.returncode or active.stdout.strip() != 'active':
                    raise RuntimeError('Service restart returned, but active state was not verified')
                state, message = 'verified', f'{service} restarted and is active.'
            with store.lock, store.connect() as db:
                db.execute('UPDATE host_actions SET state=?,message=? WHERE id=?',
                           (state, message, identifier))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            with store.lock, store.connect() as db:
                db.execute("UPDATE host_actions SET state='failed',message=? WHERE id=?",
                           (str(exc), identifier))
