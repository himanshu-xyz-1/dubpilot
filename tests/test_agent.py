# Tests for DubPilot to make sure everything works properly before deploying.

import pytest
from fastapi.testclient import TestClient

from api.server import app
from agent.engine import DubSupportEngine
from agent.tools import check_domain_dns, verify_webhook_hmac


@pytest.fixture
def client():
    # Helper to send fake HTTP requests to our FastAPI app without running a server
    return TestClient(app)


def test_knowledge_base_loading():
    # Make sure our knowledge base loads all help articles from the JSON file
    engine = DubSupportEngine()
    assert len(engine.articles) >= 8
    categories = set(a.get("category") for a in engine.articles)
    assert "Custom Domains & DNS Configuration" in categories


def test_webhook_hmac_verification():
    # Test that valid webhook signatures return True and fake ones return False
    secret = "whsec_test12345"
    payload = '{"id":"evt_123","event":"link.clicked"}'
    import hmac, hashlib
    valid_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    assert verify_webhook_hmac(payload, valid_sig, secret) is True
    assert verify_webhook_hmac(payload, "invalid_signature", secret) is False


def test_dns_checker():
    # Test that our DNS tool can resolve a real domain name
    res = check_domain_dns("google.com")
    assert "status" in res
    assert "resolved_ips" in res
    assert len(res["resolved_ips"]) > 0


def test_engine_apex_domain_resolution():
    # Test that apex domain questions give Dub's official A record instructions
    engine = DubSupportEngine()
    res = engine.resolve_ticket("How do I configure my apex domain mybrand.com on Dub?")
    assert "76.76.21.21" in res["solution_markdown"]
    assert "A record" in res["solution_markdown"]


def test_engine_cloudflare_525_resolution():
    # Test that Cloudflare 525 questions tell the user to switch to DNS Only (grey cloud)
    engine = DubSupportEngine()
    res = engine.resolve_ticket("My link has Cloudflare Error 525 SSL Handshake Failed")
    assert "Orange Cloud" in res["solution_markdown"]
    assert "DNS Only" in res["solution_markdown"]


def test_api_endpoints(client):
    # 1. Test health endpoint
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"

    # 2. Test standard chat API
    chat_payload = {"query": "How to handle 429 rate limit errors in Python?"}
    r_chat = client.post("/api/chat", json=chat_payload)
    assert r_chat.status_code == 200
    data = r_chat.json()
    assert "solution_markdown" in data
    assert "Retry-After" in data["solution_markdown"]

    # 3. Test streaming API (Server-Sent Events)
    r_stream = client.post("/api/chat/stream", json=chat_payload)
    assert r_stream.status_code == 200
    assert "text/event-stream" in r_stream.headers["content-type"]
    assert "data: " in r_stream.text
    assert "[DONE]" in r_stream.text

    # 4. Test that the web UI HTML loads
    r_ui = client.get("/")
    assert r_ui.status_code == 200
    assert "DubPilot" in r_ui.text

    # 5. Test the DNS check endpoint
    r_dns = client.get("/api/dns?domain=google.com")
    assert r_dns.status_code == 200
    assert "resolved_ips" in r_dns.json()

    # 6. Test the SSL check endpoint
    r_ssl = client.get("/api/ssl?domain=google.com")
    assert r_ssl.status_code == 200
    assert "ssl_active" in r_ssl.json()

    # 7. Test the webhook signature verification endpoint
    wh_payload = {
        "payload": '{"id":"evt_999","event":"link.clicked"}',
        "signature": "mock_invalid_sig",
        "secret": "whsec_test",
    }
    r_wh = client.post("/api/verify-webhook", json=wh_payload)
    assert r_wh.status_code == 200
    assert r_wh.json()["verified"] is False
