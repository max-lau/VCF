"""
ParaIQ Gmail Poller - synchronous psycopg2 version
Adaptive polling: active hours 5min, quiet hours 30min
"""
import asyncio
import logging
import os
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .email_filter import EmailFilterEngine, EmailMessage

logger = logging.getLogger(__name__)

SCOPES        = ["https://www.googleapis.com/auth/gmail.readonly"]
CLIENT_ID     = os.getenv("GMAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")


def _is_quiet_hours(tz_name: str, quiet_start: int, quiet_end: int) -> bool:
    try:
        tz = pytz.timezone(tz_name)
        hour = datetime.now(tz).hour
        if quiet_start > quiet_end:
            return hour >= quiet_start or hour < quiet_end
        return quiet_start <= hour < quiet_end
    except Exception:
        return False


def _refresh_credentials(account: dict) -> Credentials:
    creds = Credentials(
        token=account["access_token"],
        refresh_token=account["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )
    if creds.expired or not creds.valid:
        creds.refresh(Request())
    return creds


def _parse_gmail_message(raw: dict, account: dict) -> Optional[EmailMessage]:
    try:
        headers = {h["name"].lower(): h["value"]
                   for h in raw.get("payload", {}).get("headers", [])}
        body_text = ""
        body_html = ""
        attachment_names = []

        def extract_parts(parts_list):
            nonlocal body_text, body_html
            for part in parts_list:
                mime = part.get("mimeType", "")
                data = part.get("body", {}).get("data", "")
                if data:
                    import base64
                    decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                    if mime == "text/plain":
                        import html
                        body_text = html.unescape(decoded)
                    elif mime == "text/html":
                        body_html = decoded
                if part.get("filename"):
                    attachment_names.append(part["filename"])
                if part.get("parts"):
                    extract_parts(part["parts"])

        payload = raw.get("payload", {})
        if payload.get("body", {}).get("data"):
            import base64
            body_text = base64.urlsafe_b64decode(
                payload["body"]["data"] + "=="
            ).decode("utf-8", errors="replace")
        else:
            extract_parts(payload.get("parts", []))

        try:
            from email.utils import parsedate_to_datetime
            received_at = parsedate_to_datetime(headers.get("date", "")).astimezone(timezone.utc)
        except Exception:
            received_at = datetime.now(timezone.utc)

        return EmailMessage(
            provider_message_id=raw["id"],
            provider="gmail",
            attorney_id=str(account["attorney_id"]),
            account_id=str(account["id"]),
            firm_id=account["firm_id"],
            from_address=headers.get("from", ""),
            to_addresses=[a.strip() for a in headers.get("to", "").split(",") if a.strip()],
            cc_addresses=[a.strip() for a in headers.get("cc", "").split(",") if a.strip()],
            subject=headers.get("subject", "(no subject)"),
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            headers=headers,
            attachment_names=attachment_names,
        )
    except Exception as e:
        logger.error(f"Failed to parse Gmail message {raw.get('id')}: {e}")
        return None


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
                intake_id = None  # conflict — intake already exists

        conn.execute(
            """INSERT INTO email_processing_log (
                   account_id, attorney_id, firm_id, provider, provider_message_id,
                   from_address, subject, received_at,
                   stage1_domain_score, stage2_nlp_score,
                   stage3_spam_penalty, stage4_final_score,
                   case_id_matched, routing_decision, discard_reason, intake_id
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
                        source_ref, doc_text, entities_json, upload_date)
                   VALUES (%s, %s, %s, %s, 'email', %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (msg.firm_id,
                 result.case_id_matched,
                 f"Email: {msg.subject[:100]} [from: {msg.from_address[:60]}]",
                 'email',
                 intake_id,
                 msg.body_text[:4000] if msg.body_text else None,
                 json.dumps(result.extracted_entities),
                 msg.received_at)
            )
        # ─────────────────────────────────────────────────────────────────
    return intake_id


def _get_processed_ids(attorney_id, firm_id: str) -> set:
    """Fetch all processed message IDs for this attorney."""
    from .pg import get_conn
    try:
        with get_conn(firm_id) as conn:
            cur = conn.execute(
                "SELECT provider_message_id FROM email_processing_log WHERE attorney_id = %s",
                (attorney_id,)
            )
            rows = cur.fetchall() or []
            if not rows:
                return set()
            if hasattr(rows[0], 'keys'):
                return {r["provider_message_id"] for r in rows}
            return {r[0] for r in rows}
    except Exception as e:
        logger.warning(f"[Dedup] Could not fetch processed IDs: {e}")
        return set()
def poll_gmail_account(account: dict):
    firm_id = account["firm_id"]
    engine = EmailFilterEngine(firm_id)
    engine.load_case_registry()

    try:
        creds = _refresh_credentials(account)
    except Exception as e:
        logger.error(f"Token refresh failed for {account['email_address']}: {e}")
        return

    # Update refreshed token
    from .pg import get_conn
    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE attorney_email_accounts SET access_token=%s, token_expiry=%s, updated_at=NOW() WHERE id=%s",
            (creds.token, creds.expiry, account["id"])
        )

    try:
        service = build("gmail", "v1", credentials=creds)
        result = service.users().messages().list(
            userId="me", labelIds=["INBOX", "UNREAD"], maxResults=50
        ).execute()

        messages = result.get("messages", [])
        logger.info(f"[Gmail] {account['email_address']}: {len(messages)} new messages")

        processed_ids = _get_processed_ids(account["attorney_id"], firm_id)
        for m in messages:
            if m["id"] in processed_ids:
                logger.debug(f"[Dedup] Skipping {m['id']}")
                continue
            raw = service.users().messages().get(
                userId="me", id=m["id"], format="full"
            ).execute()
            msg = _parse_gmail_message(raw, account)
            if not msg:
                continue
            filter_result = engine.process(msg)
            _save_to_db(msg, filter_result, firm_id)


    except HttpError as e:
        logger.error(f"Gmail API error for {account['email_address']}: {e}")


def _get_firm_settings(firm_id: str) -> dict:
    from .pg import get_conn
    try:
        with get_conn(firm_id) as conn:
            row = conn.execute("SELECT * FROM firm_email_settings WHERE firm_id=%s", (firm_id,)).fetchone()
            if row:
                return dict(row)
    except Exception:
        pass
    return {
        "quiet_hour_start":   int(os.getenv("EMAIL_QUIET_HOUR_START", 21)),
        "quiet_hour_end":     int(os.getenv("EMAIL_QUIET_HOUR_END", 7)),
        "poll_interval_active": int(os.getenv("EMAIL_POLL_INTERVAL_ACTIVE", 300)),
        "poll_interval_quiet":  int(os.getenv("EMAIL_POLL_INTERVAL_QUIET", 1800)),
        "timezone": "America/New_York",
    }


def _get_active_accounts() -> list:
    from .pg import get_conn
    with get_conn("default") as conn:
        cur = conn.execute(
            "SELECT * FROM attorney_email_accounts WHERE provider=%s AND is_active=TRUE",
            ("gmail",)
        )
        rows = cur.fetchall() or []
        if not rows:
            return []
        # RealDictCursor returns dict-like rows
        if hasattr(rows[0], 'keys'):
            return [dict(r) for r in rows]
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]


class GmailPollerService:
    def __init__(self):
        self.running = False

    async def run(self):
        self.running = True
        logger.info("GmailPollerService started")
        while self.running:
            try:
                accounts = await asyncio.get_event_loop().run_in_executor(
                    None, _get_active_accounts
                )
                if not accounts:
                    logger.info("[Poller] No active Gmail accounts. Sleeping 60s.")
                    await asyncio.sleep(60)
                    continue

                sleep_interval = int(os.getenv("EMAIL_POLL_INTERVAL_ACTIVE", 300))
                for account in accounts:
                    account = dict(account)
                    settings = await asyncio.get_event_loop().run_in_executor(
                        None, _get_firm_settings, account["firm_id"]
                    )
                    quiet = _is_quiet_hours(
                        settings["timezone"],
                        settings["quiet_hour_start"],
                        settings["quiet_hour_end"],
                    )
                    interval = settings["poll_interval_quiet"] if quiet else settings["poll_interval_active"]
                    sleep_interval = min(sleep_interval, interval)
                    if quiet:
                        logger.info(f"[Poller] Quiet hours active for firm '{account['firm_id']}' — interval {interval}s")

                    await asyncio.get_event_loop().run_in_executor(
                        None, poll_gmail_account, account
                    )

                logger.info(f"[Poller] Cycle complete. Sleeping {sleep_interval}s.")
                await asyncio.sleep(sleep_interval)

            except Exception as e:
                logger.error(f"[Poller] Unexpected error: {e}")
                await asyncio.sleep(60)

    def stop(self):
        self.running = False
        logger.info("GmailPollerService stopped")
