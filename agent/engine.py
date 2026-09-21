# Main engine that takes user questions, checks domains, and finds answers from the knowledge base.

from __future__ import annotations
import json
import os
import re
from typing import Dict, List, Any, Optional

from agent.tools import check_domain_dns, check_domain_ssl


class DubSupportEngine:
    """
    Handles user support queries by looking up verified solutions
    and running live DNS/SSL network checks.
    """

    def __init__(self, kb_path: Optional[str] = None):
        # Default path to the knowledge base JSON file
        if kb_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            kb_path = os.path.join(base_dir, "data", "dub_knowledge_base.json")
        
        self.kb_path = kb_path
        self.articles = []
        self._load_knowledge_base()

    def _load_knowledge_base(self):
        # Load all help articles into memory so lookups are fast
        if os.path.exists(self.kb_path):
            with open(self.kb_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for cat in data.get("categories", []):
                for art in cat.get("articles", []):
                    art["category"] = cat.get("title")
                    self.articles.append(art)

    def extract_domain(self, text: str) -> Optional[str]:
        # Finds domain names in user messages using a standard regex
        pattern = r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
        matches = re.findall(pattern, text)
        excluded = ["dub.co", "github.com", "google.com", "cloudflare.com"]
        for m in matches:
            if m.lower() not in excluded and not m.endswith(".png") and not m.endswith(".jpg"):
                return m
        return None

    def search_kb(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        # Scores articles based on matching keywords, title words, and problem description
        q_lower = query.lower()
        scored = []

        for art in self.articles:
            score = 0
            # Exact keyword match gives the highest score
            for kw in art.get("keywords", []):
                if kw in q_lower:
                    score += 5
            # Matching words in title
            for word in art.get("title", "").lower().split():
                if len(word) > 3 and word in q_lower:
                    score += 3
            # Matching words in problem description
            if any(w in q_lower for w in art.get("problem", "").lower().split() if len(w) > 4):
                score += 2

            if score > 0:
                scored.append((score, art))

        # Sort highest score first and return the top matches
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def resolve_ticket(self, user_query: str) -> Dict[str, Any]:
        """
        Main function to answer a support ticket:
        1. Checks if the user mentioned a domain name.
        2. Runs live DNS and SSL checks if needed.
        3. Finds the best match in the knowledge base.
        4. Combines everything into a clear Markdown response.
        """
        clean_query = user_query.strip()
        detected_domain = self.extract_domain(clean_query)
        dns_diag = None

        # If a domain was mentioned alongside DNS or setup keywords, run live network checks
        if detected_domain and any(k in clean_query.lower() for k in ["domain", "cname", "dns", "ssl", "not working", "setup", "link"]):
            dns_diag = check_domain_dns(detected_domain)
            # If SSL or error 525 was mentioned, also check the SSL certificate on port 443
            if any(s in clean_query.lower() for s in ["ssl", "525", "cert", "https"]):
                dns_diag["ssl_info"] = check_domain_ssl(detected_domain)

        # Look up matching articles from our knowledge base
        kb_matches = self.search_kb(clean_query)

        # Build the final answer sections
        response_sections = []

        # 1. Add the Live DNS Telemetry box if a domain was checked
        if dns_diag:
            status_emoji = "✅" if dns_diag["status"] == "CORRECT" else "⚠️"
            telemetry_lines = [
                f"### {status_emoji} Real-Time DNS Telemetry for `{dns_diag['domain']}`\n",
                f"• **Current Resolved IPs:** `{', '.join(dns_diag['resolved_ips']) if dns_diag['resolved_ips'] else 'None (Unresolved)'}`",
                f"• **Expected Target:** `{dns_diag['expected_target']}`",
            ]
            if "ssl_info" in dns_diag:
                ssl_data = dns_diag["ssl_info"]
                ssl_desc = f"✓ Valid TLS Handshake (Issuer: {ssl_data.get('issuer') or 'Active'})" if ssl_data.get("ssl_active") else f"✗ TLS Handshake Error ({ssl_data.get('error') or 'Unreachable'})"
                telemetry_lines.append(f"• **Port 443 SSL Probe:** `{ssl_desc}`")
            telemetry_lines.append(f"• **Live Diagnosis:** {dns_diag['diagnosis']}")
            telemetry_lines.append(f"• **Action Required:** {dns_diag['action_required']}\n")
            response_sections.append("\n".join(telemetry_lines))

        # 2. Add the verified solution from the knowledge base
        if kb_matches:
            top_article = kb_matches[0]
            response_sections.append(
                f"### 📘 Solution: {top_article['title']}\n\n"
                f"{top_article['solution']}\n"
            )
            # Mention any other related articles
            if len(kb_matches) > 1:
                response_sections.append(
                    f"**Related Topics:**\n" +
                    "\n".join([f"• *{a['title']}*" for a in kb_matches[1:]]) + "\n"
                )
        else:
            # Friendly greeting fallback
            if any(w in clean_query.lower() for w in ["hi", "hello", "hey"]):
                response_sections.append(
                    "Hello! I am **DubPilot**, your autonomous technical support co-pilot for Dub.co. I can help you with:\n"
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
            "articles_referenced": [a["id"] for a in kb_matches],
        }
