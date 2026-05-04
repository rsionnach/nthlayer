#!/usr/bin/env python3
"""Minimal webhook receiver for Alertmanager — logs payloads to stdout."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 9999


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
            print(json.dumps(payload, indent=2), flush=True)
        except json.JSONDecodeError:
            print(f"[raw] {body.decode(errors='replace')}", flush=True)
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    print(f"Webhook receiver listening on port {PORT}", flush=True)
    server.serve_forever()
