"""
backend/demo1/vcf_account.py
────────────────────────────
VCF.gov Account Creation Prep module for ACP-VCF (WAW, single tenant).

Purpose
  The VCF Claimant Portal (claims.vcf.gov) requires a HUMAN to create the
  account. This module never touches VCF.gov programmatically. It prepares a
  copy-paste-ready "prep sheet" so a paralegal can open the VCF registration
  page in one window and copy each field from the WAW prep document in the
  other window.

Pipeline it supports
  OCR intake (e.g. handwritten Chinese questionnaire)
    → /vcf/extract   (Claude: raw/translated text → structured English JSON)
    → /vcf/prep      (build prep sheet: username, compliant password,
                      5 security questions + answers [synthesized in demo mode])
    → frontend VcfAccountPrep.vue (split-window copy-paste workflow)
    → /vcf/prep/{id}/status (human marks "account_created" after doing it on VCF.gov)

Field inventory (verified against the live registration page, July 2026)
  Account Information:
    User Name, Email, Confirm email, First Name, Last Name,
    Password (16 chars min, 1 upper, 1 lower, 1 special, 1 number), Confirm password
  Security Questions: 5 dropdowns, one question chosen per group, each with an answer.
  Note: DOJ supports ONLY Chrome and Edge for the claims portal.

Security
  Prep sheets contain credentials + security answers → sensitive.
  If VCF_PREP_ENC_KEY (a Fernet key) is set in .env, the payload is encrypted
  at rest. Generate one with:
      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import string
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.demo1.pg import get_conn
from backend.demo1.case_management import generate_vcf_email

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Culture-aware name splitting ──────────────────────────────────────────────
# Some cultures write the family name first. When name_order is "surname_first",
# the first token of client_name is the family name and the remainder is the
# given name(s). Otherwise we assume Western given-first order.
SURNAME_FIRST_ORDERS = {"surname_first", "family_first", "eastern_order"}


def split_client_name(name: str, name_order: str | None = None) -> tuple[str, str]:
    """Return (first_name, last_name) honoring name_order if known."""
    name = (name or "").strip()
    if not name:
        return "", ""
    parts = name.split()
    if len(parts) == 1:
        return name, ""
    if name_order and name_order.lower() in SURNAME_FIRST_ORDERS:
        # e.g. "Chen Weiming" -> first="Weiming", last="Chen"
        return " ".join(parts[1:]), parts[0]
    # Default Western order: "John Doe" -> first="John", last="Doe"
    return " ".join(parts[:-1]), parts[-1]


VCF_REGISTER_URL = (
    "https://www.claims.vcf.gov/account/Register"
    "?class=btn%20btn-default%20btn-block%20content-group"
)

# ── Security question bank (verbatim from claims.vcf.gov, one group per dropdown) ──
SECURITY_QUESTION_BANK: dict[str, list[str]] = {
    "group_1": [
        "What is your oldest sibling’s birthday month and year? (e.g., January 1900)",
        "What street did you live on in third grade?",
        "In what city did you meet your spouse/significant other?",
        "What is the name of your favorite childhood friend?",
        "What was your childhood nickname?",
    ],
    "group_2": [
        "What school did you attend for sixth grade?",
        "What is your oldest sibling's middle name?",
        "What was your childhood phone number including area code? (e.g., 000-000-0000)",
        "What is the middle name of your youngest child?",
        "What is your oldest cousin's first and last name?",
    ],
    "group_3": [
        "In what city or town did your mother and father meet?",
        "What was the name of your first stuffed animal?",
        "What is your youngest brother’s birthday month and year? (e.g., January 1900)",
        "In what city does your nearest sibling live?",
        "What is your maternal grandmother's maiden name?",
    ],
    "group_4": [
        "What is the name of your favorite childhood teacher?",
        "In what city or town was your first job?",
        "What is the name of a college you applied to but didn't attend?",
        "What was the name of your elementary / primary school?",
        "What is the name of the place your wedding reception was held?",
    ],
    "group_5": [
        "What was your dream job as a child?",
        "What is the name, breed, and color of current pet?",
        "What was the first concert you attended?",
        "Who was your childhood hero?",
        "What month and day is your anniversary? (e.g., January 2)",
    ],
}

# Demo-only plausible answers keyed loosely by question theme. Used ONLY when
# demo_mode=True; real accounts must use answers confirmed with the client.
_DEMO_ANSWER_POOLS = {
    "sibling": ["March 1965", "July 1972", "January 1958"],
    "street": ["Mott Street", "Bayard Street", "Grand Street", "Elizabeth Street"],
    "city": ["Flushing", "Brooklyn", "Guangzhou", "Manhattan"],
    "friend": ["Wei Chen", "Amy Lin", "David Wong"],
    "nickname": ["Xiao Ming", "Ah Hua", "Lily"],
    "school": ["PS 124", "PS 130", "Sun Yat-sen Elementary"],
    "phone": ["212-555-0139", "718-555-0164", "646-555-0117"],
    "name": ["Jian Zhang", "Mei Liu", "Kevin Chen"],
    "animal": ["Panda", "Bunny", "Little Tiger"],
    "teacher": ["Mrs. Huang", "Mr. Lee", "Ms. Rodriguez"],
    "job": ["Doctor", "Teacher", "Pilot"],
    "pet": ["Momo, Shiba Inu, tan", "Coco, tabby cat, gray"],
    "concert": ["Teresa Teng 1984", "Jacky Cheung 1995"],
    "hero": ["Sun Wukong", "Bruce Lee"],
    "date": ["June 12", "October 3"],
    "maiden": ["Chan", "Ng", "Lau"],
    "college": ["Hunter College", "Baruch College"],
    "place": ["Jing Fong Restaurant", "Golden Unicorn"],
}

_THEME_PATTERNS = [
    (r"sibling.*birthday|brother.*birthday", "sibling"),
    (r"street", "street"),
    (r"city|town", "city"),
    (r"friend", "friend"),
    (r"nickname", "nickname"),
    (r"school", "school"),
    (r"phone", "phone"),
    (r"middle name|cousin", "name"),
    (r"stuffed animal", "animal"),
    (r"teacher", "teacher"),
    (r"dream job", "job"),
    (r"pet", "pet"),
    (r"concert", "concert"),
    (r"hero", "hero"),
    (r"anniversary", "date"),
    (r"maiden", "maiden"),
    (r"college", "college"),
    (r"reception", "place"),
]


def _demo_answer(question: str, rng: "secrets.SystemRandom") -> str:
    q = question.lower()
    for pattern, theme in _THEME_PATTERNS:
        if re.search(pattern, q):
            return rng.choice(_DEMO_ANSWER_POOLS[theme])
    return rng.choice(_DEMO_ANSWER_POOLS["name"])


# ── Password / username generators ────────────────────────────────────────────

_SPECIALS = "!@#$%^&*"


def generate_vcf_password(length: int = 20) -> str:
    """VCF policy: ≥16 chars, ≥1 upper, ≥1 lower, ≥1 special, ≥1 number."""
    length = max(length, 16)
    rng = secrets.SystemRandom()
    core = [
        rng.choice(string.ascii_uppercase),
        rng.choice(string.ascii_lowercase),
        rng.choice(string.digits),
        rng.choice(_SPECIALS),
    ]
    pool = string.ascii_letters + string.digits + _SPECIALS
    core += [rng.choice(pool) for _ in range(length - len(core))]
    rng.shuffle(core)
    return "".join(core)


def suggest_username(first: str, last: str) -> str:
    base = re.sub(r"[^a-z]", "", f"{first}.{last}".lower().replace(" ", "")) or "wawclient"
    base = re.sub(r"[^a-z.]", "", f"{first}.{last}".lower()) or base
    return f"{base}.{secrets.randbelow(9000) + 1000}"


# ── Optional encryption at rest ────────────────────────────────────────────────

def _get_fernet():
    key = os.getenv("VCF_PREP_ENC_KEY", "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode())
    except Exception as e:  # bad key / lib missing
        logger.warning(f"[vcf_account] VCF_PREP_ENC_KEY unusable, storing plaintext: {e}")
        return None


def _seal(payload: dict) -> tuple[str, bool]:
    raw = json.dumps(payload)
    f = _get_fernet()
    if f:
        return f.encrypt(raw.encode()).decode(), True
    return raw, False


def _unseal(blob: str, encrypted: bool) -> dict:
    if encrypted:
        f = _get_fernet()
        if not f:
            raise HTTPException(500, "Prep sheet is encrypted but VCF_PREP_ENC_KEY is not set")
        blob = f.decrypt(blob.encode()).decode()
    return json.loads(blob)


# ── DB ─────────────────────────────────────────────────────────────────────────

def init_vcf_account_table():
    from backend.demo1.pg import get_conn
    with get_conn("default") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vcf_account_prep (
                id          SERIAL PRIMARY KEY,
                firm_id     TEXT NOT NULL,
                case_id     INTEGER,
                client_name TEXT,
                status      TEXT NOT NULL DEFAULT 'draft',
                -- draft → ready → account_created → verified
                demo_mode   BOOLEAN NOT NULL DEFAULT FALSE,
                encrypted   BOOLEAN NOT NULL DEFAULT FALSE,
                prep_blob   TEXT NOT NULL,
                vcf_username TEXT,
                created_by  TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vcf_prep_case ON vcf_account_prep(case_id)"
        )
        conn.commit()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ClientData(BaseModel):
    first_name: str
    last_name: str
    email: str = ""           # claimant's personal email
    vcf_email: str = ""       # law-firm-provided email used only for VCF.gov
    phone: str = ""
    date_of_birth: str = ""
    address: str = ""
    ssn_last4: str = ""
    preferred_language: str = ""
    notes: str = ""
    name_order: Optional[str] = None  # surname_first | given_first


class SecuritySelection(BaseModel):
    """Optionally pin specific questions/answers (real-client mode)."""
    group: str          # group_1 … group_5
    question: str
    answer: str


class PrepRequest(BaseModel):
    case_id: Optional[int] = None
    client: ClientData
    demo_mode: bool = True
    username: Optional[str] = None
    security: list[SecuritySelection] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    text: str
    case_id: Optional[int] = None
    source_language_hint: str = "zh"


class StatusUpdate(BaseModel):
    status: str
    vcf_username: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/questions")
def get_question_bank():
    """The 5 VCF security-question dropdowns, verbatim."""
    return {"register_url": VCF_REGISTER_URL, "groups": SECURITY_QUESTION_BANK}


def _extract_from_text(text: str) -> dict:
    """Shared: raw intake text (possibly Chinese/mixed) → English ClientData dict."""
    from backend.demo1.ai_client import get_client
    client = get_client()
    model = os.getenv("LLM_FAST", "claude-haiku-4-5-20251001")

    prompt = f"""You are processing an intake questionnaire for a 9/11 Victim Compensation Fund claim.
