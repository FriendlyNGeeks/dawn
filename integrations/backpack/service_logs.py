"""Bounded private diagnostic logs; event records live separately in SQLite."""
import json
import os
from pathlib import Path
import shutil
import time

LOG_NAMES = ('dawn.log', 'yolo.log', 'goggles.log', 'services.log')
LIMIT = 10 * 1024 * 1024
BACKUPS = 3
DAYS = 7


def append(root, service, state, detail):
    # Fixed fields only. Never copy raw radio packets, keys, process args or environments.
    path = Path(root) / 'services.log'
    line = json.dumps({'at': time.time(), 'service': service, 'state': state,
                       'detail': detail[:200]}, ensure_ascii=True) + '\n'
    with path.open('a', encoding='utf-8') as stream:
        stream.write(line)
    os.chmod(path, 0o600)


def maintain(root, now=None):
    now = time.time() if now is None else now
    for name in LOG_NAMES:
        path = Path(root) / name
        if path.is_symlink():
            continue
        for index in range(1, BACKUPS + 1):
            backup = Path(str(path) + f'.{index}')
            if backup.is_file() and not backup.is_symlink() and now - backup.stat().st_mtime > DAYS * 86400:
                backup.unlink()
        if not path.is_file() or path.stat().st_size <= LIMIT:
            continue
        # Keep the original inode: systemd and capture services hold append descriptors.
        # copytruncate can lose a diagnostic line during rotation; authoritative events
        # are transactional database rows and do not use this path.
        for index in range(BACKUPS, 1, -1):
            source = Path(str(path) + f'.{index - 1}')
            target = Path(str(path) + f'.{index}')
            if source.is_file() and not source.is_symlink() and not target.is_symlink():
                source.replace(target)
        backup = Path(str(path) + '.1')
        if backup.is_symlink():
            continue
        with path.open('rb') as source, backup.open('wb') as target:
            source.seek(max(0, path.stat().st_size - LIMIT))
            shutil.copyfileobj(source, target, 65536)
        os.chmod(backup, 0o600)
        with path.open('r+b') as stream:
            stream.truncate(0)
