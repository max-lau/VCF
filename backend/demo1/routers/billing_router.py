"""
billing_router.py — Client Billing Module
==========================================
Full invoice lifecycle: draft → certified → sent → paid/overdue
One-click PDF generation via ReportLab.
Pulls line items from certified time_entries.

Mount in main.py:
    from backend.demo1.routers.billing_router import router as billing_router
    app.include_router(billing_router, prefix="/billing", tags=["billing"])
"""

import io, logging
from datetime import date, datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from backend.demo1.auth import get_current_user, get_current_firm_id
from backend.demo1.pg import get_conn

# ReportLab
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

router = APIRouter()
log    = logging.getLogger(__name__)

INVOICE_STATUSES = [
    "draft", "pending_certification", "certified",
    "sent", "viewed", "partially_paid", "paid",
    "overdue", "disputed", "void"
]


# ── Pydantic Models ───────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    matter_id:            int
    billing_period_start: Optional[str] = None
    billing_period_end:   Optional[str] = None
    due_date:             Optional[str] = None
    tax_rate:             float = 0.0
    payment_terms:        str = "Net 30"
    notes:                Optional[str] = None

class ManualLineItem(BaseModel):
    description:   str
    activity_type: Optional[str] = None
    date:          Optional[str] = None
    quantity:      float = 1.0
    unit:          str = "hour"
    rate:          float
    amount:        Optional[float] = None

class AddItemBody(BaseModel):
    invoice_id: int
    item:       ManualLineItem

class StatusUpdate(BaseModel):
    status: str
    note:   Optional[str] = None

class PaymentBody(BaseModel):
    amount:       float
    payment_date: Optional[str] = None
    method:       str = "check"
    reference:    Optional[str] = None
    notes:        Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────

def _next_invoice_number(conn, firm_id: str) -> str:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM invoices WHERE firm_id=%s", (firm_id,)
    ).fetchone()
    n = (row["n"] or 0) + 1
    year = date.today().year
    return f"INV-{year}-{n:04d}"

def _recalc_totals(conn, invoice_id: int, tax_rate: float):
    subtotal = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM invoice_items WHERE invoice_id=%s",
        (invoice_id,)
    ).fetchone()["s"]
    subtotal = float(subtotal)
    tax_amount = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax_amount, 2)
    amount_paid = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM payments WHERE invoice_id=%s",
        (invoice_id,)
    ).fetchone()["s"]
    amount_paid = float(amount_paid)
    balance_due = round(total - amount_paid, 2)
    conn.execute("""
        UPDATE invoices SET subtotal=%s, tax_amount=%s, total=%s,
            amount_paid=%s, balance_due=%s, updated_at=NOW()
        WHERE id=%s
    """, (subtotal, tax_amount, total, amount_paid, balance_due, invoice_id))
    return subtotal, tax_amount, total, balance_due

def _serialize(d: dict) -> dict:
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif hasattr(v, "__float__"):
            try:
                d[k] = float(v)
            except (ValueError, TypeError) as e:
                log.debug(f"[Billing] Could not coerce field '{k}' to float: {e}")
    return d


# ── PDF Builder ───────────────────────────────────────────────────────────