The source text may be OCR output of a handwritten questionnaire in Chinese, English, or mixed.

Translate to English where needed and extract the client's registration data.

Return ONLY raw JSON (no markdown, no backticks) with exactly these keys:
{{
  "client_name": "full romanized/English name as written (e.g. 'Chen Weiming' or 'John Smith')",
  "name_order": "surname_first for Chinese/Vietnamese/Korean/Hungarian/etc., otherwise given_first",
  "first_name": "given name(s) in Western order (pinyin if Chinese, e.g. 'Weiming')",
  "last_name": "family name in Western order (e.g. 'Chen')",
  "email": "email address or empty string",
  "phone": "phone in 000-000-0000 format or empty string",
  "date_of_birth": "YYYY-MM-DD or empty string",
  "address": "full English address or empty string",
  "ssn_last4": "last 4 of SSN if present, else empty string",
  "preferred_language": "client's preferred language, e.g. 'Cantonese'",
  "notes": "anything relevant to VCF eligibility: presence at exposure site, dates, conditions, translated concisely",
  "missing_fields": ["fields you could not find"],
  "ocr_uncertain": ["values you extracted but that look garbled/uncertain"]
}}

Source text:
\"\"\"{text[:6000]}\"\"\""""

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)

        # Enforce Western given-first/family-last order regardless of how the LLM
        # returned the fields. If the source document is surname-first, we swap.
        name_order = data.get("name_order") or data.get("nameOrder")
        client_name = (data.get("client_name") or "").strip()
        if client_name:
            first, last = split_client_name(client_name, name_order)
            data["first_name"] = first
            data["last_name"] = last
        return data
    except json.JSONDecodeError:
        raise HTTPException(500, "Extraction response could not be parsed; retry")
    except Exception as e:
        logger.error(f"[vcf_account] extract failed: {e}")
        raise HTTPException(500, "Extraction failed")


