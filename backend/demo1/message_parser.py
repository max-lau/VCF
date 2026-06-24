import os
import io, email, mailbox, json, re, zipfile, html
from email import policy as email_policy
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

from backend.demo1.pg import get_conn

router = APIRouter(prefix="/messages", tags=["Message Parsers"])

MSG_DIR = Path(os.environ.get("MSG_DIR",
    str(Path(__file__).parent.parent.parent / "uploads" / "messages")))
MSG_DIR.mkdir(parents=True, exist_ok=True)


def init_messages_table():
    """No-op — table exists in Supabase Postgres."""
    print("[Messages] Parsed messages table initialized ✓")


# ── Feature 18: EML / mbox parser ────────────────────────────────────────────

def parse_eml_message(msg) -> dict:
    def decode_header(h):
        if not h: return ""
        parts = email.header.decode_header(h)
        return "".join(
            p.decode(enc or "utf-8", errors="replace") if isinstance(p, bytes) else p
            for p, enc in parts
        )

    body = ""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                attachments.append(part.get_filename() or "attachment")
            elif ct == "text/plain" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    return {
        "from":        decode_header(msg.get("From", "")),
        "to":          decode_header(msg.get("To", "")),
        "cc":          decode_header(msg.get("Cc", "")),
        "subject":     decode_header(msg.get("Subject", "")),
        "date":        msg.get("Date", ""),
        "message_id":  msg.get("Message-ID", ""),
        "body":        body[:3000],
        "attachments": attachments,
    }


@router.post("/parse/email")
async def parse_email(
    request: Request,
    file: UploadFile = File(...),
    case_number: Optional[str] = Form(None)
):
    firm_id = getattr(request.state, "firm_id", "default")
    ext  = Path(file.filename).suffix.lower()
    data = await file.read()
    messages = []

    if ext == ".eml":
        msg = email.message_from_bytes(data, policy=email_policy.default)
        messages.append(parse_eml_message(msg))
    elif ext == ".mbox":
        ts  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tmp = MSG_DIR / f"{ts}_{file.filename}"
        tmp.write_bytes(data)
        mbox = mailbox.mbox(str(tmp))
        for m in mbox:
            messages.append(parse_eml_message(m))
        tmp.unlink(missing_ok=True)
    else:
        raise HTTPException(400, "Supported formats: .eml, .mbox")

    threads = {}
    for m in messages:
        subj = re.sub(r'^(Re:|Fwd?:)\s*', '', m["subject"], flags=re.I).strip()
        threads.setdefault(subj, []).append(m)

    result = {
        "format":        "email",
        "message_count": len(messages),
        "thread_count":  len(threads),
        "threads": [
            {"subject": s, "messages": msgs}
            for s, msgs in sorted(threads.items(), key=lambda x: x[1][0].get("date", ""))
        ]
    }

    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO parsed_messages
              (firm_id, source_file, format, case_number, thread_count, msg_count, parsed_json, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, file.filename, "email", case_number,
              len(threads), len(messages), json.dumps(result),
              datetime.now(timezone.utc).isoformat()))
        result["id"] = cur.fetchone()["id"]

    return {"success": True, **result}


# ── Feature 19: SMS XML parser ────────────────────────────────────────────────

@router.post("/parse/sms")
async def parse_sms(
    request: Request,
    file: UploadFile = File(...),
    case_number: Optional[str] = Form(None)
):
    import xml.etree.ElementTree as ET
    firm_id = getattr(request.state, "firm_id", "default")
    data = await file.read()
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise HTTPException(400, f"Invalid XML: {e}")

    messages = []
    for sms in root.findall(".//sms"):
        a = sms.attrib
        messages.append({
            "address": a.get("address", ""),
            "date":    a.get("readable_date", a.get("date", "")),
            "type":    "sent" if a.get("type", "1") == "2" else "received",
            "body":    a.get("body", ""),
            "contact": a.get("contact_name", a.get("name", "")),
        })
    for mms in root.findall(".//mms"):
        a = mms.attrib
        parts = [p.attrib.get("text", "") for p in mms.findall(".//part")
                 if p.attrib.get("ct", "") == "text/plain"]
        messages.append({
            "address": a.get("address", ""),
            "date":    a.get("readable_date", a.get("date", "")),
            "type":    "sent" if a.get("msg_box", "1") == "2" else "received",
            "body":    " ".join(parts) or "[MMS/Media]",
            "contact": a.get("contact_name", ""),
        })

    convos = {}
    for m in messages:
        convos.setdefault(m["address"], []).append(m)

    result = {
        "format":       "sms",
        "msg_count":    len(messages),
        "thread_count": len(convos),
        "conversations": [
            {"address": addr, "contact": msgs[0].get("contact", ""),
             "msg_count": len(msgs), "messages": msgs}
            for addr, msgs in convos.items()
        ]
    }

    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO parsed_messages
              (firm_id, source_file, format, case_number, thread_count, msg_count, parsed_json, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, file.filename, "sms", case_number,
              len(convos), len(messages), json.dumps(result),
              datetime.now(timezone.utc).isoformat()))
        result["id"] = cur.fetchone()["id"]

    return {"success": True, **result}