def build_invoice_pdf(invoice: dict, items: list, payments: list, firm_id: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch)

    styles = getSampleStyleSheet()
    gold   = colors.HexColor("#C9A84C")
    dark   = colors.HexColor("#1a1a2e")
    grey   = colors.HexColor("#6b7280")
    red    = colors.HexColor("#dc2626")
    green  = colors.HexColor("#16a34a")

    h1 = ParagraphStyle("h1", parent=styles["Normal"],
        fontSize=22, textColor=gold, fontName="Helvetica-Bold", spaceAfter=4)
    FIRM_NAMES = {"default": "ParaIQ (Super Admin)", "firm_abc": "Thornton & Associates", "meridian_legal": "Meridian Legal Group"}
    h2 = ParagraphStyle("h2", parent=styles["Normal"],
        fontSize=11, textColor=dark, fontName="Helvetica-Bold", spaceAfter=2)
    normal = ParagraphStyle("normal", parent=styles["Normal"],
        fontSize=9, textColor=dark, spaceAfter=2)
    small = ParagraphStyle("small", parent=styles["Normal"],
        fontSize=8, textColor=grey, spaceAfter=2)
    right = ParagraphStyle("right", parent=styles["Normal"],
        fontSize=9, textColor=dark, alignment=TA_RIGHT)
    total_style = ParagraphStyle("total", parent=styles["Normal"],
        fontSize=12, textColor=dark, fontName="Helvetica-Bold", alignment=TA_RIGHT)
    disclaimer = ParagraphStyle("disclaimer", parent=styles["Normal"],
        fontSize=7, textColor=grey, spaceAfter=2)

    story = []

    # ── Header ──
    header_data = [[
        Paragraph("INVOICE", h1),
        Paragraph(f"Invoice #: <b>{invoice['invoice_number']}</b><br/>"
                  f"Issue Date: {invoice.get('issue_date','')}<br/>"
                  f"Due Date: <font color=red><b>{invoice.get('due_date','')}</b></font><br/>"
                  f"Status: <b>{invoice.get('status','').upper().replace('_',' ')}</b>", right)
    ]]
    header_tbl = Table(header_data, colWidths=[3.5*inch, 3.5*inch])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(header_tbl)
    story.append(HRFlowable(width="100%", thickness=2, color=gold, spaceAfter=12))

    # ── Bill To / From ──
    bill_data = [[
        [Paragraph("<b>BILL TO:</b>", small),
         Paragraph(invoice.get("client_name",""), h2),
         Paragraph(invoice.get("case_number",""), normal)],
        [Paragraph("<b>FROM:</b>", small),
         Paragraph(FIRM_NAMES.get(firm_id, firm_id.replace("_"," ").title()), h2),
         Paragraph(invoice.get("attorney_name") or "", normal),
         Paragraph(f"Payment Terms: {invoice.get('payment_terms','Net 30')}", small)],
    ]]
    bill_tbl = Table([[bill_data[0][0], bill_data[0][1]]], colWidths=[3.5*inch, 3.5*inch])
    bill_tbl.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(bill_tbl)

    if invoice.get("billing_period_start"):
        story.append(Paragraph(
            f"Billing Period: {invoice['billing_period_start']} — {invoice.get('billing_period_end','')}",
            small))
    story.append(Spacer(1, 12))

    # ── Line Items ──
    story.append(Paragraph("SERVICES RENDERED", ParagraphStyle("sh", parent=styles["Normal"],
        fontSize=9, textColor=grey, fontName="Helvetica-Bold", spaceAfter=4)))

    col_headers = [
        Paragraph("<b>Date</b>", small),
        Paragraph("<b>Description</b>", small),
        Paragraph("<b>Activity</b>", small),
        Paragraph("<b>Hrs</b>", small),
        Paragraph("<b>Rate</b>", small),
        Paragraph("<b>Amount</b>", small),
    ]
    rows = [col_headers]
    for item in items:
        qty = float(item.get("quantity") or 1)
        hrs = f"{qty:.2f}" if item.get("unit") == "hour" else f"{qty}"
        rows.append([
            Paragraph(str(item.get("date","") or "")[:10], small),
            Paragraph(str(item.get("description",""))[:80], small),
            Paragraph(str(item.get("activity_type","") or "").capitalize(), small),
            Paragraph(hrs, small),
            Paragraph(f"${float(item.get('rate') or 0):.2f}", small),
            Paragraph(f"${float(item.get('amount') or 0):.2f}", small),
        ])

    items_tbl = Table(rows, colWidths=[1.1*inch, 2.4*inch, 1*inch, 0.5*inch, 0.75*inch, 0.75*inch])
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f3f4f6")),
        ("TEXTCOLOR",  (0,0), (-1,0), grey),
        ("GRID",       (0,0), (-1,-1), 0.25, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f9fafb")]),
        ("VALIGN",     (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 12))

    # ── Totals ──
    subtotal = float(invoice.get("subtotal") or 0)
    tax_rate = float(invoice.get("tax_rate") or 0)
    tax_amt  = float(invoice.get("tax_amount") or 0)
    total    = float(invoice.get("total") or 0)
    paid     = float(invoice.get("amount_paid") or 0)
    balance  = float(invoice.get("balance_due") or 0)

    totals_data = [
        ["Subtotal", f"${subtotal:.2f}"],
        [f"Tax ({tax_rate*100:.1f}%)", f"${tax_amt:.2f}"],
        ["Total", f"${total:.2f}"],
        ["Amount Paid", f"${paid:.2f}"],
        ["Balance Due", f"${balance:.2f}"],
    ]
    totals_tbl = Table(totals_data, colWidths=[5.5*inch, 1.5*inch])
    totals_tbl.setStyle(TableStyle([
        ("ALIGN",      (1,0), (1,-1), "RIGHT"),
        ("FONTNAME",   (0,-2), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,-1), (-1,-1), 11),
        ("TEXTCOLOR",  (1,-1), (1,-1), green if balance <= 0 else red),
        ("LINEABOVE",  (0,-1), (-1,-1), 1, dark),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(totals_tbl)

    # ── Payment History ──
    if payments:
        story.append(Spacer(1, 12))
        story.append(Paragraph("PAYMENT HISTORY", ParagraphStyle("sh2", parent=styles["Normal"],
            fontSize=9, textColor=grey, fontName="Helvetica-Bold", spaceAfter=4)))
        pay_rows = [[
            Paragraph("<b>Date</b>", small),
            Paragraph("<b>Method</b>", small),
            Paragraph("<b>Reference</b>", small),
            Paragraph("<b>Amount</b>", small),
        ]]
        for p in payments:
            pay_rows.append([
                Paragraph(str(p.get("payment_date",""))[:10], small),
                Paragraph(str(p.get("method","")).capitalize(), small),
                Paragraph(str(p.get("reference","") or "—"), small),
                Paragraph(f"${float(p.get('amount') or 0):.2f}", small),
            ])
        pay_tbl = Table(pay_rows, colWidths=[1*inch, 1.5*inch, 2.5*inch, 2*inch])
        pay_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f3f4f6")),
            ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#e5e7eb")),
            ("TOPPADDING", (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]))
        story.append(pay_tbl)

    # ── Notes ──
    if invoice.get("notes"):
        story.append(Spacer(1, 12))
        story.append(Paragraph("<b>Notes:</b>", small))
        story.append(Paragraph(invoice["notes"], normal))

    # ── Footer ──
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=grey, spaceAfter=6))
    story.append(Paragraph(
        "This invoice was generated by ParaIQ Legal Practice Management. "
        "Please make checks payable to the firm or contact your attorney for wire transfer instructions. "
        "Past due invoices may be subject to interest charges per the engagement letter.",
        disclaimer))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/invoices")
