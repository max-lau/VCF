import io, email, mailbox, sqlite3, json, re, zipfile, html
from email import policy as email_policy
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

router = APIRouter(prefix="/messages", tags=["Message Parsers"])

DB_PATH = "/root/nlp-portfolio/backend/demo1/analyses.db"
MSG_DIR = Path("/root/nlp-portfolio/uploads/messages")
MSG_DIR.mkdir(parents=True, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_messages_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS parsed_messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file  TEXT NOT NULL,
            format       TEXT NOT NULL,
            case_number  TEXT,
            thread_count INTEGER DEFAULT 0,
            msg_count    INTEGER DEFAULT 0,
            parsed_json  TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_messages_table()

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
            cd = str(part.get("Content-Disposition",""))
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
        "from":        decode_header(msg.get("From","")),
        "to":          decode_header(msg.get("To","")),
        "cc":          decode_header(msg.get("Cc","")),
        "subject":     decode_header(msg.get("Subject","")),
        "date":        msg.get("Date",""),
        "message_id":  msg.get("Message-ID",""),
        "body":        body[:3000],
        "attachments": attachments,
    }

@router.post("/parse/email")
async def parse_email(
    file: UploadFile = File(...),
    case_number: Optional[str] = Form(None)
):
    ext = Path(file.filename).suffix.lower()
    data = await file.read()
    messages = []

    if ext in {".eml"}:
        msg = email.message_from_bytes(data, policy=email_policy.default)
        messages.append(parse_eml_message(msg))

    elif ext in {".mbox"}:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tmp = MSG_DIR / f"{ts}_{file.filename}"
        tmp.write_bytes(data)
        mbox = mailbox.mbox(str(tmp))
        for m in mbox:
            messages.append(parse_eml_message(m))
        tmp.unlink(missing_ok=True)

    else:
        raise HTTPException(400, "Supported formats: .eml, .mbox")

    # Reconstruct threads by subject
    threads = {}
    for m in messages:
        subj = re.sub(r'^(Re:|Fwd?:)\s*', '', m["subject"], flags=re.I).strip()
        threads.setdefault(subj, []).append(m)

    result = {
        "format":       "email",
        "message_count": len(messages),
        "thread_count":  len(threads),
        "threads": [
            {"subject": s, "messages": msgs}
            for s, msgs in sorted(threads.items(), key=lambda x: x[1][0].get("date",""))
        ]
    }

    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO parsed_messages (source_file, format, case_number, thread_count, msg_count, parsed_json)
        VALUES (?,?,?,?,?,?)
    """, (file.filename, "email", case_number,
          len(threads), len(messages), json.dumps(result)))
    result["id"] = cur.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, **result}

# ── Feature 19: SMS XML parser ────────────────────────────────────────────────

@router.post("/parse/sms")
async def parse_sms(
    file: UploadFile = File(...),
    case_number: Optional[str] = Form(None)
):
    import xml.etree.ElementTree as ET
    data = await file.read()
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise HTTPException(400, f"Invalid XML: {e}")

    messages = []
    # iOS (SMS Backup & Restore) and Android SMS Backup XML both use <sms> tags
    for sms in root.findall(".//sms"):
        a = sms.attrib
        messages.append({
            "address":  a.get("address",""),
            "date":     a.get("readable_date", a.get("date","")),
            "type":     "sent" if a.get("type","1")=="2" else "received",
            "body":     a.get("body",""),
            "contact":  a.get("contact_name", a.get("name","")),
        })

    # MMS
    for mms in root.findall(".//mms"):
        a = mms.attrib
        parts = [p.attrib.get("text","") for p in mms.findall(".//part") if p.attrib.get("ct","")=="text/plain"]
        messages.append({
            "address":  a.get("address",""),
            "date":     a.get("readable_date", a.get("date","")),
            "type":     "sent" if a.get("msg_box","1")=="2" else "received",
            "body":     " ".join(parts) or "[MMS/Media]",
            "contact":  a.get("contact_name",""),
        })

    # Group into conversations by address
    convos = {}
    for m in messages:
        convos.setdefault(m["address"], []).append(m)

    result = {
        "format":     "sms",
        "msg_count":  len(messages),
        "thread_count": len(convos),
        "conversations": [
            {"address": addr, "contact": msgs[0].get("contact",""),
             "msg_count": len(msgs), "messages": msgs}
            for addr, msgs in convos.items()
        ]
    }

    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO parsed_messages (source_file, format, case_number, thread_count, msg_count, parsed_json)
        VALUES (?,?,?,?,?,?)
    """, (file.filename, "sms", case_number,
          len(convos), len(messages), json.dumps(result)))
    result["id"] = cur.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, **result}

# ── Feature 20: WhatsApp & WeChat parser ─────────────────────────────────────

def parse_whatsapp_txt(text: str) -> List[dict]:
    # Matches: [DD/MM/YYYY, HH:MM:SS] Name: message
    # or:      MM/DD/YY, HH:MM - Name: message
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
                "date":    m.group(1),
                "time":    m.group(2),
                "sender":  m.group(3).strip(),
                "message": m.group(4).strip(),
                "is_media": m.group(4).strip() in {"<Media omitted>","image omitted","video omitted","audio omitted","sticker omitted"},
            }
        elif current:
            current["message"] += "\n" + line.strip()
    if current:
        messages.append(current)
    return messages

@router.post("/parse/chat")
async def parse_chat(
    file: UploadFile = File(...),
    platform: str = Form("whatsapp"),
    case_number: Optional[str] = Form(None)
):
    ext = Path(file.filename).suffix.lower()
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
            "messages":         messages[:500],  # cap for response size
        }

    elif platform == "wechat":
        # WeChat HTML export
        if ext not in {".html",".htm"}:
            raise HTTPException(400, "WeChat exports are .html files")
        raw = data.decode("utf-8", errors="replace")
        # Parse WeChat's standard export div structure
        msg_pattern = re.compile(
            r'<div class="message[^"]*"[^>]*>.*?<span class="time"[^>]*>([^<]+)</span>.*?<span class="sender"[^>]*>([^<]+)</span>.*?<span class="content"[^>]*>(.*?)</span>',
            re.DOTALL
        )
        messages = []
        for m in msg_pattern.finditer(raw):
            messages.append({
                "time":    m.group(1).strip(),
                "sender":  m.group(2).strip(),
                "message": html.unescape(re.sub(r'<[^>]+>','', m.group(3))).strip(),
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

    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO parsed_messages (source_file, format, case_number, thread_count, msg_count, parsed_json)
        VALUES (?,?,?,?,?,?)
    """, (file.filename, platform, case_number, 1, result["msg_count"], json.dumps(result)))
    result["id"] = cur.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, **result}

@router.get("/parsed")
def list_parsed(case_number: Optional[str] = None, limit: int = 50):
    conn = get_conn()
    if case_number:
        rows = conn.execute(
            "SELECT id,source_file,format,case_number,thread_count,msg_count,created_at FROM parsed_messages WHERE case_number=? ORDER BY id DESC LIMIT ?",
            (case_number, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id,source_file,format,case_number,thread_count,msg_count,created_at FROM parsed_messages ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return {"records": [dict(r) for r in rows], "total": len(rows)}
