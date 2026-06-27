from pathlib import Path
import os
import io, json, re as _re, logging
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import Response
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

from backend.demo1.pg import get_conn

router = APIRouter()
logger = logging.getLogger(__name__)


def base_styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("Firm",  fontName="Helvetica-Bold",    fontSize=16, textColor=colors.HexColor("#1e1b4b"), spaceAfter=4))
    s.add(ParagraphStyle("Sub",   fontName="Helvetica",         fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=2))
    s.add(ParagraphStyle("SHead", fontName="Helvetica-Bold",    fontSize=11, textColor=colors.HexColor("#7c3aed"), spaceBefore=14, spaceAfter=4))
    s.add(ParagraphStyle("Body",  fontName="Helvetica",         fontSize=10, textColor=colors.HexColor("#1e293b"), leading=15, spaceAfter=6))
    s.add(ParagraphStyle("Conf",  fontName="Helvetica-Oblique", fontSize=8,  textColor=colors.HexColor("#94a3b8"), spaceAfter=4))
    s.add(ParagraphStyle("TH",    fontName="Helvetica-Bold",    fontSize=9,  textColor=colors.white))
    s.add(ParagraphStyle("TD",    fontName="Helvetica",         fontSize=9,  textColor=colors.HexColor("#1e293b")))
    return s