def create_invoice(
    body:    InvoiceCreate,
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """Create a new invoice for a matter, pulling certified time entries."""
    with get_conn(firm_id) as conn:
        matter = conn.execute(
            "SELECT * FROM cases WHERE id=%s AND firm_id=%s AND deleted=false",
            (body.matter_id, firm_id)
        ).fetchone()
        if not matter:
            raise HTTPException(404, "Matter not found")
        matter = dict(matter)

        due = date.fromisoformat(body.due_date) if body.due_date else date.today() + timedelta(days=30)
        inv_num = _next_invoice_number(conn, firm_id)

        inv_id = conn.execute("""
            INSERT INTO invoices
                (firm_id, matter_id, invoice_number, client_name, case_number,
                 attorney_id, attorney_name, billing_period_start, billing_period_end,
                 due_date, tax_rate, payment_terms, notes, status, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s)
            RETURNING id
        """, (
            firm_id, body.matter_id, inv_num,
            matter["client_name"], matter["case_number"],
            user.get("id"), user.get("username"),
            body.billing_period_start, body.billing_period_end,
            due, body.tax_rate, body.payment_terms, body.notes,
            user.get("id")
        )).fetchone()["id"]

        # Pull certified time entries for this matter not yet invoiced
        entries = conn.execute("""
            SELECT te.* FROM time_entries te
            WHERE te.firm_id=%s AND te.matter_id=%s
              AND te.id NOT IN (
                  SELECT time_entry_id FROM invoice_items
                  WHERE time_entry_id IS NOT NULL AND firm_id=%s
              )
            ORDER BY te.date ASC
        """, (firm_id, body.matter_id, firm_id)).fetchall()

        for e in entries:
            e = dict(e)
            dur_hrs = float(e["duration_mins"]) / 60
            rate    = float(e["hourly_rate"] or 0)
            amount  = float(e["billable_amount"] or round(dur_hrs * rate, 2))
            desc    = e.get("description") or f"{e.get('activity_type','').capitalize()} — {matter['client_name']}"
            conn.execute("""
                INSERT INTO invoice_items
                    (firm_id, invoice_id, time_entry_id, description,
                     activity_type, date, quantity, unit, rate, amount)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'hour',%s,%s)
            """, (
                firm_id, inv_id, e["id"], desc,
                e.get("activity_type"), e.get("date"),
                round(dur_hrs, 2), rate, amount
            ))

        _recalc_totals(conn, inv_id, body.tax_rate)

    return {"ok": True, "invoice_id": inv_id, "invoice_number": inv_num}


@router.get("/invoices")
def list_invoices(
    matter_id: Optional[int] = None,
    status:    Optional[str] = None,
    firm_id:   str = Depends(get_current_firm_id),
    user       = Depends(get_current_user),
):
    """List all invoices for the firm."""
    with get_conn(firm_id) as conn:
        q = "SELECT i.*, c.status as matter_status FROM invoices i LEFT JOIN cases c ON c.id=i.matter_id WHERE i.firm_id=%s"
        params = [firm_id]
        if matter_id:
            q += " AND i.matter_id=%s"; params.append(matter_id)
        if status:
            q += " AND i.status=%s"; params.append(status)
        q += " ORDER BY i.created_at DESC"
        rows = conn.execute(q, params).fetchall()

    return {"invoices": [_serialize(dict(r)) for r in rows]}


@router.get("/invoices/{invoice_id}")
def get_invoice(
    invoice_id: int,
    firm_id:    str = Depends(get_current_firm_id),
    user        = Depends(get_current_user),
):
    """Get full invoice with line items and payments."""
    with get_conn(firm_id) as conn:
        inv = conn.execute(
            "SELECT * FROM invoices WHERE id=%s AND firm_id=%s", (invoice_id, firm_id)
        ).fetchone()
        if not inv:
            raise HTTPException(404, "Invoice not found")
        items = conn.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=%s ORDER BY date ASC, id ASC",
            (invoice_id,)
        ).fetchall()
        pays = conn.execute(
            "SELECT * FROM payments WHERE invoice_id=%s ORDER BY payment_date ASC",
            (invoice_id,)
        ).fetchall()

    return {
        "invoice":  _serialize(dict(inv)),
        "items":    [_serialize(dict(i)) for i in items],
        "payments": [_serialize(dict(p)) for p in pays],
    }


