"""
ParaIQ Email Filter Engine - 5-stage pipeline
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

TRUSTED_DOMAIN_PATTERNS = [
    r"\.gov$", r"\.court", r"\.uscourts\.gov$", r"\.edu$",
]
# Known system/noreply sender domains to auto-discard
SYSTEM_DOMAINS = {
    "accountprotection.microsoft.com",
    "microsoft.com", "microsoftonline.com",
    "accounts.google.com", "googlemail.com",
    "facebookmail.com", "twittermail.com",
    "bounce.linkedin.com", "notifications.linkedin.com",
    "mailer.notion.so", "notify.slack.com",
    "noreply.github.com", "notifications.github.com",
}

BULK_MAIL_HEADERS = [
    "list-unsubscribe", "list-id", "x-mailchimp", "x-sendgrid",
    "x-campaign", "x-bulk-mail", "precedence",
]
SPAM_SUBJECT_PATTERNS = [
    r"\b(unsubscribe|newsletter|webinar|% off|\$\d+ off|promo|subscribe|deal|offer)\b",
    r"\b(click here|act now|limited time|free trial|sign up today)\b",
]
LEGAL_KEYWORDS = [
    "settlement","hearing","motion","deposition","subpoena","complaint",
    "plaintiff","defendant","counsel","attorney","court","filing","discovery",
    "interrogatory","affidavit","brief","appeal","judgment","injunction",
    "damages","exhibit","testimony","verdict","stipulation","mediation",
]


@dataclass
class EmailMessage:
    provider_message_id: str
    provider: str
    attorney_id: str
    account_id: str
    firm_id: str
    from_address: str
    to_addresses: list
    cc_addresses: list
    subject: str
    body_text: str
    body_html: str
    received_at: datetime
    headers: dict = field(default_factory=dict)
    attachment_names: list = field(default_factory=list)
    source_url: str = ""


@dataclass
class FilterResult:
    stage1_domain_score: int = 0
    stage2_nlp_score: int = 0
    stage3_spam_penalty: int = 0
    stage4_final_score: int = 0
    case_id_matched: Optional[int] = None
    routing_decision: str = "discard"
    discard_reason: Optional[str] = None
    extracted_entities: dict = field(default_factory=dict)
    action_items: list = field(default_factory=list)
    deadline_dates: list = field(default_factory=list)
    priority: str = "normal"


class EmailFilterEngine:
    def __init__(self, firm_id: str):
        self.firm_id = firm_id
        self._case_registry: dict = {}
        self._client_domains: set = set()

    def load_case_registry(self):
        from .pg import get_conn
        with get_conn(self.firm_id) as conn:
            rows = conn.execute(
                """SELECT id, case_number, client_name, matter_number
                   FROM cases
                   WHERE firm_id = %s
                     AND (deleted IS NULL OR deleted = FALSE)
                     AND status NOT IN ('closed','archived')""",
                (self.firm_id,)
            ).fetchall()
        self._case_registry = {}
        for r in (rows or []):
            self._case_registry[str(r["id"])] = {
                "title":  (r["case_number"]  or "").lower(),
                "client": (r["client_name"]  or "").lower(),
                "docket": (r["matter_number"] or "").lower(),
            }
        logger.info(f"[Filter] Loaded {len(self._case_registry)} cases for firm {self.firm_id}")

    def _stage1_domain_trust(self, msg: EmailMessage) -> int:
        score = 0
        domain = msg.from_address.split("@")[-1].lower() if "@" in msg.from_address else ""
        for pattern in TRUSTED_DOMAIN_PATTERNS:
            if re.search(pattern, domain):
                score += 40; break
        if domain in self._client_domains:
            score += 30
        for header in BULK_MAIL_HEADERS:
            if header in {k.lower() for k in msg.headers}:
                score -= 50; break
        # Known system/notification domains → hard discard
        if domain in SYSTEM_DOMAINS:
            return -100
        local = msg.from_address.split("@")[0].lower()
        if local in ("no-reply","noreply","donotreply","notifications","mailer-daemon"):
            score -= 20
        return max(score, -50)

    def _stage2_nlp_case_match(self, msg: EmailMessage) -> tuple:
        score = 0
        matched_case_id = None
        entities: dict = {"case_refs": [], "legal_keywords": [], "dates": []}
        full_text = f"{msg.subject} {msg.body_text}".lower()
        for case_id, case in self._case_registry.items():
            hit = False
            if case["title"] and len(case["title"]) > 4 and case["title"] in full_text:
                entities["case_refs"].append(case["title"]); hit = True
            if case["client"] and len(case["client"]) > 3 and case["client"] in full_text:
                entities["case_refs"].append(case["client"]); hit = True
            if case["docket"] and case["docket"] in full_text:
                entities["case_refs"].append(case["docket"]); hit = True
            if hit:
                score += 35; matched_case_id = int(case_id); break
        hits = [kw for kw in LEGAL_KEYWORDS if kw in full_text]
        entities["legal_keywords"] = hits
        score += 20 if len(hits) >= 3 else (10 if hits else 0)
        dates = re.findall(
            r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2},? \d{4})\b",
            full_text
        )
        entities["dates"] = dates[:10]
        if dates: score += 5
        return score, matched_case_id, entities

    def _stage3_spam_filter(self, msg: EmailMessage) -> tuple:
        penalty = 0; reason = None
        for pattern in SPAM_SUBJECT_PATTERNS:
            if re.search(pattern, msg.subject, re.I):
                penalty -= 40; reason = "Spam subject pattern matched"; break
        if "unsubscribe" in msg.body_text.lower():
            penalty -= 35; reason = reason or "Unsubscribe link in body"
        if msg.body_html:
            if msg.body_html.lower().count("<img") > 3 and len(msg.body_text.strip()) < 200:
                penalty -= 20; reason = reason or "Image-heavy, low text"
        return penalty, reason

    def _stage4_route(self, score: int) -> str:
        if score >= 70: return "intake"
        if score >= 30: return "review"
        return "discard"

    def _stage5_priority(self, msg: EmailMessage, entities: dict) -> str:
        urgent = ["urgent","emergency","asap","immediate","deadline today",
                  "time sensitive","court order","injunction","tomorrow"]
        full_text = f"{msg.subject} {msg.body_text}".lower()
        for w in urgent:
            if w in full_text: return "urgent"
        if len(entities.get("legal_keywords", [])) >= 5: return "high"
        return "normal"

    def process(self, msg: EmailMessage) -> FilterResult:
        r = FilterResult()
        s1 = self._stage1_domain_trust(msg)
        s2, case_id, entities = self._stage2_nlp_case_match(msg)
        s3, spam_reason = self._stage3_spam_filter(msg)
        final = max(0, min(100, s1 + s2 + s3 + 50))
        r.stage1_domain_score = s1
        r.stage2_nlp_score    = s2
        r.stage3_spam_penalty = s3
        r.stage4_final_score  = final
        r.case_id_matched     = case_id
        r.routing_decision    = self._stage4_route(final)
        r.discard_reason      = spam_reason if r.routing_decision == "discard" else None
        r.extracted_entities  = entities
        r.priority            = self._stage5_priority(msg, entities)
        logger.info(f"[Filter] {msg.from_address} | '{msg.subject[:50]}' | s1={s1} s2={s2} s3={s3} final={final} → {r.routing_decision}")
        return r
