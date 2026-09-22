# FastAPI backend server that handles API requests, live DNS/SSL checks, and token streaming.

from __future__ import annotations
import json
import os
import sys
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
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
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def handle_vercel_rewrites(request, call_next):
    """
    On Vercel serverless, requests rewritten from /api/(.*) arrive with scope['path'] = '/api/index.py'.
    The real user-requested route is passed in headers like 'x-matched-path' or 'x-forwarded-uri'.
    This middleware restores the original requested path for FastAPI routing.
    """
    matched = request.headers.get("x-matched-path") or request.headers.get("x-forwarded-uri")
    if matched:
        clean = matched.split("?")[0]
        if clean and clean != "/api/index.py":
            request.scope["path"] = clean
    return await call_next(request)

# Initialize the support engine
engine = DubSupportEngine()


# Request body models using Pydantic for validation
class ChatRequest(BaseModel):
    query: str = Field(..., description="User question or domain name to check.")
    session_id: Optional[str] = Field(None, description="Optional session ID for multi-turn conversation memory.")

ChatRequest.model_rebuild()


class WebhookVerifyRequest(BaseModel):
    payload: str = Field(..., description="Raw webhook event body.")
    signature: str = Field(..., description="The signature header from Dub.")
    secret: str = Field(..., description="Your webhook secret key.")

WebhookVerifyRequest.model_rebuild()


class SimulationStateRequest(BaseModel):
    simulate_groq_failure: Optional[bool] = Field(None, description="Set to True to simulate Groq API outage.")
    simulate_ollama_failure: Optional[bool] = Field(None, description="Set to True to simulate local Ollama outage.")

SimulationStateRequest.model_rebuild()


@app.get("/health")
def health_check():
    """Simple health check endpoint returning service status and LLM availability."""
    return {
        "status": "healthy",
        "service": "dubpilot",
        "version": "1.0.0",
        "knowledge_articles_loaded": len(engine.articles),
        "llm_engine": engine.llm.get_model_name(),
        "llm_online": engine.llm.is_available(),
        "simulation_state": engine.llm.get_simulation_state(),
    }


@app.get("/api/dev/state")
def get_simulation_state():
    """Returns the current state of LLM providers and active simulation overrides."""
    return engine.llm.get_simulation_state()


@app.post("/api/dev/simulate")
def set_simulation_state(req: SimulationStateRequest):
    """
    State Manipulator:
    Allows developers to simulate Groq API failures or Ollama failures
    to verify real-time fallback behavior.
    """
    engine.llm.set_simulation_state(
        groq_failure=req.simulate_groq_failure,
        ollama_failure=req.simulate_ollama_failure
    )
    return {
        "message": "Simulation state updated successfully",
        "state": engine.llm.get_simulation_state()
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
    """Answers a question using LLaMA 3.2 with verified Dub.co context and DNS telemetry."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return engine.resolve_ticket(req.query, session_id=req.session_id)


async def sse_chat_generator(query: str, session_id: Optional[str] = None):
    """
    Streams tokens in real time directly from local LLaMA 3.2 via Ollama.
    Falls back cleanly to deterministic streaming if Ollama is busy or offline.
    """
    async for chunk in engine.stream_ticket(query, session_id=session_id):
        payload = json.dumps({"token": chunk})
        yield f"data: {payload}\n\n"

    # Signal to the browser that we are done
    yield "data: [DONE]\n\n"


@app.post("/api/chat/stream")
async def handle_chat_stream(req: ChatRequest):
    """Streams the response in real time via Server-Sent Events."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return StreamingResponse(
        sse_chat_generator(req.query, session_id=req.session_id),
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
    if not os.path.exists(web_file):
        web_file = os.path.join(os.path.dirname(__file__), "..", "public", "index.html")
    if os.path.exists(web_file):
        with open(web_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>DubPilot is running</h1>"
