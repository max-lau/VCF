#!/usr/bin/env python3
"""
ParaIQ Voice Command Bot
Telegram bot that accepts voice messages, transcribes them via Whisper,
parses intent via Claude, and executes commands against the ParaIQ backend.
"""

import os
import json
import logging
import tempfile
import httpx
from pathlib import Path

from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import openai
import anthropic

# ── LOGGING ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/nlp-portfolio/logs/voice_bot.log"),
    ]
)
log = logging.getLogger("paraiq-bot")

# ── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY   = os.environ["OPENAI_API_KEY"]
ANTHROPIC_API_KEY= os.environ["ANTHROPIC_API_KEY"]
PARAIQ_BASE_URL  = os.environ.get("PARAIQ_BASE_URL", "http://localhost:5003")
PARAIQ_USER      = os.environ.get("PARAIQ_BOT_USER", "maxwell@openfish.com")
PARAIQ_PASSWORD  = os.environ.get("PARAIQ_BOT_PASS", "maxwell")

# Telegram user IDs allowed to use this bot (whitelist for security)
# Set via env var as comma-separated IDs: "123456789,987654321"
# Leave empty to allow ALL users (not recommended for production)
ALLOWED_USER_IDS_RAW = os.environ.get("ALLOWED_TELEGRAM_IDS", "")
ALLOWED_USER_IDS = set(
    int(uid.strip()) for uid in ALLOWED_USER_IDS_RAW.split(",")
    if uid.strip().isdigit()
)

# ── PARAIQ COMMANDS CATALOGUE ────────────────────────────────────────────────
# This is what the AI uses to understand which command was requested.
# Update this list as you add more ParaIQ features.
COMMAND_CATALOGUE = """
Reply ONLY with a valid JSON object — no markdown, no explanation.

=== CALENDAR & DEADLINES ===
1.  get_deadlines           - upcoming deadlines, due dates, what is due, filing deadlines, court dates
2.  get_upcoming_calendar   - calendar, schedule, upcoming events, what is coming up, appointments
3.  get_calendar_types      - calendar event types, types of events

=== CASES & MATTERS ===
4.  get_cases_stats         - case statistics, how many cases, case count, case summary, matter overview
5.  search_cases            - find/search/look up cases or matters (params: query string)

=== CONTACTS ===
6.  get_contacts            - contacts, show contacts, contact list, who are our contacts, client list

=== DISCOVERY & DOCUMENTS ===
7.  get_discovery_stats     - discovery stats, document processing, how many documents
8.  get_discovery_queue     - discovery queue, what is being processed, pending documents, backlog
9.  get_discovery_duplicates- duplicate documents, find duplicates, duplicate files, dupes
10. get_discovery_catalog   - discovery catalog, all discovery documents, document catalog

=== AI ANALYSIS ===
11. get_risk_signals        - risk signals, risk alerts, risks, what are the risks, risk analysis
12. get_legal_bert_status   - legal bert, bert model, AI model status, NLP model, bert status
13. get_intake_history      - intake history, past intakes, previous intake forms, intake log

=== PRIVILEGE LOG ===
14. get_privilege_stats     - privilege stats, how many privileged, privilege summary
15. get_privilege_log       - privilege log, show privilege log, privileged documents list

=== REPORTS & EXPORTS ===
16. get_reports_list        - reports list, available reports, what reports, report types
17. get_deposition_stats    - deposition stats, how many depositions, deposition summary
18. get_depositions         - depositions, show depositions, deposition list
19. get_motion_stats        - motion stats, how many motions, motions summary
20. get_motions             - motions, show motions, pending motions, motion list
21. get_contract_stats      - contract stats, how many contracts, contracts summary
22. get_contracts           - contracts, show contracts, contract list

=== RESEARCH ===
23. get_research            - research notes, legal research, show research, research list

=== SYSTEM ===
24. get_dashboard_stats     - dashboard, overview, firm stats, summary, what is the status
25. get_audit_logs          - audit logs, recent activity, audit trail, what happened recently
26. get_audit_stats         - audit statistics, audit summary, audit overview
27. get_health              - system health, server status, is system running, everything ok
28. get_api_stats           - api stats, api usage, how many requests, request statistics
29. screen_all_discovery    - screen all documents, run privilege screening, screen discovery

30. get_workload_today      - my workload, what is on my plate today, daily briefing, what do I have today, morning briefing, what should I focus on
31. get_case_intelligence    - summarize case, case summary, case intelligence, brief me on case, what is happening with case (params: query = case name or number)

32. unknown                 - use when nothing above matches
"""

# ── CLIENTS ──────────────────────────────────────────────────────────────────
openai_client    = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# JWT token cache (refreshed automatically)
_jwt_token: str | None = None


