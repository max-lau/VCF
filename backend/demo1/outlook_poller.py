"""
ParaIQ Outlook / Microsoft Graph Poller
- MSAL OAuth2 (delegated, authorization code flow)
- Polls /me/mailFolders/Inbox/messages for unread mail
- DB-based deduplication via email_processing_log
- Adaptive quiet-hour hibernation (same firm_email_settings)
"""
import asyncio
import logging
import os
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

import pytz
import requests
import msal

from .email_filter import EmailFilterEngine, EmailMessage

logger = logging.getLogger(__name__)

CLIENT_ID     = os.getenv("OUTLOOK_CLIENT_ID")
TENANT_ID     = os.getenv("OUTLOOK_TENANT_ID")
CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("OUTLOOK_REDIRECT_URI", "https://app.para-iq.com/auth/outlook/callback")

SCOPES = ["Mail.Read", "User.Read", "email"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# In-memory OAuth state store (use Redis in production)
_oauth_states: dict = {}


# ── MSAL app factory ──────────────────────────────────────────────────────────
def _build_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/common",
        client_credential=CLIENT_SECRET,
    )


# ── OAuth helpers ─────────────────────────────────────────────────────────────
def get_auth_url(attorney_id: int, firm_id: str) -> str:
    state = str(uuid.uuid4())
    _oauth_states[state] = {"attorney_id": attorney_id, "firm_id": firm_id}
    app = _build_msal_app()
    url = app.get_authorization_request_url(
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI,
    )
    return url, state


def exchange_code(code: str, state: str) -> dict:
    """Exchange auth code for tokens. Returns token dict."""
    session = _oauth_states.pop(state, None)
    if not session:
        raise ValueError("Invalid OAuth state")
    app = _build_msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    if "error" in result:
        raise ValueError(f"Token exchange failed: {result.get('error_description', result['error'])}")
    return {**result, **session}


def refresh_access_token(refresh_token: str) -> dict:
    """Use refresh token to get new access token."""
    app = _build_msal_app()
    result = app.acquire_token_by_refresh_token(
        refresh_token=refresh_token,
        scopes=SCOPES,
    )
    if "error" in result:
        raise ValueError(f"Token refresh failed: {result.get('error_description', result['error'])}")
    return result


