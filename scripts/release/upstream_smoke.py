"""One actual frontend image, tested with Docker DNS and loopback upstreams."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid

BODY = b"synthetic-media-" * 4096


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if self.path.startswith("/media/"):
            if self.path == "/media/private" and self.headers.get("Cookie") != "angmoo_browser_session=synthetic":
                self.send_response(404); self.end_headers(); return
            if self.path == "/media/missing":
                self.send_response(404); self.end_headers(); return
            ranged = self.headers.get("Range") == "bytes=2-5"
            body = BODY[2:6] if ranged else BODY
            self.send_response(206 if ranged else 200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Content-Length", str(len(body)))
            if ranged:
                self.send_header("Content-Range", f"bytes 2-5/{len(BODY)}")
            self.end_headers()
            if self.command != "HEAD": self.wfile.write(body)
        elif self.path == "/api/v1/fixture-stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"data: first\n\n"); self.wfile.flush()
            time.sleep(.1)
            self.wfile.write(b"data: done\n\n")
        else:
            body = json.dumps({"upstream": "synthetic", "cookie": self.headers.get("Cookie")}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)


def docker(*args):
    return subprocess.run(["docker", *args], check=True, text=True, encoding="utf-8", stdout=subprocess.PIPE).stdout.strip()


def run(frontend, backend, platform, output):
    from launcher.termux.payload import require
    from scripts.release.candidate import ROOT
    name = "angmoo-upstream-" + uuid.uuid4().hex[:12]
    network, fixture = name + "-net", name + "-fixture"
    fronts = []
    results = []
    # Published loopback ports need a normal bridge on Docker Desktop. The
    # fixture serves synthetic data only and never calls an external provider.
    docker("network", "create", network)
    try:
        docker("run", "-d", "--name", fixture, "--platform", platform, "--network", network, "--network-alias", "backend",
               "-p", "127.0.0.1::3000", "--mount", f"type=bind,source={ROOT / 'scripts/release/upstream_smoke.py'},target=/tmp/upstream.py,readonly",
               "--entrypoint", "python", backend, "/tmp/upstream.py", "--serve")
        for mode, upstream in (("dns", "http://backend:8080"), ("loopback", "http://127.0.0.1:8080")):
            container = name + "-" + mode
            fronts.append(container)
            network_args = ["--network", network, "-p", "127.0.0.1::3000"] if mode == "dns" else ["--network", "container:" + fixture]
            docker("run", "-d", "--name", container, "--platform", platform, *network_args,
                   "--env", "ANGMOO_API_BASE_URL=" + upstream, frontend)
            port_owner = container if mode == "dns" else fixture
            doc = json.loads(docker("inspect", port_owner))[0]
            port = doc["NetworkSettings"]["Ports"]["3000/tcp"][0]["HostPort"]
            origin = "http://127.0.0.1:" + port
            deadline = time.monotonic() + 90
            while True:
                try:
                    with urllib.request.urlopen(origin + "/api/runtime-identity", timeout=2) as response:
                        require(json.load(response)["version"] == "0.1.0", "upstream_identity_invalid")
                    break
                except (OSError, ValueError):
                    require(time.monotonic() < deadline, "upstream_frontend_not_ready")
                    time.sleep(.5)
            for path, method, headers, expected, data in (
                ("/media/file", "GET", {}, 200, BODY),
                ("/media/file", "HEAD", {}, 200, b""),
                ("/media/file", "GET", {"Range": "bytes=2-5"}, 206, BODY[2:6]),
                ("/media/private", "GET", {}, 404, b""),
                ("/media/private", "GET", {"Cookie": "angmoo_browser_session=synthetic; unrelated=hidden"}, 200, BODY),
                ("/media/missing", "GET", {}, 404, b""),
                ("/api/backend/fixture-stream", "GET", {}, 200, b"data: first\n\ndata: done\n\n"),
            ):
                request = urllib.request.Request(origin + path, method=method, headers=headers)
                try:
                    response = urllib.request.urlopen(request, timeout=15)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    require(response.status == expected and response.read() == data, "runtime_upstream_response_invalid: " + mode + path)
                    if expected == 206:
                        require(response.headers.get("Content-Range") == f"bytes 2-5/{len(BODY)}", "runtime_range_invalid")
            with urllib.request.urlopen(origin + "/api/backend/fixture", timeout=15) as response:
                require(json.load(response)["upstream"] == "synthetic", "runtime_api_upstream_invalid")
            results.append({"mode": mode, "status": "PASS", "image": frontend, "checks": ["api", "stream", "media", "head", "range", "private-cookie", "missing"]})
            docker("stop", "--time", "20", container)
        (output / "upstreams.json").write_text(json.dumps({"status": "PASS", "same_frontend_image": frontend, "platform": platform, "results": results}, indent=2) + "\n")
    finally:
        for container in fronts + [fixture]:
            subprocess.run(["docker", "rm", "-f", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        docker("network", "rm", network)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.serve:
        ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
