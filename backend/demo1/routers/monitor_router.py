"""
monitor_router.py — Super Admin system monitor
Prefix: /monitor
Sections: health, api-stats, events, cloudflare, risk-log
"""
from fastapi import APIRouter, Query
from typing import Optional
import os, json, subprocess
from datetime import datetime, timezone, timedelta
import httpx

from backend.demo1.pg import get_conn

router = APIRouter(prefix="/monitor", tags=["Monitor"])

CF_TOKEN = os.getenv("CF_API_TOKEN", "")
CF_ZONE  = os.getenv("CF_ZONE_ID", "")


# ── System health ──────────────────────────────────────────────────────────────
@router.get("/health")
async def system_health():
    result = {"cpu": None, "memory": None, "disk": None,
              "uptime_seconds": None, "processes": []}
    try:
        import psutil
        result["cpu"] = round(psutil.cpu_percent(interval=0.2), 1)
        mem = psutil.virtual_memory()
        result["memory"] = {
            "percent":  round(mem.percent, 1),
            "used_gb":  round(mem.used   / 1024**3, 2),
            "total_gb": round(mem.total  / 1024**3, 2),
        }
        disk = psutil.disk_usage("/")
        result["disk"] = {
            "percent":  round(disk.percent, 1),
            "used_gb":  round(disk.used  / 1024**3, 1),
            "total_gb": round(disk.total / 1024**3, 1),
            "free_gb":  round(disk.free  / 1024**3, 1),
        }
        result["uptime_seconds"] = int(
            (datetime.now() - datetime.fromtimestamp(psutil.boot_time())).total_seconds()
        )
    except ImportError:
        result["error"] = "psutil unavailable"

    try:
        raw   = subprocess.check_output(["pm2", "jlist"], timeout=5).decode()
        procs = json.loads(raw)
        result["processes"] = [
            {
                "name":      p.get("name"),
                "status":    p.get("pm2_env", {}).get("status", "unknown"),
                "memory_mb": round(p.get("monit", {}).get("memory", 0) / 1024**2, 1),
                "cpu":       round(p.get("monit", {}).get("cpu", 0), 1),
                "restarts":  p.get("pm2_env", {}).get("restart_time", 0),
                "uptime_ms": p.get("pm2_env", {}).get("pm_uptime"),
                "pid":       p.get("pid"),
            }
            for p in procs
        ]
    except Exception as e:
        result["pm2_error"] = str(e)

    return result


# ── API statistics ─────────────────────────────────────────────────────────────
@router.get("/api-stats")
async def api_stats(hours: int = Query(24, ge=1, le=168)):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    with get_conn("default") as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE timestamp > %s", (since,)
        ).fetchone()["n"]

        server_errors = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE timestamp > %s AND status_code >= 500",
            (since,)
        ).fetchone()["n"]

        client_errors = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log "
            "WHERE timestamp > %s AND status_code >= 400 AND status_code < 500",
            (since,)
        ).fetchone()["n"]

        avg_row = conn.execute(
            "SELECT ROUND(AVG(response_time_ms)::numeric, 1) AS avg_ms "
            "FROM audit_log WHERE timestamp > %s AND response_time_ms IS NOT NULL",
            (since,)
        ).fetchone()
        avg_ms = avg_row["avg_ms"] if avg_row else None

        top = conn.execute("""
            SELECT endpoint,
                   COUNT(*) AS count,
                   ROUND(AVG(response_time_ms)::numeric, 1) AS avg_ms,
                   SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors
            FROM audit_log
            WHERE timestamp > %s
            GROUP BY endpoint
            ORDER BY count DESC
            LIMIT 10
        """, (since,)).fetchall()

        hourly = conn.execute("""
            SELECT to_char(timestamp AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24":00"') AS hour,
                   COUNT(*) AS count,
                   SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS errors
            FROM audit_log
            WHERE timestamp > %s
            GROUP BY hour
            ORDER BY hour
        """, (since,)).fetchall()

        recent_errors = conn.execute("""
            SELECT timestamp, method, endpoint, status_code,
                   error, response_time_ms, client_ip
            FROM audit_log
            WHERE status_code >= 400
            ORDER BY timestamp DESC
            LIMIT 15
        """).fetchall()

    return {
        "period_hours":    hours,
        "total_requests":  total,
        "server_errors":   server_errors,
        "client_errors":   client_errors,
        "error_rate_pct":  round(server_errors / total * 100, 2) if total else 0,
        "avg_response_ms": float(avg_ms) if avg_ms else None,
        "top_endpoints":   [dict(r) for r in top],
        "hourly":          [dict(r) for r in hourly],
        "recent_errors":   [dict(r) for r in recent_errors],
    }