# ── AUTH ─────────────────────────────────────────────────────────────────────
async def get_jwt_token() -> str:
    """Authenticate with ParaIQ backend and return a JWT token."""
    global _jwt_token
    if _jwt_token:
        return _jwt_token  # TODO: add expiry check if needed

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PARAIQ_BASE_URL}/auth/login",
            json={"username": PARAIQ_USER, "password": PARAIQ_PASSWORD},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _jwt_token = data.get("access_token") or data.get("token")
        log.info("Authenticated with ParaIQ backend ✓")
        return _jwt_token


# ── SPEECH TO TEXT ────────────────────────────────────────────────────────────
async def transcribe_audio(audio_bytes: bytes, file_ext: str = "ogg") -> str:
    """Send audio bytes to OpenAI Whisper and return the transcript."""
    with tempfile.NamedTemporaryFile(suffix=f".{file_ext}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            response = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="en",        # change or remove for multilingual
                response_format="text",
            )
        transcript = response.strip() if isinstance(response, str) else response
        log.info(f"Transcript: '{transcript}'")
        return transcript
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── INTENT PARSING ────────────────────────────────────────────────────────────
async def parse_intent(transcript: str) -> dict:
    """Use Claude to map the transcript to a structured ParaIQ command."""
    prompt = f"""You are ParaIQ's voice command interpreter.

{COMMAND_CATALOGUE}

The user said: "{transcript}"

Reply ONLY with a valid JSON object (no markdown, no explanation):
{{
  "action": "<command_name>",
  "params": {{}},
  "confidence": <float 0-1>,
  "understood_as": "<one sentence: what you think the user wants>"
}}"""

    message = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        result = json.loads(raw)
        log.info(f"Parsed intent: {result}")
        return result
    except json.JSONDecodeError:
        log.warning(f"Failed to parse intent JSON: {raw}")
        return {"action": "unknown", "params": {}, "confidence": 0.0, "understood_as": raw}


# ── COMMAND EXECUTION ─────────────────────────────────────────────────────────


def fmt_workload(d):
    lines = ["☀️ *Your Workload Today*\n"]
    # Deadlines
    deadlines = d.get("deadlines", {})
    items = deadlines.get("deadlines", []) if isinstance(deadlines, dict) else []
    if items:
        lines.append(f"📅 *Deadlines ({len(items)})*")
        for i in items[:3]:
            days = i.get("days_away","?")
            dot = "🔴" if isinstance(days,int) and days<=3 else "🟡" if isinstance(days,int) and days<=7 else "🟢"
            lines.append(f"  {dot} {i.get('event','?')} · {i.get('case_title',i.get('case_number',''))} ({days}d)")
    else:
        lines.append("📅 *Deadlines:* None upcoming")
    # Calendar
    calendar = d.get("calendar", [])
    if isinstance(calendar, list) and calendar:
        lines.append(f"\n📆 *Calendar ({len(calendar)} events)*")
        for e in calendar[:3]:
            lines.append(f"  • {e.get('title',e.get('event_type','Event'))} · {e.get('date',e.get('start_date','?'))}")
    else:
        lines.append("\n📆 *Calendar:* No upcoming events")
    # Stats
    stats = d.get("stats", {})
    if stats:
        risk = stats.get("high_risk_cases", 0)
        lines.append(f"\n📊 *Firm Overview*")
        lines.append(f"  Open cases: *{stats.get('open_cases','—')}* | High risk: *{'🔴 ' + str(risk) if risk > 0 else '🟢 0'}*")
        lines.append(f"  Analyses run: *{stats.get('total_analyses','—')}* | Requests today: *{stats.get('requests_today',0)}*")
    return "\n".join(lines)


def sanitize(text):
    """Strip characters that break Telegram Markdown."""
    if not text: return ""
    for ch in ["*","_","`","[","]","(",")","|","{","}"]:
        text = str(text).replace(ch, " ")
    return str(text).strip()