def header_block(story, s, title, subtitle, case_number, date_str):
    story.append(Paragraph("PARAIQ LEGAL INTELLIGENCE", s["Firm"]))
    story.append(Paragraph("Confidential Attorney Work Product", s["Conf"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#7c3aed")))
    story.append(Spacer(1, 8))
    story.append(Paragraph(title, s["SHead"]))
    story.append(Paragraph(f"{subtitle}  |  Case: {case_number}  |  {date_str}", s["Sub"]))
    story.append(Spacer(1, 10))


# ── 1. CLIENT SUMMARY LETTER ──────────────────────────────────────────────────

@router.get("/client-letter/{case_id}")
def export_client_letter(case_id: int, request: Request):
    from backend.demo1.main import claude_with_retry, client, LLM_STRONG
    firm_id = getattr(request.state, "firm_id", "default")

    with get_conn(firm_id) as conn:
        case = conn.execute(
            "SELECT * FROM cases WHERE id=%s AND firm_id=%s AND deleted=FALSE",
            (case_id, firm_id)
        ).fetchone()
        if not case:
            return Response(b"Case not found", status_code=404)
        case = dict(case)

        docs = conn.execute(
            "SELECT document_name, summary, upload_date FROM case_documents WHERE case_id=%s AND firm_id=%s",
            (case_id, firm_id)
        ).fetchall()
        notes = conn.execute(
            "SELECT note FROM case_notes WHERE case_id=%s AND firm_id=%s ORDER BY created_at DESC LIMIT 5",
            (case_id, firm_id)
        ).fetchall()

    doc_summaries = "\n".join(
        [f"- {d['document_name']}: {d['summary'] or 'No summary'}" for d in docs]
    ) or "No documents linked."
    notes_text = "\n".join([r["note"] for r in notes]) or "No notes."

    prompt = f"""Write a professional client update letter for a law firm. Use formal legal letter format.

Case: {case["case_number"]} | Client: {case["client_name"]}
Court: {case.get("court") or "TBD"} | Status: {case["status"]} | Filed: {case.get("filing_date") or "TBD"}
Description: {case.get("description") or "N/A"}

Documents on file:
{doc_summaries}

Attorney notes:
{notes_text}

Write a 3-4 paragraph client letter that:
1. Opens with current case status
2. Summarizes recent activity and documents reviewed
3. States next steps clearly
4. Closes professionally

Use formal legal tone. Address client by name from the case title. Sign as "ParaIQ Legal Team"."""

    resp = claude_with_retry(
        client.messages.create,
        model=LLM_STRONG,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
        firm_id=firm_id,
    )
    letter_text = resp.content[0].text

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=inch, rightMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    s = base_styles()
    story = []
    today = datetime.now().strftime("%B %d, %Y")
    header_block(story, s, "Client Status Letter", "Privileged & Confidential",
                 case["case_number"], today)

    clean = letter_text
    clean = _re.sub(r"\*\*(.+?)\*\*", r"\1", clean)
    clean = _re.sub(r"\*(.+?)\*",      r"\1", clean)
    clean = _re.sub(r"^---+$",          "",    clean, flags=_re.MULTILINE)
    clean = _re.sub(r"^#{1,3}\s*",     "",    clean, flags=_re.MULTILINE)

    for para in clean.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        lines = [l.strip() for l in para.split("\n") if l.strip()]
        story.append(Paragraph("<br/>".join(lines), s["Body"]))
        story.append(Spacer(1, 4))

    doc.build(story)
    buf.seek(0)
    filename = f"client_letter_{case['case_number'].replace('/','_')}.pdf"
    return Response(buf.read(), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


# ── 2. PRIVILEGE LOG PDF ──────────────────────────────────────────────────────

@router.get("/privilege-log/{case_id}")
def export_privilege_log(case_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")

    with get_conn(firm_id) as conn:
        case = conn.execute(
            "SELECT * FROM cases WHERE id=%s AND firm_id=%s AND deleted=FALSE",
            (case_id, firm_id)
        ).fetchone()
        if not case:
            return Response(b"Case not found", status_code=404)
        case = dict(case)

        docs = conn.execute(
            """SELECT document_name, upload_date, source, sentiment, entities_json
               FROM case_documents WHERE case_id=%s AND firm_id=%s ORDER BY upload_date ASC""",
            (case_id, firm_id)
        ).fetchall()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=inch, bottomMargin=inch)
    s = base_styles()
    story = []
    today = datetime.now().strftime("%B %d, %Y")
    header_block(story, s, "Privilege Log", "Attorney-Client Privilege / Work Product",
                 case["case_number"], today)
    story.append(Paragraph(
        f"Prepared by counsel for {case['client_name']} in connection with {case['case_number']}. "
        "All documents listed herein are withheld from production on the grounds stated.",
        s["Body"]))
    story.append(Spacer(1, 10))

    headers = ["#", "Document", "Date", "Source", "Privilege Basis", "Privilege Holder"]
    rows = []
    for i, d in enumerate(docs, 1):
        rows.append([
            str(i),
            Paragraph(d["document_name"][:50], s["TD"]),
            (d["upload_date"] or "")[:10],
            d["source"] or "uploaded",
            "Attorney-Client / Work Product",
            case["client_name"]
        ])

    col_w = [0.3*inch, 2.2*inch, 0.8*inch, 0.8*inch, 1.8*inch, 1.3*inch]
    tbl = Table([headers] + rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  colors.HexColor("#1e1b4b")),
        ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0),  8),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"Total documents withheld: {len(docs)}  |  Log prepared: {today}  |  "
        "This log is itself privileged and protected from disclosure.",
        s["Conf"]))
    doc.build(story)
    buf.seek(0)
    filename = f"privilege_log_{case['case_number'].replace('/','_')}.pdf"
    return Response(buf.read(), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


# ── 3. TIMELINE PDF ───────────────────────────────────────────────────────────

@router.get("/timeline/{case_id}")
def export_timeline_pdf(case_id: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")

    with get_conn(firm_id) as conn:
        case = conn.execute(
            "SELECT * FROM cases WHERE id=%s AND firm_id=%s AND deleted=FALSE",
            (case_id, firm_id)
        ).fetchone()
        if not case:
            return Response(b"Case not found", status_code=404)
        case = dict(case)

        docs = conn.execute(
            "SELECT document_name, events_json, upload_date FROM case_documents WHERE case_id=%s AND firm_id=%s",
            (case_id, firm_id)
        ).fetchall()

    events = []
    if case.get("filing_date"):
        events.append({"date": case["filing_date"][:10], "event": "Case filed", "source": "Case Record"})

    for d in docs:
        if d["events_json"]:
            try:
                for ev in json.loads(d["events_json"]):
                    ev["source"] = d["document_name"]
                    events.append(ev)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.warning(f"[MatterExports] failed to parse events_json for {d.get('document_name','?')}: {e}")

    events.sort(key=lambda x: (x.get("date") or x.get("event_date") or "0000")[:10])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=inch, bottomMargin=inch)
    s = base_styles()
    story = []
    today = datetime.now().strftime("%B %d, %Y")
    header_block(story, s, "Case Timeline", "Chronological Event Summary",
                 case["case_number"], today)

    if not events:
        story.append(Paragraph(
            "No timeline events extracted. Use AI Timeline Extraction to populate.", s["Body"]))
    else:
        headers = ["Date", "Event", "Source Document"]
        rows = []
        for ev in events:
            date_val   = (ev.get("date") or ev.get("event_date") or "Unknown")[:10]
            event_text = ev.get("event") or ev.get("title") or ev.get("description") or "Event"
            source     = ev.get("source", "")
            rows.append([date_val,
                         Paragraph(event_text[:120], s["TD"]),
                         Paragraph(source[:40], s["TD"])])

        col_w = [0.9*inch, 4.0*inch, 2.3*inch]
        tbl = Table([headers] + rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  colors.HexColor("#1e1b4b")),
            ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
            ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,0),  9),
            ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE",      (0,1), (-1,-1), 9),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#f8fafc"), colors.white]),
            ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Total events: {len(events)}  |  Exported: {today}", s["Conf"]))

    doc.build(story)
    buf.seek(0)
    filename = f"timeline_{case['case_number'].replace('/','_')}.pdf"
    return Response(buf.read(), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})
