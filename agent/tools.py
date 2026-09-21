# Network helper tools to check DNS, test SSL certificates, and verify webhooks.

from __future__ import annotations
import hashlib
import hmac
import socket
import ssl
from typing import Any, Dict, List, Optional


def check_domain_dns(domain: str) -> Dict[str, Any]:
    """
    Checks if a domain's DNS is pointing to Dub.co correctly.
    - Main domains (like acme.com) need an A record pointing to 76.76.21.21.
    - Subdomains (like links.acme.com) need a CNAME pointing to cname.dub.co.
    """
    # Remove http://, https://, and paths to get just the domain name
    clean_domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    
    # Subdomains have more than one dot (e.g. go.brand.com vs brand.com)
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
        # Ask the operating system to resolve the domain's IPv4 address
        addr_info = socket.getaddrinfo(clean_domain, 80, socket.AF_INET, socket.SOCK_STREAM)
        ips = list(set([item[4][0] for item in addr_info]))
        report["resolved_ips"] = ips

        # Check if the domain points directly to Dub's IP
        if "76.76.21.21" in ips:
            report["status"] = "CORRECT"
            report["diagnosis"] = f"✓ Domain '{clean_domain}' points directly to Dub's server (76.76.21.21)."
            report["action_required"] = "Everything looks good! If SSL is still showing an error, wait 5-15 minutes for the certificate to finish generating."
        else:
            # Check if the IPs belong to Cloudflare's proxy network (104.x or 172.x)
            cf_detected = any(ip.startswith("104.") or ip.startswith("172.") for ip in ips)
            report["status"] = "MISCONFIGURED"
            if cf_detected:
                report["diagnosis"] = f"⚠ Domain is going through Cloudflare's proxy ({ips}) instead of straight to Dub."
                report["action_required"] = (
                    "In your Cloudflare dashboard, change the proxy setting from 'Proxied' (orange cloud) "
                    "to 'DNS Only' (grey cloud). If you must keep proxy on, set SSL to 'Full' or 'Full (Strict)'."
                )
            else:
                report["diagnosis"] = f"✗ Domain currently points to {ips}, which is not Dub's server."
                if is_subdomain:
                    report["action_required"] = f"Add a CNAME record in your DNS: Name='{clean_domain.split('.')[0]}', Value='cname.dub.co'."
                else:
                    report["action_required"] = "Add an A record in your DNS: Name='@', Value='76.76.21.21'."

    except socket.gaierror as e:
        # This error happens if the domain doesn't exist or DNS hasn't propagated yet
        report["status"] = "UNRESOLVED"
        report["diagnosis"] = f"✗ Could not find any DNS records for '{clean_domain}'. (Error: {e})"
        if is_subdomain:
            report["action_required"] = f"Create a CNAME record with Name='{clean_domain.split('.')[0]}' pointing to 'cname.dub.co'."
        else:
            report["action_required"] = "Create an A record with Name='@' pointing to '76.76.21.21'."

    return report


def check_domain_ssl(domain: str, timeout: float = 3.0) -> Dict[str, Any]:
    """
    Connects to port 443 (HTTPS) to see if the SSL certificate is working.
    """
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
        # Try to connect to port 443 within the timeout
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
    """
    Verifies that a webhook really came from Dub by checking its signature.
    """
    # Hash the payload with the secret key using SHA-256
    expected = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    # compare_digest avoids timing attacks by comparing all characters at the same speed
    return hmac.compare_digest(expected, signature_header)