# ── Feature 20: WhatsApp & WeChat parser ─────────────────────────────────────

def parse_whatsapp_txt(text: str) -> List[dict]:
    pattern = re.compile(
        r'[\[\(]?(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}),?\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\s*[\]\)]?\s*[-–]\s*([^:]+):\s*(.*)'
    )
    messages = []
    current = None
    for line in text.splitlines():
        m = pattern.match(line)
        if m:
            if current:
                messages.append(current)
            current = {
                "date":     m.group(1),
                "time":     m.group(2),
                "sender":   m.group(3).strip(),
                "message":  m.group(4).strip(),
                "is_media": m.group(4).strip() in {
                    "<Media omitted>", "image omitted", "video omitted",
                    "audio omitted", "sticker omitted"},
            }
        elif current:
            current["message"] += "\n" + line.strip()
    if current:
        messages.append(current)
    return messages


@router.post("/parse/chat")
async def parse_chat(
    request: Request,
    file: UploadFile = File(...),
    platform: str = Form("whatsapp"),
    case_number: Optional[str] = Form(None)
):
    firm_id = getattr(request.state, "firm_id", "default")
    ext  = Path(file.filename).suffix.lower()
    data = await file.read()

    if platform == "whatsapp":
        if ext not in {".txt", ".zip"}:
            raise HTTPException(400, "WhatsApp exports are .txt or .zip files")
        if ext == ".zip":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                txt_files = [n for n in zf.namelist() if n.endswith(".txt")]
                if not txt_files:
                    raise HTTPException(400, "No .txt found in ZIP")
                text = zf.read(txt_files[0]).decode("utf-8", errors="replace")
        else:
            text = data.decode("utf-8", errors="replace")

        messages = parse_whatsapp_txt(text)
        senders = {}
        for m in messages:
            senders.setdefault(m["sender"], 0)
            senders[m["sender"]] += 1

        has_non_ascii = any(
            not all(ord(c) < 128 for c in m["message"])
            for m in messages if m["message"]
        )
        result = {
            "platform":         "whatsapp",
            "msg_count":        len(messages),
            "participants":     list(senders.keys()),
            "msg_per_sender":   senders,
            "translation_flag": has_non_ascii,
            "messages":         messages[:500],
        }

    elif platform == "wechat":
        if ext not in {".html", ".htm"}:
            raise HTTPException(400, "WeChat exports are .html files")
        raw = data.decode("utf-8", errors="replace")
        msg_pattern = re.compile(
            r'<div class="message[^"]*"[^>]*>.*?<span class="time"[^>]*>([^<]+)</span>'
            r'.*?<span class="sender"[^>]*>([^<]+)</span>'
            r'.*?<span class="content"[^>]*>(.*?)</span>',
            re.DOTALL
        )
        messages = []
        for m in msg_pattern.finditer(raw):
            messages.append({
                "time":    m.group(1).strip(),
                "sender":  m.group(2).strip(),
                "message": html.unescape(re.sub(r'<[^>]+>', '', m.group(3))).strip(),
            })
        has_non_ascii = any(
            not all(ord(c) < 128 for c in m["message"])
            for m in messages if m["message"]
        )
        result = {
            "platform":         "wechat",
            "msg_count":        len(messages),
            "translation_flag": has_non_ascii,
            "messages":         messages[:500],
        }
    else:
        raise HTTPException(400, "platform must be 'whatsapp' or 'wechat'")

    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO parsed_messages
              (firm_id, source_file, format, case_number, thread_count, msg_count, parsed_json, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (firm_id, file.filename, platform, case_number,
              1, result["msg_count"], json.dumps(result),
              datetime.now(timezone.utc).isoformat()))
        result["id"] = cur.fetchone()["id"]

    return {"success": True, **result}


@router.get("/parsed")
def list_parsed(
    request: Request,
    case_number: Optional[str] = None,
    limit: int = 50
):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        if case_number:
            rows = conn.execute(
                """SELECT id,source_file,format,case_number,thread_count,msg_count,created_at
                   FROM parsed_messages WHERE firm_id=%s AND case_number=%s
                   ORDER BY id DESC LIMIT %s""",
                (firm_id, case_number, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id,source_file,format,case_number,thread_count,msg_count,created_at
                   FROM parsed_messages WHERE firm_id=%s
                   ORDER BY id DESC LIMIT %s""",
                (firm_id, limit)
            ).fetchall()
    return {"records": [dict(r) for r in rows], "total": len(rows)}
