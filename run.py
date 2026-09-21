#!/usr/bin/env python3
"""
Dub Support AI Launcher
"""

import os
import sys
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("=" * 65)
    print("🚀 DUB.CO AI SUPPORT CO-PILOT IS ONLINE")
    print("=" * 65)
    print(f"• Local Web UI: http://localhost:{port}")
    print(f"• API Docs:     http://localhost:{port}/docs")
    print("=" * 65 + "\n")
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=False)
