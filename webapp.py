#!/usr/bin/env python3
"""LAN scanner UI: standard-library HTTP server, one camera owner, offline fusion."""
import argparse
import collections
import json
import ipaddress
import mimetypes
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlsplit, unquote, parse_qs

import jetscan

BASE = Path(__file__).resolve().parent
SCAN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
EXPORTS = {"cloud.ply", "mesh.ply", "mesh.obj", "trajectory.json", "metadata.json", "alignment.png"}


class Conflict(Exception):
    pass


class Scanner:
    def __init__(self, scans):
        self.scans = Path(scans).resolve()
        self.scans.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.camera_stop = threading.Event()
        self.shutdown = threading.Event()
        self.camera = None
        self.recording = None
        self.process = None
        self.busy = False
        self.mode = "idle"
        self.message = "Connect the camera and start a preview."
        self.active_scan = None
        self.count = 0
        self.started = None
        self.elapsed = 0
        self.seq = 0
        self.jpeg = {}
        self.logs = collections.deque(maxlen=120)

    def scan_path(self, name):
        if not isinstance(name, str) or not SCAN_ID.fullmatch(name):
            raise ValueError("Invalid scan name")
        path = (self.scans / name).resolve()
        if path.parent != self.scans:
            raise ValueError("Scan path leaves the scan directory")
        return path

    def state(self):
        with self.lock:
            return dict(mode=self.mode, message=self.message, scan=self.active_scan,
                        frames=self.count, camera_ready=bool(self.jpeg),
                        busy=self.busy, recording=self.recording is not None,
                        elapsed=(time.monotonic() - self.started) if self.recording and self.started else self.elapsed,
                        log=list(self.logs))

    def list_scans(self):
        result = []
        with self.lock:
            active = self.recording[0].name if self.recording else None
        for path in sorted(self.scans.iterdir(), key=lambda p: p.name, reverse=True):
            if not SCAN_ID.fullmatch(path.name) or path.is_symlink() or not path.is_dir():
                continue
            try:
                meta = json.loads((path / "metadata.json").read_text())
                status_file = path / "reconstruction-status.json"
                status_ok = not status_file.exists() or json.loads(status_file.read_text()).get("status") == "complete"
                files = [n for n in sorted(EXPORTS) if (path / n).is_file() and
                         (status_ok or n in ("metadata.json", "alignment.png"))]
                result.append(dict(id=path.name, frames=len(meta["frames"]),
                    recording=path.name == active,
                    reconstructed=status_ok and (path / "trajectory.json").exists(), files=files))
            except (OSError, ValueError, KeyError):
                continue
        return result

    def preview(self):
        with self.lock:
            if self.busy:
                raise Conflict("Wait for reconstruction to finish.")
            if self.camera and self.camera.is_alive():
                return
            self.camera_stop = threading.Event()
            self.jpeg = {}
            self.mode = "preview"
            self.message = "Opening OAK-D Lite…"
            self.camera = threading.Thread(target=self._camera, name="oak-camera", daemon=True)
            self.camera.start()

    def start_capture(self, limit=600):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 2 <= limit <= 3000:
            raise ValueError("Frame limit must be between 2 and 3000")
        with self.lock:
            if self.busy or self.recording:
                raise Conflict("Another operation is already running.")
            if shutil.disk_usage(str(self.scans)).free < 512 * 1024 * 1024:
                raise Conflict("At least 512 MB free storage is required.")
            self.preview()
            name = datetime.now().strftime("scan-%Y%m%d-%H%M%S-%f")
            root = self.scan_path(name)
            root.mkdir()
            self.recording = [root, None, limit]
            self.active_scan = name
            self.count = 0
            self.started = time.monotonic()
            self.elapsed = 0
            self.mode = "capturing"
            self.message = "Recording synchronized RGB and depth."

    def stop_capture(self):
        with self.lock:
            if self.recording:
                self.elapsed = time.monotonic() - self.started
                self.recording = None
                self.mode = "preview"
                self.message = "Capture saved: {} frames.".format(self.count)

    def _camera(self):
        last_preview = 0
        frames = jetscan.camera_frames(self.camera_stop)
        try:
            import cv2
            for calibration, color, depth, stamps in frames:
                if self.camera_stop.is_set():
                    break
                with self.lock:
                    if self.recording:
                        root, meta, limit = self.recording
                        if meta is None:
                            meta = dict(calibration, frames=[])
                            self.recording[1] = meta
                        if shutil.disk_usage(str(root)).free < 256 * 1024 * 1024:
                            raise RuntimeError("Storage is nearly full. Saved frames are preserved.")
                        jetscan.save_frame(root, meta, color, depth, stamps)
                        self.count = len(meta["frames"])
                        if self.count >= limit:
                            self.stop_capture()
                    elif self.message == "Opening OAK-D Lite…":
                        self.message = "Live camera ready."
                if time.monotonic() - last_preview >= 0.2:
                    bgr = color[:, :, ::-1].copy()
                    colored = cv2.applyColorMap(jetscan.np.clip(depth / 2500 * 255, 0, 255).astype("uint8"), cv2.COLORMAP_JET)
                    colored[depth == 0] = 0
                    images = {}
                    for name, image in (("rgb", bgr), ("depth", colored)):
                        ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        if not ok:
                            raise RuntimeError("JPEG encoding failed")
                        images[name] = data.tobytes()
                    with self.changed:
                        self.jpeg = images
                        self.seq += 1
                        self.changed.notify_all()
                    last_preview = time.monotonic()
        except Exception as error:
            with self.lock:
                self.mode = "error"
                self.message = str(error)
                self.logs.append("Camera: " + str(error))
        finally:
            frames.close()
            with self.lock:
                self.recording = None

    def pause_preview(self):
        with self.lock:
            if self.busy:
                raise Conflict("Reconstruction is running.")
            self.stop_capture()
            self.busy = True
            self.camera_stop.set()
            worker = self.camera
        if worker:
            worker.join(timeout=35)
            if worker.is_alive():
                with self.lock:
                    self.busy = False
                raise Conflict("The camera is still closing; try again shortly.")
        with self.lock:
            self.busy = False
            self.jpeg = {}
            self.mode = "idle"
            self.message = "Camera paused."

    def reconstruct(self, name, voxel=0.01, minimum=0.4, maximum=2.5):
        if not all(isinstance(v, (int, float)) and jetscan.np.isfinite(v) for v in (voxel, minimum, maximum)):
            raise ValueError("Reconstruction settings must be finite numbers")
        if not 0.005 <= voxel <= 0.05 or not 0.1 <= minimum < maximum <= 10:
            raise ValueError("Use voxels from 0.005 to 0.05 m and depths from 0.1 to 10 m")
        root = self.scan_path(name)
        meta = json.loads((root / "metadata.json").read_text())
        if len(meta["frames"]) < 2:
            raise ValueError("Capture at least two frames first")
        with self.lock:
            if self.busy or self.recording:
                raise Conflict("Stop capture before starting reconstruction.")
            # Reserve the operation before releasing the lock to close the camera.
            self.busy = True
            self.camera_stop.set()
            self.mode = "reconstructing"
            self.active_scan = name
            self.message = "Closing camera, then reconstructing offline…"
            self.logs.clear()
            worker = threading.Thread(target=self._reconstruct, args=(root, voxel, minimum, maximum), daemon=True)
            worker.start()

    def _reconstruct(self, root, voxel, minimum, maximum):
        try:
            if self.camera:
                self.camera.join(timeout=35)
                if self.camera.is_alive():
                    raise RuntimeError("Camera did not close; reconstruction was not started")
            with self.lock:
                self.jpeg = {}
            command = [sys.executable, "-u", str(BASE / "jetscan.py"), "reconstruct", str(root),
                       "--voxel", str(voxel), "--min-depth", str(minimum), "--max-depth", str(maximum)]
            # Old geometry must not be offered as the result of a failed retry.
            status = root / "reconstruction-status.json"
            status.write_text(json.dumps({"status": "running"}))
            with self.lock:
                if self.shutdown.is_set():
                    raise RuntimeError("Server is shutting down")
                self.process = subprocess.Popen(command, cwd=str(BASE), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, universal_newlines=True)
            log_path = root / "reconstruction.log"
            with log_path.open("w") as log:
                for line in self.process.stdout:
                    log.write(line)
                    log.flush()
                    with self.lock:
                        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
                        self.logs.append(clean)
                        self.message = clean
            code = self.process.wait()
            status.write_text(json.dumps({"status": "complete" if code == 0 else "failed", "exit_code": code}))
            if code:
                raise RuntimeError("Reconstruction failed. Saved capture is intact; see the log below.")
            with self.lock:
                self.mode = "idle"
                self.message = "Reconstruction complete. Open the 3D model below."
        except Exception as error:
            with self.lock:
                self.mode = "error"
                self.message = str(error)
                self.logs.append(str(error))
        finally:
            with self.lock:
                self.busy = False
                self.process = None

    def close(self):
        self.shutdown.set()
        self.camera_stop.set()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
        if self.camera:
            self.camera.join(timeout=10)


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith("POST"):
            super().log_message(fmt, *args)

    def reply(self, data, code=200, mime="application/json"):
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        # A custom header plus same-origin checking prevents cross-site form commands.
        origin = self.headers.get("Origin")
        try:
            host = urlsplit("//" + self.headers.get("Host", "")).hostname
            if host not in ("localhost", socket.gethostname(), socket.gethostname() + ".local"):
                if not ipaddress.ip_address(host).is_private:
                    return self.reply({"error": "Use the Nano LAN address."}, 403)
        except ValueError:
            return self.reply({"error": "Use the Nano LAN address."}, 403)
        if (self.headers.get("X-Scanner-Request") != "1" or
                (origin and urlsplit(origin).netloc != self.headers.get("Host"))):
            return self.reply({"error": "Use the scanner page on the same origin."}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 4096:
                return self.reply({"error": "Request too large"}, 413)
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Expected an object")
            path = urlsplit(self.path).path
            if path == "/api/preview/start":
                self.app.preview()
            elif path == "/api/preview/stop":
                self.app.pause_preview()
            elif path == "/api/capture/start":
                self.app.start_capture(data.get("frames", 600))
            elif path == "/api/capture/stop":
                self.app.stop_capture()
            elif path == "/api/reconstruct":
                self.app.reconstruct(data.get("scan"), data.get("voxel", 0.01),
                                     data.get("min_depth", 0.4), data.get("max_depth", 2.5))
            else:
                return self.reply({"error": "Not found"}, 404)
            self.reply(self.app.state())
        except Conflict as error:
            self.reply({"error": str(error)}, 409)
        except (ValueError, TypeError, OSError, KeyError) as error:
            self.reply({"error": str(error)}, 400)

    def do_GET(self):
        try:
            url = urlsplit(self.path)
            path = unquote(url.path)
            if path == "/api/state":
                return self.reply(self.app.state())
            if path == "/api/scans":
                return self.reply(self.app.list_scans())
            if path in ("/api/live/rgb", "/api/live/depth"):
                return self.stream(path.rsplit("/", 1)[1])
            match = re.fullmatch(r"/api/scans/([^/]+)/frames/(\d+)\.jpg", path)
            if match:
                return self.frame(match[1], int(match[2]), parse_qs(url.query).get("kind", ["rgb"])[0])
            match = re.fullmatch(r"/api/scans/([^/]+)/files/([^/]+)", path)
            if match:
                if match[2] not in EXPORTS:
                    return self.reply({"error": "Not found"}, 404)
                root = self.app.scan_path(match[1])
                return self.file(root / match[2], root, download=True)
            relative = "index.html" if path == "/" else path.lstrip("/")
            return self.file(BASE / "web" / relative, BASE / "web")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, ValueError, KeyError, IndexError) as error:
            self.reply({"error": str(error)}, 404)

    def file(self, path, allowed, download=False):
        path = path.resolve()
        allowed = allowed.resolve()
        if allowed not in path.parents or not path.is_file():
            return self.reply({"error": "Not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("X-Content-Type-Options", "nosniff")
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="{}"'.format(path.name))
        self.end_headers()
        with path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile)

    def frame(self, name, index, kind):
        import cv2
        root = self.app.scan_path(name)
        meta = json.loads((root / "metadata.json").read_text())
        filename = meta["frames"][index]["file"]
        if not re.fullmatch(r"\d{6}\.npz", filename):
            raise ValueError("Invalid frame filename")
        source = (root / filename).resolve()
        if source.parent != root:
            raise ValueError("Invalid frame path")
        with jetscan.np.load(str(source)) as data:
            if kind == "depth":
                depth = data["depth"]
                image = cv2.applyColorMap(jetscan.np.clip(depth / 2500 * 255, 0, 255).astype("uint8"), cv2.COLORMAP_JET)
                image[depth == 0] = 0
            else:
                image = data["color"][:, :, ::-1].copy()
        ok, jpeg = cv2.imencode(".jpg", image)
        if not ok:
            raise ValueError("Could not encode frame")
        self.reply(jpeg.tobytes(), mime="image/jpeg")

    def stream(self, kind):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        sequence = -1
        try:
            while not self.app.shutdown.is_set():
                with self.app.changed:
                    self.app.changed.wait_for(lambda: self.app.seq != sequence or self.app.shutdown.is_set(), timeout=3)
                    if self.app.seq == sequence:
                        continue
                    sequence = self.app.seq
                    data = self.app.jpeg.get(kind)
                if data:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                     str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--scans", default=str(BASE / "scans"))
    args = parser.parse_args()
    app = Scanner(args.scans)
    server = Server((args.host, args.port), Handler)
    server.app = app
    def stop(*unused):
        app.close()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print("JetScan web interface on http://{}:{}".format(args.host, args.port), flush=True)
    try:
        server.serve_forever()
    finally:
        app.close()
        server.server_close()


if __name__ == "__main__":
    main()
