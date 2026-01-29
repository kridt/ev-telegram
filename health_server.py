#!/usr/bin/env python3
"""Simple health check server for Render."""

import http.server
import socketserver
import os

PORT = int(os.environ.get("PORT", 8000))

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK - EV Telegram Bot Running")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
        print(f"Health server running on port {PORT}")
        httpd.serve_forever()
