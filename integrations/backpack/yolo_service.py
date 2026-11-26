#!/usr/bin/env python3
"""Resident TensorRT YOLO: warm GPU model, owner-only requests, on-demand frames."""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import socket
import socketserver
import struct
import tempfile
import subprocess
import time

import numpy as np


def read_stream_frame(request, stream, now=None):
    """Read one bounded BGR image from an owner-authenticated local client."""
    if (request.get('source') != 'goggles3' or request.get('pixel_format') != 'bgr24'
            or type(request.get('width')) is not int or request['width'] != 640
            or type(request.get('height')) is not int or request['height'] != 360
            or type(request.get('byte_length')) is not int
            or request['byte_length'] != 640 * 360 * 3
            or type(request.get('frame_id')) is not int
            or not 0 <= request['frame_id'] < 2**63):
        raise ValueError('Invalid goggles frame contract')
    decoded_at = request.get('decoded_at')
    if (type(decoded_at) not in (int, float) or not math.isfinite(decoded_at)
            or not -1 <= (time.time() if now is None else now) - decoded_at <= 2):
        raise ValueError('Stale or invalid goggles frame timestamp')
    frame = stream.read(request['byte_length'])
    if len(frame) != request['byte_length']:
        raise ValueError('Incomplete goggles frame')
    return np.frombuffer(frame, dtype=np.uint8).reshape((360, 640, 3))


def write_stream_snapshot(state, image, request, result):
    """Publish one atomic, source-tagged JPEG for explicit DAWN scene requests."""
    import cv2
    ok, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok or jpeg.nbytes > 1048576:
        raise RuntimeError('Could not encode the drone snapshot')
    header = json.dumps({'source': 'goggles3', 'decoded_at': request['decoded_at'],
                         'frame_id': request['frame_id'],
                         'detections': result['detections']}).encode() + b'\n'
    temporary = state / 'goggles-frame.tmp'
    with temporary.open('wb') as stream:
        os.chmod(temporary, 0o600)
        stream.write(header)
        stream.write(jpeg.tobytes())
    temporary.replace(state / 'goggles-frame.bin')


def memory_snapshot():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        values[key] = int(value.split()[0]) * 1024
    rss = 0
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith('VmRSS:'):
            rss = int(line.split()[1]) * 1024
    # Linux available memory includes reclaimable cache; do not count model RSS twice.
    return {'total_bytes': values['MemTotal'], 'available_bytes': values['MemAvailable'],
            'used_bytes': values['MemTotal'] - values['MemAvailable'],
            'swap_used_bytes': values['SwapTotal'] - values['SwapFree'],
            'process_rss_bytes': rss}


def detections(rows, names, width, height, scale, left, top, threshold=0.35):
    result = []
    for row in rows:
        if len(row) != 6 or not np.isfinite(row).all():
            continue
        x1, y1, x2, y2, score, category = map(float, row)
        index = int(category)
        if not threshold <= score <= 1 or category != index or not 0 <= index < len(names):
            continue
        box = [max(0., min(float(width), (x1 - left) / scale)),
               max(0., min(float(height), (y1 - top) / scale)),
               max(0., min(float(width), (x2 - left) / scale)),
               max(0., min(float(height), (y2 - top) / scale))]
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        result.append({'class_id': index, 'label': names[index],
                       'confidence': round(score, 4), 'box_xyxy': [round(v, 1) for v in box]})
    return result


