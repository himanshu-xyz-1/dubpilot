"""
Dub.co Autonomous Diagnostic Tools
==================================
Deterministic troubleshooting functions that verify DNS records, SSL certificates,
rate limit calculations, and webhook security.
"""

from __future__ import annotations
import hashlib
import hmac
import socket
import ssl
import time
from typing import Any, Dict, List, Optional


def check_domain_dns(domain: str) -> Dict[str, Any]:
    """
    Performs real-time DNS resolution on a domain to diagnose Dub configuration.
    Apex domains should resolve to 76.76.21.21.
    Subdomains should have CNAME targeting cname.dub.co.
    """
    clean_domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    is_subdomain = clean_domain.count(".") > 1 and not clean_domain.startswith("www.")

    report = {
        "domain": clean_domain,
        "is_subdomain": is_subdomain,
        "resolved_ips": [],
        "expected_target": "cname.dub.co" if is_subdomain else "76.76.21.21",
        "status": "UNKNOWN",
        "diagnosis": "",
        "action_required": "",
    }

    try:
        # Resolve IPv4 addresses
        addr_info = socket.getaddrinfo(clean_domain, 80, socket.AF_INET, socket.SOCK_STREAM)
        ips = list(set([item[4][0] for item in addr_info]))
        report["resolved_ips"] = ips

        # Check if resolves to Dub Anycast IP (76.76.21.21)
        if "76.76.21.21" in ips:
            report["status"] = "CORRECT"
            report["diagnosis"] = f"✓ Domain '{clean_domain}' successfully resolves to Dub's Anycast IP (76.76.21.21)."
            report["action_required"] = "No action needed. If SSL is still pending, please allow 5-15 minutes for Let's Encrypt automated issuance."
        else:
            # Check for Cloudflare Anycast IPs (often 104.21.x.x, 172.67.x.x, etc.)
            cf_detected = any(ip.startswith("104.") or ip.startswith("172.") for ip in ips)
            report["status"] = "MISCONFIGURED"
            if cf_detected:
                report["diagnosis"] = f"⚠ Domain resolves to Cloudflare Proxied IPs {ips} instead of Dub directly."
                report["action_required"] = (
                    "In your Cloudflare DNS dashboard, change the proxy toggle for this record from 'Proxied' (Orange Cloud) "
                    "to 'DNS Only' (Grey Cloud). If you must use Cloudflare proxy, set SSL/TLS mode to 'Full' or 'Full (strict)'."
                )
            else:
                report["diagnosis"] = f"✗ Domain currently resolves to {ips}, not Dub's target."
                if is_subdomain:
                    report["action_required"] = f"Add a CNAME record: Name='{clean_domain.split('.')[0]}', Value='cname.dub.co', TTL=86400."
                else:
                    report["action_required"] = "Add an A record: Name='@', Value='76.76.21.21', TTL=86400."

    except socket.gaierror as e:
        report["status"] = "UNRESOLVED"
        report["diagnosis"] = f"✗ DNS resolution failed for '{clean_domain}' (Error: {e}). Record does not exist or has not propagated."
        if is_subdomain:
            report["action_required"] = f"Create a CNAME record with Host/Name='{clean_domain.split('.')[0]}' pointing to 'cname.dub.co'."
        else:
            report["action_required"] = "Create an A record with Host/Name='@' pointing to '76.76.21.21'."

    return report


def check_domain_ssl(domain: str, timeout: float = 3.0) -> Dict[str, Any]:
    """Inspects SSL certificate on port 443 of the target domain."""
    clean_domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    result = {
        "domain": clean_domain,
        "ssl_active": False,
        "issuer": None,
        "not_after": None,
        "error": None,
    }

    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((clean_domain, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=clean_domain) as ssock:
                cert = ssock.getpeercert()
                result["ssl_active"] = True
                result["not_after"] = cert.get("notAfter")
                issuer_components = cert.get("issuer", ())
                for comp in issuer_components:
                    for k, v in comp:
                        if k == "organizationName":
                            result["issuer"] = v
    except Exception as e:
        result["error"] = str(e)
        result["ssl_active"] = False

    return result


def verify_webhook_hmac(payload: str, signature_header: str, secret: str) -> bool:
    """Verifies HMAC SHA-256 signature for Dub.co webhook payloads."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
