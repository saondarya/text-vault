#!/usr/bin/env python3
"""Run locally: python run_local.py → http://localhost:5001"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))

from index import app  # noqa: E402

if __name__ == "__main__":
    # macOS uses port 5000 for AirPlay Receiver, so 5001 is preferred as local default
    port = int(os.getenv("PORT", 5001))
    print(f"🚀 Text Vault running locally at: http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
