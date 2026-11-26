#!/bin/bash
# Install/start the reboot-safe native development services idempotently.
set -euo pipefail
dev_root="${1:-$HOME/jetson-backpack-dev}"
exec python3 "$dev_root/backpack/install_services.py" --root "$dev_root"
