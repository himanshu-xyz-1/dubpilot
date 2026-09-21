# Main engine that takes user questions, checks domains, and finds answers from the knowledge base.

from __future__ import annotations
import json
import os
import re
from typing import Dict, List, Any, Optional

from agent.tools import check_domain_dns, check_domain_ssl
from agent.llm import OllamaLLM


class DubSupportEngine:
    """
    Handles user support queries by combining live DNS/SSL network checks,
    curated Dub.co troubleshooting playbooks, and local LLaMA 3.2 reasoning via Ollama.
    """

    def __init__(self, kb_path: Optional[str] = None):
        # Default path to the knowledge base JSON file
        if kb_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            kb_path = os.path.join(base_dir, "data", "dub_knowledge_base.json")
        
        self.kb_path = kb_path
        self.articles = []
        self._load_knowledge_base()
        self.llm = OllamaLLM()

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
        # Normalize common typos and abbreviations
        q_norm = query.lower()
        replacements = {
            "shortning": "shortening",
            "agter": "after",
            "faling": "failing",
            "redir": "redirect",
            "cant": "can not",
            "isnt": "is not",
        }
        for wrong, right in replacements.items():
            q_norm = q_norm.replace(wrong, right)

        scored = []
        is_troubleshooting_query = any(w in q_norm for w in ["not working", "broken", "failed", "failing", "error", "404", "500", "525", "down", "issue"])

        for art in self.articles:
            score = 0
            art_title_lower = art.get("title", "").lower()
            art_prob_lower = art.get("problem", "").lower()

            # 1. Exact phrase keyword matching
            for kw in art.get("keywords", []):
                if kw in q_norm:
                    # Multi-word phrase matches are strong intent indicators
                    score += 8 if " " in kw else 4

            # 2. Matching title words
            for word in art_title_lower.split():
                if len(word) > 3 and word in q_norm:
                    score += 3

            # 3. Matching problem description
            for word in art_prob_lower.split():
                if len(word) > 4 and word in q_norm:
                    score += 2

            # 4. Intent alignment: penalize tutorial/creation articles if query is an error/broken link report
            if is_troubleshooting_query:
                if "create" in art_title_lower or "api & sdk" in art_title_lower:
                    score -= 8
                if "troubleshooting" in art_title_lower or "failing" in art_title_lower or "error" in art_title_lower:
                    score += 10

            if score > 0:
                scored.append((score, art))

        # Sort highest score first and return top matches
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def check_guardrail(self, query: str) -> Optional[str]:
        """
        Fast pre-LLM security and scope filter.
        Blocks jailbreaks and out-of-scope requests before wasting LLM compute.
        """
        q_lower = query.lower().strip()

        # 1. Jailbreak and Prompt Injection Attempts
        jailbreak_triggers = [
            "ignore previous instructions",
            "ignore all instructions",
            "disregard previous",
            "disregard all instructions",
            "ignore your rules",
            "you are now dan",
            "pretend you are chatgpt",
            "act as an unrestricted ai",
            "ignore system prompt",
            "jailbreak mode",
        ]
        if any(trig in q_lower for trig in jailbreak_triggers):
            return (
                "### ⚠️ Security Guardrail Notice\n\n"
                "I am **DubPilot**, dedicated exclusively to **Dub.co** infrastructure, custom domain DNS, and link attribution.\n\n"
                "System instructions and scope boundaries cannot be overridden or modified. "
                "How can I assist you with your Dub.co links, custom domains, or API setup?"
            )

        # 2. Obvious Out-of-Scope Requests (creative writing, homework, recipes, etc.)
        out_of_scope_triggers = [
            "write a poem", "write a story", "write an essay", "write lyrics", "write a script",
            "tell me a joke", "recipe for", "how to bake", "how to cook",
            "solve for x", "solve equation", "calculus",
            "who is the president", "capital of", "weather today", "translate this to",
        ]
        if any(trig in q_lower for trig in out_of_scope_triggers):
            return (
                "### 🔒 Scope Boundary Notice\n\n"
                "I am **DubPilot**, an autonomous technical support engineer specialized exclusively for **Dub.co** infrastructure.\n\n"
                "My domain is strictly focused on:\n"
                "• Custom Domain DNS routing (Apex A records `76.76.21.21` & Subdomain CNAMEs `cname.dub.co`)\n"
                "• SSL/TLS troubleshooting (Cloudflare 525 & Let's Encrypt certificates)\n"
                "• Dub REST APIs, Python/TypeScript SDKs, & 429 rate limit backoff\n"
                "• Webhook HMAC SHA-256 verification\n"
                "• Short link expiration, QR codes, & click analytics\n\n"
                "I cannot assist with general creative writing, homework, or general trivia. "
                "Please let me know if you have any questions regarding your Dub.co short links or domains!"
            )

        return None

    def _build_telemetry_markdown(self, dns_diag: Dict[str, Any]) -> str:
        # Formats live DNS and SSL socket probe results into a clean markdown box
        status_emoji = "✅" if dns_diag["status"] == "CORRECT" else "⚠️"
        lines = [
            f"### {status_emoji} Real-Time DNS Telemetry for `{dns_diag['domain']}`\n",
            f"• **Current Resolved IPs:** `{', '.join(dns_diag['resolved_ips']) if dns_diag['resolved_ips'] else 'None (Unresolved)'}`",
            f"• **Expected Target:** `{dns_diag['expected_target']}`",
        ]
        if "ssl_info" in dns_diag:
            ssl_data = dns_diag["ssl_info"]
            ssl_desc = f"✓ Valid TLS Handshake (Issuer: {ssl_data.get('issuer') or 'Active'})" if ssl_data.get("ssl_active") else f"✗ TLS Handshake Error ({ssl_data.get('error') or 'Unreachable'})"
            lines.append(f"• **Port 443 SSL Probe:** `{ssl_desc}`")
        lines.append(f"• **Live Diagnosis:** {dns_diag['diagnosis']}")
        lines.append(f"• **Action Required:** {dns_diag['action_required']}\n")
        return "\n".join(lines)

    def _build_system_prompt(self, kb_matches: List[Dict[str, Any]], dns_diag: Optional[Dict[str, Any]] = None) -> str:
        # Injects verified playbooks, strict scope boundaries, and telemetry into LLaMA 3.2
        kb_context = "\n\n".join([f"### {a['title']}\n{a['solution']}" for a in kb_matches[:3]])
        telemetry_txt = ""
        if dns_diag:
            telemetry_txt = (
                f"\nLIVE TELEMETRY RESULT:\n"
                f"Domain: {dns_diag['domain']}\n"
                f"Status: {dns_diag['status']}\n"
                f"Resolved IPs: {dns_diag['resolved_ips']}\n"
                f"Diagnosis: {dns_diag['diagnosis']}\n"
                f"Action Required: {dns_diag['action_required']}\n"
            )

        return (
            "You are DubPilot, the dedicated AI Technical Support Engineer for Dub.co.\n\n"
            "STRICT SCOPE BOUNDARY:\n"
            "You ONLY answer questions about Dub.co infrastructure, link shortening, custom domain DNS (A record 76.76.21.21, CNAME cname.dub.co), SSL errors (Cloudflare 525, Let's Encrypt), Dub REST APIs/SDKs, webhooks, analytics, and self-hosting.\n\n"
            "REFUSAL POLICY:\n"
            "If the user asks about ANYTHING outside Dub.co (such as general knowledge, history, recipes, math/homework, general coding unrelated to Dub, creative writing, or chit-chat), you MUST politely refuse and state that you are specialized exclusively in Dub.co link infrastructure.\n\n"
            "OFFICIAL DUB TECHNICAL SPECIFICATIONS:\n"
            "- Apex / Root domains: A Record pointing to 76.76.21.21.\n"
            "- Subdomains: CNAME record pointing to cname.dub.co.\n"
            "- Cloudflare Proxy: Grey Cloud (DNS Only) recommended, or SSL mode Full (Strict).\n"
            "- Rate Limits: Free=60/min, Pro=600/min, Business=1200/min. For batch, use POST /links/bulk.\n"
            "- Webhook verification: HMAC-SHA256 with Dub-Signature header.\n"
            "- Structure your answer with clean Markdown, bold headings, and bullet points.\n\n"
            f"VERIFIED DUB PLAYBOOKS:\n{kb_context}\n"
            f"{telemetry_txt}"
        )

    def resolve_ticket(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        Answers a support ticket using LLaMA 3.2 via Ollama with verified grounding.
        Falls back to deterministic knowledge base resolution if Ollama is offline.
        """
        clean_query = user_query.strip()

        # Security & Scope Guardrail check
        guardrail_block = self.check_guardrail(clean_query)
        if guardrail_block:
            return {
                "query": user_query,
                "session_id": session_id,
                "detected_domain": None,
                "dns_diagnostic": None,
                "solution_markdown": guardrail_block,
                "articles_referenced": [],
                "engine_used": "security_scope_guardrail",
            }

        detected_domain = self.extract_domain(clean_query)
        dns_diag = None

        # Live network probe
        if detected_domain and any(k in clean_query.lower() for k in ["domain", "cname", "dns", "ssl", "not working", "setup", "link"]):
            dns_diag = check_domain_dns(detected_domain)
            if any(s in clean_query.lower() for s in ["ssl", "525", "cert", "https"]):
                dns_diag["ssl_info"] = check_domain_ssl(detected_domain)

        kb_matches = self.search_kb(clean_query)
        telemetry_md = self._build_telemetry_markdown(dns_diag) if dns_diag else ""

        # Try generating via LLaMA 3.2 if available
        if use_llm and self.llm.is_available():
            system_prompt = self._build_system_prompt(kb_matches, dns_diag)
            history = self.llm.memory.get_history(session_id or "")
            messages = list(history) + [{"role": "user", "content": clean_query}]

            llm_text = self.llm.generate(messages, system_prompt=system_prompt)
            if llm_text:
                self.llm.memory.add_turn(session_id or "", clean_query, llm_text)
                final_text = f"{telemetry_md}\n\n{llm_text}".strip() if telemetry_md else llm_text
                return {
                    "query": user_query,
                    "session_id": session_id,
                    "detected_domain": detected_domain,
                    "dns_diagnostic": dns_diag,
                    "solution_markdown": final_text,
                    "articles_referenced": [a["id"] for a in kb_matches],
                    "engine_used": "llama3.2:3b (ollama)",
                }

        # Deterministic Fallback if Ollama is offline or generation failed
        response_sections = []
        if telemetry_md:
            response_sections.append(telemetry_md)

        if kb_matches:
            top_article = kb_matches[0]
            response_sections.append(
                f"### 📘 Solution: {top_article['title']}\n\n"
                f"{top_article['solution']}\n"
            )
            if len(kb_matches) > 1:
                response_sections.append(
                    f"**Related Topics:**\n" +
                    "\n".join([f"• *{a['title']}*" for a in kb_matches[1:]]) + "\n"
                )
        else:
            if any(w in clean_query.lower() for w in ["hi", "hello", "hey"]):
                response_sections.append(
                    "Hello! I am **DubPilot**, your autonomous technical support engineer for Dub.co. I can help you with:\n"
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
            "session_id": session_id,
            "detected_domain": detected_domain,
            "dns_diagnostic": dns_diag,
            "solution_markdown": final_text,
            "articles_referenced": [a["id"] for a in kb_matches],
            "engine_used": "deterministic_kb_fallback",
        }

    async def stream_ticket(
        self,
        user_query: str,
        session_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Asynchronously streams the response tokens in real-time.
        Streams telemetry status first, then streams LLaMA 3.2 tokens live.
        """
        import asyncio
        clean_query = user_query.strip()

        # Security & Scope Guardrail check
        guardrail_block = self.check_guardrail(clean_query)
        if guardrail_block:
            yield guardrail_block
            return

        detected_domain = self.extract_domain(clean_query)
        dns_diag = None

        if detected_domain and any(k in clean_query.lower() for k in ["domain", "cname", "dns", "ssl", "not working", "setup", "link"]):
            dns_diag = check_domain_dns(detected_domain)
            if any(s in clean_query.lower() for s in ["ssl", "525", "cert", "https"]):
                dns_diag["ssl_info"] = check_domain_ssl(detected_domain)

        kb_matches = self.search_kb(clean_query)
        telemetry_md = self._build_telemetry_markdown(dns_diag) if dns_diag else ""

        # Yield telemetry badge immediately if present
        if telemetry_md:
            yield f"{telemetry_md}\n\n"

        # Stream via LLaMA if available
        if self.llm.is_available():
            system_prompt = self._build_system_prompt(kb_matches, dns_diag)
            history = self.llm.memory.get_history(session_id or "")
            messages = list(history) + [{"role": "user", "content": clean_query}]

            full_llm_text = ""
            async for token in self.llm.stream_chat(messages, system_prompt=system_prompt):
                full_llm_text += token
                yield token

            if full_llm_text:
                self.llm.memory.add_turn(session_id or "", clean_query, full_llm_text)
                return

        # Fallback: stream deterministic response word by word
        fallback_res = self.resolve_ticket(clean_query, session_id=session_id, use_llm=False)
        content = fallback_res["solution_markdown"]
        # Skip telemetry if we already yielded it above
        if telemetry_md and content.startswith(telemetry_md):
            content = content[len(telemetry_md):].strip()

        words = content.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield chunk
            await asyncio.sleep(0.012)

