# DubPilot

> Autonomous Technical Support & Live DNS Diagnostic Engine for [Dub.co](https://dub.co).  
> **Live Demo:** [dubpilot.vercel.app](https://dubpilot.vercel.app) • **Source Code:** [github.com/himanshu-xyz-1/dubpilot](https://github.com/himanshu-xyz-1/dubpilot)  
> Engineered by **Himanshu Joshi ([@himanshu-xyz-1](https://github.com/himanshu-xyz-1))**.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://www.python.org/downloads/)
[![Groq LPU](https://img.shields.io/badge/LLM-Groq%20Cloud-orange.svg)](https://groq.com/)
[![Ollama Fallback](https://img.shields.io/badge/Fallback-Local%20Ollama-blue.svg)](https://ollama.ai/)
[![Tests](https://img.shields.io/badge/tests-10%2F10%20passing-brightgreen.svg)]()
[![Docker](https://img.shields.io/badge/Docker-Multi--stage-2496ED.svg?logo=docker&logoColor=white)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

[Dub.co](https://dub.co) is a high-scale link attribution platform serving hundreds of millions of clicks every month with a compact core team. A significant portion of developer support questions in community channels and issue trackers center around infrastructure edge cases:

1. **Custom Domain DNS Configuration:** Subdomains not pointing to `cname.dub.co`, or apex domains missing the Anycast `A` record (`76.76.21.21`).
2. **Cloudflare Proxy & SSL Handshakes:** Proxied (orange-cloud) setups triggering `Error 525: SSL Handshake Failed` due to origin encryption mismatches.
3. **Webhook Security & HMAC:** Signature mismatch debugging on `link.clicked` and `link.created` event streams.
4. **Base62 Slug Case-Sensitivity:** Queries regarding case-sensitive short link routing and root domain 404 redirects.

**DubPilot** is a dedicated diagnostic backend and chat interface designed to troubleshoot these problems automatically. Instead of returning generic documentation snippets, DubPilot **actively probes the user's domain over network sockets**, checks live DNS records and SSL handshakes, and provides exact, copy-paste remediation steps.

---

## Product Integration: Where DubPilot Fits in Dub.co

DubPilot is architected to integrate into Dub's existing developer touchpoints:

```
                          ┌────────────────────────────────────────────────────────┐
                          │                   Dub.co Touchpoints                   │
                          └──────────────────────────┬─────────────────────────────┘
                                                     │
               ┌─────────────────────────────────────┼─────────────────────────────────────┐
               │                                     │                                     │
               ▼                                     ▼                                     ▼
 ┌───────────────────────────┐         ┌───────────────────────────┐         ┌───────────────────────────┐
 │   Dashboard Domain Tab    │         │     Webhook Playground    │         │  Community Support Bot    │
 │ (dub.co/settings/domains) │         │(dub.co/settings/webhooks) │         │  (Discord / Slack / GH)   │
 │                           │         │                           │         │                           │
 │ Embedded self-serve DNS   │         │ Interactive HMAC-SHA256   │         │ Autonomous triage bot     │
 │ diagnostic widget to test │         │ payload validator for     │         │ that runs live socket     │
 │ failing records in-place. │         │ developer event debugging.│         │ probes on shared domains. │
 └─────────────┬─────────────┘         └─────────────┬─────────────┘         └─────────────┬─────────────┘
               │                                     │                                     │
               └─────────────────────────────────────┼─────────────────────────────────────┘
                                                     │
                                                     ▼
                                   ┌───────────────────────────────────┐
                                   │      DubPilot Core Engine         │
                                   │ (FastAPI + DNS Sockets + Fallback)│
                                   └───────────────────────────────────┘
```

1. **In-Dashboard Domain Diagnostic Widget:** Embedded inside `dub.co/dashboard/settings/domains`. When a custom domain fails verification, users can click "Diagnose Domain" to immediately run socket checks against Dub's Anycast IP (`76.76.21.21`) or CNAME (`cname.dub.co`).
2. **Developer Webhook Testing Playground:** Embedded inside `dub.co/dashboard/settings/webhooks` to validate signatures and debug payload delivery in Node.js, Python, or Go.
3. **Automated First-Responder Bot:** Connected to Dub's community Discord and GitHub Discussions to parse user queries, execute non-invasive DNS probes, and provide immediate setup instructions.

---

## Architecture & Provider Fallback

DubPilot uses a three-tier execution hierarchy to ensure high availability:

```
                            POST /api/chat/stream
                                      │
                                      ▼
                      ┌─────────────────────────────────┐
                      │  Security & Pre-Filter Layer    │
                      │  • Injection / scope checks     │
                      │  • Regex domain extraction      │
                      └───────────────┬─────────────────┘
                                      │
                                      ▼
                      ┌─────────────────────────────────┐
                      │    Live Telemetry Subsystem     │
                      │  • socket.getaddrinfo() (DNS)   │
                      │  • Port 443 TLS handshake probe │
                      │  • Webhook HMAC-SHA256 verifier │
                      └───────────────┬─────────────────┘
                                      │
                                      ▼
                      ┌─────────────────────────────────┐
                      │   Multi-Tier Provider Engine    │
                      │                                 │
                      │  Tier 1: Groq Cloud (120B model)│
                      │    │ (on timeout/outage)        │
                      │    ▼                            │
                      │  Tier 2: Local Ollama (LLaMA 3.2│
                      │    │ (if offline)               │
                      │    ▼                            │
                      │  Tier 3: Deterministic Playbook │
                      └───────────────┬─────────────────┘
                                      │
                                      ▼
                      ┌─────────────────────────────────┐
                      │  SSE Token Streaming Generator  │
                      │      (text/event-stream)        │
                      └─────────────────────────────────┘
```

* **Tier 1 (Primary):** Groq Cloud running `openai/gpt-oss-120b` for low-latency token streaming.
* **Tier 2 (Edge / Local Fallback):** Local Ollama running `llama3.2:3b` for offline inference.
* **Tier 3 (Offline Deterministic):** Rule-based synthesis using Dub's verified knowledge base when no LLM provider is reachable.
* **Failover Simulation:** Built-in developer endpoint (`POST /api/dev/simulate`) to test provider transitions without dropping active connections.

---

## Knowledge Base Grounding & Verification

DubPilot's response synthesizer is grounded in **38 structured playbooks** indexed in `data/dub_knowledge_base.json`. Each playbook was verified against official [Dub.co Documentation](https://dub.co/docs):

### Representative Playbook Examples

```json
// Example 1: Apex Domain Routing (Verified against dub.co/docs/custom-domains)
{
  "id": "custom_domain_apex_a_record",
  "title": "Apex / Root Custom Domain Configuration",
  "problem": "How to configure a root apex domain (e.g. brand.com) with Dub?",
  "required_record": {
    "type": "A",
    "host": "@",
    "value": "76.76.21.21",
    "purpose": "Points apex traffic directly to Dub's global Anycast routing edge"
  }
}
```

```json
// Example 2: Subdomain Configuration (Verified against dub.co/docs/custom-domains)
{
  "id": "custom_domain_subdomain_cname",
  "title": "Subdomain CNAME Routing",
  "problem": "How to configure a subdomain (e.g. links.brand.com, go.brand.com)?",
  "required_record": {
    "type": "CNAME",
    "host": "links (or subdomain prefix)",
    "value": "cname.dub.co",
    "purpose": "Routes subdomain requests to Dub's multi-tenant ingress"
  }
}
```

```json
// Example 3: Cloudflare Proxy SSL Handshake (Verified against dub.co/docs/custom-domains/cloudflare)
{
  "id": "cloudflare_proxy_status",
  "title": "Cloudflare Proxy 525 Handshake Troubleshooting",
  "problem": "Cloudflare Error 525 (SSL Handshake Failed) on custom domain.",
  "resolution": "Set Cloudflare SSL/TLS encryption mode to 'Full' or 'Full (Strict)', or toggle proxy status to DNS-Only (Grey Cloud) to let Dub provision native Let's Encrypt certificates."
}
```

---

## Live Diagnostics Engine (`agent/tools.py`)

DubPilot includes three diagnostic tools:

1. **DNS Record Inspection (`check_domain_dns`):**
   * Resolves `A` and `CNAME` records using raw socket lookups.
   * Compares resolved targets against Dub's Anycast IP (`76.76.21.21`) and CNAME (`cname.dub.co`).
   * Detects whether Cloudflare Proxying (Orange Cloud) is active on the domain.

2. **SSL Handshake Probe (`check_domain_ssl`):**
   * Establishes a TLS connection to port 443 of the target domain.
   * Inspects certificate subject and validity to identify provisioning delays or expired certificates.

3. **Webhook HMAC Cryptography (`verify_webhook_hmac`):**
   * Implements constant-time SHA-256 HMAC verification (`hmac.compare_digest`) to validate webhook signatures from Dub event notifications without timing vulnerability risks.

---

## Limitations & Operational Scope

| Category | In Scope | Out of Scope |
| :--- | :--- | :--- |
| **DNS & Networking** | Apex `A` records (`76.76.21.21`), Subdomain `CNAME` (`cname.dub.co`), Cloudflare 525 errors, SSL port 443 checks. | Modifying registrar DNS records on the user's behalf (requires user access to their DNS provider). |
| **Link Configuration** | Base62 case sensitivity, 404 default redirects, mobile deep linking (`apple-app-site-association`), UTM parameters. | Inspecting private analytics databases or customer click history. |
| **Developer APIs** | HTTP 429 rate limit backoff strategies, pagination, HMAC-SHA256 signature verification code. | Generating or revoking live production API keys. |
| **Account & Billing** | General feature availability, pricing tier limits from public docs. | Private account access, invoice disputes, workspace deletion (deferred to `support@dub.co`). |

---

## Quickstart & Local Setup

### 1. Prerequisites
- Python 3.10+
- Optional: [Groq API Key](https://console.groq.com) for cloud inference
- Optional: [Ollama](https://ollama.ai) with `llama3.2:3b` for local offline fallback

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/himanshu-xyz-1/dubpilot.git
cd dubpilot

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration (Optional)

Create a `.env` file in the root directory:
```bash
GROQ_API_KEY=gsk_your_groq_api_key_here
```
*(If no API key is set, DubPilot automatically falls back to local Ollama or deterministic playbook resolution).*

### 4. Run Automated Tests

```bash
pytest tests/ -v
```

**Test Suite Scope (10 Tests):**
* Knowledge base schema integrity and article count
* Broken link diagnostic matching
* Constant-time HMAC-SHA256 webhook signature validation
* Real socket DNS resolution
* Apex A-record (`76.76.21.21`) configuration responses
* Cloudflare Error 525 troubleshooting output
* REST & SSE streaming API endpoints (`/health`, `/api/chat`, `/api/chat/stream`, `/api/dns`, `/api/ssl`, `/api/verify-webhook`)
* Real GitHub issue scenario resolutions (slugs, deep links, Docker self-hosting, CSV export)
* Security guardrails and out-of-scope prompt filtering
* Provider failover simulation and state manipulator (`/api/dev/simulate`)

### 5. Start the Server

```bash
# Native Python
python run.py

# Or with Docker
docker build -t dubpilot:latest .
docker run -p 8080:8080 dubpilot:latest
```

Open **[http://localhost:8080](http://localhost:8080)** in your browser.

---

## API Reference

### 1. Real-Time Token Streaming (SSE)
- **Endpoint:** `POST /api/chat/stream`
- **Headers:** `Content-Type: application/json`

```bash
curl -N -X POST http://localhost:8080/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "my domain links.acmecorp.com is showing Cloudflare 525 error", "session_id": "sess_demo"}'
```

### 2. Standard JSON Chat
- **Endpoint:** `POST /api/chat`

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I configure my apex domain mycompany.com?"}'
```

### 3. Failover Simulation
- **Endpoint:** `POST /api/dev/simulate`

```bash
# Toggle simulated provider outage
curl -X POST http://localhost:8080/api/dev/simulate \
  -H "Content-Type: application/json" \
  -d '{"simulate_groq_failure": true}'
```

### 4. Direct DNS Telemetry
- **Endpoint:** `GET /api/dns?domain=links.dub.sh`

```bash
curl -s "http://localhost:8080/api/dns?domain=links.dub.sh"
```

---

## Project Structure

```
dubpilot/
├── agent/
│   ├── engine.py             # Diagnostic triage, domain extraction, RAG & guardrails
│   ├── llm.py                # Multi-tier provider routing (Groq, Ollama, Playbook)
│   └── tools.py              # DNS socket resolver, SSL port 443 probe & HMAC verifier
├── api/
│   ├── server.py             # FastAPI REST & SSE streaming routes
│   └── index.py              # Vercel serverless entrypoint
├── data/
│   └── dub_knowledge_base.json # 38 verified Dub.co troubleshooting playbooks
├── web/
│   └── index.html            # Dub-styled web interface with live streaming
├── tests/
│   └── test_agent.py         # 10 automated test suites
├── Dockerfile                # Production multi-stage container build
├── docker-compose.yml        # Docker execution with host network bridge
├── requirements.txt          # Python dependencies
├── pytest.ini                # Pytest configuration
├── vercel.json               # Vercel deployment routing
└── README.md                 # Project documentation
```

---

## Author

**Himanshu Joshi** ([@himanshu-xyz-1](https://github.com/himanshu-xyz-1))  
- GitHub: [https://github.com/himanshu-xyz-1](https://github.com/himanshu-xyz-1)  
- Repository: [https://github.com/himanshu-xyz-1/dubpilot](https://github.com/himanshu-xyz-1/dubpilot)  
- Live Deployment: [https://dubpilot.vercel.app](https://dubpilot.vercel.app)

---

## License

MIT License. Free to use, modify, and distribute.
