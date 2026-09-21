#!/usr/bin/env python3
# Main entrypoint script to run the local server.

import os
import sys
import uvicorn

# Make sure Python can find our local modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

if __name__ == "__main__":
    # Use the PORT env variable if set, otherwise default to 8080
    port = int(os.environ.get("PORT", "8080"))
    print("=" * 60)
    print("🚀 DubPilot server is starting up...")
    print(f"• Web UI:  http://localhost:{port}")
    print(f"• Swagger: http://localhost:{port}/docs")
    print("=" * 60 + "\n")
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=False)
