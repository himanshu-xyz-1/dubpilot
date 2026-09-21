"""
Dub.co AI Customer Support & Autonomous Triage Engine
====================================================
Combines indexed knowledge base search with real-time deterministic
diagnostic tools (DNS & SSL verification) to deliver instant support resolution.
"""

from __future__ import annotations
import json
import os
import re
from typing import Dict, List, Any, Optional

from agent.tools import check_domain_dns, check_domain_ssl, verify_webhook_hmac


class DubSupportEngine:
    """Autonomous customer support resolution engine for Dub.co."""

    def __init__(self, kb_path: Optional[str] = None):
        if kb_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            kb_path = os.path.join(base_dir, "data", "dub_knowledge_base.json")
        
        self.kb_path = kb_path
        self.articles = []
        self._load_knowledge_base()

    def _load_knowledge_base(self):
        if os.path.exists(self.kb_path):
            with open(self.kb_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for cat in data.get("categories", []):
                for art in cat.get("articles", []):
                    art["category"] = cat.get("title")
                    self.articles.append(art)

    def extract_domain(self, text: str) -> Optional[str]:
        """Extracts candidate domain names from query string."""
        pattern = r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
        matches = re.findall(pattern, text)
        excluded = ["dub.co", "github.com", "google.com", "cloudflare.com"]
        for m in matches:
            if m.lower() not in excluded and not m.endswith(".png") and not m.endswith(".jpg"):
                return m
        return None

    def search_kb(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Finds most relevant knowledge base articles for a query."""
        q_lower = query.lower()
        scored = []

        for art in self.articles:
            score = 0
            # Check keywords
            for kw in art.get("keywords", []):
                if kw in q_lower:
                    score += 5
            # Check title
            for word in art.get("title", "").lower().split():
                if len(word) > 3 and word in q_lower:
                    score += 3
            # Check problem description
            if any(w in q_lower for w in art.get("problem", "").lower().split() if len(w) > 4):
                score += 2

            if score > 0:
                scored.append((score, art))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def resolve_ticket(self, user_query: str) -> Dict[str, Any]:
        """
        Executes end-to-end autonomous support resolution:
        1. Identifies if a specific domain is mentioned.
        2. Executes real-time live DNS diagnostic if domain detected.
        3. Retrieves relevant knowledge base articles.
        4. Synthesizes a developer-ready resolution.
        """
        clean_query = user_query.strip()
        detected_domain = self.extract_domain(clean_query)
        dns_diag = None

        if detected_domain and any(k in clean_query.lower() for k in ["domain", "cname", "dns", "ssl", "not working", "setup", "link"]):
            dns_diag = check_domain_dns(detected_domain)

        # Retrieve relevant KB articles
        kb_matches = self.search_kb(clean_query)

        # Build structured resolution response
        response_sections = []

        # 1. Real-time Live DNS Diagnostic Box (if domain present)
        if dns_diag:
            status_emoji = "✅" if dns_diag["status"] == "CORRECT" else "⚠️"
            response_sections.append(
                f"### {status_emoji} Real-Time DNS Telemetry for `{dns_diag['domain']}`\n\n"
                f"• **Current Resolved IPs:** `{', '.join(dns_diag['resolved_ips']) if dns_diag['resolved_ips'] else 'None (Unresolved)'}`\n"
                f"• **Expected Target:** `{dns_diag['expected_target']}`\n"
                f"• **Live Diagnosis:** {dns_diag['diagnosis']}\n"
                f"• **Action Required:** {dns_diag['action_required']}\n"
            )

        # 2. Knowledge Base Article Solution
        if kb_matches:
            top_article = kb_matches[0]
            response_sections.append(
                f"### 📘 Solution: {top_article['title']}\n\n"
                f"{top_article['solution']}\n"
            )
            # Add secondary helpful articles if applicable
            if len(kb_matches) > 1:
                response_sections.append(
                    f"**Related Topics:**\n" +
                    "\n".join([f"• *{a['title']}*" for a in kb_matches[1:]]) + "\n"
                )
        else:
            # Fallback for general greetings or unrecognized queries
            if any(w in clean_query.lower() for w in ["hi", "hello", "hey"]):
                response_sections.append(
                    "Hello! I am the **Dub.co Support AI Assistant**. I can help you with:\n"
                    "• Custom Domain DNS setup (Apex A record or Subdomain CNAME)\n"
                    "• Cloudflare SSL 525 & ERR_SSL_PROTOCOL_ERROR fixes\n"
                    "• API rate limits, 429 backoff & SDK link creation\n"
                    "• Webhook HMAC signature verification\n\n"
                    "Tell me what you're trying to set up or provide your custom domain!"
                )
            else:
                response_sections.append(
                    f"Regarding your query: *'{clean_query}'*\n\n"
                    "Could you specify if this is related to **Custom Domain DNS**, **API link creation**, **Rate limits**, or **Webhooks**? "
                    "If you share your domain name (e.g. `links.yourcompany.com`), I will run a live DNS inspection right now."
                )

        final_text = "\n".join(response_sections)
        return {
            "query": user_query,
            "detected_domain": detected_domain,
            "dns_diagnostic": dns_diag,
            "solution_markdown": final_text,
            "matched_articles_count": len(kb_matches),
        }