class Detector:
    def __init__(self, model_dir):
        import tensorrt as trt
        self.model_dir = Path(model_dir)
        self.metadata = json.loads((self.model_dir / 'model.json').read_text())
        self.cuda = ctypes.CDLL('/usr/local/cuda/lib64/libcudart.so.13')
        signatures = {
            'cudaSetDevice': [ctypes.c_int],
            'cudaMalloc': [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t],
            'cudaFree': [ctypes.c_void_p],
            'cudaMemcpy': [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int],
            'cudaStreamCreate': [ctypes.POINTER(ctypes.c_void_p)],
            'cudaStreamSynchronize': [ctypes.c_void_p],
            'cudaStreamDestroy': [ctypes.c_void_p]}
        for name, arguments in signatures.items():
            getattr(self.cuda, name).argtypes = arguments
            getattr(self.cuda, name).restype = ctypes.c_int
        self.check(self.cuda.cudaSetDevice(0))
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.runtime = trt.Runtime(self.logger)
        self.engine = self.runtime.deserialize_cuda_engine(
            (self.model_dir / 'yolo26n.engine').read_bytes())
        if self.engine is None:
            raise RuntimeError('Cannot load the local TensorRT engine')
        self.context = self.engine.create_execution_context()
        self.stream = ctypes.c_void_p()
        self.check(self.cuda.cudaStreamCreate(ctypes.byref(self.stream)))
        self.buffers = []
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            shape = tuple(self.engine.get_tensor_shape(name))
            if any(value <= 0 for value in shape):
                raise RuntimeError('Only the fixed-shape engine is supported')
            array = np.empty(shape, dtype=trt.nptype(self.engine.get_tensor_dtype(name)))
            pointer = ctypes.c_void_p()
            self.check(self.cuda.cudaMalloc(ctypes.byref(pointer), array.nbytes))
            if not self.context.set_tensor_address(name, pointer.value):
                raise RuntimeError('Cannot bind TensorRT tensor')
            entry = (array, pointer)
            self.buffers.append(entry)
            if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                self.input = entry
            else:
                self.output = entry
        if self.input[0].shape != (1, 3, 640, 640) or self.output[0].shape != (1, 300, 6):
            raise RuntimeError('Unexpected YOLO end-to-end tensor contract')
        self.input[0].fill(0)
        for _ in range(3):
            self.infer()
        self.ready_at = time.time()
        self.count = 0

    @staticmethod
    def check(code):
        if code:
            raise RuntimeError(f'CUDA operation failed ({code})')

    def infer(self):
        array, pointer = self.input
        self.check(self.cuda.cudaMemcpy(pointer, array.ctypes.data, array.nbytes, 1))
        started = time.monotonic()
        if not self.context.execute_async_v3(stream_handle=self.stream.value):
            raise RuntimeError('TensorRT execution failed')
        self.check(self.cuda.cudaStreamSynchronize(self.stream))
        elapsed = (time.monotonic() - started) * 1000
        array, pointer = self.output
        self.check(self.cuda.cudaMemcpy(array.ctypes.data, pointer, array.nbytes, 2))
        return array[0], elapsed

    def detect(self, frame):
        import cv2
        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError('Invalid camera image')
        return self.detect_image(image)

    def detect_image(self, image):
        import cv2
        height, width = image.shape[:2]
        scale = min(640 / width, 640 / height)
        resized = cv2.resize(image, (round(width * scale), round(height * scale)))
        left, top = (640 - resized.shape[1]) // 2, (640 - resized.shape[0]) // 2
        padded = np.full((640, 640, 3), 114, dtype=np.uint8)
        padded[top:top + resized.shape[0], left:left + resized.shape[1]] = resized
        self.input[0][0] = padded[:, :, ::-1].transpose(2, 0, 1) / 255.
        rows, elapsed = self.infer()
        self.count += 1
        return {'detections': detections(rows, self.metadata['names'], width, height,
                                         scale, left, top),
                'inference_ms': round(elapsed, 3), 'image_width': width, 'image_height': height}

    def close(self):
        for _, pointer in self.buffers:
            self.cuda.cudaFree(pointer)
        self.cuda.cudaStreamDestroy(self.stream)


