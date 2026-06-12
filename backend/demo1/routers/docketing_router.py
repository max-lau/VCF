"""
docketing_router.py — Rules-Based Docketing Chains
===================================================
Jurisdictions: SDNY/EDNY, NYSCEF, NJ Superior, MA Superior
Auto-generates deadline chains from trigger events.
All events require attorney confirmation — unconfirmed events
surface in morning brief daily until confirmed.

DISCLAIMER: Auto-calculated deadlines. Attorney must independently
verify against court rules, local rules, and standing orders.
ParaIQ is not a substitute for legal judgment and does not
guarantee accuracy of calculated deadlines.
"""

import logging
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn

router = APIRouter()
log    = logging.getLogger(__name__)

DISCLAIMER = (
    "AUTO-CALCULATED DEADLINE: Attorney must independently verify against "
    "court rules, local rules, and any standing orders. ParaIQ is not a "
    "substitute for legal judgment and does not guarantee accuracy."
)

# ── US Federal Holidays (static for next 2 years) ─────────────────────────
FEDERAL_HOLIDAYS = {
    date(2025,1,1), date(2025,1,20), date(2025,2,17), date(2025,5,26),
    date(2025,6,19), date(2025,7,4), date(2025,9,1), date(2025,10,13),
    date(2025,11,11), date(2025,11,27), date(2025,12,25),
    date(2026,1,1), date(2026,1,19), date(2026,2,16), date(2026,5,25),
    date(2026,6,19), date(2026,7,4), date(2026,7,3), date(2026,9,7),
    date(2026,10,12), date(2026,11,11), date(2026,11,26), date(2026,12,25),
}

def add_business_days(start: date, days: int, holidays=FEDERAL_HOLIDAYS) -> tuple:
    """
    Add business days to a date per FRCP 6(a).
    Returns (result_date, was_adjusted, note).
    """
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holidays:
            added += 1
    # Check if we need to roll forward from weekend/holiday
    original = current
    while current.weekday() >= 5 or current in holidays:
        current += timedelta(days=1)
    adjusted = current != original
    note = None
    if adjusted:
        note = f"Rolled from {original.strftime('%a %b %d')} (weekend/holiday) to next business day per FRCP 6(a)"
    return current, adjusted, note

def add_calendar_days(start: date, days: int) -> tuple:
    """Add calendar days, roll forward if lands on weekend/holiday."""
    result = start + timedelta(days=days)
    original = result
    while result.weekday() >= 5 or result in FEDERAL_HOLIDAYS:
        result += timedelta(days=1)
    adjusted = result != original
    note = f"Rolled from {original.strftime('%a %b %d')} to next business day" if adjusted else None
    return result, adjusted, note


# ── Jurisdiction Chain Definitions ────────────────────────────────────────

