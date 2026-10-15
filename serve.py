
"""
BridgeLab — WSGI Server Entry Point
Local deployment compatibility test.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "platform"))

from app import app
from waitress import serve


if __name__ == "__main__":
    print("BridgeLab WSGI Server")
    print("Open: http://127.0.0.1:5001")

    serve(
        app,
        host="127.0.0.1",
        port=5001,
        threads=4,
        max_request_body_size=26 * 1024 * 1024
    )
