"""
DubPilot Production SRE Incident Simulator.
Provides 20 real-world production incident scenarios covering database, memory,
networking, SSL/DNS, CPU, and upstream API failures.
Dispatches live webhooks to Amber SRE engine and maintains real-time state for UI.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("dubpilot.sre")

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "postgres_pool_starvation",
        "title": "PostgreSQL Connection Pool Starvation",
        "severity": "P1",
        "service": "dubpilot-postgres",
        "description": "Connection pool reached 100/100 connections. 45 incoming requests queued in PgBouncer.",
        "metrics": {"active_connections": 100, "pool_limit": 100, "waiting_clients": 45, "pool_utilization": "100%"},
        "remediation_tool": "kill_db_connections",
        "suggested_action": "Terminate leaked idle-in-transaction connections and scale pool limit."
    },
    {
        "id": "redis_oom_eviction",
        "title": "Redis Out-of-Memory & Eviction Storm",
        "severity": "P1",
        "service": "dubpilot-cache",
        "description": "Redis memory exceeded 512MB maxmemory limit. Volatile-LRU eviction rate spiked 1,200/sec.",
        "metrics": {"memory_used": "512MB", "max_memory": "512MB", "evictions_per_sec": 1240, "hit_rate": "42.1%"},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Flush stale cache partitions and restart cache cluster."
    },
    {
        "id": "cpu_runaway_spike",
        "title": "Worker Thread Runaway CPU Saturation",
        "severity": "P2",
        "service": "dubpilot-worker",
        "description": "Regex backtracking on user-submitted domain validation pegged Core #2 at 100% CPU.",
        "metrics": {"cpu_utilization": "99.8%", "load_average_1m": 8.4, "throttled_threads": 6},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Kill runaway regex thread and restart worker pod."
    },
    {
        "id": "upstream_dub_429",
        "title": "Upstream Dub API HTTP 429 Rate Limit Breached",
        "severity": "P2",
        "service": "dubpilot-edge",
        "description": "Outbound requests to api.dub.co exceeded 600 req/min enterprise quota. 429s cascading.",
        "metrics": {"http_429_rate": "18.4 req/sec", "retry_after_header": "45s", "dropped_requests": 280},
        "remediation_tool": "rollback_deployment",
        "suggested_action": "Enable exponential jitter backoff and purge queued link lookups."
    },
    {
        "id": "custom_domain_dns_nxdomain",
        "title": "Custom Domain DNS Resolution Failure (NXDOMAIN)",
        "severity": "P1",
        "service": "dubpilot-dns",
        "description": "Anycast CNAME cname.dub.co returning SERVFAIL/NXDOMAIN on 3 global POP locations.",
        "metrics": {"dns_resolution_time": "3200ms", "error_code": "NXDOMAIN", "affected_regions": ["iad1", "fra1"]},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Re-announce BGP routes and trigger DNS cache flush."
    },
    {
        "id": "ssl_cert_expired",
        "title": "Cloudflare SSL Handshake Error 525",
        "severity": "P0",
        "service": "dubpilot-ingress",
        "description": "TLS certificate expired on custom link edge proxy. SSL handshakes dropping globally.",
        "metrics": {"tls_handshake_error": "SSL_ERROR_EXPIRED_CERT", "http_525_count": 842, "traffic_loss": "100%"},
        "remediation_tool": "rollback_deployment",
        "suggested_action": "Trigger automated Let's Encrypt renewal and edge cert propagation."
    },
    {
        "id": "sse_memory_leak",
        "title": "Server-Sent Events Token Stream Buffer Leak",
        "severity": "P2",
        "service": "dubpilot-api",
        "description": "Dangling SSE connections retaining raw token buffers in heap. RSS expanded from 180MB to 1.9GB.",
        "metrics": {"heap_used": "1.92GB", "open_sse_connections": 1420, "gc_pause_ms": 680},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Close idle SSE connections and restart API server process."
    },
    {
        "id": "pg_deadlock_analytics",
        "title": "PostgreSQL Transaction Deadlock on link_analytics_clicks",
        "severity": "P1",
        "service": "dubpilot-postgres",
        "description": "Concurrent UPSERT queries on daily click partitions triggered mutual transaction locks.",
        "metrics": {"deadlocks_detected": 14, "blocked_processes": 8, "query_wait_time": "14.2s"},
        "remediation_tool": "kill_db_connections",
        "suggested_action": "Terminate blocked transactions and reorder indexing lock statements."
    },
    {
        "id": "disk_io_saturation",
        "title": "NVMe Disk I/O Saturation",
        "severity": "P2",
        "service": "dubpilot-storage",
        "description": "PostgreSQL write-ahead logs (WAL) saturated local NVMe IOPS. Disk await spiked to 480ms.",
        "metrics": {"iops_utilized": "100%", "await_ms": 482, "wal_checkpoint_lag": "120s"},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Trigger WAL checkpoint flush and rotate uncompressed transaction logs."
    },
    {
        "id": "gateway_timeout_504",
        "title": "Upstream Gateway Timeout HTTP 504 on Link Redirection",
        "severity": "P0",
        "service": "dubpilot-gateway",
        "description": "Shortlink 301 redirection pipeline timing out after 15,000ms. End-user links failing.",
        "metrics": {"http_504_percentage": "64.2%", "p99_latency": "15,200ms", "downstream_errors": 1840},
        "remediation_tool": "rollback_deployment",
        "suggested_action": "Bypass cold analytics enrichment pipeline and serve cached direct redirects."
    },
    {
        "id": "webhook_hmac_desync",
        "title": "Webhook HMAC-SHA256 Secret Desynchronization",
        "severity": "P2",
        "service": "dubpilot-webhooks",
        "description": "Rotated secret in Dub.co dashboard not matched on local instance. 100% webhooks rejected.",
        "metrics": {"invalid_signature_ratio": "100%", "failed_webhooks": 312, "last_valid_sig": "2h ago"},
        "remediation_tool": "rollback_deployment",
        "suggested_action": "Hot-reload webhook signing credentials from secret manager."
    },
    {
        "id": "worker_crashloop",
        "title": "Async Worker Background Process CrashLoopBackOff",
        "severity": "P1",
        "service": "dubpilot-worker",
        "description": "Celery worker died with SIGSEGV on malformed geo-IP database binary lookup. Restart loop.",
        "metrics": {"restart_count": 9, "status": "CrashLoopBackOff", "unprocessed_queue": 8420},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Replace corrupt MaxMind GeoLite2 binary and restart worker pod."
    },
    {
        "id": "chat_stream_500",
        "title": "Unhandled 500 Error in LLM Resolution Stream",
        "severity": "P1",
        "service": "dubpilot-ai",
        "description": "Ollama local socket disconnect during streaming response generated uncaught JSON decode exception.",
        "metrics": {"stream_disconnects": 42, "unhandled_exceptions": 38, "error_code": "ECONNRESET"},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Drain local inference socket and restart Ollama container runtime."
    },
    {
        "id": "billing_row_lock",
        "title": "Row Lock Contention on Stripe Customer Subscription Table",
        "severity": "P2",
        "service": "dubpilot-billing",
        "description": "Webhook storm from Stripe invoice updates holding exclusive row lock on enterprise org.",
        "metrics": {"exclusive_locks_held": 4, "lock_wait_seconds": 38.5, "transaction_backlog": 19},
        "remediation_tool": "kill_db_connections",
        "suggested_action": "Terminate long-running billing transactions and apply advisory locks."
    },
    {
        "id": "socket_leak_ephemeral",
        "title": "Linux TCP Ephemeral Port Exhaustion",
        "severity": "P1",
        "service": "dubpilot-network",
        "description": "Unclosed HTTP client sessions left 28,400 sockets in TIME_WAIT. System cannot allocate new sockets.",
        "metrics": {"sockets_time_wait": 28410, "local_port_range": "32768-60999", "socket_allocation_err": "EADDRNOTAVAIL"},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Enable tcp_tw_reuse kernel flag and restart gateway connection pool."
    },
    {
        "id": "slow_query_latency",
        "title": "Unindexed Query Latency Spike (>8500ms on domains)",
        "severity": "P2",
        "service": "dubpilot-postgres",
        "description": "Sequential table scan on 2.4M domains table without composite index on (org_id, verified).",
        "metrics": {"p95_query_time": "8,540ms", "seq_scans_per_min": 140, "cpu_iowait": "42%"},
        "remediation_tool": "kill_db_connections",
        "suggested_action": "Kill slow sequential query and inject composite B-tree index."
    },
    {
        "id": "dns_propagation_stall",
        "title": "Cloudflare Anycast DNS Propagation Failure",
        "severity": "P2",
        "service": "dubpilot-dns",
        "description": "New domain routing records stuck in PENDING status for >4 hours on Asia-Pacific resolvers.",
        "metrics": {"propagation_pct": "14%", "unresolved_regions": ["ap-south-1", "ap-southeast-1"], "retries": 180},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Force DNS edge zone rebuild through Cloudflare API."
    },
    {
        "id": "threadpool_starvation",
        "title": "Asyncio Event Loop Threadpool Starvation",
        "severity": "P1",
        "service": "dubpilot-api",
        "description": "Blocking disk synchronous file I/O executed on main thread, stalling async event loop by 4200ms.",
        "metrics": {"event_loop_lag_ms": 4250, "slow_callbacks": 84, "request_timeout_count": 92},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Offload sync calls to ThreadPoolExecutor and cycle worker instance."
    },
    {
        "id": "redis_replication_lag",
        "title": "Redis Replica Replication Offset Desync",
        "severity": "P2",
        "service": "dubpilot-cache",
        "description": "Replica redis node fell 54MB behind primary during write spike. Reads returning stale link targets.",
        "metrics": {"replication_offset_diff": "54.2MB", "replica_lag_seconds": 18.2, "dirty_reads": 640},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Trigger PSYNC2 incremental resynchronization."
    },
    {
        "id": "corrupted_json_payload",
        "title": "Malformed JSON Ingestion Buffer Overflow",
        "severity": "P2",
        "service": "dubpilot-webhooks",
        "description": "Attacker payload with 10MB recursive nested JSON objects causing high memory and parser stalls.",
        "metrics": {"payload_size_mb": 10.4, "parser_latency_ms": 9400, "stack_depth": 2400},
        "remediation_tool": "restart_service_pod",
        "suggested_action": "Deploy payload size limit guardrail and reset ingress parser."
    },
]

# In-memory incident tracking
_active_incident: Optional[Dict[str, Any]] = None


def get_all_scenarios() -> List[Dict[str, Any]]:
    return SCENARIOS


def get_current_sre_status() -> Dict[str, Any]:
    global _active_incident
    if not _active_incident:
        return {
            "status": "OPERATIONAL",
            "active_incident": None,
            "message": "All 20 subsystems healthy. Zero active incidents.",
            "metrics": {
                "active_connections": 14,
                "pool_limit": 100,
                "memory_used": "142MB",
                "cpu_utilization": "4.2%",
                "p99_latency": "22ms"
            }
        }

    # If an incident is active, sync with Amber SRE resolution state
    if _active_incident.get("status") in ["CRITICAL", "DEGRADED", "INCIDENT"]:
        try:
            amber_api_base = os.getenv("AMBER_API_URL", "https://toxic-ban-falls-searches.trycloudflare.com")
            urls_to_poll = [
                f"{amber_api_base}/api/v1/incidents?page=1&page_size=1",
                "http://localhost:8000/api/v1/incidents?page=1&page_size=1",
            ]
            for poll_url in urls_to_poll:
                try:
                    with httpx.Client(timeout=1.5) as client:
                        res = client.get(poll_url)
                        if res.status_code == 200:
                            incidents = res.json()
                            if incidents:
                                latest = incidents[0]
                                if latest.get("status") == "RESOLVED":
                                    remediate_active_incident({
                                        "tool_name": _active_incident.get("remediation_tool", "kill_db_connections"),
                                        "approver": "SRE Lead via Telegram (@ambersre_alert_bot)"
                                    })
                                    break
                except Exception:
                    continue
        except Exception:
            pass

    return {
        "status": _active_incident.get("status", "INCIDENT"),
        "active_incident": _active_incident,
        "message": f"Active SRE Incident: {_active_incident.get('title')}",
        "metrics": _active_incident.get("metrics", {})
    }


async def trigger_scenario(scenario_id: str, amber_webhook_url: str = "https://toxic-ban-falls-searches.trycloudflare.com/api/v1/webhooks/generic") -> Dict[str, Any]:
    global _active_incident
    target = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
    if not target:
        raise ValueError(f"Scenario '{scenario_id}' not found.")

    incident_id = f"inc_{scenario_id}_{int(datetime.now().timestamp())}"
    now_str = datetime.now(timezone.utc).isoformat()

    _active_incident = {
        "id": incident_id,
        "scenario_id": target["id"],
        "title": target["title"],
        "severity": target["severity"],
        "service": target["service"],
        "description": target["description"],
        "metrics": target["metrics"],
        "status": "CRITICAL" if target["severity"] in ["P0", "P1"] else "DEGRADED",
        "triggered_at": now_str,
        "remediation_tool": target["remediation_tool"],
        "suggested_action": target["suggested_action"],
    }

    # Dispatch real alert webhook to Amber
    webhook_dispatched = False
    amber_response = {}
    try:
        dubpilot_base = os.getenv("DUBPILOT_BASE_URL", "https://dubpilot.vercel.app")
        target_service_url = f"{dubpilot_base}/api/sre/remediate"

        urls_to_try = [
            amber_webhook_url,
            os.getenv("AMBER_WEBHOOK_URL", "https://toxic-ban-falls-searches.trycloudflare.com/api/v1/webhooks/generic"),
            "http://127.0.0.1:8000/api/v1/webhooks/generic",
            "http://host.docker.internal:8000/api/v1/webhooks/generic",
        ]
        payload = {
            "source": "PROMETHEUS",
            "title": f"[{target['severity']}] {target['title']}",
            "raw_payload": {
                "incident_id": incident_id,
                "alertname": target["title"],
                "service": target["service"],
                "severity": target["severity"],
                "description": target["description"],
                "metrics": target["metrics"],
                "target_service_url": target_service_url,
                "proposed_tool": target["remediation_tool"],
            }
        }
        errors = []
        async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
            for url in urls_to_try:
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code in [200, 201, 202]:
                        webhook_dispatched = True
                        amber_response = resp.json()
                        logger.info(f"Successfully alerted Amber SRE at {url}")
                        break
                    else:
                        errors.append(f"{url} returned status {resp.status_code}")
                except Exception as ex:
                    errors.append(f"{url} error: {str(ex)}")
                    continue
    except Exception as e:
        logger.warning(f"Could not reach Amber webhook: {e}")

    return {
        "status": "INCIDENT_TRIGGERED",
        "incident": _active_incident,
        "amber_alert_dispatched": webhook_dispatched,
        "amber_response": amber_response,
        "delivery_errors": errors if not webhook_dispatched else [],
    }


def remediate_active_incident(remediation_info: Dict[str, Any]) -> Dict[str, Any]:
    global _active_incident
    if not _active_incident:
        return {"status": "NO_ACTIVE_INCIDENT", "message": "Cluster already nominal."}

    tool_name = remediation_info.get("tool_name", "manual_remediation")
    approver = remediation_info.get("approver", "SRE Lead")

    _active_incident["status"] = "RESOLVED_BY_AMBER"
    _active_incident["resolved_at"] = datetime.now(timezone.utc).isoformat()
    _active_incident["remediated_by_tool"] = tool_name
    _active_incident["authorized_by"] = approver
    _active_incident["metrics"] = {
        "active_connections": 14,
        "pool_limit": 100,
        "pool_utilization": "14.0% (Recovered from 100%)",
        "memory_used": "142MB",
        "cpu_utilization": "5.1%",
        "p99_latency": "24ms (Recovered from timeout)",
        "recovery_status": "All health probes 200 OK"
    }

    return {
        "status": "REMEDIATION_APPLIED",
        "message": f"Incident '{_active_incident['title']}' successfully remediated by Amber SRE tool '{tool_name}'.",
        "incident": _active_incident
    }