@router.post("/extract")
def extract_client_data(body: ExtractRequest, request: Request):
    """Raw intake text (OCR output, Chinese or mixed) → structured English ClientData."""
    if not body.text or len(body.text.strip()) < 10:
        raise HTTPException(400, "Text too short")
    return {"success": True, "client": _extract_from_text(body.text)}


@router.post("/from-scan/{scan_id}")
def client_from_scan(scan_id: int, request: Request):
    """
    Bridge from OCR intake → VCF prep. Loads an intake_scans row; if the
    Vision pass already produced VCF-structured form_fields, maps them
    directly (no second AI call). Otherwise runs Claude extraction on the
    stored raw_text. Returns a ClientData payload ready for /vcf/prep.
    """
    firm_id = getattr(request.state, "firm_id", "default")
    from backend.demo1.pg import get_conn
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT id, filename, raw_text, confidence, ocr_engine, form_fields "
            "FROM intake_scans WHERE id=%s AND firm_id=%s",
            (scan_id, firm_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Intake scan not found")

    ff = row["form_fields"]
    if isinstance(ff, str):
        try:
            ff = json.loads(ff)
        except (json.JSONDecodeError, TypeError):
            ff = None

    warnings: list[str] = []
    if ff and ff.get("client_name"):
        # Vision pass already structured it — map without another AI call.
        name = (ff.get("client_name") or "").strip()
        name_order = ff.get("name_order") or ff.get("nameOrder")
        first, last = split_client_name(name, name_order)
        notes_bits = []
        if ff.get("client_name_native"):
            notes_bits.append(f"Native name: {ff['client_name_native']}")
        if ff.get("exposure_location"):
            notes_bits.append(f"Exposure: {ff['exposure_location']}")
        if ff.get("presence_dates"):
            notes_bits.append(f"Present: {ff['presence_dates']} ({ff.get('presence_role') or 'role unknown'})")
        if ff.get("medical_conditions"):
            notes_bits.append("Conditions: " + ", ".join(ff["medical_conditions"]))
        if ff.get("wtc_health_program") is not None:
            notes_bits.append(f"WTC Health Program: {'yes' if ff['wtc_health_program'] else 'no'}")
        if name_order:
            notes_bits.append(f"Name order: {name_order}")
        notes_bits += ff.get("key_facts") or []
        client_data = {
            "first_name": first,
            "last_name": last,
            "email": ff.get("email") or "",
            "vcf_email": "",
            "phone": ff.get("phone") or "",
            "date_of_birth": ff.get("date_of_birth") or "",
            "address": ff.get("address") or "",
            "ssn_last4": ff.get("ssn_last4") or "",
            "preferred_language": ff.get("preferred_language") or "",
            "notes": " | ".join(notes_bits)[:2000],
            "name_order": name_order if name_order else None,
        }
        for k in ("email", "phone", "date_of_birth", "address"):
            if not client_data[k]:
                warnings.append(f"missing: {k}")
        if not last:
            warnings.append("could not split first/last name — review")
        source = "vision_form_fields"
    else:
        text = (row["raw_text"] or "").strip()
        if len(text) < 10:
            raise HTTPException(400, "Scan has no usable text to extract from")
        client_data = _extract_from_text(text)
        source = "claude_text_extraction"

    return {
        "success": True,
        "scan": {"id": row["id"], "filename": row["filename"],
                 "confidence": row["confidence"], "engine": row["ocr_engine"]},
        "source": source,
        "warnings": warnings,
        "client": client_data,
    }


@router.post("/prep")
def create_prep(body: PrepRequest, request: Request):
    """Build a copy-paste-ready VCF registration prep sheet and store it."""
    firm_id = getattr(request.state, "firm_id", "default")
    user_id = str(getattr(request.state, "user_id", "") or "")
    rng = secrets.SystemRandom()

    c = body.client
    if not c.first_name or not c.last_name:
        raise HTTPException(400, "first_name and last_name are required")

    username = body.username or suggest_username(c.first_name, c.last_name)
    password = generate_vcf_password()

    # Security questions: use pinned selections when provided, otherwise pick
    # one per group; answers synthesized only in demo mode.
    pinned = {s.group: s for s in body.security}
    security = []
    for group, questions in SECURITY_QUESTION_BANK.items():
        if group in pinned:
            sel = pinned[group]
            security.append({"group": group, "question": sel.question, "answer": sel.answer,
                             "synthesized": False})
        elif body.demo_mode:
            q = rng.choice(questions)
            security.append({"group": group, "question": q, "answer": _demo_answer(q, rng),
                             "synthesized": True})
        else:
            security.append({"group": group, "question": "", "answer": "",
                             "synthesized": False})  # to be confirmed with client

    # Resolve the VCF email: explicit field wins, then case record (auto-generate
    # if missing), then personal email as a last resort.
    vcf_email = (c.vcf_email or "").strip()
    if not vcf_email and body.case_id:
        with get_conn(firm_id) as conn:
            row = conn.execute(
                "SELECT vcf_email FROM cases WHERE id=%s AND firm_id=%s",
                (body.case_id, firm_id),
            ).fetchone()
            if row and row.get("vcf_email"):
                vcf_email = row["vcf_email"]
            elif row:
                # Auto-reserve the next dedicated law-firm email for this claimant.
                generated = generate_vcf_email(conn)
                if generated:
                    conn.execute(
                        "UPDATE cases SET vcf_email=%s, updated_at=NOW() WHERE id=%s AND firm_id=%s",
                        (generated, body.case_id, firm_id),
                    )
                    conn.commit()
                    vcf_email = generated
                    logger.info(f"[vcf_account] auto-generated vcf_email {generated} for case {body.case_id}")
                else:
                    logger.error("[vcf_account] Cannot generate prep sheet: VCF_DEDICATED_EMAIL_DOMAIN not configured")
                    raise HTTPException(
                        500,
                        "VCF dedicated email domain is not configured. "
                        "Add VCF_DEDICATED_EMAIL_DOMAIN=wawvcf.com to .env and restart the backend."
                    )
    if not vcf_email:
        vcf_email = c.email
    if not vcf_email:
        raise HTTPException(400, "No VCF email or client email available for prep sheet.")

    prep = {
        "register_url": VCF_REGISTER_URL,
        "browser_note": "VCF supports ONLY Google Chrome or Microsoft Edge.",
        "account_information": {
            "user_name": username,
            "email": vcf_email,
            "confirm_email": vcf_email,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "password": password,
            "confirm_password": password,
            "password_policy": "16+ chars, 1 uppercase, 1 lowercase, 1 special, 1 number",
        },
        "security_questions": security,
        "client_reference": {
            "phone": c.phone,
            "date_of_birth": c.date_of_birth,
            "address": c.address,
            "preferred_language": c.preferred_language,
            "notes": c.notes,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    blob, encrypted = _seal(prep)
    with get_conn(firm_id) as conn:
        row = conn.execute(
            """INSERT INTO vcf_account_prep
               (firm_id, case_id, client_name, status, demo_mode, encrypted, prep_blob, created_by)
               VALUES (%s,%s,%s,'ready',%s,%s,%s,%s) RETURNING id""",
            (firm_id, body.case_id, f"{c.first_name} {c.last_name}",
             body.demo_mode, encrypted, blob, user_id),
        ).fetchone()
        conn.commit()
        prep_id = row["id"] if row else None

    if not encrypted:
        logger.warning("[vcf_account] prep sheet stored UNENCRYPTED — set VCF_PREP_ENC_KEY")

    return {"success": True, "prep_id": prep_id, "demo_mode": body.demo_mode,
            "encrypted_at_rest": encrypted, "prep": prep}


@router.get("/prep/{prep_id}")
def get_prep(prep_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    from backend.demo1.pg import get_conn
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM vcf_account_prep WHERE id=%s AND firm_id=%s",
            (prep_id, firm_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Prep sheet not found")
    prep = _unseal(row["prep_blob"], row["encrypted"])
    return {"success": True, "prep_id": prep_id, "case_id": row["case_id"],
            "client_name": row["client_name"], "status": row["status"],
            "demo_mode": row["demo_mode"], "prep": prep}


@router.get("/prep")
def list_preps(request: Request, case_id: Optional[int] = None, limit: int = 50):
    firm_id = getattr(request.state, "firm_id", "default")
    from backend.demo1.pg import get_conn
    with get_conn(firm_id) as conn:
        if case_id is not None:
            rows = conn.execute(
                """SELECT id, case_id, client_name, status, demo_mode, created_at
                   FROM vcf_account_prep WHERE firm_id=%s AND case_id=%s
                   ORDER BY created_at DESC LIMIT %s""",
                (firm_id, case_id, min(limit, 200)),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, case_id, client_name, status, demo_mode, created_at
                   FROM vcf_account_prep WHERE firm_id=%s
                   ORDER BY created_at DESC LIMIT %s""",
                (firm_id, min(limit, 200)),
            ).fetchall()
    return {"success": True, "count": len(rows), "preps": [dict(r) for r in rows]}


def _vcf_status_can_advance_to(current: str | None, target: str) -> bool:
    """Only move cases.vcf_status forward if it is not already past target."""
    if not current:
        return True
    order = {"pending": 0, "intake": 1, "registered": 2, "submitted": 3,
             "under_review": 4, "award_determination": 5, "disbursed": 6, "closed": 7}
    return order.get(current, 0) <= order.get(target, 0)


@router.patch("/prep/{prep_id}/status")
def update_status(prep_id: int, body: StatusUpdate, request: Request):
    allowed = {"draft", "ready", "account_created", "verified", "abandoned"}
    if body.status not in allowed:
        raise HTTPException(400, f"status must be one of {sorted(allowed)}")
    firm_id = getattr(request.state, "firm_id", "default")
    from backend.demo1.pg import get_conn
    with get_conn(firm_id) as conn:
        prep = conn.execute(
            "SELECT id, case_id, client_name, status FROM vcf_account_prep WHERE id=%s AND firm_id=%s",
            (prep_id, firm_id),
        ).fetchone()
        if not prep:
            raise HTTPException(404, "Prep sheet not found")

        conn.execute(
            """UPDATE vcf_account_prep
               SET status=%s, vcf_username=COALESCE(%s, vcf_username), updated_at=NOW()
               WHERE id=%s AND firm_id=%s""",
            (body.status, body.vcf_username, prep_id, firm_id),
        )

        if body.status in {"account_created", "verified"} and prep["case_id"]:
            case_id = prep["case_id"]
            case = conn.execute(
                "SELECT id, case_number, vcf_status FROM cases WHERE id=%s AND firm_id=%s AND deleted = FALSE",
                (case_id, firm_id),
            ).fetchone()
            if case:
                new_vcf_status = "registered"
                if _vcf_status_can_advance_to(case.get("vcf_status"), new_vcf_status):
                    vcf_status_value = new_vcf_status
                else:
                    vcf_status_value = case["vcf_status"]

                conn.execute(
                    """UPDATE cases
                       SET vcf_account_created = TRUE,
                           vcf_status = COALESCE(%s, vcf_status),
                           updated_at = NOW()
                       WHERE id=%s AND firm_id=%s""",
                    (vcf_status_value, case_id, firm_id),
                )

                username = body.vcf_username or "(unknown)"
                note = (
                    f"VCF account marked {body.status} for {prep['client_name'] or 'claimant'} "
                    f"(username: {username})."
                )
                conn.execute(
                    "INSERT INTO case_notes (firm_id, case_id, note) VALUES (%s,%s,%s)",
                    (firm_id, case_id, note),
                )

                due = datetime.now(timezone.utc).date() + timedelta(days=30)
                conn.execute(
                    """INSERT INTO vcf_deadlines
                       (firm_id, case_id, deadline_type, due_date, status, description)
                       VALUES (%s, %s, %s, %s, 'pending', %s)
                       ON CONFLICT DO NOTHING""",
                    (firm_id, case_id, "verify_portal_access", due,
                     "Confirm claimant can log in to VCF portal within 30 days."),
                )

        conn.commit()
    return {"success": True, "prep_id": prep_id, "status": body.status}


@router.get("/cases/{case_id}/prep-status")
def get_case_prep_status(case_id: int, request: Request):
    """Return the latest prep sheet status for a case."""
    firm_id = getattr(request.state, "firm_id", "default")
    from backend.demo1.pg import get_conn
    with get_conn(firm_id) as conn:
        row = conn.execute(
            """SELECT id, status, vcf_username, client_name, created_at, updated_at
               FROM vcf_account_prep
               WHERE firm_id=%s AND case_id=%s
               ORDER BY updated_at DESC LIMIT 1""",
            (firm_id, case_id),
        ).fetchone()
        case = conn.execute(
            "SELECT id, vcf_account_created, vcf_status FROM cases WHERE id=%s AND firm_id=%s AND deleted = FALSE",
            (case_id, firm_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "No prep sheet found for this case")
    return {
        "success": True,
        "case_id": case_id,
        "prep_id": row["id"],
        "status": row["status"],
        "vcf_username": row["vcf_username"],
        "client_name": row["client_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "case_vcf_account_created": case["vcf_account_created"] if case else None,
        "case_vcf_status": case["vcf_status"] if case else None,
    }