@router.post("/invoices/{invoice_id}/items")
def add_item(
    invoice_id: int,
    body:       ManualLineItem,
    firm_id:    str = Depends(get_current_firm_id),
    user        = Depends(get_current_user),
):
    """Add a manual line item to an invoice."""
    with get_conn(firm_id) as conn:
        inv = conn.execute(
            "SELECT * FROM invoices WHERE id=%s AND firm_id=%s", (invoice_id, firm_id)
        ).fetchone()
        if not inv:
            raise HTTPException(404, "Invoice not found")
        if dict(inv)["status"] in ("paid","void"):
            raise HTTPException(400, "Cannot modify a paid or void invoice")

        amount = body.amount or round(body.quantity * body.rate, 2)
        conn.execute("""
            INSERT INTO invoice_items
                (firm_id, invoice_id, description, activity_type, date,
                 quantity, unit, rate, amount, is_manual)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
        """, (firm_id, invoice_id, body.description, body.activity_type,
              body.date, body.quantity, body.unit, body.rate, amount))

        tax_rate = float(dict(inv)["tax_rate"] or 0)
        _recalc_totals(conn, invoice_id, tax_rate)

    return {"ok": True}


@router.patch("/invoices/{invoice_id}/status")
def update_status(
    invoice_id: int,
    body:       StatusUpdate,
    firm_id:    str = Depends(get_current_firm_id),
    user        = Depends(get_current_user),
):
    """Advance invoice status."""
    if body.status not in INVOICE_STATUSES:
        raise HTTPException(400, f"Invalid status: {body.status}")

    with get_conn(firm_id) as conn:
        inv = conn.execute(
            "SELECT * FROM invoices WHERE id=%s AND firm_id=%s", (invoice_id, firm_id)
        ).fetchone()
        if not inv:
            raise HTTPException(404)
        inv = dict(inv)
        if body.status == "void" and inv["status"] in ("paid", "partially_paid"):
            raise HTTPException(400, "Cannot void a paid or partially paid invoice")

        updates = {"status": body.status, "updated_at": "NOW()"}
        now = datetime.now(timezone.utc)

        extra_sets = "status=%s, updated_at=NOW()"
        extra_vals = [body.status]

        if body.status == "certified":
            extra_sets += ", certified_by=%s, certified_at=NOW()"
            extra_vals += [user.get("id")]
        elif body.status == "sent":
            extra_sets += ", sent_at=NOW()"
        elif body.status == "viewed":
            extra_sets += ", viewed_at=NOW()"
        elif body.status == "paid":
            extra_sets += ", paid_at=NOW()"
        elif body.status == "overdue":
            extra_sets += ", overdue_at=NOW()"

        conn.execute(
            f"UPDATE invoices SET {extra_sets} WHERE id=%s AND firm_id=%s",
            extra_vals + [invoice_id, firm_id]
        )

    return {"ok": True, "status": body.status}


