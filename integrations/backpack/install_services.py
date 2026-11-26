#!/usr/bin/env python3
"""Install native user services; keep development state and databases in place."""
import json
import argparse
from pathlib import Path
import subprocess


def quoted(path):
    return json.dumps(str(path).replace('%', '%%'))


def install(root):
    units = Path.home() / '.config/systemd/user'
    units.mkdir(parents=True, exist_ok=True)
    services = {
        'backpack-mqtt-dev': (
            '', f'/usr/sbin/mosquitto -c {quoted(root / "backpack/mosquitto-dev.conf")}'),
        'backpack-power-sim-dev': (
            'Requires=backpack-mqtt-dev.service\nAfter=backpack-mqtt-dev.service\n',
            f'/usr/bin/python3 -u {quoted(root / "backpack/simulate_power.py")} '
            '--scenario normal --count 86400 --interval 1 --port 18884 --publish'),
        'backpack-runtime': (
            'Wants=pipewire-pulse.service wireplumber.service\n'
            'After=pipewire-pulse.service wireplumber.service\n',
            f'/usr/bin/python3 -u {quoted(root / "backpack/runtime.py")} --root {quoted(root)}'),
        'backpack-dawn-dev': (
            'Requires=backpack-runtime.service backpack-mqtt-dev.service\n'
            'Wants=backpack-power-sim-dev.service\n'
            'After=backpack-runtime.service backpack-mqtt-dev.service\n',
            f'/bin/bash {quoted(root / "backpack/run_dev.sh")} {quoted(root)}'),
    }
    if (root / 'deps/yolo/yolo26n.engine').is_file():
        services['backpack-yolo'] = (
            '', f'/usr/bin/python3 -u {quoted(root / "backpack/yolo_service.py")} '
            f'--root {quoted(root)}')
    bridge_python = root / 'deps/meshtastic-cli/bin/python'
    if bridge_python.is_file():
        services['backpack-meshtastic-events'] = (
            'Requires=backpack-runtime.service\nAfter=backpack-runtime.service\n',
            f'{quoted(bridge_python)} -u {quoted(root / "backpack/meshtastic_bridge.py")} '
            f'--root {quoted(root)}')
    for name, (dependencies, command) in services.items():
        unit = ('[Unit]\nDescription=Jetson backpack ' + name + '\n' + dependencies +
                '\n[Service]\nType=simple\nUMask=0077\nRestart=always\nRestartSec=5\n'
                'TimeoutStopSec=40\nExecStart=' + command + '\n')
        if name == 'backpack-dawn-dev':
            unit = unit.replace('Type=simple', 'Type=notify\nNotifyAccess=main\nWatchdogSec=300\n'
                                'WatchdogSignal=SIGTERM\nTimeoutStartSec=600')
            unit += (f'StandardOutput=append:{root}/run/dawn.log\n'
                     f'StandardError=append:{root}/run/dawn.log\n')
        elif name == 'backpack-yolo':
            unit += (f'StandardOutput=append:{root}/run/yolo.log\n'
                     f'StandardError=append:{root}/run/yolo.log\n')
        unit += '\n[Install]\nWantedBy=default.target\n'
        (units / (name + '.service')).write_text(unit)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now',
                    *[name + '.service' for name in services if name != 'backpack-yolo']], check=True)
    if 'backpack-yolo' in services:
        # Install the model service, but leave residency under recon session control.
        # Disabling boot startup does not interrupt a currently running session.
        subprocess.run(['systemctl', '--user', 'disable', 'backpack-yolo.service'], check=True)
    if (units / 'goggle-yolo.service').is_file():
        subprocess.run(['systemctl', '--user', 'disable', 'goggle-yolo.service'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home() / 'jetson-backpack-dev')
    install(parser.parse_args().root.resolve())
