"""
risk_watcher.py
===============
Agentic 24/7 system monitor for ParaIQ Super Admin.
- Runs every 30 minutes via APScheduler
- Collects system signals (errors, disk, latency, CF threats, process restarts)
- Sends signals to Claude for risk assessment + 48h prediction
- Fires Slack DM + email if risk >= warning
- Logs every assessment to risk_assessments table
"""
import os, json, asyncio, logging
from backend.demo1.pg import get_conn as _pg_get_conn
from datetime import datetime, timezone, timedelta

import httpx
import psutil
from anthropic import Anthropic
from backend.demo1.hermes_kanban import run_hermes_kanban
from backend.demo1.notifications_router import generate_notifications
from backend.demo1.routers.morning_brief_router import run_all_firms_brief, get_active_firms as _get_active_firms

log = logging.getLogger("risk_watcher")

CF_TOKEN      = os.getenv("CF_API_TOKEN", "")
CF_ZONE       = os.getenv("CF_ZONE_ID", "")
SLACK_URL     = os.getenv("SLACK_WEBHOOK_URL", "")
SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASS     = os.getenv("SMTP_PASS", "")
ALERT_TO      = os.getenv("ALERT_EMAIL_TO", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_anthropic = Anthropic(api_key=ANTHROPIC_KEY)

# ── DB setup ───────────────────────────────────────────────────────────────────
def init_risk_table():
    """No-op -- table exists in Supabase Postgres."""
    log.info("[RiskWatcher] Table initialized")

def save_assessment(risk_level, summary, signals, prediction, actions, alerted):
    with _pg_get_conn("default") as conn:  # noqa: intentional — risk watcher is a system-level monitor, cross-firm
        conn.execute("""
            INSERT INTO risk_assessments
              (assessed_at, risk_level, summary, signals, prediction, actions, alerted)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            datetime.now(timezone.utc).isoformat(),
            risk_level, summary,
            json.dumps(signals), prediction,
            json.dumps(actions) if actions else None,
            alerted,
        ))

# ── Signal collection ─────────────────────────────────────────────────────────
def collect_system_signals():
    signals = {}

    # CPU + memory + disk
    try:
        signals["cpu_percent"]    = round(psutil.cpu_percent(interval=1), 1)
        mem = psutil.virtual_memory()
        signals["memory_percent"] = round(mem.percent, 1)
        disk = psutil.disk_usage("/")
        signals["disk_percent"]   = round(disk.percent, 1)
        signals["disk_free_gb"]   = round(disk.free / 1024**3, 1)
    except Exception as e:
        signals["system_error"] = str(e)

    # API error rate (last hour)
    try:
        from backend.demo1.pg import get_conn as _get_conn
        since = (datetime.now(timezone.utc) - timedelta(hours=1))
        recent_since = (datetime.now(timezone.utc) - timedelta(minutes=10))
        with _get_conn("default") as pg:  # noqa: intentional — risk watcher queries system audit_log, cross-firm
            total = pg.execute(
                "SELECT COUNT(*) AS n FROM audit_log WHERE timestamp > %s", (since,)
            ).fetchone()["n"]
            errors = pg.execute(
                "SELECT COUNT(*) AS n FROM audit_log WHERE timestamp > %s AND status_code >= 500",
                (since,)
            ).fetchone()["n"]
            avg_ms = pg.execute(
                "SELECT AVG(response_time_ms) AS a FROM audit_log WHERE timestamp > %s AND response_time_ms IS NOT NULL",
                (since,)
            ).fetchone()["a"]
            recent_errors = pg.execute(
                "SELECT COUNT(*) AS n FROM audit_log WHERE timestamp > %s AND status_code >= 500",
                (recent_since,)
            ).fetchone()["n"]
        signals["api_requests_1h"]  = total
        signals["api_errors_1h"]    = errors
        signals["api_error_rate"]   = round(errors / total * 100, 2) if total else 0
        signals["api_avg_ms"]       = round(float(avg_ms), 1) if avg_ms else None
        signals["api_errors_10min"] = recent_errors
    except Exception as e:
        signals["db_error"] = str(e)

    # PM2 process health
    try:
        import subprocess
        raw = subprocess.check_output(["pm2", "jlist"], timeout=5).decode()
        procs = json.loads(raw)
        down = [p["name"] for p in procs if p.get("pm2_env", {}).get("status") != "online"]
        high_restarts = [
            f"{p['name']}({p['pm2_env'].get('restart_time',0)})"
            for p in procs
            if p.get("name","").startswith("paraiq") and p.get("pm2_env",{}).get("restart_time",0) > 20
        ]
        signals["processes_down"]         = down
        signals["paraiq_high_restarts"]   = high_restarts
    except Exception as e:
        signals["pm2_error"] = str(e)

    return signals

async def collect_cloudflare_signals():
    signals = {}
    if not (CF_TOKEN and CF_ZONE):
        return signals
    hdrs = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            gql = """{ viewer { zones(filter: {zoneTag: "%s"}) {
              httpRequests1hGroups(limit: 1, orderBy: [datetime_DESC]) {
                sum { requests threats }
              } } } }""" % CF_ZONE
            r = await client.post(
                "https://api.cloudflare.com/client/v4/graphql",
                headers=hdrs, json={"query": gql}
            )
            d = r.json()
            zones = (d.get("data") or {}).get("viewer", {}).get("zones", [])
            if zones:
                groups = zones[0].get("httpRequests1hGroups", [])
                if groups:
                    s = groups[0]["sum"]
                    signals["cf_requests_1h"] = s.get("requests", 0)
                    signals["cf_threats_1h"]  = s.get("threats", 0)

            # Zone status
            r2 = await client.get(
                f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE}", headers=hdrs)
            d2 = r2.json()
            if d2.get("success"):
                signals["cf_zone_status"] = d2["result"].get("status")
                signals["cf_zone_paused"] = d2["result"].get("paused", False)

            # Public status
            r3 = await client.get("https://www.cloudflarestatus.com/api/v2/status.json")
            d3 = r3.json()
            signals["cf_platform_indicator"]   = d3["status"]["indicator"]
            signals["cf_platform_description"] = d3["status"]["description"]
    except Exception as e:
        signals["cf_error"] = str(e)
    return signals

# ── Claude risk assessment ─────────────────────────────────────────────────────
def assess_risk_with_claude(signals: dict) -> dict:
    prompt = f"""You are the AI risk analyst for ParaIQ, a legal AI SaaS platform.

Analyze these system signals collected right now and provide a risk assessment.

SIGNALS:
{json.dumps(signals, indent=2)}

Respond ONLY with a JSON object (no markdown, no explanation outside JSON):
{{
  "risk_level": "ok" | "watch" | "warning" | "critical",
  "summary": "One sentence summary of the current system state",
  "prediction": "What risks might materialize in the next 48 hours based on these signals",
  "actions": ["specific action 1", "specific action 2"],
  "key_concerns": ["concern 1", "concern 2"]
}}

Risk level definitions:
- ok: everything normal, no action needed
- watch: minor anomalies worth monitoring, no immediate action
- warning: meaningful risk present, Super Admin should be notified and act within a few hours
- critical: immediate action required, system stability or data security at risk

Be specific. Reference actual signal values in your summary and prediction."""

    try:
        resp = _anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        log.error(f"[RiskWatcher] Claude assessment failed: {e}")
        return {
            "risk_level": "watch",
            "summary": "Risk assessment unavailable — check system manually.",
            "prediction": "Unknown",
            "actions": ["Check system manually"],
            "key_concerns": [str(e)],
        }

# ── Alerts ────────────────────────────────────────────────────────────────────
async def send_slack_alert(assessment: dict, signals: dict):
    if not SLACK_URL:
        return
    level = assessment["risk_level"]
    emoji = {"warning": ":warning:", "critical": ":red_circle:"}.get(level, ":eyes:")
    color = {"warning": "#ffb74d", "critical": "#e03131"}.get(level, "#888")

    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text",
                             "text": f"{emoji} ParaIQ Risk Alert — {level.upper()}"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn",
                             "text": f"*Summary:* {assessment['summary']}"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn",
                             "text": f"*48h Prediction:* {assessment.get('prediction', '—')}"}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn",
                             "text": "*Key signals:*\n" + "\n".join([
                                 f"• CPU: {signals.get('cpu_percent','—')}%",
                                 f"• Disk: {signals.get('disk_percent','—')}% ({signals.get('disk_free_gb','—')} GB free)",
                                 f"• API errors (1h): {signals.get('api_errors_1h','—')}",
                                 f"• CF threats (1h): {signals.get('cf_threats_1h','—')}",
                             ])}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn",
                             "text": "*Recommended actions:*\n" +
                                     "\n".join(f"• {a}" for a in assessment.get("actions", []))}
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn",
                                  "text": f"ParaIQ System Monitor · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}]
                }
            ]
        }]
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(SLACK_URL, json=payload)
            log.info(f"[RiskWatcher] Slack alert sent: {r.status_code}")
    except Exception as e:
        log.error(f"[RiskWatcher] Slack failed: {e}")

async def send_email_alert(assessment: dict, signals: dict):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, ALERT_TO]):
        return
    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        level  = assessment["risk_level"].upper()
        ts     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
          <div style="background:#0e0e1a;padding:24px;border-radius:8px 8px 0 0">
            <h2 style="color:#c9a84c;margin:0;font-weight:300;letter-spacing:.08em">
              PARA IQ — Risk Alert
            </h2>
          </div>
          <div style="background:#f5f3ee;padding:24px;border-radius:0 0 8px 8px">
            <p style="font-size:14px;color:#555;margin-bottom:16px">
              <strong>Risk level:</strong>
              <span style="color:{'#e03131' if level=='CRITICAL' else '#f59f00'};font-weight:700">{level}</span>
            </p>
            <p style="font-size:14px;color:#333"><strong>Summary:</strong> {assessment['summary']}</p>
            <p style="font-size:14px;color:#333"><strong>48h Prediction:</strong> {assessment.get('prediction','—')}</p>
            <hr style="border:none;border-top:1px solid #ddd;margin:16px 0"/>
            <p style="font-size:13px;color:#555"><strong>Key signals:</strong></p>
            <ul style="font-size:13px;color:#555">
              <li>CPU: {signals.get('cpu_percent','—')}%</li>
              <li>Disk: {signals.get('disk_percent','—')}% ({signals.get('disk_free_gb','—')} GB free)</li>
              <li>API errors (1h): {signals.get('api_errors_1h','—')}</li>
              <li>API avg response: {signals.get('api_avg_ms','—')} ms</li>
              <li>CF threats (1h): {signals.get('cf_threats_1h','—')}</li>
            </ul>
            <hr style="border:none;border-top:1px solid #ddd;margin:16px 0"/>
            <p style="font-size:13px;color:#555"><strong>Recommended actions:</strong></p>
            <ul style="font-size:13px;color:#555">
              {''.join(f'<li>{a}</li>' for a in assessment.get('actions',[]))}
            </ul>
            <p style="font-size:11px;color:#aaa;margin-top:24px">
              ParaIQ System Monitor · {ts}
            </p>
          </div>
        </div>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[ParaIQ] {level} Risk Alert — {ts}"
        msg["From"]    = SMTP_USER
        msg["To"]      = ALERT_TO
        msg.attach(MIMEText(html, "html"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST, port=SMTP_PORT,
            username=SMTP_USER, password=SMTP_PASS,
            start_tls=True,
        )
        log.info(f"[RiskWatcher] Email alert sent to {ALERT_TO}")
    except Exception as e:
        log.error(f"[RiskWatcher] Email failed: {e}")

# ── Main assessment cycle ─────────────────────────────────────────────────────
async def run_assessment():
    log.info("[RiskWatcher] Starting assessment cycle…")
    try:
        sys_signals = collect_system_signals()
        cf_signals  = await collect_cloudflare_signals()
        signals     = {**sys_signals, **cf_signals}

        assessment  = assess_risk_with_claude(signals)
        risk_level  = assessment.get("risk_level", "watch")
        alerted     = False

        log.info(f"[RiskWatcher] Risk level: {risk_level} — {assessment.get('summary','')}")

        if risk_level in ("warning", "critical"):
            await asyncio.gather(
                send_slack_alert(assessment, signals),
                send_email_alert(assessment, signals),
            )
            alerted = True

        save_assessment(
            risk_level  = risk_level,
            summary     = assessment.get("summary", ""),
            signals     = signals,
            prediction  = assessment.get("prediction"),
            actions     = assessment.get("actions"),
            alerted     = alerted,
        )
    except Exception as e:
        log.error(f"[RiskWatcher] Assessment cycle failed: {e}")

def start_scheduler(app):
    """Call this from FastAPI lifespan or startup event."""
    if os.getenv("TESTING"):
        log.info("[RiskWatcher] TESTING mode — scheduler disabled")
        return None
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    init_risk_table()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_assessment, "interval", minutes=30, id="risk_watcher",
                      next_run_time=datetime.now())   # run immediately on startup too
    scheduler.add_job(
        run_hermes_kanban,
        "interval", minutes=15, id="hermes_kanban", replace_existing=True,
        args=[os.getenv("HERMES_SERVICE_JWT", "")]
    )
    scheduler.add_job(
        lambda: [generate_notifications(firm) for firm in _get_active_firms()],
        "interval", minutes=30, id="notifications_gen", replace_existing=True,
    )
    scheduler.add_job(
        run_all_firms_brief,
        'cron', hour=8, minute=0, id='morning_brief', replace_existing=True,
    )
    # Drift monitor — check Claude response quality every hour
    from backend.demo1.mlops.drift_monitor import check_drift, log_drift_check
    scheduler.add_job(
        lambda: log_drift_check(check_drift()),
        "interval", hours=1, id="drift_monitor", replace_existing=True,
    )
    # Purge expired JWT blocklist rows daily at 03:00 UTC
    from backend.demo1.auth import purge_expired_blocklist
    scheduler.add_job(
        purge_expired_blocklist,
        "cron", hour=3, minute=0, id="blocklist_cleanup", replace_existing=True,
    )
    scheduler.start()
    log.info("[RiskWatcher] Scheduler started — running every 30 minutes")
    return scheduler
