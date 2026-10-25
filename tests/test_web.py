import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import webapp


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = webapp.Scanner(self.temporary.name)
        self.server = webapp.Server(("127.0.0.1", 0), webapp.Handler)
        self.server.app = self.app
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.app.close()
        self.server.shutdown()
        self.server.server_close()
        self.temporary.cleanup()

    def request(self, method, path, data=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request(method, path, body=None if data is None else json.dumps(data), headers=headers or {})
        response = connection.getresponse()
        content = response.read()
        connection.close()
        return response.status, content

    def test_control_requires_same_origin_header(self):
        code, unused = self.request("POST", "/api/capture/start", {"frames": 5})
        self.assertEqual(code, 403)
        code, unused = self.request("POST", "/api/capture/start", {"frames": 5},
                                    {"X-Scanner-Request": "1", "Origin": "http://unrelated.example"})
        self.assertEqual(code, 403)
        code, unused = self.request("POST", "/api/capture/start", {"frames": 5},
                                    {"X-Scanner-Request": "1", "Host": "unrelated.example",
                                     "Origin": "http://unrelated.example"})
        self.assertEqual(code, 403)
        self.assertIsNone(self.app.recording)

    def test_capture_start_stop_and_operation_exclusion(self):
        with mock.patch.object(self.app, "preview"):
            code, content = self.request("POST", "/api/capture/start", {"frames": 5}, {"X-Scanner-Request": "1"})
            self.assertEqual(code, 200)
            self.assertTrue(json.loads(content)["recording"])
            code, unused = self.request("POST", "/api/capture/start", {"frames": 5}, {"X-Scanner-Request": "1"})
            self.assertEqual(code, 409)
            code, content = self.request("POST", "/api/capture/stop", {}, {"X-Scanner-Request": "1"})
            self.assertEqual(code, 200)
            self.assertFalse(json.loads(content)["recording"])

    def test_path_traversal_and_invalid_limits(self):
        with self.assertRaises(ValueError):
            self.app.scan_path("../private")
        for limit in (1, 3001, True, "10"):
            with self.assertRaises(ValueError):
                self.app.start_capture(limit)
        code, unused = self.request("GET", "/%2e%2e/webapp.py")
        self.assertEqual(code, 404)

    def test_failed_reconstruction_hides_stale_geometry(self):
        root = self.app.scan_path("saved-scan")
        root.mkdir()
        (root / "metadata.json").write_text(json.dumps({"frames": [{}, {}]}))
        (root / "trajectory.json").write_text("[]")
        (root / "mesh.ply").write_text("stale")
        (root / "reconstruction-status.json").write_text(json.dumps({"status": "failed"}))
        scan = self.app.list_scans()[0]
        self.assertFalse(scan["reconstructed"])
        self.assertNotIn("mesh.ply", scan["files"])

    def test_preview_blocked_during_reconstruction(self):
        self.app.busy = True
        with self.assertRaises(webapp.Conflict):
            self.app.preview()


if __name__ == "__main__":
    unittest.main()
