#!/usr/bin/env python3
"""Record available-based whole-system memory while optional local work runs."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import threading
import time

from yolo_service import memory_snapshot


def measure(root, label, seconds, combined=False):
    work = []
    def run_work():
        if not combined:
            return
        qwen = subprocess.Popen(
            ['python3', '-B', str(root / 'backpack/camera_look.py'),
             '--state', str(root / 'run'), '--query', 'Describe the scene briefly.'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # Let Qwen finish its ~2.5s Argus capture before the YOLO capture.
            # YOLO then detects while Qwen is still interpreting its own frame.
            time.sleep(3)
            result = subprocess.run(['python3', '-B', str(root / 'backpack/yolo_service.py'),
                                     '--root', str(root), '--request', 'detect'],
                                    capture_output=True, text=True, timeout=35)
            work.append({'kind': 'yolo_camera', 'exit_code': result.returncode,
                         'output': result.stdout[-10000:], 'error': result.stderr[-1000:]})
            output, error = qwen.communicate(timeout=115)
            work.append({'kind': 'qwen_camera', 'exit_code': qwen.returncode,
                         'output': output[-4000:], 'error': error[-1000:]})
        except (OSError, subprocess.TimeoutExpired) as exc:
            work.append({'kind': 'combined', 'error': str(exc), 'exit_code': 1})
        finally:
            if qwen.poll() is None:
                qwen.kill()
                qwen.communicate()
    worker = threading.Thread(target=run_work)
    worker.start()
    started = time.monotonic()
    samples = []
    while time.monotonic() - started < seconds or worker.is_alive():
        samples.append(memory_snapshot())
        time.sleep(.2)
    worker.join()
    used = [s['used_bytes'] for s in samples]
    result = {'label': label, 'epoch': time.time(), 'samples': len(samples),
              'used_min_bytes': min(used), 'used_mean_bytes': round(statistics.mean(used)),
              'used_peak_bytes': max(used),
              'available_min_bytes': min(s['available_bytes'] for s in samples),
              'swap_peak_bytes': max(s['swap_used_bytes'] for s in samples),
              'budget_bytes': 12000000000, 'under_budget': max(used) <= 12000000000,
              'work': work}
    (root / 'run' / f'memory-{label}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home() / 'jetson-backpack-dev')
    parser.add_argument('--label', required=True)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--combined', action='store_true')
    args = parser.parse_args()
    if not args.label.replace('-', '').isalnum() or not 1 <= args.seconds <= 300:
        parser.error('Use a short alphanumeric label and 1 to 300 seconds')
    measure(args.root, args.label, args.seconds, args.combined)