def camera_frame(state):
    # Same verified Argus pipeline and mounting correction as Victor's camera tool.
    with tempfile.TemporaryDirectory(prefix='yolo-camera-', dir=state) as directory:
        result = subprocess.run([
            'gst-launch-1.0', '-q', 'nvarguscamerasrc', 'num-buffers=15', '!',
            'video/x-raw(memory:NVMM),width=1920,height=1080,framerate=30/1', '!',
            'nvvidconv', 'flip-method=2', '!',
            'video/x-raw,width=640,height=360,format=I420', '!', 'jpegenc', 'quality=85', '!',
            'multifilesink', 'max-files=1', f'location={directory}/frame-%02d.jpg'],
            capture_output=True, timeout=20)
        frames = sorted(Path(directory).glob('frame-*.jpg'))
        if result.returncode or not frames:
            raise RuntimeError('Fresh camera capture failed')
        frame = frames[-1].read_bytes()
        if not 4 <= len(frame) <= 1048576 or not frame.startswith(b'\xff\xd8'):
            raise RuntimeError('Invalid camera frame')
        return frame


def serve(root):
    os.umask(0o077)
    state = root / 'run'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    detector = Detector(root / 'deps/yolo')
    last_snapshot = 0.

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            nonlocal last_snapshot
            self.request.settimeout(3)
            _, uid, _ = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET,
                                                                  socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                return
            try:
                line = self.rfile.readline(4097)
                if len(line) > 4096 or not line.endswith(b'\n'):
                    raise ValueError('Request too large or incomplete')
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError('Expected an object')
                operation = request.get('operation')
                if operation == 'status':
                    result = {'ready': True, 'model': 'yolo26n', 'backend': 'TensorRT FP32 CUDA',
                              'warmed_at': detector.ready_at, 'requests': detector.count,
                              'memory': memory_snapshot()}
                elif operation in ('detect', 'self_test'):
                    started = time.monotonic()
                    frame = (camera_frame(state) if operation == 'detect' else
                             (root / 'deps/yolo/bus.jpg').read_bytes())
                    result = detector.detect(frame)
                    result.update(fresh=operation == 'detect',
                                  total_seconds=round(time.monotonic() - started, 3),
                                  memory=memory_snapshot())
                elif operation == 'detect_frame':
                    started = time.monotonic()
                    image = read_stream_frame(request, self.rfile)
                    result = detector.detect_image(image)
                    result.update(source='goggles3', frame_id=request['frame_id'],
                                  decoded_at=request['decoded_at'],
                                  fresh=time.time() - request['decoded_at'] <= 2,
                                  total_seconds=round(time.monotonic() - started, 4))
                    if result['fresh'] and time.monotonic() - last_snapshot >= 0.5:
                        write_stream_snapshot(state, image, request, result)
                        last_snapshot = time.monotonic()
                else:
                    raise ValueError('Use status, detect, self_test, or detect_frame')
            except (ValueError, TypeError, KeyError, RuntimeError, OSError,
                    subprocess.TimeoutExpired) as exc:
                result = {'error': str(exc)}
            try:
                self.wfile.write(json.dumps(result).encode() + b'\n')
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass  # Recon termination can cancel a client during inference.

    address = state / 'yolo.sock'
    address.unlink(missing_ok=True)
    # Single worker deliberately owns the CUDA context and serializes inference.
    with socketserver.UnixStreamServer(str(address), Handler) as server:
        os.chmod(address, 0o600)
        print(json.dumps({'ready': True, 'model': 'yolo26n', 'memory': memory_snapshot()}), flush=True)
        try:
            server.serve_forever()
        finally:
            detector.close()
            address.unlink(missing_ok=True)


def client(root, operation):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(30)
        connection.connect(str(root / 'run/yolo.sock'))
        connection.sendall(json.dumps({'operation': operation}).encode() + b'\n')
        with connection.makefile('rb') as stream:
            result = json.loads(stream.readline(65537))
    print(json.dumps(result, indent=2))
    if 'error' in result:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home() / 'jetson-backpack-dev')
    parser.add_argument('--request', choices=['status', 'detect', 'self_test'])
    args = parser.parse_args()
    if args.request:
        client(args.root, args.request)
    else:
        serve(args.root)
