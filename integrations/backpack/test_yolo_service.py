"""Postprocessing contract tests without importing CUDA or TensorRT."""
import unittest
import io
import numpy as np

from yolo_service import detections, read_stream_frame


class DetectionTests(unittest.TestCase):
    def test_letterbox_coordinates_and_labels(self):
        result = detections(np.array([[20, 160, 620, 460, .9, 0]]),
                            ['person'], 640, 360, 1, 0, 140)
        self.assertEqual([20., 20., 620., 320.], result[0]['box_xyxy'])
        self.assertEqual('person', result[0]['label'])

    def test_rescale_and_clip_to_original_image(self):
        result = detections(np.array([[-10, -10, 700, 700, .5, 0]]),
                            ['person'], 1280, 720, .5, 0, 140)
        self.assertEqual([0., 0., 1280., 720.], result[0]['box_xyxy'])

    def test_bad_scores_classes_and_boxes_are_not_detections(self):
        rows = np.array([[0, 0, 100, 100, .1, 0], [0, 0, 100, 100, .9, 80],
                         [0, 0, 100, 100, .9, .5], [0, 0, 100, 100, np.nan, 0],
                         [100, 100, 0, 0, .9, 0], [0, 0, 100, 100, 1.2, 0]])
        self.assertEqual([], detections(rows, ['person'], 640, 640, 1, 0, 0))


class StreamFrameTests(unittest.TestCase):
    def header(self):
        return dict(source='goggles3', pixel_format='bgr24', width=640, height=360,
                    byte_length=640 * 360 * 3, frame_id=1, decoded_at=100.)

    def test_raw_frame_preserves_bgr_and_dimensions(self):
        image = read_stream_frame(self.header(), io.BytesIO(bytes([10, 20, 30]) *
                                  (640 * 360)), now=100.1)
        self.assertEqual((360, 640, 3), image.shape)
        self.assertEqual([10, 20, 30], image[0, 0].tolist())

    def test_bad_contract_and_stale_frames_are_rejected_before_read(self):
        for key, value in [('source', 'camera'), ('width', 1000000),
                           ('byte_length', 2**31), ('pixel_format', 'rgb24'),
                           ('frame_id', True), ('frame_id', -1),
                           ('decoded_at', 90.), ('decoded_at', 105.),
                           ('decoded_at', float('nan'))]:
            with self.subTest(key=key, value=value):
                request = self.header()
                request[key] = value
                with self.assertRaises(ValueError):
                    read_stream_frame(request, io.BytesIO(), now=100.)

    def test_truncated_frame_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            read_stream_frame(self.header(), io.BytesIO(b'partial'), now=100.)


if __name__ == '__main__':
    unittest.main()
