"""Camera contract tests; no real camera or inference in this suite."""
import base64
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from camera_look import CameraLook


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.commands, self.requests = [], []
        self.camera = CameraLook(self.temp.name, self.capture, self.respond)

    def capture(self, args, **kwargs):
        self.commands.append(args)
        location = args[-1].removeprefix('location=')
        Path(location % 14).write_bytes(b'\xff\xd8fresh-frame\xff\xd9')
        return subprocess.CompletedProcess(args, 0)

    def respond(self, request, **kwargs):
        self.requests.append(json.loads(request.data))
        self.assertEqual('http://127.0.0.1:11434/api/chat', request.full_url)
        return io.BytesIO(json.dumps({'message': {'content': 'A desk with cards.'}}).encode())

    def test_fresh_upright_frame_reaches_local_model(self):
        result = self.camera.describe('Are you seeing this?')
        self.assertEqual('A desk with cards.', result['description'])
        self.assertTrue(result['fresh'])
        self.assertIn('flip-method=2', self.commands[0])
        body = self.requests[0]
        self.assertFalse(body['think'])
        self.assertEqual(b'\xff\xd8fresh-frame\xff\xd9',
                         base64.b64decode(body['messages'][1]['images'][0]))
        self.assertEqual(1, len(list(Path(self.temp.name).iterdir())))

    def test_failed_capture_never_reuses_preview(self):
        self.camera.describe('First look')
        self.camera.runner = lambda *a, **kw: subprocess.CompletedProcess(a, 1)
        with self.assertRaisesRegex(RuntimeError, 'capture failed'):
            self.camera.describe('Second look')
        self.assertEqual(1, len(self.requests))

    def test_timeout_and_busy_do_not_call_model(self):
        self.camera.lock.acquire()
        with self.assertRaisesRegex(RuntimeError, 'already'):
            self.camera.describe('Look')
        self.camera.lock.release()
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired('camera', 20)
        self.camera.runner = timeout
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.camera.describe('Look')
        self.assertFalse(self.requests)

    def test_bad_queries_and_missing_model_answer(self):
        for query in (None, '', ' ', 'x' * 501):
            with self.assertRaises(ValueError):
                self.camera.describe(query)
        self.camera.opener = lambda *a, **kw: io.BytesIO(b'{"message":{"content":""}}')
        with self.assertRaisesRegex(RuntimeError, 'could not describe'):
            self.camera.describe('Look')


if __name__ == '__main__':
    unittest.main()
