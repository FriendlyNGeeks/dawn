#!/bin/bash
# Prepare pinned, private ARM64 speech dependencies for the development build.
set -euo pipefail
dev_root="${1:-$HOME/jetson-backpack-dev}"
test "$(uname -m)" = aarch64
test -d "$dev_root/dawn"
deps="$dev_root/deps"
mkdir -p "$deps"
if [ ! -d "$deps/piper_phonemize" ]; then
  curl -fL --max-time 180 \
    https://github.com/rhasspy/piper-phonemize/releases/download/2023.11.14-4/piper-phonemize_linux_aarch64.tar.gz \
    -o "$deps/piper-phonemize.tar.gz"
  tar -xzf "$deps/piper-phonemize.tar.gz" -C "$deps"
fi
if [ ! -d "$deps/onnxruntime-linux-aarch64-1.19.2" ]; then
  curl -fL --max-time 180 \
    https://github.com/microsoft/onnxruntime/releases/download/v1.19.2/onnxruntime-linux-aarch64-1.19.2.tgz \
    -o "$deps/onnxruntime.tgz"
  tar -xzf "$deps/onnxruntime.tgz" -C "$deps"
fi
if [ ! -d "$deps/piper-phonemize-src/.git" ]; then
  git clone --depth 1 --branch 2023.11.14-4 \
    https://github.com/rhasspy/piper-phonemize.git "$deps/piper-phonemize-src"
fi
# The upstream bundle also ships ONNX 1.14. Expose ONLY eSpeak in this prefix,
# or its old ONNX headers/libraries shadow the explicit 1.19 dependency.
mkdir -p "$deps/espeak-private/include" "$deps/espeak-private/lib"
for header in espeak espeak-ng; do
  test -e "$deps/espeak-private/include/$header" || \
    ln -s "$deps/piper_phonemize/include/$header" "$deps/espeak-private/include/$header"
done
for library in "$deps/piper_phonemize/lib/"libespeak-ng.so*; do
  test -e "$deps/espeak-private/lib/$(basename "$library")" || \
    ln -s "$library" "$deps/espeak-private/lib/$(basename "$library")"
done
cmake -S "$deps/piper-phonemize-src" -B "$deps/piper-build" -G Ninja \
  -DONNXRUNTIME_DIR="$deps/onnxruntime-linux-aarch64-1.19.2" \
  -DESPEAK_NG_DIR="$deps/espeak-private" -DCMAKE_BUILD_TYPE=Release
cmake --build "$deps/piper-build" --target piper_phonemize -j 2
readelf -d "$deps/piper-build/libpiper_phonemize.so" | grep -F '[libonnxruntime.so.1]'
if [ ! -e /usr/share/espeak-ng-data ]; then
  sudo cp -a "$deps/piper_phonemize/share/espeak-ng-data" /usr/share/espeak-ng-data
fi
mkdir -p "$dev_root/dawn/models/whisper.cpp"
if [ ! -s "$dev_root/dawn/models/whisper.cpp/ggml-base.bin" ]; then
  curl -fL --max-time 180 \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin \
    -o "$dev_root/dawn/models/whisper.cpp/ggml-base.bin"
fi
