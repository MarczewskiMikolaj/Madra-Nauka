"""Generate a dependency-free loopback listener for a self-hosted web instance."""


def helper_script(public_url):
    return (
        """#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

DESTINATION = """
        + repr(public_url + "/konto/ai/powrot")
        + """

class Callback(BaseHTTPRequestHandler):
    finished = False
    def log_message(self, *args):
        pass
    def do_GET(self):
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query)
        if parsed.path != "/auth/callback" or not params.get("state"):
            self.send_error(404)
            return
        safe = {key: params[key][0] for key in ("code", "state", "client_id", "error") if key in params}
        self.send_response(302)
        self.send_header("Location", DESTINATION + "#" + urlencode(safe))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        Callback.finished = True

try:
    server = HTTPServer(("127.0.0.1", 8085), Callback)
except OSError:
    raise SystemExit("Port 8085 jest zajęty. Zamknij poprzedni pomocnik i spróbuj ponownie.")
print("Pomocnik działa. Kliknij Kontynuuj z ChatGPT w Mądrej Nauce.")
try:
    while not Callback.finished:
        server.handle_request()
finally:
    server.server_close()
"""
    )
