# Resident YOLO on the NX

YOLO26 nano runs on the Orin NX GPU using a native TensorRT FP32 engine. The `backpack-yolo` user service keeps the model, execution context, buffers, and three warmup passes resident. Whisper base and Piper remain loaded in DAWN; Qwen remains resident in Ollama. As of November 14, the optional headless Goggles 3 service continuously submits drone frames; Victor can start the feed and describe a fresh stream frame with Qwen. The original on-demand CSI detector remains available.

## Headless drone input

The viewer's `--yolo --yolo-fps 15` path bypasses Avalonia initialization and requires no Xvfb or preview. It auto-connects to the verified DJI USB adapter, decodes H.264 once, scales to 640 × 360 BGR, and paces submissions by wall clock. One pending frame is retained, with newer frames replacing older ones. Five seconds without video restarts the session, with a two-second retry delay. The existing DJI NetworkManager profile supplies the USB address; headless mode never opens a polkit dialog.

`detect_frame` extends the owner-only, peer-UID-checked `run/yolo.sock` protocol with a JSON header followed by exactly 691,200 BGR bytes. It validates source `goggles3`, dimensions, format, length, frame ID, and a decode timestamp at most two seconds old. Truncated payloads fail. Inference stays on the single CUDA-owning worker.

`--yolo-output /absolute/path` atomically writes the latest JSON result and a timestamped `.metrics` sidecar every five seconds. Consumers must check source, freshness, and timestamp age; an old `fresh:true` file is not proof of current video. The service also writes metrics to `run/goggles.log`. A private atomic JPEG-plus-metadata snapshot, refreshed at most twice per second, supplies explicit DAWN scene requests. No client-supplied image path is accepted.

Short live measurements on November 14: approximately 30 decoded FPS, 15 submitted FPS, and 12–13 completed inferences per second. Fifteen is the submission target, not a guaranteed inference rate. Sustained performance, temperature and memory limits remain to measure.