def fmt_intelligence(d):
    if "error" in d:
        return f"❌ {d['error']}"
    intel = d.get("intelligence", d)
    title = intel.get("_case_title", "Case")
    number = intel.get("_case_number", "")
    lines = [f"🧠 *Case Intelligence*", f"*{title}* {('· ' + number) if number else ''}\n"]
    # Summary
    summary = intel.get("summary", intel.get("executive_summary", intel.get("overview","")))
    if summary:
        lines.append(f"📋 *Summary*\n{sanitize(str(summary)[:400])}")
    # Key issues
    issues = intel.get("key_issues", intel.get("issues", []))
    if issues:
        lines.append(f"\n⚠️ *Key Issues*")
        for i in (issues[:3] if isinstance(issues, list) else [issues]):
            lines.append(f"  • {sanitize(str(i)[:100])}")
    # Risk
    risk = intel.get("risk_level", intel.get("risk",""))
    if risk:
        dot = "🔴" if str(risk).lower() in ["high","critical"] else "🟡" if str(risk).lower()=="medium" else "🟢"
        lines.append(f"\n{dot} *Risk Level:* {risk}")
    # Recommendations
    recs = intel.get("recommendations", intel.get("next_steps",[]))
    if recs:
        lines.append(f"\n💡 *Recommendations*")
        for r in (recs[:2] if isinstance(recs, list) else [recs]):
            lines.append(f"  • {sanitize(str(r)[:100])}")
    if len(lines) <= 2:
        # fallback: show raw keys
        lines.append(sanitize(json.dumps({k:v for k,v in intel.items() if not k.startswith("_")}, indent=2)[:500]))
    return "\n".join(lines)

