#!/bin/bash
# Build the NX development checkout with private speech libraries and CUDA Whisper.
set -euo pipefail
dev_root="${1:-$HOME/jetson-backpack-dev}"
ort="$dev_root/deps/onnxruntime-linux-aarch64-1.19.2"
phon="$dev_root/deps/piper_phonemize"
phon_build="$dev_root/deps/piper-build"
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="$ort/lib:$phon_build:$phon/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
test -x /usr/local/cuda/bin/nvcc
test -f "$phon_build/libpiper_phonemize.so"
cmake -S "$dev_root/dawn" -B "$dev_root/dawn/build-backpack" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DENABLE_WEBUI=ON -DENABLE_TUI=OFF -DENABLE_AEC=OFF \
  -DENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=87 -DCUDAToolkit_ROOT=/usr/local/cuda \
  -DCMAKE_PREFIX_PATH="$ort;$phon" \
  -DCMAKE_LIBRARY_PATH="$ort/lib;$phon_build;$phon/lib" \
  -DCMAKE_INCLUDE_PATH="$ort/include;$phon/include" \
  -DONNXRUNTIME_LIBRARY="$ort/lib/libonnxruntime.so" \
  -DONNXRUNTIME_INCLUDE_DIR="$ort/include" \
  -DPIPER_PHONEMIZE_LIBRARY="$phon_build/libpiper_phonemize.so" \
  -DPIPER_PHONEMIZE_INCLUDE_DIR="$phon/include" \
  -DESPEAK_NG_LIBRARY="$phon/lib/libespeak-ng.so" \
  -DCMAKE_CXX_FLAGS="-I$ort/include -I$phon/include" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$ort/lib -L$phon_build -L$phon/lib" \
  -DCMAKE_BUILD_RPATH="$ort/lib;$phon_build;$phon/lib" \
  -DDAWN_ENABLE_EMAIL_TOOL=ON -DDAWN_ENABLE_DOCUMENT_SEARCH_TOOL=OFF \
  -DDAWN_ENABLE_CODE_PROJECTS=OFF -DDAWN_ENABLE_MCP_BRIDGE_TOOL=OFF \
  -DDAWN_ENABLE_MP3=OFF -DDAWN_ENABLE_OGG=OFF
cmake --build "$dev_root/dawn/build-backpack" --target dawn dawn-admin -j "$(nproc)"