@router.post("/invoices/{invoice_id}/payments")
def record_payment(
    invoice_id: int,
    body:       PaymentBody,
    firm_id:    str = Depends(get_current_firm_id),
    user        = Depends(get_current_user),
):
    """Record a payment against an invoice."""
    with get_conn(firm_id) as conn:
        inv = conn.execute(
            "SELECT * FROM invoices WHERE id=%s AND firm_id=%s", (invoice_id, firm_id)
        ).fetchone()
        if not inv:
            raise HTTPException(404)
        inv = dict(inv)

        conn.execute("""
            INSERT INTO payments (firm_id, invoice_id, amount, payment_date, method, reference, notes, recorded_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (firm_id, invoice_id, body.amount,
              body.payment_date or date.today().isoformat(),
              body.method, body.reference, body.notes, user.get("id")))

        tax_rate = float(inv.get("tax_rate") or 0)
        _, _, total, balance = _recalc_totals(conn, invoice_id, tax_rate)

        # Auto-advance status
        new_status = None
        if balance <= 0:
            new_status = "paid"
        elif body.amount > 0:
            new_status = "partially_paid"

        if new_status:
            extra = ", paid_at=NOW()" if new_status == "paid" else ""
            conn.execute(
                f"UPDATE invoices SET status=%s{extra}, updated_at=NOW() WHERE id=%s",
                (new_status, invoice_id)
            )

    return {"ok": True, "balance_due": balance}


@router.get("/invoices/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    inline:     bool = False,
    firm_id:    str = Depends(get_current_firm_id),
    user        = Depends(get_current_user),
):
    """Generate and download invoice PDF."""
    with get_conn(firm_id) as conn:
        inv = conn.execute(
            "SELECT * FROM invoices WHERE id=%s AND firm_id=%s", (invoice_id, firm_id)
        ).fetchone()
        if not inv:
            raise HTTPException(404)
        items = conn.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=%s ORDER BY date ASC",
            (invoice_id,)
        ).fetchall()
        pays = conn.execute(
            "SELECT * FROM payments WHERE invoice_id=%s ORDER BY payment_date ASC",
            (invoice_id,)
        ).fetchall()

    inv_d   = _serialize(dict(inv))
    items_d = [_serialize(dict(i)) for i in items]
    pays_d  = [_serialize(dict(p)) for p in pays]

    try:
        pdf_bytes = build_invoice_pdf(inv_d, items_d, pays_d, firm_id)
    except Exception as e:
        import traceback
        log.error(f"[Billing] PDF build failed: {e}\n{traceback.format_exc()}")
        import logging; logging.getLogger(__name__).error(f"[billing_router] PDF generation error: {e}")
        raise HTTPException(500, "PDF generation failed. Please try again.")
    filename    = f"invoice_{inv_d['invoice_number']}.pdf"
    disposition = f'inline; filename="{filename}"' if inline else f'attachment; filename="{filename}"'
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition}
    )


@router.get("/dashboard")
def billing_dashboard(
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """Summary stats for billing dashboard."""
    with get_conn(firm_id) as conn:
        rows = conn.execute("""
            SELECT status, COUNT(*) AS n, COALESCE(SUM(total),0) AS total_amt,
                   COALESCE(SUM(balance_due),0) AS outstanding
            FROM invoices WHERE firm_id=%s
            GROUP BY status
        """, (firm_id,)).fetchall()

        overdue = conn.execute("""
            UPDATE invoices SET status='overdue', overdue_at=NOW(), updated_at=NOW()
            WHERE firm_id=%s AND status IN ('sent','viewed','partially_paid')
              AND due_date < CURRENT_DATE
            RETURNING id
        """, (firm_id,)).fetchall()

        rates = conn.execute("""
            SELECT br.*, u.email FROM billing_rates br
            LEFT JOIN users u ON u.id=br.user_id
            WHERE br.firm_id=%s
              AND br.effective_from <= CURRENT_DATE
              AND (br.effective_to IS NULL OR br.effective_to >= CURRENT_DATE)
            ORDER BY br.username
        """, (firm_id,)).fetchall()

    stats = {r["status"]: {"count": int(r["n"]), "total": float(r["total_amt"]), "outstanding": float(r["outstanding"])} for r in rows}
    return {
        "stats":          stats,
        "newly_overdue":  len(overdue),
        "billing_rates":  [_serialize(dict(r)) for r in rates],
    }


@router.post("/rates")
def set_billing_rate(
    body:    dict,
    firm_id: str = Depends(get_current_firm_id),
    user     = Depends(get_current_user),
):
    """Set billing rate for a user (proxies to time_router logic)."""
    if user.get("role") not in ("paraiq_super","admin","attorney"):
        raise HTTPException(403, "Insufficient permissions")
    with get_conn(firm_id) as conn:
        conn.execute("""
            INSERT INTO billing_rates
                (firm_id, user_id, username, role_type, hourly_rate, currency,
                 effective_from, effective_to, notes, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            firm_id, body["user_id"], body["username"], body.get("role_type","attorney"),
            body["hourly_rate"], body.get("currency","USD"),
            body.get("effective_from", date.today().isoformat()),
            body.get("effective_to"), body.get("notes"), user.get("id")
        ))
    return {"ok": True}