async def get_workload_today(token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    async with httpx.AsyncClient() as http:
        for key, url in [
            ("deadlines", f"{PARAIQ_BASE_URL}/dashboard/deadlines"),
            ("calendar",  f"{PARAIQ_BASE_URL}/calendar/upcoming"),
            ("stats",     f"{PARAIQ_BASE_URL}/dashboard/stats"),
        ]:
            try:
                r = await http.get(url, headers=headers, timeout=10)
                results[key] = r.json() if r.status_code == 200 else {}
            except:
                results[key] = {}
    return {"workload": results}


async def get_case_intelligence(query: str, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as http:
        r = await http.get(f"{PARAIQ_BASE_URL}/cases/search",
                           params={"query": query}, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        cases = data.get("cases", data if isinstance(data, list) else [])
        if not cases:
            return {"error": f"No case found matching '{query}'"}
        case = cases[0]
        case_id = case.get("id") or case.get("case_id")
        if not case_id:
            return {"error": "Could not determine case ID"}
        r2 = await http.get(f"{PARAIQ_BASE_URL}/cases/{case_id}/intelligence",
                            headers=headers, timeout=15)
        if r2.status_code == 200:
            intel = r2.json()
            intel["_case_title"] = case.get("case_title", query)
            intel["_case_number"] = case.get("case_number", "")
            return {"intelligence": intel}
        return {"error": f"Intelligence not available for case {case_id}"}

async def execute_command(action: str, params: dict) -> str:
    """Call the appropriate ParaIQ API endpoint and return a human-readable result."""
    try:
        token = await get_jwt_token()
        headers = {"Authorization": f"Bearer {token}"}
    except Exception as e:
        return f"⚠️ Could not authenticate with ParaIQ: {e}"

    # Route each action to the correct endpoint
    # Update these endpoints to match your actual FastAPI routes
    ROUTE_MAP = {
    "get_deadlines": ["GET", "/dashboard/deadlines"],
    "get_upcoming_calendar": ["GET", "/calendar/upcoming"],
    "get_calendar_types": ["GET", "/calendar/types"],
    "get_cases_stats": ["GET", "/cases/stats"],
    "search_cases": ["GET", "/cases/search"],
    "get_contacts": ["GET", "/contacts/firm/default"],
    "get_discovery_stats": ["GET", "/discovery/stats"],
    "get_discovery_queue": ["GET", "/discovery/queue"],
    "get_discovery_duplicates": ["GET", "/discovery/duplicates"],
    "get_discovery_catalog": ["GET", "/discovery/catalog"],
    "get_risk_signals": ["GET", "/risk/signals"],
    "get_legal_bert_status": ["GET", "/legal-bert/status"],
    "get_intake_history": ["GET", "/intake/history"],
    "get_privilege_stats": ["GET", "/privilege/stats"],
    "get_privilege_log": ["GET", "/privilege/log"],
    "get_reports_list": ["GET", "/reports/types/list"],
    "get_deposition_stats": ["GET", "/depositions/stats"],
    "get_depositions": ["GET", "/depositions/"],
    "get_motion_stats": ["GET", "/motions/stats"],
    "get_motions": ["GET", "/motions/"],
    "get_contract_stats": ["GET", "/contracts/stats"],
    "get_contracts": ["GET", "/contracts/"],
    "get_research": ["GET", "/research/firm/default"],
    "get_dashboard_stats": ["GET", "/dashboard/stats"],
    "get_audit_logs": ["GET", "/audit/logs"],
    "get_audit_stats": ["GET", "/audit/stats"],
    "get_health": ["GET", "/health"],
    "get_api_stats": ["GET", "/monitor/api-stats"],
    "screen_all_discovery": ["POST", "/discovery/screen-all"],
}

    # Special multi-step commands
    if action == "get_workload_today":
        try:
            token = await get_jwt_token()
            data = await get_workload_today(token)
            return fmt_workload(data.get("workload", {}))
        except Exception as e:
            return f"⚠️ Could not fetch workload: {e}"
    if action == "get_case_intelligence":
        try:
            token = await get_jwt_token()
            query = params.get("query", "") or "recent"
            data = await get_case_intelligence(query, token)
            return fmt_intelligence(data)
        except Exception as e:
            return f"⚠️ Could not fetch case intelligence: {e}"
    if action == "unknown" or action not in ROUTE_MAP:
        return "❓ I couldn't understand that command. Try rephrasing — e.g. *\"show upcoming deadlines\"* or *\"any new cases today\"* or *\"system health\"*."

    method, path = ROUTE_MAP[action]
    url = f"{PARAIQ_BASE_URL}{path}"

    try:
        async with httpx.AsyncClient() as client:
            if method == "GET":
                resp = await client.get(url, params=params, headers=headers, timeout=15)
            else:
                resp = await client.post(url, json=params, headers=headers, timeout=15)

            if resp.status_code == 401:
                global _jwt_token
                _jwt_token = None  # clear cached token and retry next time
                return "🔐 Session expired. Please try again."

            resp.raise_for_status()
            data = resp.json()
            return format_response(action, data)

    except httpx.HTTPStatusError as e:
        return f"⚠️ ParaIQ returned an error: {e.response.status_code}"
    except httpx.RequestError as e:
        return f"⚠️ Could not reach ParaIQ backend: {e}"


def format_response(action: str, data: dict) -> str:
    """Format the API response as a readable Telegram message."""
    # Generic fallback formatter — customise per action as your API responses become clearer
    def fmt_deadlines(d):
        items = d.get("deadlines", [])
        if not items:
            return "📅 *Upcoming Deadlines*\nNo deadlines found."
        lines = [f"📅 *Upcoming Deadlines* ({d.get('count', len(items))} total)\n"]
        for item in items[:5]:
            days = item.get("days_away", "?")
            urgency = "🔴" if isinstance(days, int) and days <= 3 else "🟡" if isinstance(days, int) and days <= 7 else "🟢"
            lines.append(
                f"{urgency} *{item.get('event', 'Deadline')}*\n"
                f"   Case: {item.get('case_title', item.get('case_number', '—'))}\n"
                f"   Due: {item.get('date', '—')} ({days} days away)"
            )
        return "\n\n".join(lines)

    def fmt_dashboard(d):
        risk = d.get("high_risk_cases", 0)
        risk_flag = "🔴" if risk > 0 else "🟢"
        return (
            f"📊 *Dashboard Overview*\n\n"
            f"📁 Total Cases: *{d.get('total_cases', '—')}*\n"
            f"🔓 Open Cases: *{d.get('open_cases', '—')}*\n"
            f"{risk_flag} High Risk Cases: *{risk}*\n"
            f"🔬 Total Analyses: *{d.get('total_analyses', '—')}*\n"
            f"🌐 Languages Supported: *{d.get('languages', '—')}*\n"
            f"⚙️ Modules Live: *{d.get('modules_live', '—')}*\n"
            f"📨 Requests Today: *{d.get('requests_today', 0)}*"
        )

    def fmt_discovery(d):
        return (
            f"🗂 *Discovery Stats*\n\n"
            f"📄 Total Documents: *{d.get('total_files', d.get('total', '—'))}*\n"
            f"⏳ Pending: *{d.get('pending', '—')}*\n"
            f"✅ Processed: *{d.get('processed', d.get('completed', '—'))}*\n"
            f"❌ Failed: *{d.get('failed', '—')}*"
        )

    def fmt_cases(d):
        items = d.get("cases", [])
        if not items:
            return "📁 *Cases*\nNo cases found."
        lines = [f"📁 *Cases Found* ({len(items)})\n"]
        for c in items[:5]:
            status = c.get("status", "unknown").upper()
            flag = "🟢" if status == "OPEN" else "⚪"
            lines.append(
                f"{flag} *{c.get('case_title', c.get('matter_number', '—'))}*\n"
                f"   #{c.get('case_number', '—')} · {status}\n"
                f"   Client: {c.get('client_name', '—')}"
            )
        return "\n\n".join(lines)

    def fmt_queue(d):
        items = d.get("queue", d.get("items", []))
        if not items:
            return "🗂 *Discovery Queue*\nQueue is empty."
        return (
            f"🗂 *Discovery Queue* ({len(items)} items)\n\n" +
            "\n".join(f"• {i.get('filename', i.get('file_id', '?'))} — {i.get('status','?')}" for i in items[:8])
        )

    def fmt_health(d):
        status = d.get("status", "unknown")
        icon = "🟢" if status == "ok" else "🔴"
        return (
            f"{icon} *System Health: {status.upper()}*\n"
            f"Model: `{d.get('model', '—')}`"
        )

    def fmt_audit(d):
        logs = d.get("logs", d.get("entries", []))
        if not logs:
            return "📋 *Audit Logs*\nNo recent entries."
        lines = [f"📋 *Recent Audit Logs* ({len(logs)} entries)\n"]
        for log in logs[:5]:
            lines.append(f"• {log.get('action', log.get('event', '?'))} — {log.get('user', log.get('firm_id', '?'))} @ {str(log.get('created_at', log.get('timestamp', '')))[:16]}")
        return "\n".join(lines)

    def fmt_privilege(d):
        return (
            f"⚖️ *Privilege Stats*\n\n"
            f"Total Logged: *{d.get('total', d.get('count', '—'))}*\n"
            f"Privileged: *{d.get('privileged', '—')}*\n"
            f"Non-Privileged: *{d.get('non_privileged', '—')}*\n"
            f"Pending Review: *{d.get('pending_review', d.get('pending', '—'))}*"
        )

    def fmt_reports(d):
        items = d.get("reports", d.get("items", []))
        if not items:
            return "📑 *Reports*\nNo reports available."
        return (
            f"📑 *Available Reports* ({len(items)})\n\n" +
            "\n".join(f"• {r.get('title', r.get('report_type', r.get('name', '?')))}" for r in items[:8])
        )

    def fmt_deadlines(d):
        items = d.get("deadlines", [])
        if not items: return "📅 *Upcoming Deadlines*\nNone found."
        lines = [f"📅 *Upcoming Deadlines* ({d.get('count', len(items))} total)\n"]
        for i in items[:5]:
            days = i.get("days_away","?")
            dot = "🔴" if isinstance(days,int) and days<=3 else "🟡" if isinstance(days,int) and days<=7 else "🟢"
            lines.append(f"{dot} *{i.get('event','Deadline')}*\n   {i.get('case_title',i.get('case_number','—'))} · Due {i.get('date','—')} ({days}d)")
        return "\n\n".join(lines)

    def fmt_calendar(d):
        if isinstance(d, list): items = d
        else: items = d.get("events", d.get("items", []))
        if not items: return "📆 *Upcoming Calendar*\nNo events found."
        lines = [f"📆 *Upcoming Events* ({len(items)})\n"]
        for e in items[:5]:
            lines.append(f"• *{e.get('title',e.get('event_type','Event'))}*\n  {e.get('date',e.get('start_date','—'))} · {e.get('matter_id',e.get('case_number',''))}")
        return "\n\n".join(lines)

    def fmt_cases_stats(d):
        return (f"📁 *Case Statistics*\n\n"
                f"Total: *{d.get('total',d.get('total_cases','—'))}*\n"
                f"Open: *{d.get('open',d.get('open_cases','—'))}*\n"
                f"Closed: *{d.get('closed',d.get('closed_cases','—'))}*\n"
                f"High Risk: *{d.get('high_risk',d.get('high_risk_cases','—'))}*")

    def fmt_cases(d):
        items = d.get("cases",[])
        if not items: return "📁 *Cases*\nNo cases found."
        lines = [f"📁 *Cases Found* ({len(items)})\n"]
        for c in items[:5]:
            flag = "🟢" if c.get("status","")=="open" else "⚪"
            lines.append(f"{flag} *{c.get('case_title',c.get('case_number','—'))}*\n   #{c.get('case_number','—')} · {c.get('client_name','—')}")
        return "\n\n".join(lines)

    def fmt_contacts(d):
        items = d.get("contacts",[])
        if not items: return "👥 *Contacts*\nNo contacts found."
        lines = [f"👥 *Contacts* ({len(items)})\n"]
        for c in items[:6]:
            role = c.get("role",c.get("contact_type",""))
            lines.append(f"• *{c.get('name',c.get('full_name','—'))}* — {role}\n  {c.get('email','')}")
        return "\n".join(lines)

    def fmt_discovery_stats(d):
        return (f"🗂 *Discovery Stats*\n\n"
                f"Total: *{d.get('total_files',d.get('total','—'))}*\n"
                f"Pending: *{d.get('pending','—')}*\n"
                f"Processed: *{d.get('processed',d.get('completed','—'))}*\n"
                f"Failed: *{d.get('failed','—')}*\n"
                f"Privileged: *{d.get('privileged','—')}*")

    def fmt_discovery_queue(d):
        items = d.get("queue",d.get("items",[]))
        if not items: return "🗂 *Discovery Queue*\nQueue is empty — all caught up!"
        return (f"🗂 *Discovery Queue* ({len(items)} items)\n\n" +
                "\n".join(f"• {i.get('filename',i.get('file_id','?'))} — _{i.get('status','?')}_" for i in items[:8]))

    def fmt_duplicates(d):
        items = d.get("duplicates",d.get("groups",[]))
        count = d.get("count",len(items))
        if not items: return "✅ *No Duplicate Documents Found*"
        return (f"⚠️ *Duplicate Documents* ({count} groups)\n\n" +
                "\n".join(f"• {g.get('filename',g.get('hash','?'))} — {g.get('count','?')} copies" for g in items[:5]))

    def fmt_risk(d):
        signals = d.get("signals",d.get("items",[]))
        if not signals: return "✅ *Risk Signals*\nNo active risk signals."
        lines = [f"⚠️ *Risk Signals* ({len(signals)})\n"]
        for s in signals[:5]:
            lvl = s.get("level",s.get("severity","?"))
            dot = "🔴" if str(lvl).lower() in ["high","critical"] else "🟡" if str(lvl).lower()=="medium" else "🟢"
            lines.append(f"{dot} {s.get('description',s.get('signal','?'))}")
        return "\n".join(lines)

    def fmt_bert(d):
        status = d.get("status","unknown")
        icon = "🟢" if status in ["ready","ok","loaded","online"] else "🔴"
        return (f"{icon} *Legal-BERT Status*\n"
                f"Status: *{status}*\n"
                f"Model: {d.get('model',d.get('model_name','—'))}\n"
                f"Version: {d.get('version','—')}")

    def fmt_privilege_stats(d):
        return (f"⚖️ *Privilege Stats*\n\n"
                f"Total Logged: *{d.get('total',d.get('count','—'))}*\n"
                f"Privileged: *{d.get('privileged','—')}*\n"
                f"Non-Privileged: *{d.get('non_privileged','—')}*\n"
                f"Pending Review: *{d.get('pending_review',d.get('pending','—'))}*")

    def fmt_privilege_log(d):
        items = d.get("entries",d.get("logs",d.get("items",[])))
        if not items: return "⚖️ *Privilege Log*\nNo entries found."
        lines = [f"⚖️ *Privilege Log* ({len(items)} entries)\n"]
        for e in items[:5]:
            tag = "🔒" if e.get("privileged") else "📄"
            lines.append(f"{tag} {e.get('document_name',e.get('filename','?'))} — {e.get('privilege_type',e.get('status','?'))}")
        return "\n".join(lines)

    def fmt_reports(d):
        items = d.get("report_types",d.get("types",d.get("items",[])))
        if not items: return "📑 *Reports*\nNo report types available."
        return (f"📑 *Available Report Types* ({len(items)})\n\n" +
                "\n".join(f"• {r.get('name',r.get('report_type',str(r)))}" for r in items[:10]))

    def fmt_depositions(d):
        items = d.get("depositions",[])
        stats = d.get("stats",{})
        if "total" in d or "count" in d:
            return (f"📋 *Deposition Stats*\n\nTotal: *{d.get('total',d.get('count','—'))}*\n"
                    f"Scheduled: *{d.get('scheduled','—')}*\nCompleted: *{d.get('completed','—')}*")
        if not items: return "📋 *Depositions*\nNo depositions found."
        lines = [f"📋 *Depositions* ({len(items)})\n"]
        for dep in items[:5]:
            lines.append(f"• *{dep.get('witness_name',dep.get('title','?'))}* — {dep.get('date','?')} · {dep.get('status','?')}")
        return "\n".join(lines)

    def fmt_motions(d):
        items = d.get("motions",[])
        if "total" in d or "count" in d:
            return (f"⚖️ *Motion Stats*\n\nTotal: *{d.get('total',d.get('count','—'))}*\n"
                    f"Pending: *{d.get('pending','—')}*\nGranted: *{d.get('granted','—')}*\nDenied: *{d.get('denied','—')}*")
        if not items: return "⚖️ *Motions*\nNo motions found."
        lines = [f"⚖️ *Motions* ({len(items)})\n"]
        for m in items[:5]:
            lines.append(f"• *{m.get('title',m.get('motion_type','?'))}* — {m.get('status','?')} · {m.get('filed_date',m.get('date','?'))}")
        return "\n".join(lines)

    def fmt_contracts(d):
        items = d.get("contracts",[])
        if "total" in d or "count" in d:
            return (f"📄 *Contract Stats*\n\nTotal: *{d.get('total',d.get('count','—'))}*\n"
                    f"Active: *{d.get('active','—')}*\nExpiring Soon: *{d.get('expiring_soon','—')}*")
        if not items: return "📄 *Contracts*\nNo contracts found."
        lines = [f"📄 *Contracts* ({len(items)})\n"]
        for c in items[:5]:
            lines.append(f"• *{c.get('title',c.get('contract_type','?'))}* — {c.get('status','?')}")
        return "\n".join(lines)

    def fmt_research(d):
        items = d.get("notes",d.get("research",d.get("items",[])))
        if not items: return "🔍 *Legal Research*\nNo research notes found."
        lines = [f"🔍 *Legal Research* ({len(items)} notes)\n"]
        for r in items[:5]:
            lines.append(f"• *{r.get('title','Untitled')}* — {r.get('research_type',r.get('type','?'))} · {str(r.get('created_at',''))[:10]}")
        return "\n".join(lines)

    def fmt_dashboard(d):
        risk = d.get("high_risk_cases",0)
        return (f"📊 *Dashboard Overview*\n\n"
                f"📁 Total Cases: *{d.get('total_cases','—')}*\n"
                f"🔓 Open Cases: *{d.get('open_cases','—')}*\n"
                f"{'🔴' if risk>0 else '🟢'} High Risk: *{risk}*\n"
                f"🔬 Analyses: *{d.get('total_analyses','—')}*\n"
                f"🌐 Languages: *{d.get('languages','—')}*\n"
                f"⚙️ Modules Live: *{d.get('modules_live','—')}*\n"
                f"📨 Requests Today: *{d.get('requests_today',0)}*")

    def fmt_audit(d):
        logs = d.get("logs",d.get("entries",[]))
        if "total" in d and not logs:
            return (f"📋 *Audit Stats*\n\nTotal Events: *{d.get('total','—')}*\n"
                    f"Today: *{d.get('today','—')}*\nThis Week: *{d.get('this_week','—')}*")
        if not logs: return "📋 *Audit Logs*\nNo recent entries."
        lines = [f"📋 *Recent Audit Logs* ({len(logs)})\n"]
        for log in logs[:5]:
            lines.append(f"• {log.get('action',log.get('event','?'))} — {log.get('user',log.get('firm_id','?'))} @ {str(log.get('created_at',log.get('timestamp','')))[:16]}")
        return "\n".join(lines)

    def fmt_health(d):
        status = d.get("status","unknown")
        icon = "🟢" if status=="ok" else "🔴"
        return f"{icon} *System Health: {status.upper()}*\nModel: `{d.get('model','—')}`"

    def fmt_api_stats(d):
        return (f"📡 *API Stats*\n\n"
                f"Total Requests: *{d.get('total_requests',d.get('total','—'))}*\n"
                f"Today: *{d.get('requests_today',d.get('today','—'))}*\n"
                f"Errors: *{d.get('errors',d.get('error_count','—'))}*\n"
                f"Avg Response: *{d.get('avg_response_ms',d.get('avg_ms','—'))}ms*")

    def fmt_generic(action, d):
        return f"✅ Done.\n```json\n{json.dumps(d,indent=2)[:600]}\n```"

    formatters = {
        "get_deadlines":            fmt_deadlines,
        "get_upcoming_calendar":    fmt_calendar,
        "get_calendar_types":       lambda d: "📆 *Calendar Types*\n\n" + "\n".join(f"• {t.get('name',str(t))}" for t in d.get("types",d.get("items",[]))) or "No types found.",
        "get_cases_stats":          fmt_cases_stats,
        "search_cases":             fmt_cases,
        "get_contacts":             fmt_contacts,
        "get_discovery_stats":      fmt_discovery_stats,
        "get_discovery_queue":      fmt_discovery_queue,
        "get_discovery_duplicates": fmt_duplicates,
        "get_discovery_catalog":    lambda d: f"🗂 *Discovery Catalog*\n\nTotal files: *{d.get('total',d.get('count','—'))}*",
        "get_risk_signals":         fmt_risk,
        "get_legal_bert_status":    fmt_bert,
        "get_intake_history":       lambda d: f"📥 *Intake History*\n\n{len(d.get('history',d.get('items',[])))} past intakes found.",
        "get_privilege_stats":      fmt_privilege_stats,
        "get_privilege_log":        fmt_privilege_log,
        "get_reports_list":         fmt_reports,
        "get_deposition_stats":     fmt_depositions,
        "get_depositions":          fmt_depositions,
        "get_motion_stats":         fmt_motions,
        "get_motions":              fmt_motions,
        "get_contract_stats":       fmt_contracts,
        "get_contracts":            fmt_contracts,
        "get_research":             fmt_research,
        "get_dashboard_stats":      fmt_dashboard,
        "get_audit_logs":           fmt_audit,
        "get_audit_stats":          fmt_audit,
        "get_health":               fmt_health,
        "get_api_stats":            fmt_api_stats,
        "screen_all_discovery":     lambda d: f"🔍 *Screening launched!*\n\nDocuments queued: *{d.get('queued',d.get('count','—'))}*",
    }

    fmt = formatters.get(action)
    if fmt:
        try:
            return fmt(data)
        except Exception:
            pass

    # Fallback: pretty-print the raw JSON
    return f"✅ Done.\n```json\n{json.dumps(data, indent=2)[:800]}\n```"


# ── SECURITY CHECK ────────────────────────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True  # open to all if whitelist is empty
    return user_id in ALLOWED_USER_IDS


# ── TELEGRAM HANDLERS ─────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    await update.message.reply_markdown(
        f"👋 Hey *{user.first_name}*! I'm your *ParaIQ Voice Assistant*.\n\n"
        f"Send me a 🎤 *voice message* or type a command:\n\n"
        f'• _\"Show upcoming deadlines\"_\n'
        f'• _\"Any new cases today?\"_\n'
        f'• _\"Dashboard stats\"_\n'
        f'• _\"System health\"_\n\n'
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_markdown(
        "*ParaIQ Voice Commands*\n\n"
        "🐋 Whale activity, scanner control, top gainers, portfolio, daily summary\n\n"
        "Just speak naturally — no need to use exact phrases.\n\n"
        "*Commands:*\n"
        "/start — Welcome message\n"
        "/help — This message\n"
        "/status — Quick scanner status check\n\n"
        "_Tip: Hold the mic button in Telegram to record, release to send._"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("⏳ Checking scanner status...")
    result = await execute_command("get_scanner_status", {})
    await update.message.reply_markdown(result)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages: download → transcribe → parse → execute → reply."""
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    log.info(f"Voice message from {user.username or user.id}")

    # 1. Acknowledge immediately (feels responsive)
    thinking_msg = await update.message.reply_text("🎙 Got it, processing...")

    try:
        # 2. Download audio file from Telegram
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        audio_bytes = await voice_file.download_as_bytearray()
        audio_bytes = bytes(audio_bytes)
        log.info(f"Downloaded voice file: {len(audio_bytes)} bytes")

        # 3. Transcribe with Whisper
        await thinking_msg.edit_text("📝 Transcribing...")
        transcript = await transcribe_audio(audio_bytes, file_ext="ogg")

        if not transcript.strip():
            await thinking_msg.edit_text("🤔 Couldn't hear anything. Please try again.")
            return

        # 4. Parse intent with Claude
        await thinking_msg.edit_text(f'💬 Heard: _"{transcript}"_\n⚙️ Running...', parse_mode="Markdown")
        parsed = await parse_intent(transcript)

        action     = parsed.get("action", "unknown")
        params     = parsed.get("params", {})
        confidence = parsed.get("confidence", 0)
        understood = parsed.get("understood_as", "")

        # Low confidence — ask user to repeat
        if confidence < 0.65 or action == "unknown":
            await thinking_msg.edit_text(
                f'❓ Not sure I understood that.\n'
                f'_You said:_ "{transcript}"\n\n'
                f'Try: _\"show upcoming deadlines\"_ or _\"any new cases today\"_',
                parse_mode="Markdown")
            return

        # 5. Execute against ParaIQ backend
        result = await execute_command(action, params)

        # 6. Send result
        header = f'🗣 _"{transcript}"_\n\n'
        await thinking_msg.edit_text(header + result, parse_mode="Markdown")

    except Exception as e:
        log.exception(f"Error handling voice message: {e}")
        await thinking_msg.edit_text(f"⚠️ Something went wrong: {str(e)[:200]}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages the same way as voice (useful for testing)."""
    user = update.effective_user
    if not is_allowed(user.id):
        return

    transcript = update.message.text.strip()
    if transcript.startswith("/"):
        return  # let command handlers deal with it

    log.info(f"Text command from {user.username or user.id}: '{transcript}'")
    thinking_msg = await update.message.reply_text("⚙️ Running...")

    try:
        parsed    = await parse_intent(transcript)
        action    = parsed.get("action", "unknown")
        params    = parsed.get("params", {})
        confidence= parsed.get("confidence", 0)

        if confidence < 0.65 or action == "unknown":
            await thinking_msg.edit_text(
                f'Try: _\"show upcoming deadlines\"_ or _\"any new cases today\"_',
                parse_mode="Markdown"
            )
            return

        result = await execute_command(action, params)
        await thinking_msg.edit_text(result, parse_mode="Markdown")

    except Exception as e:
        log.exception(e)
        await thinking_msg.edit_text(f"⚠️ Error: {str(e)[:200]}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    log.info("Starting ParaIQ Voice Bot...")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
