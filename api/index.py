# Vercel Serverless entrypoint for FastAPI
import os
import sys

# Ensure project root is in sys.path for Vercel serverless runtime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.server import app
