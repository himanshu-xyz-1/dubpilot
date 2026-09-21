"""
DubPilot API Server
===================
FastAPI backend powering the interactive DubPilot web interface,
real-time SSE streaming, live DNS/SSL diagnostic probes, and webhook verification.
"""

from __future__ import annotations
import asyncio
import json
import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.engine import DubSupportEngine
from agent.tools import check_domain_dns, check_domain_ssl, verify_webhook_hmac

app = FastAPI(
    title="DubPilot • AI Support & Diagnostic Platform for Dub.co",
    description="Autonomous customer support and real-time DNS/SSL troubleshooting engine for Dub.co",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = DubSupportEngine()


class ChatRequest(BaseModel):
    query: str = Field(..., description="Developer support query or domain to diagnose.")


class WebhookVerifyRequest(BaseModel):
    payload: str = Field(..., description="Raw webhook event payload body.")
    signature: str = Field(..., description="Dub-Signature header value.")
    secret: str = Field(..., description="Workspace webhook signing secret.")


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "dubpilot",
        "version": "1.0.0",
        "knowledge_articles_loaded": len(engine.articles),
    }


@app.get("/api/dns")
def test_dns(domain: str):
    """Executes live socket-level DNS inspection on a domain."""
    if not domain.strip():
        raise HTTPException(status_code=400, detail="Domain query parameter required.")
    return check_domain_dns(domain.strip())


@app.get("/api/ssl")
def test_ssl(domain: str):
    """Inspects port 443 TLS handshake and certificate validity."""
    if not domain.strip():
        raise HTTPException(status_code=400, detail="Domain query parameter required.")
    return check_domain_ssl(domain.strip())


@app.post("/api/verify-webhook")
def verify_webhook(req: WebhookVerifyRequest):
    """Validates HMAC SHA-256 signatures for Dub.co webhook payloads."""
    is_valid = verify_webhook_hmac(req.payload, req.signature, req.secret)
    return {
        "verified": is_valid,
        "algorithm": "HMAC-SHA256",
        "status": "VALID" if is_valid else "INVALID_SIGNATURE",
    }


@app.post("/api/chat")
def handle_chat(req: ChatRequest):
    """Processes user support query and returns resolution with live diagnostics."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return engine.resolve_ticket(req.query)


async def sse_chat_generator(query: str):
    """Streams resolution tokens with smooth typing latency and live diagnostics."""
    result = engine.resolve_ticket(query)
    full_markdown = result["solution_markdown"]

    # Stream chunks smoothly
    words = full_markdown.split(" ")
    for i, word in enumerate(words):
        chunk = word + (" " if i < len(words) - 1 else "")
        payload = json.dumps({"token": chunk})
        yield f"data: {payload}\n\n"
        await asyncio.sleep(0.015)

    yield "data: [DONE]\n\n"


@app.post("/api/chat/stream")
async def handle_chat_stream(req: ChatRequest):
    """Streams resolution tokens in real-time via Server-Sent Events (SSE)."""
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
    """Serves sleek Dub.co-styled interactive web client."""
    web_file = os.path.join(os.path.dirname(__file__), "..", "web", "index.html")
    if os.path.exists(web_file):
        with open(web_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>DubPilot Active</h1>"
