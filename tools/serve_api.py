"""Lightweight HTTP Micro-API for remote server deployment or network processing.

Zero third-party framework dependencies (pure standard library http.server).
Can be deployed on any remote VM, container, or local machine.

Endpoints:
- GET  /health           -> Check engine status & OpenCV availability
- POST /crop             -> Upload raw image / multipart, returns cropped image
- POST /crop/json        -> Send {"image_base64": "...", "deskew": true}, returns cropped base64 + metadata
- GET  /gallery          -> View interactive HTML QA gallery
"""
from __future__ import annotations

import argparse
import base64
import cgi
import io
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from padron_crop import crop, opencv_ext
from padron_crop.crop import crop_image
from padron_crop.gallery import build_gallery


class PadronCropHandler(BaseHTTPRequestHandler):
    out_dir = Path("out/api_server")

    def log_message(self, format, *args):
        # Clean logging
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/health", "/health/"):
            self._send_json(200, {
                "status": "healthy",
                "service": "padron-crop-api",
                "opencv_available": opencv_ext.is_opencv_available(),
                "python_version": sys.version.split()[0],
            })
            return

        if self.path.startswith("/gallery"):
            self.out_dir.mkdir(parents=True, exist_ok=True)
            gallery_path = build_gallery(self.out_dir)
            if gallery_path.exists():
                html = gallery_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            else:
                self._send_json(404, {"error": "No records in gallery yet."})
            return

        self._send_json(404, {"error": f"Endpoint not found: {self.path}"})

    def do_POST(self):
        self.out_dir.mkdir(parents=True, exist_ok=True)

        if self.path == "/crop/json":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self._send_json(400, {"error": "Missing request body"})
                return
            try:
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"error": f"Invalid JSON: {e}"})
                return

            b64_data = body.get("image_base64", "")
            if not b64_data:
                self._send_json(400, {"error": "Missing 'image_base64' field"})
                return

            if ";base64," in b64_data:
                b64_data = b64_data.split(";base64,")[1]

            try:
                img_bytes = base64.b64decode(b64_data)
            except Exception as e:
                self._send_json(400, {"error": f"Base64 decode failed: {e}"})
                return

            deskew = bool(body.get("deskew", False))
            face_safety = bool(body.get("face_safety", True))

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp_path = Path(tmp.name)

            try:
                rec = crop_image(tmp_path, self.out_dir, deskew=deskew, face_safety=face_safety)
                out_p = rec.get("out_path")
                if out_p and Path(out_p).exists() and rec["status"] == "ok":
                    rec["cropped_base64"] = base64.b64encode(Path(out_p).read_bytes()).decode("utf-8")
                self._send_json(200, rec)
            finally:
                tmp_path.unlink(missing_ok=True)
            return

        if self.path == "/crop":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self._send_json(400, {"error": "Empty body"})
                return

            img_bytes = self.rfile.read(content_length)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp_path = Path(tmp.name)

            try:
                rec = crop_image(tmp_path, self.out_dir, deskew=True, face_safety=True)
                out_p = rec.get("out_path")
                if out_p and Path(out_p).exists() and rec["status"] == "ok":
                    data = Path(out_p).read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("X-Crop-Status", rec["status"])
                    self.send_header("X-Crop-Box", json.dumps(rec.get("crop_box_xywh")))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._send_json(422, rec)
            finally:
                tmp_path.unlink(missing_ok=True)
            return

        self._send_json(404, {"error": f"Endpoint not found: {self.path}"})


def run_server(host: str = "0.0.0.0", port: int = 8000, out_dir: str = "out/api_server"):
    PadronCropHandler.out_dir = Path(out_dir)
    server_address = (host, port)
    httpd = HTTPServer(server_address, PadronCropHandler)
    print(f"============================================================")
    print(f"  PADRÓN CROP MICRO-API LISTA EN http://{host}:{port}")
    print(f"  - Health check:     http://localhost:{port}/health")
    print(f"  - Galería visual:   http://localhost:{port}/gallery")
    print(f"  - POST imagen raw:  http://localhost:{port}/crop")
    print(f"  - POST JSON base64: http://localhost:{port}/crop/json")
    print(f"============================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Servidor detenido por el usuario.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Padrón Crop HTTP API Server")
    p.add_argument("--host", default="0.0.0.0", help="Dirección host (default: 0.0.0.0)")
    p.add_argument("--port", type=int, default=8000, help="Puerto HTTP (default: 8000)")
    p.add_argument("--out", default="out/api_server", help="Directorio para almacenar procesados")
    args = p.parse_args()
    run_server(host=args.host, port=args.port, out_dir=args.out)
