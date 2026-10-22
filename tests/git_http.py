"""Real Git smart HTTP server with Basic authentication for integration tests."""

import base64
import os
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


@contextmanager
def authenticated_remote(root, username="oauth2", token="test-token"):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            expected = "Basic " + base64.b64encode(f"{server.username}:{server.token}".encode()).decode()
            if self.headers.get("Authorization") != expected:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="Git"')
                self.end_headers()
                return
            url = urlsplit(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            proc = subprocess.run(
                ["git", "http-backend"], input=body, capture_output=True, check=True,
                env={
                    **os.environ,
                    "GIT_PROJECT_ROOT": str(root), "GIT_HTTP_EXPORT_ALL": "1",
                    "PATH_INFO": url.path, "QUERY_STRING": url.query,
                    "REQUEST_METHOD": self.command,
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": str(len(body)), "REMOTE_USER": server.username,
                },
            )
            headers, data = proc.stdout.split(b"\r\n\r\n", 1)
            headers = [line.split(": ", 1) for line in headers.decode().split("\r\n")]
            status = next((int(v.split()[0]) for k, v in headers if k.lower() == "status"), 200)
            self.send_response(status)
            for key, value in headers:
                if key.lower() != "status":
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_GET

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.username, server.token = username, token
    server.url = f"http://127.0.0.1:{server.server_port}/remote.git"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
