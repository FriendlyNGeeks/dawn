"""Actual host observations and an OS-confined, bounded diagnostic shell."""
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid


def host_snapshot(proc=Path('/proc'), sys=Path('/sys'), disk=Path('/')):
    memory = {}
    for line in (proc / 'meminfo').read_text().splitlines():
        name, value = line.split(':', 1)
        memory[name] = int(value.split()[0]) * 1024
    total, available = memory['MemTotal'], memory['MemAvailable']
    if total <= 0 or not 0 <= available <= total:
        raise RuntimeError('Invalid host memory observation')
    def cpu_sample():
        values = list(map(int, (proc / 'stat').read_text().splitlines()[0].split()[1:9]))
        return sum(values), values[3] + (values[4] if len(values) > 4 else 0)
    before = cpu_sample()
    time.sleep(.1)
    after = cpu_sample()
    elapsed, idle = after[0] - before[0], after[1] - before[1]
    usage = shutil.disk_usage(disk)
    temperatures = []
    for zone in sorted((sys / 'class/thermal').glob('thermal_zone*')):
        try:
            value = int((zone / 'temp').read_text()) / 1000
            if -50 <= value <= 150:
                temperatures.append({'sensor': (zone / 'type').read_text().strip(), 'celsius': value})
        except (OSError, ValueError):
            continue
    processes = []
    for item in proc.iterdir():
        if not item.name.isdigit():
            continue
        try:
            rss = next((int(line.split()[1]) * 1024
                        for line in (item / 'status').read_text().splitlines()
                        if line.startswith('VmRSS:')), 0)
            # Never expose command-line arguments or process environments.
            processes.append({'pid': int(item.name), 'name': (item / 'comm').read_text().strip()[:64],
                              'rss_bytes': rss})
        except (OSError, ValueError):
            continue
    return {'source': 'live Linux kernel', 'simulated': False,
            'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'uptime_seconds': float((proc / 'uptime').read_text().split()[0]),
            'memory': {'total_bytes': total, 'used_bytes': total - available,
                       'available_bytes': available, 'used_percent': round(100 * (total - available) / total, 1),
                       'swap_used_bytes': memory['SwapTotal'] - memory['SwapFree']},
            'cpu_used_percent': round(max(0., min(100., 100 * (1 - idle / elapsed))), 1) if elapsed > 0 else None,
            'load_average': list(map(float, (proc / 'loadavg').read_text().split()[:3])),
            'disk': {'total_bytes': usage.total, 'used_bytes': usage.used, 'free_bytes': usage.free,
                     'used_percent': round(100 * usage.used / usage.total, 1)},
            'temperatures': temperatures,
            'top_processes': sorted(processes, key=lambda p: p['rss_bytes'], reverse=True)[:8]}


class DiagnosticShell:
    """Immutable launch properties, not an LLM command-safety classifier."""
    def __init__(self, runner=subprocess.run):
        self.runner = runner
        self.lock = threading.Lock()

    @staticmethod
    def launch(command):
        if not isinstance(command, str) or not command.strip() or len(command) > 2048 or '\0' in command:
            raise ValueError('Use a nonempty diagnostic command of at most 2048 characters')
        properties = [
            'DynamicUser=yes', 'ProtectSystem=strict', 'ProtectHome=yes', 'PrivateTmp=no',
            'PrivateNetwork=yes', 'PrivateDevices=yes', 'NoNewPrivileges=yes',
            'CapabilityBoundingSet=', 'AmbientCapabilities=', 'ProtectProc=invisible',
            'ProtectKernelTunables=yes', 'ProtectKernelModules=yes', 'ProtectKernelLogs=yes',
            'ProtectControlGroups=yes', 'RestrictSUIDSGID=yes', 'RestrictNamespaces=yes',
            'RestrictRealtime=yes', 'LockPersonality=yes', 'RestrictAddressFamilies=AF_UNIX',
            'InaccessiblePaths=/var /opt /mnt /media /srv /boot',
            'TemporaryFileSystem=/run:ro /etc:ro /tmp:rw,size=16M,mode=1777', 'WorkingDirectory=/tmp',
            'BindReadOnlyPaths=-/etc/alternatives -/etc/os-release',
            'RuntimeMaxSec=8', 'TimeoutStopSec=1', 'KillMode=control-group',
            'MemoryMax=128M', 'MemorySwapMax=0', 'TasksMax=16', 'CPUQuota=25%',
            'LimitFSIZE=65536', 'LimitNOFILE=64', 'UMask=0077',
            'Environment=PATH=/usr/bin:/bin HOME=/tmp LC_ALL=C']
        args = ['sudo', '-n', '/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect',
                '--service-type=exec', '--expand-environment=no',
                '--unit=victor-diagnostic-' + uuid.uuid4().hex]
        for prop in properties:
            args += ['--property', prop]
        # The model controls only bash's final argument, never launcher options.
        return args + ['--', '/bin/bash', '--noprofile', '--norc', '-c', command]

    def execute(self, command):
        args = self.launch(command)
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Another diagnostic command is still running')
        started = time.monotonic()
        try:
            with tempfile.TemporaryFile() as output:
                timed_out = False
                try:
                    result = self.runner(args, stdin=subprocess.DEVNULL, stdout=output,
                                         stderr=subprocess.STDOUT, timeout=12, check=False)
                    code = result.returncode
                except subprocess.TimeoutExpired:
                    timed_out, code = True, None
                output.seek(0)
                raw = output.read(8193)
            text = raw[:8192].decode('utf-8', errors='replace')
            text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
            text = ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)
            return {'source': 'OS-confined diagnostic CLI', 'command': command,
                    'exit_code': code, 'timed_out': timed_out,
                    'seconds': round(time.monotonic() - started, 3),
                    'output': text, 'truncated': len(raw) > 8192,
                    'limitations': 'Read-only host; private temporary files; no home, host processes, '
                                   'network, system bus, sudo, or host control. Use host_status for '
                                   'actual top processes and host_control for confirmed actions.'}
        finally:
            self.lock.release()
