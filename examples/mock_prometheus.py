#!/usr/bin/env python3
"""
Mock Prometheus server for testing.

Simulates Prometheus API responses for SLO testing.
"""

import argparse
import json
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


class MockPrometheusHandler(BaseHTTPRequestHandler):
    """Handler for mock Prometheus API requests."""

    def log_message(self, format, *args):
        """Log messages to stdout."""
        print(f"[{self.log_date_time_string()}] {format % args}")

    def do_GET(self):
        """Handle GET requests."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)

        if path == "/api/v1/query":
            self._handle_instant_query(query_params)
        elif path == "/api/v1/query_range":
            self._handle_range_query(query_params)
        elif path == "/-/healthy":
            self._send_json_response({"status": "healthy"})
        else:
            self._send_error(404, f"Path not found: {path}")

    def _handle_instant_query(self, params):
        """Handle instant query."""
        query = params.get("query", [""])[0]
        
        # Simple mock: return 1.0 for any query
        response = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"__name__": "mock_metric"},
                        "value": [datetime.now().timestamp(), "1.0"],
                    }
                ],
            },
        }
        
        self._send_json_response(response)

    def _handle_range_query(self, params):
        """Handle range query."""
        query = params.get("query", [""])[0]
        start = float(params.get("start", [datetime.now().timestamp() - 3600])[0])
        end = float(params.get("end", [datetime.now().timestamp()])[0])
        step = params.get("step", ["5m"])[0]
        
        # Parse step to seconds
        step_seconds = self._parse_step(step)
        
        # Generate mock time series data
        # Simulate high availability (99.9% uptime)
        values = []
        current = start
        
        while current <= end:
            # 99.9% of the time return 1.0 (good), occasionally 0.95 (some errors)
            import random
            sli_value = 1.0 if random.random() < 0.999 else 0.95
            
            values.append([current, str(sli_value)])
            current += step_seconds
        
        response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {
                            "__name__": "mock_metric",
                            "job": "api",
                            "service": "payment-api",
                        },
                        "values": values,
                    }
                ],
            },
        }
        
        self._send_json_response(response)

    def _parse_step(self, step: str) -> float:
        """Parse step string to seconds."""
        if step.endswith("s"):
            return float(step[:-1])
        elif step.endswith("m"):
            return float(step[:-1]) * 60
        elif step.endswith("h"):
            return float(step[:-1]) * 3600
        elif step.endswith("d"):
            return float(step[:-1]) * 86400
        else:
            return 300.0  # Default 5 minutes

    def _send_json_response(self, data, status_code=200):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, status_code, message):
        """Send error response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        error = {
            "status": "error",
            "errorType": "bad_data",
            "error": message,
        }
        self.wfile.write(json.dumps(error).encode())


def main():
    """Run mock Prometheus server."""
    parser = argparse.ArgumentParser(description="Mock Prometheus server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=9090, help="Port to bind to")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), MockPrometheusHandler)
    
    print(f"🚀 Mock Prometheus server running on http://{args.host}:{args.port}")
    print(f"   API endpoint: http://{args.host}:{args.port}/api/v1/query")
    print(f"   Health check: http://{args.host}:{args.port}/-/healthy")
    print()
    print("Press Ctrl+C to stop")
    print()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✅ Server stopped")
        server.shutdown()


if __name__ == "__main__":
    main()