# ── Event log ─────────────────────────────────────────────────────────────────
@router.get("/events")
async def event_log(
    page:     int           = Query(1,   ge=1),
    per_page: int           = Query(50,  ge=10, le=200),
    method:   Optional[str] = None,
    status:   Optional[str] = None,   # "errors" | "ok"
    endpoint: Optional[str] = None,
):
    clauses, params = [], []
    if method:
        clauses.append("method = %s")
        params.append(method.upper())
    if status == "errors":
        clauses.append("status_code >= 400")
    elif status == "ok":
        clauses.append("status_code < 400")
    if endpoint:
        clauses.append("endpoint ILIKE %s")
        params.append(f"%{endpoint}%")

    where  = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    offset = (page - 1) * per_page

    with get_conn("default") as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM audit_log {where}", params
        ).fetchone()["n"]

        rows = conn.execute(
            f"""SELECT id, timestamp, method, endpoint, status_code,
                       response_time_ms, client_ip, body_size_bytes, error
                FROM audit_log {where}
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s""",
            params + [per_page, offset]
        ).fetchall()

    return {
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "events":   [dict(r) for r in rows],
    }


# ── Cloudflare ─────────────────────────────────────────────────────────────────
@router.get("/cloudflare")
async def cloudflare_status():
    result = {"configured":    bool(CF_TOKEN and CF_ZONE),
              "public_status": None, "zone": None, "analytics": None}
    hdrs = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=8.0) as http:
        try:
            r = await http.get("https://www.cloudflarestatus.com/api/v2/status.json")
            d = r.json()
            result["public_status"] = {
                "indicator":   d["status"]["indicator"],
                "description": d["status"]["description"],
            }
        except Exception as e:
            result["public_status_error"] = str(e)

        if not (CF_TOKEN and CF_ZONE):
            return result

        try:
            r = await http.get(
                f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE}", headers=hdrs)
            d = r.json()
            if d.get("success"):
                z = d["result"]
                result["zone"] = {
                    "name":   z.get("name"),
                    "status": z.get("status"),
                    "plan":   z.get("plan", {}).get("name"),
                    "paused": z.get("paused", False),
                }
        except Exception as e:
            result["zone_error"] = str(e)

        try:
            gql = """{ viewer { zones(filter: {zoneTag: "%s"}) {
              httpRequests1hGroups(limit: 1, orderBy: [datetime_DESC]) {
                sum { requests cachedRequests bytes threats pageViews }
              } } } }""" % CF_ZONE
            r = await http.post(
                "https://api.cloudflare.com/client/v4/graphql",
                headers=hdrs, json={"query": gql}
            )
            d     = r.json()
            zones = d.get("data", {}).get("viewer", {}).get("zones", [])
            if zones:
                groups = zones[0].get("httpRequests1hGroups", [])
                if groups:
                    s = groups[0]["sum"]
                    result["analytics"] = {
                        "requests_total":  s.get("requests", 0),
                        "requests_cached": s.get("cachedRequests", 0),
                        "bandwidth_bytes": s.get("bytes", 0),
                        "threats_total":   s.get("threats", 0),
                        "pageviews":       s.get("pageViews", 0),
                    }
                else:
                    result["analytics_error"] = "no data in last hour"
            else:
                result["analytics_error"] = str(d.get("errors", "no zones returned"))
        except Exception as e:
            result["analytics_error"] = str(e)

    return result


# ── Risk assessment log ────────────────────────────────────────────────────────
@router.get("/risk-log")
async def risk_log(limit: int = Query(20, ge=1, le=100)):
    try:
        with get_conn("default") as conn:
            rows = conn.execute("""
                SELECT id, assessed_at, risk_level, summary, prediction, actions, alerted
                FROM risk_assessments
                ORDER BY assessed_at DESC
                LIMIT %s
            """, (limit,)).fetchall()
        return {"assessments": [dict(r) for r in rows]}
    except Exception:
        return {"assessments": [], "note": "Risk table not yet initialized"}