def build_sdny_chain(trigger_date: date, service_method: str) -> list:
    """SDNY/EDNY Federal Civil — FRCP based."""
    events = []

    # Answer deadline varies by service method
    answer_days = {"personal": 21, "substituted": 21, "mail": 24, "waiver": 60}
    days = answer_days.get(service_method, 21)
    ans_date, adj, note = add_business_days(trigger_date, days)
    events.append({
        "title": "Answer or Motion to Dismiss Due",
        "event_type": "answer_deadline",
        "rule_reference": "FRCP 12(a)(1)(A)",
        "calculated_date": ans_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Rule 26(f) conference — within 21 days of answer
    r26_date, adj, note = add_business_days(ans_date, 21)
    events.append({
        "title": "Rule 26(f) Conference",
        "event_type": "rule26f_conference",
        "rule_reference": "FRCP 26(f)",
        "calculated_date": r26_date,
        "is_court_date": True,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Initial disclosures — 14 days after 26(f)
    disc_date, adj, note = add_business_days(r26_date, 14)
    events.append({
        "title": "Initial Disclosures Due",
        "event_type": "initial_disclosures",
        "rule_reference": "FRCP 26(a)(1)(C)",
        "calculated_date": disc_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Discovery cutoff — 180 days after 26(f) (placeholder, judge sets)
    disco_date, adj, note = add_business_days(r26_date, 180)
    events.append({
        "title": "Discovery Cutoff (Placeholder — Verify Scheduling Order)",
        "event_type": "discovery_cutoff",
        "rule_reference": "FRCP 16(b)",
        "calculated_date": disco_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Dispositive motions — 30 days after discovery cutoff
    mot_date, adj, note = add_business_days(disco_date, 30)
    events.append({
        "title": "Dispositive Motions Due",
        "event_type": "motions_deadline",
        "rule_reference": "FRCP 56",
        "calculated_date": mot_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Opposition — 21 days after motions
    opp_date, adj, note = add_business_days(mot_date, 21)
    events.append({
        "title": "Opposition to Dispositive Motions Due",
        "event_type": "opposition_deadline",
        "rule_reference": "FRCP 56(c)(1)",
        "calculated_date": opp_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Reply — 14 days after opposition
    rep_date, adj, note = add_business_days(opp_date, 14)
    events.append({
        "title": "Reply in Support of Dispositive Motions Due",
        "event_type": "reply_deadline",
        "rule_reference": "FRCP 56(c)(1)",
        "calculated_date": rep_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    return events


def build_nyscef_chain(trigger_date: date, service_method: str) -> list:
    """NY State Supreme Court — CPLR based."""
    events = []

    answer_days = {"personal": 20, "substituted": 30, "mail": 33, "waiver": 30}
    days = answer_days.get(service_method, 20)
    ans_date, adj, note = add_calendar_days(trigger_date, days)
    events.append({
        "title": "Answer Due",
        "event_type": "answer_deadline",
        "rule_reference": "CPLR 320(a)",
        "calculated_date": ans_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # RJI filing triggers preliminary conference within 45 days
    rji_date, adj, note = add_calendar_days(ans_date, 10)
    events.append({
        "title": "RJI Filing Deadline",
        "event_type": "rji_filing",
        "rule_reference": "CPLR 312-a",
        "calculated_date": rji_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    pc_date, adj, note = add_calendar_days(rji_date, 45)
    events.append({
        "title": "Preliminary Conference",
        "event_type": "preliminary_conference",
        "rule_reference": "CPLR 3402",
        "calculated_date": pc_date,
        "is_court_date": True,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Compliance conference 60 days after preliminary
    cc_date, adj, note = add_calendar_days(pc_date, 60)
    events.append({
        "title": "Compliance Conference",
        "event_type": "compliance_conference",
        "rule_reference": "CPLR 3402",
        "calculated_date": cc_date,
        "is_court_date": True,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Note of Issue — 90 days after compliance conference
    noi_date, adj, note = add_calendar_days(cc_date, 90)
    events.append({
        "title": "Note of Issue Filing Deadline",
        "event_type": "note_of_issue",
        "rule_reference": "CPLR 3402",
        "calculated_date": noi_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Trial ready 90 days after Note of Issue
    trial_date, adj, note = add_calendar_days(noi_date, 90)
    events.append({
        "title": "Trial Ready Date",
        "event_type": "trial_ready",
        "rule_reference": "CPLR 3402",
        "calculated_date": trial_date,
        "is_court_date": True,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    return events


def build_nj_chain(trigger_date: date, service_method: str) -> list:
    """NJ Superior Court — NJ Court Rules based."""
    events = []

    answer_days = {"personal": 35, "substituted": 35, "mail": 38, "waiver": 60}
    days = answer_days.get(service_method, 35)
    ans_date, adj, note = add_calendar_days(trigger_date, days)
    events.append({
        "title": "Answer Due",
        "event_type": "answer_deadline",
        "rule_reference": "NJ R. 4:6-1(a)",
        "calculated_date": ans_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Track assignment — standard 300 days from complaint
    std_date, adj, note = add_calendar_days(trigger_date, 300)
    events.append({
        "title": "Discovery End Date — Standard Track (300 days)",
        "event_type": "discovery_cutoff",
        "rule_reference": "NJ R. 4:24-1",
        "calculated_date": std_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Dispositive motions 30 days after discovery
    mot_date, adj, note = add_calendar_days(std_date, 30)
    events.append({
        "title": "Dispositive Motions Due",
        "event_type": "motions_deadline",
        "rule_reference": "NJ R. 4:46-1",
        "calculated_date": mot_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Opposition 30 days after motions
    opp_date, adj, note = add_calendar_days(mot_date, 30)
    events.append({
        "title": "Opposition to Motions Due",
        "event_type": "opposition_deadline",
        "rule_reference": "NJ R. 1:6-3",
        "calculated_date": opp_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    return events


def build_ma_chain(trigger_date: date, service_method: str) -> list:
    """MA Superior Court — Mass. R. Civ. P. based."""
    events = []

    answer_days = {"personal": 20, "substituted": 20, "mail": 23, "waiver": 60}
    days = answer_days.get(service_method, 20)
    ans_date, adj, note = add_calendar_days(trigger_date, days)
    events.append({
        "title": "Answer Due",
        "event_type": "answer_deadline",
        "rule_reference": "Mass. R. Civ. P. 12(a)",
        "calculated_date": ans_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Rule 9A conference within 60 days of answer
    r9a_date, adj, note = add_calendar_days(ans_date, 60)
    events.append({
        "title": "Rule 9A Conference",
        "event_type": "rule9a_conference",
        "rule_reference": "Mass. Sup. Ct. Rule 9A",
        "calculated_date": r9a_date,
        "is_court_date": True,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Fast track — 12 months from complaint
    fast_date, adj, note = add_calendar_days(trigger_date, 365)
    events.append({
        "title": "Discovery Cutoff — Fast Track (12 months)",
        "event_type": "discovery_cutoff_fast",
        "rule_reference": "Standing Order 1-88",
        "calculated_date": fast_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Standard track — 18 months
    std_date, adj, note = add_calendar_days(trigger_date, 548)
    events.append({
        "title": "Discovery Cutoff — Standard Track (18 months)",
        "event_type": "discovery_cutoff_standard",
        "rule_reference": "Standing Order 1-88",
        "calculated_date": std_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Motions 30 days after standard track cutoff
    mot_date, adj, note = add_calendar_days(std_date, 30)
    events.append({
        "title": "Dispositive Motions Due",
        "event_type": "motions_deadline",
        "rule_reference": "Mass. R. Civ. P. 56",
        "calculated_date": mot_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    # Opposition 21 days after motions
    opp_date, adj, note = add_calendar_days(mot_date, 21)
    events.append({
        "title": "Opposition to Motions Due",
        "event_type": "opposition_deadline",
        "rule_reference": "Mass. R. Civ. P. 56(c)",
        "calculated_date": opp_date,
        "is_court_date": False,
        "is_business_day_adj": adj,
        "business_day_note": note,
        "service_method": service_method,
    })

    return events


CHAIN_BUILDERS = {
    "SDNY":        build_sdny_chain,
    "EDNY":        build_sdny_chain,
    "NYSCEF":      build_nyscef_chain,
    "NJ_SUPERIOR": build_nj_chain,
    "MA_SUPERIOR": build_ma_chain,
}


# ── Pydantic Models ───────────────────────────────────────────────────────

class TriggerRequest(BaseModel):
    matter_id:      int
    jurisdiction:   str
    trigger_event:  str
    trigger_date:   str   # ISO date
    service_method: str

class ConfirmRequest(BaseModel):
    confirmed_date: Optional[str] = None  # ISO date, None = accept calculated
    note:           Optional[str] = None
    disclaimer_ack: bool = False

class PostponeRequest(BaseModel):
    new_date:          str
    postponement_note: str
    disclaimer_ack:    bool = False


# ── Helpers ───────────────────────────────────────────────────────────────

def _log_confirmation(conn, event_id, firm_id, action, prev_date, new_date,
                      prev_state, new_state, note, user_id, username):
    conn.execute("""
        INSERT INTO docketing_confirmations
            (event_id, firm_id, action, prev_date, new_date,
             prev_state, new_state, note, disclaimer_text, performed_by, performed_by_username)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (event_id, firm_id, action, prev_date, new_date,
          prev_state, new_state, note, DISCLAIMER, user_id, username))


# ── Routes ────────────────────────────────────────────────────────────────

@router.get("/preview")
def preview_chain(
    matter_id:      int,
    jurisdiction:   str,
    trigger_date:   str,
    service_method: str,
    firm_id: str  = Depends(get_current_firm_id),
    user         = Depends(get_current_user),
):
    """Preview chain without saving — used by service method modal."""
    builder = CHAIN_BUILDERS.get(jurisdiction.upper())
    if not builder:
        raise HTTPException(400, f"Unknown jurisdiction: {jurisdiction}")
    try:
        td = date.fromisoformat(trigger_date)
    except ValueError:
        raise HTTPException(400, "Invalid trigger_date format, use YYYY-MM-DD")

    # Build previews for all service methods for the modal
    previews = {}
    for method in ["personal", "substituted", "mail", "waiver"]:
        events = builder(td, method)
        previews[method] = [
            {
                "title": e["title"],
                "calculated_date": e["calculated_date"].isoformat(),
                "is_court_date": e["is_court_date"],
                "rule_reference": e.get("rule_reference"),
                "is_business_day_adj": e["is_business_day_adj"],
                "business_day_note": e.get("business_day_note"),
            }
            for e in events
        ]
    return {
        "jurisdiction": jurisdiction,
        "trigger_date": trigger_date,
        "previews": previews,
        "disclaimer": DISCLAIMER,
    }


@router.post("/trigger")
def trigger_chain(
    body:    TriggerRequest,
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """Generate and save a docketing chain for a matter."""
    builder = CHAIN_BUILDERS.get(body.jurisdiction.upper())
    if not builder:
        raise HTTPException(400, f"Unknown jurisdiction: {body.jurisdiction}")
    try:
        td = date.fromisoformat(body.trigger_date)
    except ValueError:
        raise HTTPException(400, "Invalid trigger_date")

    events = builder(td, body.service_method)

    with get_conn(firm_id) as conn:
        # Verify matter belongs to firm
        matter = conn.execute(
            "SELECT id, case_number, client_name FROM cases WHERE id=%s AND firm_id=%s AND deleted=false",
            (body.matter_id, firm_id)
        ).fetchone()
        if not matter:
            raise HTTPException(404, "Matter not found")

        # Create chain
        chain_id = conn.execute("""
            INSERT INTO docketing_chains
                (firm_id, matter_id, jurisdiction, trigger_event, trigger_date, service_method, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (firm_id, body.matter_id, body.jurisdiction.upper(),
              body.trigger_event, td, body.service_method,
              user.get("id"))).fetchone()["id"]

        # Insert events and create calendar entries
        event_ids = []
        for ev in events:
            # Create calendar event
            cal_id = conn.execute("""
                INSERT INTO calendar_events
                    (firm_id, matter_id, title, event_type, due_date,
                     is_court_date, status, description)
                VALUES (%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id
            """, (
                firm_id, body.matter_id, ev["title"], ev["event_type"],
                ev["calculated_date"], ev["is_court_date"],
                f"Auto-generated by docketing chain. {ev.get('rule_reference','')}. {DISCLAIMER}"
            )).fetchone()["id"]

            # Create docketing event
            ev_id = conn.execute("""
                INSERT INTO docketing_events
                    (firm_id, chain_id, matter_id, calendar_event_id, title,
                     event_type, jurisdiction, rule_reference, calculated_date,
                     is_court_date, is_business_day_adj, business_day_note,
                     service_method, confirmation_state)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending') RETURNING id
            """, (
                firm_id, chain_id, body.matter_id, cal_id, ev["title"],
                ev["event_type"], body.jurisdiction.upper(),
                ev.get("rule_reference"), ev["calculated_date"],
                ev["is_court_date"], ev["is_business_day_adj"],
                ev.get("business_day_note"), body.service_method
            )).fetchone()["id"]

            # Log generation with disclaimer
            _log_confirmation(
                conn, ev_id, firm_id, "generated",
                None, ev["calculated_date"],
                None, "pending",
                f"Auto-generated from {body.jurisdiction} chain. Service: {body.service_method}.",
                user.get("id"), user.get("username")
            )
            event_ids.append(ev_id)

    log.info(f"[Docketing] Chain generated: {body.jurisdiction} for matter {body.matter_id}, {len(events)} events")
    return {
        "ok": True,
        "chain_id": chain_id,
        "matter_id": body.matter_id,
        "jurisdiction": body.jurisdiction,
        "events_created": len(events),
        "disclaimer": DISCLAIMER,
    }


@router.get("/matter/{matter_id}")
def get_matter_chains(
    matter_id: int,
    firm_id:   str = Depends(get_current_firm_id),
    user       = Depends(get_current_user),
):
    """Get all docketing chains and events for a matter."""
    with get_conn(firm_id) as conn:
        chains = conn.execute("""
            SELECT dc.*, c.case_number, c.client_name
            FROM docketing_chains dc
            JOIN cases c ON c.id = dc.matter_id
            WHERE dc.matter_id=%s AND dc.firm_id=%s AND dc.status='active'
            ORDER BY dc.created_at DESC
        """, (matter_id, firm_id)).fetchall()

        result = []
        for chain in chains:
            ch = dict(chain)
            for f in ["trigger_date","created_at","updated_at"]:
                if ch.get(f) and hasattr(ch[f],"isoformat"):
                    ch[f] = ch[f].isoformat()

            events = conn.execute("""
                SELECT *,
                    EXTRACT(DAY FROM NOW() - created_at)::INTEGER AS days_unconfirmed
                FROM docketing_events
                WHERE chain_id=%s AND firm_id=%s
                ORDER BY calculated_date ASC
            """, (ch["id"], firm_id)).fetchall()

            ch["events"] = []
            for ev in events:
                e = dict(ev)
                for f in ["calculated_date","confirmed_date","confirmed_at","created_at","updated_at"]:
                    if e.get(f) and hasattr(e[f],"isoformat"):
                        e[f] = e[f].isoformat()
                ch["events"].append(e)
            result.append(ch)

    return {"chains": result, "disclaimer": DISCLAIMER}


@router.get("/pending")
def get_pending_events(
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """All unconfirmed docketing events for the firm — used by morning brief."""
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT de.*,
                c.case_number, c.client_name,
                EXTRACT(DAY FROM NOW() - de.created_at)::INTEGER AS days_unconfirmed
            FROM docketing_events de
            JOIN cases c ON c.id = de.matter_id
            WHERE de.firm_id=%s AND de.confirmation_state='pending'
            ORDER BY de.calculated_date ASC
        """, (firm_id,)).fetchall()

    items = []
    for r in rows:
        e = dict(r)
        for f in ["calculated_date","confirmed_date","confirmed_at","created_at","updated_at"]:
            if e.get(f) and hasattr(e[f],"isoformat"):
                e[f] = e[f].isoformat()
        items.append(e)
    return {"items": items, "count": len(items), "disclaimer": DISCLAIMER}


@router.post("/events/{event_id}/confirm")
def confirm_event(
    event_id: int,
    body:     ConfirmRequest,
    firm_id:  str = Depends(get_current_firm_id),
    user      = Depends(get_current_user),
):
    """Attorney confirms a docketing event."""
    if not body.disclaimer_ack:
        raise HTTPException(400, "Must acknowledge disclaimer before confirming")

    with get_conn(firm_id) as conn:
        ev = conn.execute(
            "SELECT * FROM docketing_events WHERE id=%s AND firm_id=%s",
            (event_id, firm_id)
        ).fetchone()
        if not ev:
            raise HTTPException(404, "Event not found")
        ev = dict(ev)

        confirmed_date = date.fromisoformat(body.confirmed_date) if body.confirmed_date else ev["calculated_date"]
        modified = body.confirmed_date and confirmed_date != ev["calculated_date"]
        new_state = "modified" if modified else "confirmed"
        prev_date = ev["calculated_date"]

        conn.execute("""
            UPDATE docketing_events
            SET confirmation_state=%s, confirmed_date=%s, confirmed_by=%s,
                confirmed_at=NOW(), disclaimer_ack=TRUE, updated_at=NOW()
            WHERE id=%s
        """, (new_state, confirmed_date, user.get("id"), event_id))

        # Update calendar event date if modified
        if modified and ev.get("calendar_event_id"):
            conn.execute(
                "UPDATE calendar_events SET due_date=%s, updated_at=NOW() WHERE id=%s",
                (confirmed_date, ev["calendar_event_id"])
            )

        _log_confirmation(
            conn, event_id, firm_id,
            "modified" if modified else "confirmed",
            prev_date, confirmed_date,
            "pending", new_state,
            body.note, user.get("id"), user.get("username")
        )

    return {"ok": True, "new_state": new_state, "confirmed_date": confirmed_date.isoformat()}


@router.post("/events/{event_id}/postpone")
def postpone_event(
    event_id: int,
    body:     PostponeRequest,
    firm_id:  str = Depends(get_current_firm_id),
    user      = Depends(get_current_user),
):
    """Record a postponement — turns pill to green with double-edge highlight."""
    if not body.disclaimer_ack:
        raise HTTPException(400, "Must acknowledge disclaimer before postponing")

    with get_conn(firm_id) as conn:
        ev = conn.execute(
            "SELECT * FROM docketing_events WHERE id=%s AND firm_id=%s",
            (event_id, firm_id)
        ).fetchone()
        if not ev:
            raise HTTPException(404, "Event not found")
        ev = dict(ev)

        new_date = date.fromisoformat(body.new_date)
        prev_date = ev.get("confirmed_date") or ev["calculated_date"]

        conn.execute("""
            UPDATE docketing_events
            SET confirmed_date=%s, postponed=TRUE,
                postponement_note=%s, confirmation_state='modified',
                confirmed_by=%s, confirmed_at=NOW(),
                disclaimer_ack=TRUE, updated_at=NOW()
            WHERE id=%s
        """, (new_date, body.postponement_note, user.get("id"), event_id))

        if ev.get("calendar_event_id"):
            conn.execute(
                "UPDATE calendar_events SET due_date=%s, updated_at=NOW() WHERE id=%s",
                (new_date, ev["calendar_event_id"])
            )

        _log_confirmation(
            conn, event_id, firm_id, "postponed",
            prev_date, new_date, ev["confirmation_state"], "modified",
            body.postponement_note, user.get("id"), user.get("username")
        )

    return {"ok": True, "new_date": body.new_date}


@router.get("/events/{event_id}/audit")
def get_event_audit(
    event_id: int,
    firm_id:  str = Depends(get_current_firm_id),
    user      = Depends(get_current_user),
):
    """Full audit trail for a single docketing event."""
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT * FROM docketing_confirmations
            WHERE event_id=%s AND firm_id=%s
            ORDER BY performed_at ASC
        """, (event_id, firm_id)).fetchall()

    items = []
    for r in rows:
        d = dict(r)
        if d.get("performed_at") and hasattr(d["performed_at"],"isoformat"):
            d["performed_at"] = d["performed_at"].isoformat()
        for f in ["prev_date","new_date"]:
            if d.get(f) and hasattr(d[f],"isoformat"):
                d[f] = d[f].isoformat()
        items.append(d)
    return {"audit": items}
