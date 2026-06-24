"""
ParaIQ Email Router - uses synchronous psycopg2 via db_dep
"""
import os, uuid, logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow

from .auth import get_current_user
from .pg import db_dep, PgConn, get_conn

logger = logging.getLogger(__name__)
router = APIRouter(tags=["email"])

GMAIL_CLIENT_ID     = os.getenv("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
GMAIL_REDIRECT_URI  = os.getenv("GMAIL_REDIRECT_URI", "https://app.para-iq.com/auth/gmail/callback")
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "openid","https://www.googleapis.com/auth/userinfo.email",
]
_oauth_states: dict = {}

def _build_flow():
    return Flow.from_client_config(
        {"web":{"client_id":GMAIL_CLIENT_ID,"client_secret":GMAIL_CLIENT_SECRET,
                "auth_uri":"https://accounts.google.com/o/oauth2/auth",
                "token_uri":"https://oauth2.googleapis.com/token",
                "redirect_uris":[GMAIL_REDIRECT_URI]}},
        scopes=GMAIL_SCOPES, redirect_uri=GMAIL_REDIRECT_URI,
    )

def _rows(cur) -> list:
    rows = cur.fetchall()
    if not rows:
        return []
    # RealDictCursor returns dict-like rows — convert directly
    if hasattr(rows[0], 'keys'):
        return [dict(r) for r in rows]
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]

def _row(cur) -> Optional[dict]:
    r = cur.fetchone()
    if not r:
        return None
    if hasattr(r, 'keys'):
        return dict(r)
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, r))

# ── Accounts ─────────────────────────────────────────────────────────────────

@router.get("/email/accounts")
def list_email_accounts(current_user=Depends(get_current_user), db:PgConn=Depends(db_dep)):
    cur = db.execute(
        "SELECT id,provider,email_address,is_active,created_at,updated_at FROM attorney_email_accounts WHERE attorney_id=%s ORDER BY created_at DESC",
        (current_user["id"],)
    )
    return _rows(cur)

@router.post("/email/accounts/gmail/connect")
def connect_gmail(current_user=Depends(get_current_user)):
    flow = _build_flow()
    state = str(uuid.uuid4())
    _oauth_states[state] = {"attorney_id": current_user["id"], "firm_id": current_user.get("firm_id","default")}
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    _oauth_states[state]["code_verifier"] = flow.code_verifier
    return {"auth_url": auth_url}