See [Goggles setup and PiP behavior](../../../learning/goggles-3-jetson-liveview.md) and [the voice workflow](RUNTIME.md#drone-feed).

## Operation

```sh
python3 -B ~/jetson-backpack-dev/backpack/yolo_service.py --request status
python3 -B ~/jetson-backpack-dev/backpack/yolo_service.py --request detect
python3 -B ~/jetson-backpack-dev/backpack/yolo_service.py --request self_test
systemctl --user status backpack-yolo
systemctl --user stop backpack-yolo
```

`detect` captures a new 640 × 360 Argus frame, applies the verified `flip-method=2` mounting correction, letterboxes to 640 × 640, and returns COCO-class detections with confidence and pixel coordinates. No input path, shell command, or external network request is accepted. Requests use the owner-only `run/yolo.sock` socket, verified peer UID, bounded JSON, and a single CUDA-owning worker. Empty detections are a valid result. The model only detects its 80 trained COCO categories; it is not a general scene interpreter or a validated drone-landing detector. The transient YOLO camera frames are removed afterward. Concurrent camera clients can contend for Argus; a capture failure returns an error rather than reusing an image.

`self_test` uses Ultralytics' fixed bus sample stored privately with the model. It successfully returned a bus and four people in validation. A live desk capture worked but returned no objects above the 0.35 confidence threshold.

YOLO and headless capture are now started on demand by **“Victor, initiate ASTRA”** and stopped by **“Victor, terminate ASTRA.”** The native installer includes YOLO when `deps/yolo/yolo26n.engine` exists, disables its boot startup, and preserves any currently running session. It also disables boot startup of the separately installed `goggle-yolo` unit. Termination unloads the runtime model without deleting engine/weight files. Manual CSI detection requires starting `backpack-yolo` first. DAWN and Qwen stay resident after recon shutdown. See [the recon workflow](RUNTIME.md#drone-feed).

## Reproduce installation

The NX has distro NumPy 1.26.4, OpenCV 4.6.0 and TensorRT 10.16.2.10 built for CUDA 13.2. Installation added 15 packages, approximately 3.35 GB of disk files, and upgraded/removed none. PyTorch and Ultralytics are not installed on the NX. Export uses an isolated development-PC environment and the pinned [export requirements](requirements-yolo-export.txt), with the PC's CPU Torch installation usable through a system-site-packages venv:

```powershell
python -m venv --system-site-packages "$env:TEMP/jetson-yolo-export"
& "$env:TEMP/jetson-yolo-export/Scripts/python.exe" -m pip install -r software/jetson/backpack/requirements-yolo-export.txt
& "$env:TEMP/jetson-yolo-export/Scripts/python.exe" software/jetson/backpack/export_yolo.py --output "$env:TEMP/jetson-yolo-export"
```

The exporter downloads the official YOLO26n weights, checks the ONNX graph and fixed `(1,300,6)` end-to-end output, and writes `model.json` with labels, package version and SHA-256 hashes. Transfer `yolo26n.onnx` and `model.json` to `~/jetson-backpack-dev/deps/yolo/`. Keep weights, generated engines, venvs, and sample images outside source control. On the NX:

```sh
sudo apt-get install --no-install-recommends python3-libnvinfer=10.16.2.10-1+cuda13.2 libnvinfer-bin=10.16.2.10-1+cuda13.2 python3-opencv
/usr/src/tensorrt/bin/trtexec \
  --onnx=$HOME/jetson-backpack-dev/deps/yolo/yolo26n.onnx \
  --saveEngine=$HOME/jetson-backpack-dev/deps/yolo/yolo26n.engine \
  --memPoolSize=workspace:256 --builderOptimizationLevel=0 --maxAuxStreams=0 --skipInference
curl -fL https://ultralytics.com/images/bus.jpg -o ~/jetson-backpack-dev/deps/yolo/bus.jpg
python3 -B ~/jetson-backpack-dev/backpack/install_services.py --root ~/jetson-backpack-dev
```

Build the engine on its target GPU and TensorRT version. FP16 builds failed with a TensorRT convolution shader/KTM assertion at optimization levels 1 and 0; FP32 succeeded. This is a verified precision/build-path limitation, not an ARM64 loading failure. See [the matching NVIDIA report](https://forums.developer.nvidia.com/t/jetson-orin-nx-8gb-hard-reboots-during-tensorrt-engine-build-on-fresh-jetpack-7-2-1-deepstream-9-1/382905) and the [Ultralytics Jetson guide](https://docs.ultralytics.com/guides/nvidia-jetson/). Do not relabel this engine FP16 or change the platform software merely to match a generic installation guide.

## Memory and latency results

All values below are decimal GB, using `MemTotal - MemAvailable`, so reclaimable filesystem cache is not counted as committed workload memory. Total physical memory reported by Linux is 16.356 GB (15.233 GiB). The working ceiling is explicitly **12,000,000,000 bytes**, approximately 11.18 GiB.

| Phase | Mean used | Peak used | Conditions |
|---|---:|---:|---|
| Before YOLO | 10.512 GB | 10.620 GB | DAWN Whisper/Piper and resident Qwen |
| YOLO warmed and idle | 10.721 GB | 10.725 GB | All four models resident; no continuous YOLO video |
| Qwen vision then YOLO | 10.844 GB | 10.932 GB | Fresh still requests, all models resident |
| Overlapping Qwen vision and YOLO | 10.977 GB | **11.112 GB** | YOLO capture staggered after Qwen capture, overlapping inference |

The observed quiet mean increase was approximately 0.209 GB, but short before/after samples include normal system variability. YOLO process RSS after real inference was about 0.700 GB and includes shared library pages; do not add that RSS to whole-system usage again. The overlap run left at least 5.245 GB physically available and **0.888 GB under the chosen 12 GB ceiling**. About 1.3 MB of swap remained used with no increase during overlap. This leaves less than 1 GB of budget for future services at that measured peak; the initial 8 GB estimate was not the live baseline.

GPU inference took 62–66 ms in the sample/quiet camera tests and 142 ms during Qwen overlap. Fresh camera detection took 2.5–2.7 seconds including Argus capture. The overlapping Qwen request captured in 2.418 seconds and interpreted its frame in 7.336 seconds. Whisper and Piper were resident throughout but were not deliberately driven through simultaneous speech work. These are short sampled checks, not sustained load, power, temperature, or worst-case memory guarantees. Whisper was not changed to small.en.

Re-run measurement with:

```sh
python3 -B ~/jetson-backpack-dev/backpack/measure_memory.py --label yolo-resident --seconds 10
python3 -B ~/jetson-backpack-dev/backpack/measure_memory.py --label overlap --seconds 10 --combined
```

Private phase JSON is written to `run/memory-<label>.json`. The overlap helper starts Qwen camera work, waits three seconds for its capture, then requests fresh YOLO detection while Qwen analyzes its frame. Check both exit codes and timings before interpreting the peak. Sampling every 200 ms can miss shorter spikes.
