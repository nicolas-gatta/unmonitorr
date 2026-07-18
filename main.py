"""
Entry point.

Local/dev:   python3 main.py       (uses Flask's dev server)
Production:  gunicorn ... main:app (used inside the Docker image)
"""

import os
from app import app 

if __name__ == "__main__":
    host = os.environ.get("LISTEN_HOST", "0.0.0.0")
    port = int(os.environ.get("LISTEN_PORT", "5055"))
    app.run(host=host, port=port)