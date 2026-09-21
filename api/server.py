# FastAPI backend server that handles API requests, live DNS/SSL checks, and token streaming.

from __future__ import annotations
import asyncio
import json
import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Make sure we can import from our agent folder
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.engine import DubSupportEngine
from agent.tools import check_domain_dns, check_domain_ssl, verify_webhook_hmac

app = FastAPI(
    title="DubPilot API",
    description="Support and DNS troubleshooting backend for Dub.co",
    version="1.0.0",
)

# Allow requests from any origin so frontend clients can connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the support engine
engine = DubSupportEngine()


# Request body models using Pydantic for validation
class ChatRequest(BaseModel):
    query: str = Field(..., description="User question or domain name to check.")


class WebhookVerifyRequest(BaseModel):
    payload: str = Field(..., description="Raw webhook event body.")
    signature: str = Field(..., description="The signature header from Dub.")
    secret: str = Field(..., description="Your webhook secret key.")


@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "service": "dubpilot",
        "version": "1.0.0",
        "knowledge_articles_loaded": len(engine.articles),
    }


@app.get("/api/dns")
def test_dns(domain: str):
    """Checks DNS records for a domain in real time."""
    if not domain.strip():
        raise HTTPException(status_code=400, detail="Please provide a domain parameter.")
    return check_domain_dns(domain.strip())


@app.get("/api/ssl")
def test_ssl(domain: str):
    """Tests the SSL certificate on port 443 of a domain."""
    if not domain.strip():
        raise HTTPException(status_code=400, detail="Please provide a domain parameter.")
    return check_domain_ssl(domain.strip())


@app.post("/api/verify-webhook")
def verify_webhook(req: WebhookVerifyRequest):
    """Verifies that a webhook was actually sent by Dub.co."""
    is_valid = verify_webhook_hmac(req.payload, req.signature, req.secret)
    return {
        "verified": is_valid,
        "algorithm": "HMAC-SHA256",
        "status": "VALID" if is_valid else "INVALID_SIGNATURE",
    }


@app.post("/api/chat")
def handle_chat(req: ChatRequest):
    """Answers a question and returns the full response at once."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return engine.resolve_ticket(req.query)


async def sse_chat_generator(query: str):
    """
    Streams the response word by word using Server-Sent Events (SSE).
    This gives an instant, typewriter-style feel in the UI.
    """
    result = engine.resolve_ticket(query)
    full_markdown = result["solution_markdown"]

    # Send words one by one with a tiny delay
    words = full_markdown.split(" ")
    for i, word in enumerate(words):
        chunk = word + (" " if i < len(words) - 1 else "")
        payload = json.dumps({"token": chunk})
        yield f"data: {payload}\n\n"
        await asyncio.sleep(0.015)

    # Signal to the browser that we are done
    yield "data: [DONE]\n\n"


@app.post("/api/chat/stream")
async def handle_chat_stream(req: ChatRequest):
    """Streams the response in real time via Server-Sent Events."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return StreamingResponse(
        sse_chat_generator(req.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/", response_class=HTMLResponse)
def serve_ui():
    """Serves the main web interface."""
    web_file = os.path.join(os.path.dirname(__file__), "..", "web", "index.html")
    if os.path.exists(web_file):
        with open(web_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>DubPilot is running</h1>"