# ── Graph API helpers ─────────────────────────────────────────────────────────
def _graph_get(endpoint: str, access_token: str) -> dict:
    resp = requests.get(
        f"{GRAPH_BASE}{endpoint}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _get_inbox_messages(access_token: str, top: int = 50) -> list:
    """Fetch unread inbox messages via Graph API."""
    data = _graph_get(
        f"/me/mailFolders/Inbox/messages"
        f"?$filter=isRead eq false"
        f"&$top={top}"
        f"&$select=id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments,attachments",
        access_token
    )
    return data.get("value", [])


def _parse_graph_message(raw: dict, account: dict) -> Optional[EmailMessage]:
    """Convert Microsoft Graph message → normalised EmailMessage."""
    try:
        from_addr = raw.get("from", {}).get("emailAddress", {})
        from_str  = f"{from_addr.get('name', '')} <{from_addr.get('address', '')}>"

        to_list = [
            r["emailAddress"]["address"]
            for r in raw.get("toRecipients", [])
            if r.get("emailAddress", {}).get("address")
        ]
        cc_list = [
            r["emailAddress"]["address"]
            for r in raw.get("ccRecipients", [])
            if r.get("emailAddress", {}).get("address")
        ]

        body     = raw.get("body", {})
        body_text = body.get("content", "") if body.get("contentType") == "text" else ""
        body_html = body.get("content", "") if body.get("contentType") == "html" else ""

        # Strip HTML tags for text version if only HTML available
        if not body_text and body_html:
            import re
            import html
            body_text = re.sub(r'<[^>]+>', ' ', body_html)
            body_text = html.unescape(body_text)
            body_text = re.sub(r'\s+', ' ', body_text).strip()

        received_str = raw.get("receivedDateTime", "")
        try:
            received_at = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
        except (ValueError, TypeError) as e:
            logger.debug(f"[outlook_poller] receivedDateTime parse failed for '{received_str}': {e}")
            received_at = datetime.now(timezone.utc)

        return EmailMessage(
            provider_message_id=raw["id"],
            provider="outlook",
            attorney_id=str(account["attorney_id"]),
            account_id=str(account["id"]),
            firm_id=account["firm_id"],
            from_address=from_str,
            to_addresses=to_list,
            cc_addresses=cc_list,
            subject=raw.get("subject", "(no subject)"),
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            headers={},
            source_url=raw.get("webLink", ""),
            attachment_names=[],
        )
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        logger.error(f"Failed to parse Outlook message {raw.get('id')}: {e}")
        return None


# ── DB helpers ────────────────────────────────────────────────────────────────
def _get_processed_ids(attorney_id, firm_id: str) -> set:
    from .pg import get_conn
    try:
        with get_conn(firm_id) as conn:
            cur = conn.execute(
                "SELECT provider_message_id FROM email_processing_log WHERE attorney_id = %s AND provider = 'outlook'",
                (attorney_id,)
            )
            rows = cur.fetchall() or []
            if not rows:
                return set()
            if hasattr(rows[0], 'keys'):
                return {r["provider_message_id"] for r in rows}
            return {r[0] for r in rows}
    except (psycopg2.Error, KeyError, ValueError) as e:
        logger.warning(f"[Outlook Dedup] Could not fetch processed IDs: {e}")
        return set()


def _save_to_db(msg: EmailMessage, result, firm_id: str):
    from .pg import get_conn
    intake_id = None
    with get_conn(firm_id) as conn:
        if result.routing_decision in ("intake", "review"):
            intake_id = str(uuid.uuid4())
            priority = result.priority if result.routing_decision == "intake" else "review"
            cur = conn.execute(
                """INSERT INTO email_intakes (
                       id, account_id, attorney_id, firm_id, case_id,
                       provider, provider_message_id,
                       from_address, to_addresses, cc_addresses, subject, body_text,
                       received_at, extracted_entities, action_items, deadline_dates,
                       priority, has_attachments, attachment_names
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (provider, provider_message_id, attorney_id) DO NOTHING""",
                (intake_id, msg.account_id, msg.attorney_id, msg.firm_id,
                 result.case_id_matched, msg.provider, msg.provider_message_id,
                 msg.from_address, msg.to_addresses, msg.cc_addresses,
                 msg.subject, msg.body_text, msg.received_at,
                 json.dumps(result.extracted_entities),
                 json.dumps(result.action_items),
                 json.dumps(result.deadline_dates),
                 priority, bool(msg.attachment_names), msg.attachment_names)
            )
            if cur.rowcount == 0:
                intake_id = None

        conn.execute(
            """INSERT INTO email_processing_log (
                   account_id, attorney_id, firm_id, provider, provider_message_id,
                   from_address, subject, received_at,
                   stage1_domain_score, stage2_nlp_score,
                   stage3_spam_penalty, stage4_final_score,
                   case_id_matched, routing_decision, discard_reason, intake_id
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (provider_message_id, attorney_id) DO NOTHING""",
            (msg.account_id, msg.attorney_id, msg.firm_id,
             msg.provider, msg.provider_message_id,
             msg.from_address, msg.subject, msg.received_at,
             result.stage1_domain_score, result.stage2_nlp_score,
             result.stage3_spam_penalty, result.stage4_final_score,
             result.case_id_matched, result.routing_decision,
             result.discard_reason, intake_id)
        )

        # ── Case Binder auto-link ─────────────────────────────────────────
        if (intake_id and result.routing_decision == "intake"
                and result.case_id_matched):
            conn.execute(
                """INSERT INTO case_documents
                       (firm_id, case_id, document_name, source, source_type,
                        source_ref, doc_text, entities_json, upload_date, source_url)
                   VALUES (%s, %s, %s, %s, 'email', %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (msg.firm_id,
                 result.case_id_matched,
                 f"Email: {msg.subject[:100]} [from: {msg.from_address[:60]}]",
                 'email',
                 intake_id,
                 msg.body_text[:4000] if msg.body_text else None,
                 json.dumps(result.extracted_entities),
                 msg.received_at,
                 getattr(msg, 'source_url', None))
            )
        # ─────────────────────────────────────────────────────────────────
        # -- Attachment vault (Outlook) --
        if (intake_id and result.routing_decision == "intake"
                and msg.attachment_names):
            try:
                from .attachment_handler import process_attachments
                import requests as _req
                att_list = []
                access_token = getattr(msg, '_access_token', None)
                graph_msg_id = getattr(msg, '_graph_msg_id', None)
                if access_token and graph_msg_id:
                    url = f"https://graph.microsoft.com/v1.0/me/messages/{graph_msg_id}/attachments"
                    resp = _req.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
                    if resp.status_code == 200:
                        for att in resp.json().get("value", []):
                            if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
                                import base64
                                data = base64.b64decode(att.get("contentBytes", ""))
                                att_list.append({"filename": att.get("name", "attachment"), "data": data})
                if att_list:
                    process_attachments(att_list, msg.firm_id, result.case_id_matched, intake_id, conn)
            except (OSError, ValueError, KeyError) as ve:
                logger.error(f"[Vault] Outlook attachment processing error: {ve}")
        # -- Attachment vault (Outlook) --
        if (intake_id and result.routing_decision == "intake"
                and msg.attachment_names):
            try:
                from .attachment_handler import process_attachments
                import requests as _req
                att_list = []
                access_token = getattr(msg, '_access_token', None)
                graph_msg_id = getattr(msg, '_graph_msg_id', None)
                if access_token and graph_msg_id:
                    url = f"https://graph.microsoft.com/v1.0/me/messages/{graph_msg_id}/attachments"
                    resp = _req.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
                    if resp.status_code == 200:
                        for att in resp.json().get("value", []):
                            if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
                                import base64
                                data = base64.b64decode(att.get("contentBytes", ""))
                                att_list.append({"filename": att.get("name", "attachment"), "data": data})
                if att_list:
                    process_attachments(att_list, msg.firm_id, result.case_id_matched, intake_id, conn)
            except (OSError, ValueError, KeyError) as ve:
                logger.error(f"[Vault] Outlook attachment processing error: {ve}")
    return intake_id


def _get_active_accounts() -> list:
    """Enumerate active firms, then fetch each firm's accounts inside its own
    tenant context. RLS-correct under FORCE ROW LEVEL SECURITY (migration 005):
    the old single-query scan from 'default' context would silently see only
    default-firm rows once attorney_email_accounts is forced."""
    from .pg import get_conn
    accounts: list = []
    with get_conn("default") as conn:  # firms table: no firm_id, not forced -- readable anywhere
        cur = conn.execute("SELECT id FROM firms WHERE active=TRUE")
        firm_rows = cur.fetchall() or []
    firm_ids = [r["id"] if hasattr(r, "keys") else r[0] for r in firm_rows]
    for fid in firm_ids:
        with get_conn(fid) as conn:
            cur = conn.execute(
                "SELECT * FROM attorney_email_accounts WHERE provider=%s AND is_active=TRUE",
                ("outlook",),
            )
            rows = cur.fetchall() or []
            if not rows:
                continue
            if hasattr(rows[0], "keys"):
                accounts.extend(dict(r) for r in rows)
            else:
                cols = [d[0] for d in cur.description]
                accounts.extend(dict(zip(cols, r)) for r in rows)
    return accounts
def _get_firm_settings(firm_id: str) -> dict:
    from .pg import get_conn
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT * FROM firm_email_settings WHERE firm_id=%s", (firm_id,)
            ).fetchone()
            if row:
                return dict(row)
    except (psycopg2.Error, KeyError, ValueError) as e:
        logger.warning(f"[outlook_poller] _get_firm_settings failed for firm '{firm_id}': {e}")
    return {
        "quiet_hour_start":     int(os.getenv("EMAIL_QUIET_HOUR_START", 21)),
        "quiet_hour_end":       int(os.getenv("EMAIL_QUIET_HOUR_END", 7)),
        "poll_interval_active": int(os.getenv("EMAIL_POLL_INTERVAL_ACTIVE", 300)),
        "poll_interval_quiet":  int(os.getenv("EMAIL_POLL_INTERVAL_QUIET", 1800)),
        "timezone":             "America/New_York",
    }


def _is_quiet_hours(tz_name: str, quiet_start: int, quiet_end: int) -> bool:
    try:
        tz = pytz.timezone(tz_name)
        hour = datetime.now(tz).hour
        if quiet_start > quiet_end:
            return hour >= quiet_start or hour < quiet_end
        return quiet_start <= hour < quiet_end
    except (pytz.exceptions.UnknownTimeZoneError, ValueError, TypeError) as e:
        logger.warning(f"[outlook_poller] _is_quiet_hours failed for tz '{tz_name}': {e}")
        return False


# ── Per-account poll ──────────────────────────────────────────────────────────
def poll_outlook_account(account: dict):
    firm_id = account["firm_id"]
    engine  = EmailFilterEngine(firm_id)
    engine.load_case_registry()

    # Refresh token
    try:
        token_result = refresh_access_token(account["refresh_token"])
        access_token = token_result["access_token"]
        new_refresh   = token_result.get("refresh_token", account["refresh_token"])
    except (httpx.HTTPError, KeyError, ValueError, RuntimeError) as e:
        logger.error(f"[Outlook] Token refresh failed for {account['email_address']}: {e}")
        if "invalid_grant" in str(e).lower():
            from .pg import get_conn
            try:
                with get_conn(firm_id) as conn:
                    conn.execute(
                        "UPDATE attorney_email_accounts SET is_active=FALSE WHERE id=%s",
                        (account["id"],)
                    )
                logger.warning(f"[Outlook] Auto-deactivated {account['email_address']} — invalid_grant. Re-authenticate via Settings.")
            except (psycopg2.Error, OSError) as db_err:
                logger.error(f"[Outlook] Failed to deactivate account: {db_err}")
        return

    # Save refreshed tokens
    from .pg import get_conn
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE attorney_email_accounts SET access_token=%s, refresh_token=%s, updated_at=NOW() WHERE id=%s",
            (access_token, new_refresh, account["id"])
        )

    # Fetch and process messages
    try:
        messages = _get_inbox_messages(access_token)
        logger.info(f"[Outlook] {account['email_address']}: {len(messages)} unread messages")

        processed_ids = _get_processed_ids(account["attorney_id"], firm_id)
        for raw in messages:
            if raw["id"] in processed_ids:
                logger.debug(f"[Outlook Dedup] Skipping {raw['id']}")
                continue
            msg = _parse_graph_message(raw, account)
            if not msg:
                continue
            filter_result = engine.process(msg)
            _save_to_db(msg, filter_result, firm_id)

    except (httpx.HTTPError, ValueError, KeyError, RuntimeError) as e:
        logger.error(f"[Outlook] API error for {account['email_address']}: {e}")


# ── Poller service ────────────────────────────────────────────────────────────
class OutlookPollerService:
    def __init__(self):
        self.running = False

    async def run(self):
        self.running = True
        logger.info("OutlookPollerService started")
        while self.running:
            try:
                accounts = await asyncio.get_event_loop().run_in_executor(
                    None, _get_active_accounts
                )
                if not accounts:
                    await asyncio.sleep(60)
                    continue

                sleep_interval = int(os.getenv("EMAIL_POLL_INTERVAL_ACTIVE", 300))
                for account in accounts:
                    settings = await asyncio.get_event_loop().run_in_executor(
                        None, _get_firm_settings, account["firm_id"]
                    )
                    quiet    = _is_quiet_hours(
                        settings["timezone"],
                        settings["quiet_hour_start"],
                        settings["quiet_hour_end"],
                    )
                    interval = settings["poll_interval_quiet"] if quiet else settings["poll_interval_active"]
                    sleep_interval = min(sleep_interval, interval)

                    await asyncio.get_event_loop().run_in_executor(
                        None, poll_outlook_account, account
                    )

                logger.info(f"[Outlook Poller] Cycle complete. Sleeping {sleep_interval}s.")
                await asyncio.sleep(sleep_interval)

            except (RuntimeError, OSError, asyncio.CancelledError, ValueError) as e:
                logger.error(f"[Outlook Poller] Unexpected error: {e}")
                await asyncio.sleep(60)

    def stop(self):
        self.running = False
