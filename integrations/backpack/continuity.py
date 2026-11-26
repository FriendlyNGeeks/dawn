"""Durable event history and mode-aware continuity; no model or shell execution."""
import json
import math
import re
import sqlite3
import time
import uuid

import service_logs

DAY = 86400
RETENTION = {'communication': 90, 'activity': 14, 'fault': 90}
SERVICES = {
    'meshtastic': ('Meshtastic', 'meshtasticd.service', 'system'),
    # No scanner is installed by this project. Configure the existing adapter, not a guessed command.
    'sdr': ('SDR', None, 'user'),
}
MAX_EVENT_BYTES = 128 * 1024 * 1024
MAX_EVENTS = 100000
MAX_PAYLOAD_BYTES = 16384


def number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'Invalid {name}')
    return float(value)


def bounded(value, name, limit=128):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError(f'Invalid {name}')
    return value


class Continuity:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        self.next_cleanup = 0
        self.next_attempt = {}
        self.control_errors = set()
        self.starting = clock()
        self.ready_since = {}
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS event_schema(version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO event_schema VALUES(1);
                CREATE TABLE IF NOT EXISTS events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE, schema_version INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL, type TEXT NOT NULL, category TEXT NOT NULL,
                    observed_at REAL NOT NULL, recorded_at REAL NOT NULL,
                    severity TEXT NOT NULL, data TEXT NOT NULL, external_id TEXT,
                    pinned INTEGER NOT NULL DEFAULT 0, announced INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS events_dedupe
                    ON events(source, external_id) WHERE external_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS events_time ON events(observed_at, sequence);
                CREATE INDEX IF NOT EXISTS events_source_time ON events(source, observed_at);
                CREATE TABLE IF NOT EXISTS event_usage(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    rows INTEGER NOT NULL, bytes INTEGER NOT NULL);
                INSERT OR IGNORE INTO event_usage
                    SELECT 1,COUNT(*),COALESCE(SUM(length(CAST(data AS BLOB))),0) FROM events;
                CREATE TRIGGER IF NOT EXISTS events_usage_insert AFTER INSERT ON events BEGIN
                    UPDATE event_usage SET rows=rows+1,
                        bytes=bytes+length(CAST(NEW.data AS BLOB)) WHERE singleton=1;
                END;
                CREATE TRIGGER IF NOT EXISTS events_usage_delete AFTER DELETE ON events BEGIN
                    UPDATE event_usage SET rows=rows-1,
                        bytes=bytes-length(CAST(OLD.data AS BLOB)) WHERE singleton=1;
                END;
                CREATE TABLE IF NOT EXISTS runtime_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS service_preferences(
                    name TEXT PRIMARY KEY, autostart INTEGER NOT NULL DEFAULT 0,
                    session_boot TEXT, session_enabled INTEGER, managed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS service_health(
                    name TEXT PRIMARY KEY, ready INTEGER NOT NULL, detail TEXT NOT NULL,
                    checked_at REAL NOT NULL, boot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runtime_notices(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
                    message TEXT NOT NULL, boot TEXT NOT NULL,
                    delivered INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS service_transitions(
                    name TEXT PRIMARY KEY, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS action_event_receipts(
                    source TEXT NOT NULL, action_id INTEGER NOT NULL, state TEXT NOT NULL,
                    PRIMARY KEY(source, action_id, state));
            """)
            for key, value in [('mode', 'normal'), ('retention', RETENTION),
                               ('summary_minutes', 0), ('summary_cursor', 0),
                               ('history_floor', clock()), ('storage_pressure', False)]:
                db.execute('INSERT OR IGNORE INTO runtime_settings VALUES(?,?)',
                           (key, json.dumps(value)))
            for name in SERVICES:
                db.execute('INSERT OR IGNORE INTO service_preferences(name) VALUES(?)', (name,))
            db.execute('UPDATE runtime_notices SET delivered=1 WHERE boot!=?', (store.boot_id,))

    def get(self, key):
        with self.store.connect() as db:
            row = db.execute('SELECT value FROM runtime_settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key, value):
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO runtime_settings VALUES(?,?)', (key, json.dumps(value)))

    def publish(self, event):
        if not isinstance(event, dict):
            raise ValueError('Expected event object')
        source = bounded(event.get('source'), 'source', 64)
        kind = bounded(event.get('type'), 'event type', 96)
        if not re.fullmatch(r'[a-z0-9_.-]+', source + kind):
            raise ValueError('Use lowercase identifiers for source and type')
        category = event.get('category', 'activity')
        severity = event.get('severity', 'info')
        if category not in RETENTION or severity not in ('info', 'warning', 'critical'):
            raise ValueError('Invalid category or severity')
        data = event.get('data', {})
        if not isinstance(data, dict):
            raise ValueError('Expected structured event data')
        encoded = json.dumps(data, allow_nan=False, ensure_ascii=False)
        if len(encoded.encode('utf-8')) > MAX_PAYLOAD_BYTES:
            raise ValueError('Event payload too large; store recordings in files')
        now = self.clock()
        observed = number(event.get('observed_at', now), 'observed_at')
        if observed < 0 or observed > now + 300:
            raise ValueError('Event observation time is out of range')
        external = event.get('external_id')
        if external is not None:
            bounded(external, 'external_id', 192)
        with self.store.lock, self.store.connect() as db:
            if external is not None:
                old = db.execute('SELECT id FROM events WHERE source=? AND external_id=?',
                                 (source, external)).fetchone()
                if old:
                    return {'id': old[0], 'duplicate': True}
            # Bound ingestion even if all retained events are pinned.
            count, size = db.execute('SELECT rows,bytes FROM event_usage WHERE singleton=1').fetchone()
            if count >= MAX_EVENTS or size + len(encoded.encode('utf-8')) > MAX_EVENT_BYTES:
                raise RuntimeError('Event history capacity reached; save or expire records before ingestion')
            identifier = str(uuid.uuid4())
            db.execute('INSERT INTO events(id,source,type,category,observed_at,recorded_at,'
                       'severity,data,external_id) VALUES(?,?,?,?,?,?,?,?,?)',
                       (identifier, source, kind, category, observed, now, severity, encoded, external))
        return {'id': identifier, 'duplicate': False}

    def query(self, since, until=None, source=None, category=None, after=0, limit=20):
        since = number(since, 'since')
        until = self.clock() if until is None else number(until, 'until')
        if since < 0 or until < since:
            raise ValueError('Invalid event time range')
        if type(limit) is not int or not 1 <= limit <= 100 or type(after) is not int or after < 0:
            raise ValueError('Invalid event page')
        conditions = ['observed_at>=?', 'observed_at<=?', 'sequence>?']
        args = [since, until, after]
        for key, value in [('source', source), ('category', category)]:
            if value is not None:
                bounded(value, key)
                conditions.append(f'{key}=?')
                args.append(value)
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM events WHERE ' + ' AND '.join(conditions) +
                              ' ORDER BY sequence LIMIT ?', (*args, limit + 1)).fetchall()
        result = []
        for row in rows[:limit]:
            item = dict(row)
            item['data'] = json.loads(item['data'])
            result.append(item)
        return {'events': result, 'more': len(rows) > limit,
                'next_after': result[-1]['sequence'] if result else after,
                'history_available_since': self.get('history_floor'),
                'storage_pressure': self.get('storage_pressure')}

    def audit(self, event):
        """History backpressure must not prevent mode changes or service recovery."""
        try:
            self.publish(event)
            return True
        except (RuntimeError, OSError, sqlite3.Error):
            try:
                self.set('storage_pressure', True)
                self.set('history_floor', self.clock())
                service_logs.append(self.store.path.parent, 'runtime', 'event_write_failed',
                                    'A control-plane event could not be recorded')
            except (OSError, sqlite3.Error):
                pass
            return False

    def cleanup(self):
        now, removed = self.clock(), 0
        policies = self.get('retention')
        with self.store.lock, self.store.connect() as db:
            for category, days in policies.items():
                cursor = db.execute('DELETE FROM events WHERE sequence IN '
                                    '(SELECT sequence FROM events WHERE pinned=0 AND category=? '
                                    'AND recorded_at<? ORDER BY sequence LIMIT 500)',
                                    (category, now - days * DAY))
                removed += cursor.rowcount
            count, size = db.execute('SELECT rows,bytes FROM event_usage WHERE singleton=1').fetchone()
            pressure = count >= MAX_EVENTS * .9 or size >= MAX_EVENT_BYTES * .9
            if pressure:
                removed += db.execute('DELETE FROM events WHERE sequence IN '
                                      '(SELECT sequence FROM events WHERE pinned=0 '
                                      'ORDER BY sequence LIMIT 500)').rowcount
            # These are delivery records, not historical events.
            db.execute('DELETE FROM runtime_notices WHERE delivered=1 AND created<?', (now - 7 * DAY,))
        if removed:
            # Conservative: disclose possible gaps rather than claiming complete history.
            self.set('history_floor', now)
        self.set('storage_pressure', pressure)
        return {'removed': removed, 'storage_pressure': pressure}

    def queue(self, kind, message):
        with self.store.connect() as db:
            # Coalesce undelivered updates by kind. New state supersedes a stale summary.
            db.execute('UPDATE runtime_notices SET delivered=1 WHERE kind=? AND delivered=0', (kind,))
            db.execute('INSERT INTO runtime_notices(kind,message,boot,created) VALUES(?,?,?,?)',
                       (kind, message[:4000], self.store.boot_id, self.clock()))

    def health(self, name, ready, detail):
        if name not in SERVICES or type(ready) is not bool:
            raise ValueError('Unknown service or invalid readiness')
        detail = bounded(detail, 'health detail', 200)
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO service_health VALUES(?,?,?,?,?)',
                       (name, int(ready), detail, self.clock(), self.store.boot_id))
        return {'ok': True}

    def desired(self, name, enabled, persistent=False):
        if name not in SERVICES or type(enabled) is not bool or type(persistent) is not bool:
            raise ValueError('Invalid service preference')
        with self.store.connect() as db:
            if persistent:
                db.execute('UPDATE service_preferences SET autostart=? WHERE name=?',
                           (int(enabled), name))
            db.execute('UPDATE service_preferences SET session_boot=?,session_enabled=?,managed=1 WHERE name=?',
                       (self.store.boot_id, int(enabled), name))
        self.next_attempt.pop(name, None)
        self.audit({'source': name, 'type': 'service.requested',
                      'data': {'enabled': enabled, 'persistent': persistent}})
        return {'message': f"{SERVICES[name][0]} {'enabled' if enabled else 'disabled'} "
                           f"{'for future boots and this session' if persistent else 'for this session'}. "
                           + ('No scanner is configured.' if SERVICES[name][1] is None else
                              'Readiness is not yet verified.')}

    def services(self):
        now = self.clock()
        with self.store.connect() as db:
            preferences = db.execute('SELECT * FROM service_preferences ORDER BY name').fetchall()
            health = {r['name']: dict(r) for r in db.execute('SELECT * FROM service_health')}
        output = []
        for pref in preferences:
            name = pref['name']
            enabled = (pref['session_enabled'] if pref['session_boot'] == self.store.boot_id
                       else pref['autostart'])
            h = health.get(name, {})
            fresh = h.get('boot') == self.store.boot_id and 0 <= now - h.get('checked_at', 0) <= 30
            ready = bool(fresh and h.get('ready'))
            output.append({'name': name, 'enabled': bool(enabled), 'autostart': bool(pref['autostart']),
                           'ready': ready, 'managed': bool(pref['managed']), 'detail': h.get('detail') if fresh else 'No fresh readiness report',
                           'has_health': bool(h),
                           'configured': SERVICES[name][1] is not None})
        return output

    def reconcile_services(self):
        for service in self.services():
            name, enabled = service['name'], service['enabled']
            label, unit, scope = SERVICES[name]
            state = 'ready' if service['ready'] else (
                'waiting' if enabled or (not service['managed'] and service['has_health']) else
                'disabled' if service['managed'] else 'unobserved')
            if service['ready']:
                self.control_errors.discard(name)
            with self.store.connect() as db:
                old = db.execute('SELECT state FROM service_transitions WHERE name=?', (name,)).fetchone()
                db.execute('INSERT OR REPLACE INTO service_transitions VALUES(?,?)', (name, state))
            if not old or old[0] != state:
                service_logs.append(self.store.path.parent, name, state, service['detail'])
            if old and old[0] != state:
                intentional = service['managed'] and not enabled
                self.audit({'source': name, 'type': 'service.' + state,
                              'category': 'fault' if state == 'waiting' else 'activity',
                              'severity': 'warning' if state == 'waiting' else 'info',
                              'data': {'summary': f'{label}: {state}.',
                                       'intentional': intentional}})
                if not intentional:
                    self.queue('service.' + name, f'{label}: {state}.')
            if (not service['managed'] or unit is None or (enabled and service['ready'])
                    or self.clock() < self.next_attempt.get(name, 0)):
                continue
            self.next_attempt[name] = self.clock() + 60
            command = ['systemctl', '--user'] if scope == 'user' else ['sudo', '-n', 'systemctl']
            # No privilege grants are installed. Existing authorization is required.
            result = self.store.runner([*command, '--no-block', 'start' if enabled else 'stop', unit])
            if result.returncode:
                self.health(name, False, 'Service control unavailable; check authorization and service logs')
                if name not in self.control_errors:
                    self.queue('service.' + name, f'{label} could not be controlled. Check service authorization and logs.')
                    service_logs.append(self.store.path.parent, name, 'control_failed',
                                        'Fixed service control command failed')
                self.control_errors.add(name)
            else:
                self.control_errors.discard(name)

    def record_operation(self, request, result):
        operation = request.get('operation')
        if operation not in ('camera_describe', 'drone_start', 'drone_stop', 'drone_describe'):
            return
        failed = 'error' in result
        data = {'summary': operation.replace('_', ' ') + (' failed' if failed else ' completed')}
        if not failed:
            data.update({key: result[key] for key in ('source', 'fresh', 'frame_id', 'decoded_at')
                         if key in result})
        self.publish({'source': 'camera' if operation.startswith('camera') else 'astra',
                      'type': operation.replace('_', '.') + ('.failed' if failed else '.completed'),
                      'category': 'fault' if failed else 'activity',
                      'severity': 'warning' if failed else 'info', 'data': data})

    def record_actions(self):
        with self.store.connect() as db:
            rows = [dict(row, source='power') for row in db.execute(
                "SELECT id,state,message FROM actions a WHERE state IN ('verified','failed') "
                "AND NOT EXISTS(SELECT 1 FROM action_event_receipts r WHERE r.source='power' "
                'AND r.action_id=a.id AND r.state=a.state)')]
            rows += [dict(row, source='host') for row in db.execute(
                "SELECT id,state,message FROM host_actions a WHERE state IN ('verified','failed','unverified') "
                "AND NOT EXISTS(SELECT 1 FROM action_event_receipts r WHERE r.source='host' "
                'AND r.action_id=a.id AND r.state=a.state)')]
        for row in rows:
            self.publish({'source': row['source'], 'type': 'action.' + row['state'],
                          'external_id': f"action:{row['id']}:{row['state']}",
                          'category': 'fault' if row['state'] != 'verified' else 'activity',
                          'severity': 'warning' if row['state'] != 'verified' else 'info',
                          'data': {'summary': row['message']}})
            with self.store.connect() as db:
                db.execute('INSERT OR IGNORE INTO action_event_receipts VALUES(?,?,?)',
                           (row['source'], row['id'], row['state']))

    def startup(self):
        """Called once by each DAWN process; state survives runtime and DAWN restarts."""
        previous = self.get('dawn_boot')
        self.set('dawn_boot', self.store.boot_id)
        with self.store.connect() as db:
            pending = db.execute("SELECT 1 FROM actions WHERE delivered=0 AND state IN "
                                 "('pending','applying','rebooting','verified','failed') LIMIT 1").fetchone()
            pending_host = db.execute("SELECT 1 FROM host_actions WHERE delivered=0 AND state IN "
                                      "('pending','executing','issued','verified','failed','unverified') "
                                      "LIMIT 1").fetchone()
            db.execute("UPDATE runtime_notices SET delivered=1 WHERE kind='startup' AND delivered=0")
        self.set('startup_due', None)
        # Never replace a verified action notice with a generic introduction.
        if previous != self.store.boot_id and not (pending or pending_host):
            self.set('startup_due', self.clock() + 15)
        return {'skip_greeting': True, 'reason': 'service_restart' if previous == self.store.boot_id
                else 'action_handoff' if pending or pending_host else 'startup'}

    def tick(self):
        now = self.clock()
        if now >= self.next_cleanup:
            self.cleanup()
            self.next_cleanup = now + 60
        self.set('runtime_last_seen', {'boot': self.store.boot_id, 'at': now})
        self.reconcile_services()
        due = self.get('startup_due')
        services = [s for s in self.services() if s['enabled'] or s['has_health']]
        if due is not None and (now >= due or (services and all(s['ready'] for s in services))):
            self.queue('startup', self.startup_message())
            with self.store.connect() as db:
                db.execute("UPDATE runtime_notices SET delivered=1 WHERE kind LIKE 'service.%' "
                           'AND boot=? AND delivered=0', (self.store.boot_id,))
            self.set('startup_due', None)
        minutes = self.get('summary_minutes')
        if minutes:
            last = self.get('summary_at')
            if last is None:
                self.set('summary_at', now)
            elif now - last >= minutes * 60:
                with self.store.connect() as db:
                    cursor = self.get('summary_cursor')
                    row = db.execute('SELECT COUNT(*),COALESCE(MAX(sequence),?) FROM events '
                                     'WHERE sequence>?', (cursor, cursor)).fetchone()
                if row[0]:
                    self.queue('summary', f'{row[0]} new events recorded. Ask me to read messages or summarize activity.')
                self.set('summary_cursor', row[1])
                self.set('summary_at', now)

    def notice(self):
        if self.get('mode') == 'silent' or not self.store.audio_ready:
            return None
        if self.get('startup_due') is not None:
            return None
        with self.store.connect() as db:
            row = db.execute('SELECT id,message,kind FROM runtime_notices WHERE delivered=0 AND boot=? '
                             "ORDER BY CASE WHEN kind='startup' THEN 0 ELSE 1 END,id LIMIT 1",
                             (self.store.boot_id,)).fetchone()
            if row:
                return {'id': row['id'], 'kind': 'runtime',
                        'message': self.startup_message() if row['kind'] == 'startup' else row['message']}
            # Communication announcements are debounced and bounded; structured payload is untrusted content.
            rows = db.execute("SELECT * FROM events WHERE announced=0 AND recorded_at<=? "
                              "AND recorded_at>=? AND (category='communication' OR severity='critical') "
                              "ORDER BY sequence LIMIT 5", (self.clock() - 2, self.clock() - 300)).fetchall()
            if rows:
                text = 'New events. ' + ' '.join(self.describe(dict(r)) for r in rows)
                # The notice acknowledgment carries the batch boundary; do not mark before speech.
                return {'id': rows[-1]['sequence'], 'kind': 'events', 'message': text[:4000]}
        return None

    def startup_message(self):
        services = [s for s in self.services() if s['enabled'] or s['has_health']]
        parts = [f"{SERVICES[s['name']][0]}: " +
                 ('ready' if s['ready'] else 'not configured' if not s['configured']
                  else 'waiting for verified readiness') for s in services]
        return ('Startup status. ' + '; '.join(parts) + '.' if parts else
                'Victor is ready. No peripheral autostart preferences are set.')

    def ack(self, kind, identifier):
        if type(identifier) is not int or identifier < 1:
            raise ValueError('Invalid delivery id')
        with self.store.connect() as db:
            if kind == 'runtime':
                db.execute('UPDATE runtime_notices SET delivered=1 WHERE id=?', (identifier,))
            elif kind == 'events':
                db.execute('UPDATE events SET announced=1 WHERE sequence<=?', (identifier,))
            else:
                raise ValueError('Invalid notice kind')
        return {'ok': True}

    def describe(self, event):
        data = event['data']
        if isinstance(data, str):
            data = json.loads(data)
        stamp = time.strftime('%H:%M UTC', time.gmtime(event['observed_at']))
        # Templates keep radio text out of model instructions and never execute it.
        text = data.get('text') if event['category'] == 'communication' else data.get('summary')
        if not isinstance(text, str):
            text = event['type'].replace('.', ' ')
        text = ''.join(c if c.isprintable() else ' ' for c in text)[:600]
        sender = data.get('sender') if event['category'] == 'communication' else None
        sender = ''.join(c for c in sender if c.isprintable())[:64] if isinstance(sender, str) else ''
        origin = event['source'] + (f', from {sender}' if sender else '')
        return f"{stamp}, {origin}: {text}."

    def report(self, hours, messages):
        result = self.query(max(0, self.clock() - hours * 3600),
                            category='communication' if messages else None, limit=20)
        rows = sorted(result['events'], key=lambda r: (r['observed_at'], r['sequence']))
        text = ' '.join(self.describe(row) for row in rows) or 'No matching events were retained for that period.'
        if result['more']:
            text += ' More events are available; ask for a narrower period or use the paginated history API.'
        if result['history_available_since'] > self.clock() - hours * 3600:
            text += ' History is incomplete for part of that period.'
        if result['storage_pressure']:
            text += ' Storage pressure has shortened available history.'
        # Disclose receiver gaps, including gaps recovered before the query.
        gaps = self.query(max(0, self.clock() - hours * 3600), category='fault', limit=100)
        if any(e['type'] in ('service.waiting', 'receiver.coverage_gap') for e in gaps['events']):
            text += ' A receiver had an availability gap during that period.'
        return text[:15000]

    def resume(self):
        service_logs.append(self.store.path.parent, 'runtime', 'started', 'Event collection resumed')
        last = self.get('runtime_last_seen')
        now = self.clock()
        if last and (last['boot'] != self.store.boot_id or now - last['at'] > 30):
            self.audit({'source': 'runtime', 'type': 'receiver.coverage_gap', 'category': 'fault',
                          'severity': 'warning',
                          'data': {'summary': 'Event collection continuity was interrupted',
                                   'since': last['at'], 'until': now}})
        self.set('runtime_last_seen', {'boot': self.store.boot_id, 'at': now})

    def voice(self, text):
        if not isinstance(text, str) or len(text) > 500:
            return {'handled': False}
        phrase = re.sub(r'[^a-z0-9 ]', '', text.lower()).strip()
        phrase = re.sub(r'\s+', ' ', phrase)
        phrase = re.sub(r'^(?:(?:please|go ahead and) )+', '', phrase)
        phrase = re.sub(r'\bmesh tastic\b', 'meshtastic', phrase)
        phrase = re.sub(r'\brtlsdr\b', 'rtl sdr', phrase)
        if phrase in ('silent mode', 'enable silent mode', 'go silent', 'normal mode',
                      'disable silent mode', 'exit silent mode'):
            silent = phrase in ('silent mode', 'enable silent mode', 'go silent')
            self.set('mode', 'silent' if silent else 'normal')
            self.audit({'source': 'victor', 'type': 'mode.changed',
                          'data': {'mode': 'silent' if silent else 'normal'}})
            return {'handled': True, 'message': 'Silent mode enabled. Collection continues.' if silent
                    else 'Normal reporting enabled.'}
        match = re.fullmatch(r'(always start|start|stop|never start) (meshtastic|sdr|rtl sdr)', phrase)
        if match:
            action, name = match.groups()
            name = 'sdr' if name == 'rtl sdr' else name
            result = self.desired(name, action in ('always start', 'start'),
                                  action in ('always start', 'never start'))
            return dict(result, handled=True)
        match = re.fullmatch(r'(?:read(?: me| me out)?|read out) (?:the |my )?messages'
                             r'(?: from)?(?: the)? last (one|two|three|four|\d+) hours?', phrase)
        activity = re.fullmatch(r'summarize activity(?: from)?(?: the)? last (one|two|three|four|\d+) hours?', phrase)
        if match or activity:
            value = (match or activity)[1]
            hours = {'one': 1, 'two': 2, 'three': 3, 'four': 4}.get(value)
            hours = hours if hours is not None else int(value)
            if not 1 <= hours <= 2160:
                return {'handled': True, 'message': 'Choose a period between one hour and ninety days.'}
            return {'handled': True, 'message': self.report(hours, bool(match))}
        match = re.fullmatch(r'(?:give me )?(?:event |activity )?summaries every (\d+) minutes', phrase)
        if match:
            minutes = int(match[1])
            if not 1 <= minutes <= 1440:
                return {'handled': True, 'message': 'Choose a summary interval from one to 1440 minutes.'}
            self.set('summary_minutes', minutes)
            self.set('summary_at', self.clock())
            return {'handled': True, 'message': f'Event summaries enabled every {minutes} minutes. Silent mode still applies.'}
        if phrase == 'stop periodic summaries':
            self.set('summary_minutes', 0)
            return {'handled': True, 'message': 'Periodic summaries disabled.'}
        if phrase in ('service status', 'peripheral status'):
            return {'handled': True, 'message': '; '.join(
                f"{SERVICES[s['name']][0]}: " + ('ready' if s['ready'] else s['detail'])
                for s in self.services())}
        return {'handled': False}

    def dispatch(self, request):
        op = request['operation']
        if op == 'publish_event':
            return self.publish(request.get('event'))
        if op == 'query_events':
            return self.query(request.get('since'), request.get('until'), request.get('source'),
                              request.get('category'), request.get('after', 0), request.get('limit', 20))
        if op == 'service_health':
            return self.health(request.get('name'), request.get('ready'), request.get('detail'))
        if op == 'service_preference':
            return self.desired(request.get('name'), request.get('enabled'), request.get('persistent', False))
        if op == 'service_status':
            return {'services': self.services(), 'mode': self.get('mode')}
        if op == 'dawn_startup':
            return self.startup()
        if op == 'continuity_voice':
            return self.voice(request.get('text'))
        if op == 'pin_event':
            identifier = bounded(request.get('id'), 'event id')
            pinned = request.get('pinned')
            if type(pinned) is not bool:
                raise ValueError('Invalid pin setting')
            with self.store.connect() as db:
                changed = db.execute('UPDATE events SET pinned=? WHERE id=?', (int(pinned), identifier)).rowcount
            return {'ok': bool(changed)}
        if op == 'set_retention':
            category, days = request.get('category'), request.get('days')
            if category not in RETENTION or type(days) is not int or not 1 <= days <= 3650:
                raise ValueError('Invalid retention policy')
            policy = self.get('retention')
            policy[category] = days
            self.set('retention', policy)
            return {'retention': policy}
        raise ValueError('Unknown continuity operation')


OPERATIONS = frozenset(('publish_event', 'query_events', 'service_health', 'service_preference',
                        'service_status', 'dawn_startup', 'continuity_voice', 'pin_event', 'set_retention'))