@router.get("/auth/gmail/callback")
def gmail_callback(code:str, state:str, db:PgConn=Depends(db_dep)):
    session = _oauth_states.pop(state, None)
    if not session:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    flow = _build_flow()
    try:
        flow.fetch_token(code=code, code_verifier=session.get("code_verifier"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")
    creds = flow.credentials
    try:
        from google.oauth2 import id_token as git
        from google.auth.transport import requests as gr
        email_address = git.verify_oauth2_token(creds.id_token, gr.Request(), GMAIL_CLIENT_ID).get("email","unknown")
    except Exception:
        email_address = "unknown"
    db.execute(
        """INSERT INTO attorney_email_accounts (attorney_id,firm_id,provider,email_address,access_token,refresh_token,token_expiry)
           VALUES (%s,%s,'gmail',%s,%s,%s,%s)
           ON CONFLICT (attorney_id,provider,email_address) DO UPDATE SET
               access_token=EXCLUDED.access_token, refresh_token=EXCLUDED.refresh_token,
               token_expiry=EXCLUDED.token_expiry, is_active=TRUE, updated_at=NOW()""",
        (session["attorney_id"],session["firm_id"],email_address,creds.token,creds.refresh_token,creds.expiry)
    )
    logger.info(f"Gmail connected: {email_address}")
    return RedirectResponse(url="/dashboard?gmail=connected")

@router.delete("/email/accounts/{account_id}")
def disconnect_account(account_id:str, current_user=Depends(get_current_user), db:PgConn=Depends(db_dep)):
    db.execute("UPDATE attorney_email_accounts SET is_active=FALSE,updated_at=NOW() WHERE id=%s AND attorney_id=%s",
               (account_id, current_user["id"]))
    return {"status":"disconnected"}

# ── Intake ────────────────────────────────────────────────────────────────────

@router.get("/email/intake")
def get_intake(case_id:Optional[str]=Query(None), priority:Optional[str]=Query(None),
               from_address:Optional[str]=Query(None), limit:int=Query(20,le=100), offset:int=Query(0),
               current_user=Depends(get_current_user), db:PgConn=Depends(db_dep)):
    filters = ["attorney_id=%s"]; params:list = [current_user["id"]]
    if case_id:       filters.append("case_id=%s");              params.append(case_id)
    if priority:      filters.append("priority=%s");             params.append(priority)
    if from_address:  filters.append("from_address ILIKE %s");   params.append(f"%{from_address}%")
    where = " AND ".join(filters)
    rows  = _rows(db.execute(f"SELECT id,provider,from_address,subject,received_at,case_id,priority,has_attachments,extracted_entities,action_items,deadline_dates,ingested_at FROM email_intakes WHERE {where} ORDER BY received_at DESC LIMIT %s OFFSET %s", (*params,limit,offset)))
    total = _row(db.execute(f"SELECT COUNT(*) as cnt FROM email_intakes WHERE {where}", params))
    return {"total": total["cnt"] if total else 0, "limit":limit, "offset":offset, "items":rows}

@router.get("/email/intake/{intake_id}")
def get_intake_detail(intake_id:str, current_user=Depends(get_current_user), db:PgConn=Depends(db_dep)):
    row = _row(db.execute(
        """SELECT i.*, l.stage1_domain_score, l.stage2_nlp_score,
               l.stage3_spam_penalty, l.stage4_final_score,
               l.routing_decision, l.discard_reason
           FROM email_intakes i
           LEFT JOIN email_processing_log l ON l.intake_id = i.id
           WHERE i.id = %s AND i.attorney_id = %s LIMIT 1""",
        (intake_id, current_user["id"])))
    if not row: raise HTTPException(status_code=404, detail="Intake not found")
    return row
# ── Log ───────────────────────────────────────────────────────────────────────

@router.get("/email/log")
def get_processing_log(routing_decision:Optional[str]=Query(None), from_address:Optional[str]=Query(None),
                       date_from:Optional[datetime]=Query(None), date_to:Optional[datetime]=Query(None),
                       limit:int=Query(50,le=200), offset:int=Query(0),
                       current_user=Depends(get_current_user), db:PgConn=Depends(db_dep)):
    filters = ["attorney_id=%s"]; params:list = [current_user["id"]]
    if routing_decision: filters.append("routing_decision=%s");  params.append(routing_decision)
    if from_address:     filters.append("from_address ILIKE %s"); params.append(f"%{from_address}%")
    if date_from:        filters.append("processed_at>=%s");      params.append(date_from)
    if date_to:          filters.append("processed_at<=%s");      params.append(date_to)
    where = " AND ".join(filters)
    rows  = _rows(db.execute(f"SELECT id,provider,from_address,subject,received_at,processed_at,stage1_domain_score,stage2_nlp_score,stage3_spam_penalty,stage4_final_score,case_id_matched,routing_decision,discard_reason,reprocessed,intake_id FROM email_processing_log WHERE {where} ORDER BY processed_at DESC LIMIT %s OFFSET %s", (*params,limit,offset)))
    total = _row(db.execute(f"SELECT COUNT(*) as cnt FROM email_processing_log WHERE {where}", params))
    return {"total": total["cnt"] if total else 0, "items":rows}

@router.post("/email/log/{log_id}/reprocess")
def reprocess_email(log_id:str, current_user=Depends(get_current_user), db:PgConn=Depends(db_dep)):
    log_row = _row(db.execute("SELECT * FROM email_processing_log WHERE id=%s AND attorney_id=%s", (log_id, current_user["id"])))
    if not log_row: raise HTTPException(status_code=404, detail="Log entry not found")
    db.execute("UPDATE email_processing_log SET reprocessed=TRUE,reprocessed_at=NOW() WHERE id=%s", (log_id,))
    return {"status":"flagged_for_reprocess","message_id":log_row["provider_message_id"],
            "original_decision":log_row["routing_decision"],"original_score":log_row["stage4_final_score"]}


# ── Outlook OAuth ─────────────────────────────────────────────────────────────

@router.post("/email/accounts/outlook/connect")
def connect_outlook(current_user=Depends(get_current_user)):
    from .outlook_poller import get_auth_url
    auth_url, state = get_auth_url(current_user["id"], current_user.get("firm_id", "default"))
    return {"auth_url": auth_url}


@router.get("/auth/outlook/callback")
def outlook_callback(code: str, state: str, db: PgConn = Depends(db_dep)):
    from .outlook_poller import exchange_code
    try:
        result = exchange_code(code, state)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    email_address = result.get("id_token_claims", {}).get("email") or \
                    result.get("id_token_claims", {}).get("preferred_username", "unknown")
    db.execute(
        """INSERT INTO attorney_email_accounts
           (attorney_id, firm_id, provider, email_address, access_token, refresh_token)
           VALUES (%s, %s, 'outlook', %s, %s, %s)
           ON CONFLICT (attorney_id, provider, email_address)
           DO UPDATE SET
               access_token  = EXCLUDED.access_token,
               refresh_token = EXCLUDED.refresh_token,
               is_active     = TRUE,
               updated_at    = NOW()""",
        (result["attorney_id"], result["firm_id"], email_address,
         result["access_token"], result.get("refresh_token", ""))
    )
    logger.info(f"Outlook connected: {email_address}")
    return RedirectResponse(url="/dashboard?outlook=connected")

# ── Reply endpoints ───────────────────────────────────────────────────────────

import base64, json as _json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from anthropic import Anthropic as _Anthropic

_ai_client = _Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def _get_intake_and_account(intake_id: str, attorney_id: int, db: PgConn) -> tuple:
    """Fetch intake record and associated email account."""
    cur = db.execute(
        "SELECT * FROM email_intakes WHERE id=%s AND attorney_id=%s",
        (intake_id, attorney_id)
    )
    intake = _row(cur)
    if not intake:
        raise HTTPException(404, "Email intake not found")

    cur = db.execute(
        "SELECT * FROM attorney_email_accounts WHERE id=%s AND attorney_id=%s AND is_active=TRUE",
        (intake["account_id"], attorney_id)
    )
    account = _row(cur)
    if not account:
        raise HTTPException(404, "Email account not found or inactive")

    return intake, account


def _generate_ai_reply(intake: dict) -> str:
    """Use Claude to draft a professional reply."""
    subject    = intake.get("subject", "")
    body       = intake.get("body_text", "")[:2000]
    from_addr  = intake.get("from_address", "")
    entities   = intake.get("extracted_entities") or {}
    action_items = intake.get("action_items") or []
    sentiment  = intake.get("sentiment", "neutral")

    prompt = f"""You are a senior litigation attorney's assistant drafting a professional email reply.

ORIGINAL EMAIL:
From: {from_addr}
Subject: {subject}
Body:
{body}

CONTEXT:
- Sender sentiment: {sentiment}
- Key entities identified: {_json.dumps(entities)[:300]}
- Action items detected: {_json.dumps(action_items)[:300]}

Draft a professional, concise reply email. Follow these guidelines:
- Use formal legal correspondence tone
- Address the sender's key points directly
- If action items were detected, acknowledge them
- Keep it under 200 words unless complexity requires more
- Do NOT include a subject line — just the body
- End with a professional closing and [Attorney Name] placeholder
- Do not make up facts not present in the original email

Write only the email body, nothing else."""

    msg = _ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()


def _send_gmail_reply(account: dict, intake: dict, reply_text: str) -> bool:
    """Send reply via Gmail API."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

    creds = Credentials(
        token=account["access_token"],
        refresh_token=account["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist refreshed token back to DB to avoid expiry loop
        with get_conn(account.get("firm_id", "default")) as _db:
            _db.execute(
                "UPDATE attorney_email_accounts SET access_token=%s, token_expiry=%s, updated_at=NOW() WHERE id=%s",
                (creds.token, creds.expiry, account["id"])
            )

    service = build("gmail", "v1", credentials=creds)

    msg = MIMEMultipart()
    msg["To"]      = intake["from_address"]
    msg["Subject"] = f"Re: {intake.get('subject','')}"
    msg["In-Reply-To"] = intake.get("provider_message_id", "")
    msg["References"]  = intake.get("provider_message_id", "")
    msg.attach(MIMEText(reply_text, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    thread_id = intake.get("thread_id")
    body = {"raw": raw}
    if thread_id:
        body["threadId"] = thread_id

    service.users().messages().send(userId="me", body=body).execute()
    return True


def _send_outlook_reply(account: dict, intake: dict, reply_text: str) -> bool:
    """Send reply via Microsoft Graph API."""
    import msal, requests as _req

    OUTLOOK_CLIENT_ID     = os.getenv("OUTLOOK_CLIENT_ID")
    OUTLOOK_CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
    TENANT_ID             = os.getenv("OUTLOOK_TENANT_ID", "common")

    app = msal.ConfidentialClientApplication(
        OUTLOOK_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=OUTLOOK_CLIENT_SECRET,
    )
    result = app.acquire_token_by_refresh_token(
        refresh_token=account["refresh_token"],
        scopes=["https://graph.microsoft.com/Mail.Send",
                "https://graph.microsoft.com/Mail.Read"],
    )
    if "access_token" not in result:
        raise HTTPException(500, "Failed to refresh Outlook token")

    access_token = result["access_token"]
    message_id   = intake.get("provider_message_id", "")

    reply_payload = {
        "message": {
            "body": {"contentType": "Text", "content": reply_text}
        },
        "comment": reply_text,
    }

    resp = _req.post(
        f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=reply_payload,
    )
    return resp.status_code == 202


@router.get("/email/intake/{intake_id}/draft-reply")
def get_ai_draft_reply(
    intake_id: str,
    current_user=Depends(get_current_user),
    db: PgConn = Depends(db_dep),
):
    """Generate an AI-suggested reply for an email intake."""
    intake, account = _get_intake_and_account(intake_id, current_user["id"], db)
    draft = _generate_ai_reply(intake)
    return {
        "intake_id":   intake_id,
        "to":          intake["from_address"],
        "subject":     f"Re: {intake.get('subject','')}",
        "draft":       draft,
        "provider":    account["provider"],
        "account_email": account["email_address"],
    }


class ReplyBody(BaseModel):
    content: str

@router.post("/email/intake/{intake_id}/send-reply")
def send_reply(
    intake_id: str,
    body: ReplyBody,
    current_user=Depends(get_current_user),
    db: PgConn = Depends(db_dep),
):
    """Send the reply via Gmail or Outlook and log it."""
    intake, account = _get_intake_and_account(intake_id, current_user["id"], db)

    if intake.get("replied_at"):
        raise HTTPException(400, "This email has already been replied to")

    provider = account["provider"]
    try:
        if provider == "gmail":
            _send_gmail_reply(account, intake, body.content)
        elif provider == "outlook":
            _send_outlook_reply(account, intake, body.content)
        else:
            raise HTTPException(400, f"Unsupported provider: {provider}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reply send failed: {e}")
        raise HTTPException(500, f"Failed to send reply: {str(e)}")

    # Log the reply
    db.execute(
        """UPDATE email_intakes
           SET replied_at=%s, reply_content=%s, reply_sent_by=%s
           WHERE id=%s""",
        (datetime.utcnow(), body.content, current_user.get("username"), intake_id)
    )

    return {"ok": True, "provider": provider, "to": intake["from_address"]}
