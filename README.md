# ⚡ Dub.co AI Customer Support & Autonomous DNS Triage Co-Pilot

> **Autonomous L1/L2 Technical Support Agent & Live DNS Diagnostic Engine built specifically for Dub.co.**  
> Designed and engineered by **Himanshu Joshi (`himanshu-xyz-1`)**.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tailwind CSS](https://img.shields.io/badge/UI-Tailwind%20CSS-38B2AC.svg)](https://tailwindcss.com/)
[![Tests Passing](https://img.shields.io/badge/tests-6%2F6%20passing-brightgreen.svg)]()

---

## 🌟 The Problem & The Solution

At **Dub.co**, an ultra-lean team (<15 people) powers hundreds of millions of link clicks. Because Dub has no massive tier-1 support department, founding engineers frequently jump in to debug developer tickets:
- **Custom Domain DNS Misconfigurations:** CNAME targets not pointing to `cname.dub.co`, or Apex A records missing `76.76.21.21`.
- **Cloudflare 525 Handshake & SSL Errors:** Users leaving Cloudflare Proxy on (Orange Cloud) without Full SSL encryption.
- **API & Rate Limits:** Developers hitting 429 Too Many Requests without knowing how to read `Retry-After` headers or use bulk link creation.
- **Webhook Security:** Implementing and debugging HMAC SHA-256 signature verification.

### 💡 What This Agent Does:
1. **Live DNS Telemetry Tool:** Directly resolves the user's domain in real-time, determines whether it's an Apex or Subdomain, detects Cloudflare proxying, and gives the exact, copy-paste DNS record fix.
2. **Deterministic RAG Knowledge Engine:** Pre-indexed with official Dub.co error resolution playbooks.
3. **Interactive Dark-Mode UI:** Built with a clean aesthetic matching Dub.co's exact design language.

---

## 🏗️ Architecture

```
User Prompt (e.g. "go.mybrand.com is showing SSL error")
                   │
                   ▼
┌────────────────────────────────────────────────────────────┐
│                  DUB SUPPORT ENGINE (RAG)                  │
│                                                            │
│  1. Domain Detection Regex                                 │
│  2. Deterministic Tool Execution                           │
│     ├── check_domain_dns(domain) ➔ Live socket resolution  │
│     └── check_domain_ssl(domain) ➔ Port 443 handshake      │
│  3. Knowledge Base Matching (data/dub_knowledge_base.json) │
└──────────────────────────┬─────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────┐
│                    SYNTHESIZED RESPONSE                    │
│                                                            │
│  • Live DNS Telemetry Box (Resolved IPs, Target, Status)   │
│  • Root Cause Diagnosis (e.g. Cloudflare Orange Cloud)     │
│  • Exact Remediation Steps (Table / CLI commands)          │
└────────────────────────────────────────────────────────────┘
```

---

## ⚡ Quickstart

```bash
cd /home/himanshu/projects/dub-ai-agent

# Run automated tests
pytest tests/ -v

# Launch the interactive server & UI
python run.py
```
Open **[http://localhost:8080](http://localhost:8080)** in your browser!

---

## 📁 Repository Structure

```
dub-ai-agent/
├── agent/
│   ├── engine.py             # Autonomous triage & KB retrieval engine
│   └── tools.py              # Live DNS resolution, SSL handshake, HMAC tools
├── api/
│   └── server.py             # FastAPI REST endpoints & UI router
├── data/
│   └── dub_knowledge_base.json # Official Dub troubleshooting playbooks
├── web/
│   └── index.html            # Dark-mode Tailwind client
├── tests/
│   └── test_agent.py         # Pytest verification suite (100% passing)
├── PITCH_TO_STEVEN.md        # Cold email, Twitter DM, and 60-sec Loom script
├── run.py                    # Server launcher
└── README.md
```

---

## 📜 License
MIT License. Created with pride by **Himanshu Joshi**.