@router.get("/matter/{matter_id}/ledger")
def get_matter_ledger(
    matter_id: int,
    firm_id:   str = Depends(get_current_firm_id),
    user       = Depends(get_current_user),
):
    """Full billing ledger for a matter — all invoices, line items, payments, running balance."""
    with get_conn(firm_id) as conn:
        invoices = conn.execute("""
            SELECT * FROM invoices
            WHERE firm_id=%s AND matter_id=%s
            ORDER BY issue_date ASC, id ASC
        """, (firm_id, matter_id)).fetchall()

        result = []
        running_balance = 0.0
        total_billed    = 0.0
        total_paid      = 0.0

        for inv in invoices:
            inv_d = _serialize(dict(inv))
            items = conn.execute("""
                SELECT * FROM invoice_items
                WHERE invoice_id=%s ORDER BY date ASC, id ASC
            """, (inv_d["id"],)).fetchall()
            pays = conn.execute("""
                SELECT * FROM payments
                WHERE invoice_id=%s ORDER BY payment_date ASC
            """, (inv_d["id"],)).fetchall()

            inv_d["items"]    = [_serialize(dict(i)) for i in items]
            inv_d["payments"] = [_serialize(dict(p)) for p in pays]

            total_billed    += float(inv_d.get("total") or 0)
            total_paid      += float(inv_d.get("amount_paid") or 0)
            running_balance  = total_billed - total_paid
            inv_d["running_balance"] = round(running_balance, 2)

            result.append(inv_d)

        # Uncertified time entries not yet on any invoice
        unbilled = conn.execute("""
            SELECT te.* FROM time_entries te
            WHERE te.firm_id=%s AND te.matter_id=%s
              AND te.id NOT IN (
                  SELECT time_entry_id FROM invoice_items
                  WHERE time_entry_id IS NOT NULL AND firm_id=%s
              )
            ORDER BY te.date ASC
        """, (firm_id, matter_id, firm_id)).fetchall()

        unbilled_total = sum(float(e["billable_amount"] or 0) for e in unbilled)

    return {
        "invoices":        result,
        "invoice_count":   len(result),
        "total_billed":    round(total_billed, 2),
        "total_paid":      round(total_paid, 2),
        "balance_due":     round(running_balance, 2),
        "unbilled_entries": [_serialize(dict(e)) for e in unbilled],
        "unbilled_total":  round(unbilled_total, 2),
    }
