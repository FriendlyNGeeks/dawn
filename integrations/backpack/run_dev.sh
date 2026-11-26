#!/bin/bash
# Foreground DAWN entry point, normally supervised by a user development unit.
set -euo pipefail
dev_root="${1:-$HOME/jetson-backpack-dev}"
ort="$dev_root/deps/onnxruntime-linux-aarch64-1.19.2"
phon="$dev_root/deps/piper_phonemize"
export LD_LIBRARY_PATH="$ort/lib:$dev_root/deps/piper-build:$phon/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ESPEAK_DATA_PATH="$phon/share/espeak-ng-data"
# Runtime maintains stable virtual devices and links a headset when available.
export DAWN_BACKPACK_SOCKET="$dev_root/run/runtime.sock"
for attempt in {1..30}; do
  if pactl list short sources | awk '$2 == "backpack_capture.monitor" {found=1} END {exit !found}'; then
    break
  fi
  sleep 1
done
export DAWN_AUDIO_CAPTURE_DEVICE="backpack_capture.monitor"
export DAWN_AUDIO_PLAYBACK_DEVICE="backpack_playback"
mkdir -p "$dev_root/run/data"
chmod 700 "$dev_root/run" "$dev_root/run/data"
cd "$dev_root/dawn"
# First-run web account setup prints an enrollment token to stderr. Do not log it.
exec ./build-backpack/dawn --config "$dev_root/backpack/dawn-dev.toml" \
  2> >(sed -u '/Token:/d' >&2)
