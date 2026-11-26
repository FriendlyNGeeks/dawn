#!/usr/bin/env python3
"""Export YOLO26 nano on the development PC; build the engine on the target NX."""
import argparse
import hashlib
import json
from pathlib import Path


def export(directory):
    import onnx
    import ultralytics
    from ultralytics import YOLO
    directory.mkdir(parents=True, exist_ok=True)
    weights = directory / 'yolo26n.pt'
    model = YOLO(str(weights))
    artifact = Path(model.export(format='onnx', imgsz=640, batch=1, dynamic=False,
                                 simplify=False, opset=17, nms=False, device='cpu'))
    graph = onnx.load(str(artifact))
    onnx.checker.check_model(graph)
    output = tuple(d.dim_value for d in graph.graph.output[0].type.tensor_type.shape.dim)
    if output != (1, 300, 6):
        raise RuntimeError(f'Unexpected end-to-end output: {output}')
    metadata = {
        'model': 'yolo26n', 'ultralytics': ultralytics.__version__,
        'weights_source': 'https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt',
        'weights_sha256': hashlib.sha256(weights.read_bytes()).hexdigest(),
        'onnx_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
        'input_shape': [1, 3, 640, 640], 'output_shape': [1, 300, 6],
        'names': [model.names[i] for i in range(len(model.names))]}
    (directory / 'model.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.output.resolve())
