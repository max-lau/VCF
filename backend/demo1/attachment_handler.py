"""
attachment_handler.py  (ACP-VCF revision)
=========================================
Vault-first attachment processing pipeline for email intake.

Changes vs. ParaIQ original
  1. Uses the real case_documents schema (no source_type/source_ref columns).
  2. Uploads cleared attachments to Supabase storage so they are viewable
     in the case binder.
  3. Computes SHA-256 content_hash so duplicate email attachments are caught
     by the same duplicate-prevention logic as intake scans.
  4. Virus scan and MIME detection are best-effort: on Windows/dev machines
     without ClamAV/libmagic they warn and continue instead of quarantining
     every legitimate medical PDF.
  5. Unmatched attachments (no case identified) are still written to
     case_documents with match_status='unmatched' so the Document Inbox
     can route them manually.
"""
import os
import uuid
import shutil
import subprocess
import zipfile
import logging
import json
import hashlib
import mimetypes
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# python-magic requires libmagic, which is often missing on Windows.
try:
    import magic
    _MAGIC_AVAILABLE = True
except Exception:
    magic = None
    _MAGIC_AVAILABLE = False

BASE_DIR = Path(__file__).parent.parent.parent
QUARANTINE = Path(os.environ.get(
    "QUARANTINE_DIR",
    str(BASE_DIR / "uploads" / "email_attachments" / "quarantine")
))
CLEARED = Path(os.environ.get(
    "CLEARED_DIR",
    str(BASE_DIR / "uploads" / "email_attachments" / "cleared")
))

STRICT_VIRUS_SCAN = os.getenv("ATTACHMENT_STRICT_VIRUS_SCAN", "false").lower() == "true"
EMAIL_OCR_ENABLED = os.getenv("EMAIL_OCR_ENABLED", "true").lower() != "false"

# Allowed MIME types
ALLOWED_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "message/rfc822",       # .eml
    "application/zip",      # handled specially
}

ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".csv", ".txt", ".png", ".jpg", ".jpeg",
    ".tiff", ".tif", ".eml", ".msg",
}

MAX_SINGLE_MB  = 25
MAX_TOTAL_MB   = 50
MAX_ATTACH     = 10
MAX_ZIP_FILES  = 10
MAX_ZIP_MB     = 50


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _safe_mime(path: Path) -> str:
    """Best-effort MIME detection. Falls back to mimetypes if python-magic
    is unavailable or fails."""
    if _MAGIC_AVAILABLE:
        try:
            return magic.from_file(str(path), mime=True)
        except (OSError, ValueError) as e:
            logger.warning(f"[Vault] magic.from_file failed for {path}: {e}")
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _virus_scan(path: Path) -> tuple[bool, str]:
    """Returns (is_clean, detail). Missing ClamAV is treated as clean in dev,
    configurable via ATTACHMENT_STRICT_VIRUS_SCAN=true."""
    if not shutil.which("clamscan"):
        msg = "clamscan not installed"
        if STRICT_VIRUS_SCAN:
            return False, msg
        logger.warning(f"[Vault] {msg}; skipping virus scan for {path.name}")
        return True, "skipped (clamscan unavailable)"

    try:
        result = subprocess.run(
            ["clamscan", "--no-summary", "-i", str(path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, "clean"
        elif result.returncode == 1:
            return False, result.stdout.strip() or "virus detected"
        else:
            return False, f"scan error: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "scan timeout"
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        return False, f"scan exception: {e}"


def _content_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _upload_to_storage(
    data: bytes,
    firm_id: str,
    case_id: Optional[int],
    ext: str,
) -> Optional[str]:
    """Upload bytes to Supabase storage. Returns the storage path or None."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        logger.warning("[Vault] SUPABASE_URL or SUPABASE_SERVICE_KEY not set; skipping upload")
        return None

    try:
        from supabase import create_client
        supabase = create_client(supabase_url, supabase_key)
        storage_path = (
            f"{firm_id}/cases/{case_id}/email/{uuid.uuid4().hex}.{ext}"
            if case_id else
            f"{firm_id}/email/unmatched/{uuid.uuid4().hex}.{ext}"
        )
        supabase.storage.from_("vcf-documents").upload(
            path=storage_path,
            file=data,
            file_options={"content-type": mimetypes.guess_type(f"file{ext}")[0] or "application/octet-stream"}
        )
        return storage_path
    except Exception as e:
        logger.warning(f"[Vault] Supabase upload failed: {e}")
        return None


def _infer_doc_type(filename: str) -> str:
    ext = _ext(filename)
    return {
        ".pdf": "pdf",
        ".doc": "word",
        ".docx": "word",
        ".xls": "spreadsheet",
        ".xlsx": "spreadsheet",
        ".csv": "spreadsheet",
        ".txt": "text",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".tif": "image",
        ".eml": "email",
        ".msg": "email",
    }.get(ext, "other")


def _mime_type_from_ext(filename: str) -> str:
    ext = _ext(filename)
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }.get(ext, "application/octet-stream")


def _process_single_file(src: Path, original_name: str) -> dict:
    """Validate + scan one file already in quarantine. Returns status dict."""
    result = {
        "original_name": original_name,
        "path": str(src),
        "status": "rejected",
        "reason": None,
        "cleared_path": None,
        "file_url": None,
        "mime": None,
        "size_kb": round(src.stat().st_size / 1024, 1),
        "content_hash": None,
    }

    # Extension check — block double extensions like invoice.pdf.exe
    name_parts = original_name.split(".")
    if len(name_parts) > 2:
        ext1 = "." + name_parts[-2].lower()
        ext2 = "." + name_parts[-1].lower()
        if ext1 in ALLOWED_EXTENSIONS and ext2 not in ALLOWED_EXTENSIONS:
            result["reason"] = f"double extension blocked: {original_name}"
            return result

    ext = _ext(original_name)
    if ext not in ALLOWED_EXTENSIONS:
        result["reason"] = f"file type not allowed: {ext}"
        return result

    # Size check
    size_mb = src.stat().st_size / (1024 * 1024)
    if size_mb > MAX_SINGLE_MB:
        result["reason"] = f"file too large: {size_mb:.1f}MB (max {MAX_SINGLE_MB}MB)"
        return result

    # MIME check
    mime = _safe_mime(src)
    result["mime"] = mime
    if mime not in ALLOWED_MIMES and not mime.startswith("text/"):
        result["reason"] = f"MIME type not allowed: {mime}"
        return result

    # Virus scan
    is_clean, detail = _virus_scan(src)
    if not is_clean:
        result["reason"] = f"virus scan failed: {detail}"
        result["status"] = "quarantined"
        return result

    # Compute hash
    result["content_hash"] = _content_hash(src)

    # Move to cleared
    cleared_path = CLEARED / src.name
    shutil.move(str(src), str(cleared_path))
    result["status"] = "clean"
    result["cleared_path"] = str(cleared_path)
    return result


def _run_ocr_on_attachment(
    firm_id: str,
    doc_id: int,
    filename: str,
    file_bytes: bytes,
    initial_case_id: Optional[int],
    content_hash: str,
    conn,
) -> dict:
    """Run OCR on an email attachment and auto-link it to a case by identity.

    OCR failures are logged and swallowed so the document stays in the inbox.
    Returns a small status dict for debugging/metrics.
    """
    from backend.demo1.ocr_intake import (
        extract_text, clean_ocr_text, extract_form_fields,
        pdf_to_image_pages, _extract_identity_signals, find_case_by_identity,
    )

    result = {
        "ocr_done": False,
        "case_id": initial_case_id,
        "match_status": "matched" if initial_case_id else "unmatched",
        "match_reason": None,
        "error": None,
    }
    try:
        mime = _mime_type_from_ext(filename)
        if mime == "application/pdf":
            pages = pdf_to_image_pages(file_bytes)
        elif mime.startswith("image/"):
            pages = file_bytes
        else:
            logger.info(f"[Vault OCR] Skipping OCR for non-image/PDF attachment: {filename}")
            return result

        ocr_result = extract_text(pages, lang="eng", engine="auto",
                                  mime_type=mime, firm_id=firm_id)
        text = clean_ocr_text(ocr_result.get("text", ""))
        form_fields = ocr_result.get("form_fields") or extract_form_fields(text)
        signals = _extract_identity_signals(form_fields)

        matched_case_id = initial_case_id
        match_status = "matched" if initial_case_id else "unmatched"
        match_reason = "provided_case_id" if initial_case_id else None

        if not matched_case_id and signals.get("name"):
            found_case_id, found_status, found_reason = find_case_by_identity(firm_id, signals)
            if found_case_id:
                matched_case_id = found_case_id
                match_status = found_status or "matched"
                match_reason = found_reason

        summary = ""
        key_facts = form_fields.get("key_facts") or []
        if key_facts:
            summary = " ".join(str(k) for k in key_facts)[:1000]
        elif text:
            summary = text[:1000]

        doc_type = _infer_doc_type(filename)
        if form_fields.get("doc_type") and form_fields["doc_type"] != "other":
            doc_type = form_fields["doc_type"]

        identity_signals = {k: v for k, v in signals.items() if v}

        conn.execute("""
            UPDATE case_documents
               SET case_id = COALESCE(%s, case_id),
                   doc_text = %s,
                   summary = %s,
                   doc_type = %s,
                   identity_signals = %s,
                   match_status = %s,
                   updated_at = NOW()
             WHERE id = %s AND firm_id = %s
        """, (
            matched_case_id, text, summary, doc_type,
            json.dumps(identity_signals), match_status, doc_id, firm_id,
        ))

        if matched_case_id and match_reason:
            reason_text = f"Email attachment {filename} auto-linked to case via {match_reason}"
            conn.execute("""
                INSERT INTO case_notes (firm_id, case_id, note)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (firm_id, matched_case_id, reason_text))

        result["ocr_done"] = True
        result["case_id"] = matched_case_id
        result["match_status"] = match_status
        result["match_reason"] = match_reason
        logger.info(f"[Vault OCR] Processed attachment id={doc_id} case={matched_case_id} status={match_status}")
    except Exception as e:
        logger.warning(f"[Vault OCR] OCR failed for attachment {filename} (doc_id={doc_id}): {e}")
        result["error"] = str(e)
    return result


def process_attachments(
    attachments: list[dict],   # [{"filename": str, "data": bytes}]
    firm_id: str,
    case_id: Optional[int],
    intake_id: str,
    conn,                      # pg connection
) -> dict:
    """
    Full vault pipeline. Returns summary dict with per-file results.
    Writes cleared files into case_documents and uploads them to Supabase.
    """
    summary = {
        "total": len(attachments),
        "clean": 0,
        "rejected": 0,
        "quarantined": 0,
        "manual_review": False,
        "files": [],
    }

    if not attachments:
        return summary

    # Count gate
    if len(attachments) > MAX_ATTACH:
        summary["manual_review"] = True
        logger.warning(f"[Vault] {intake_id}: {len(attachments)} attachments — held for manual review")
        return summary

    # Total size gate
    total_mb = sum(len(a.get("data", b"")) for a in attachments) / (1024 * 1024)
    if total_mb > MAX_TOTAL_MB:
        summary["manual_review"] = True
        logger.warning(f"[Vault] {intake_id}: total size {total_mb:.1f}MB exceeds limit")
        return summary

    files_to_process = []

    # Stage all files into quarantine first
    for att in attachments:
        filename = att.get("filename") or "attachment"
        data = att.get("data", b"")
        safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
        q_path = QUARANTINE / safe_name
        q_path.write_bytes(data)
        files_to_process.append((q_path, filename))

    # Expand zips one level
    expanded = []
    for q_path, original_name in files_to_process:
        if _ext(original_name) == ".zip":
            zip_results = _expand_zip(q_path, original_name)
            expanded.extend(zip_results)
            try:
                q_path.unlink()
            except (OSError, PermissionError):
                pass
        else:
            expanded.append((q_path, original_name))

    # Process each file
    cleared_files = []
    for q_path, original_name in expanded:
        if not q_path.exists():
            continue
        result = _process_single_file(q_path, original_name)
        summary["files"].append(result)
        if result["status"] == "clean":
            summary["clean"] += 1
            cleared_files.append(result)
        elif result["status"] == "quarantined":
            summary["quarantined"] += 1
            logger.error(f"[Vault] VIRUS detected: {original_name} — {result['reason']}")
        else:
            summary["rejected"] += 1
            logger.warning(f"[Vault] Rejected: {original_name} — {result['reason']}")
            try:
                q_path.unlink()
            except (OSError, PermissionError):
                pass

    # Upload cleared files and write case_documents rows
    for f in cleared_files:
        try:
            ext = _ext(f["original_name"])
            with open(f["cleared_path"], "rb") as fh:
                file_bytes = fh.read()
            file_url = _upload_to_storage(file_bytes, firm_id, case_id, ext)
            f["file_url"] = file_url

            cur = conn.execute("""
                INSERT INTO case_documents
                    (firm_id, case_id, document_name, source, doc_text,
                     summary, doc_type, language, upload_date, file_url,
                     identity_signals, match_status, content_hash)
                VALUES (%s, %s, %s, 'email_attachment', '', '', %s, 'en',
                        NOW(), %s, '{}', %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
            """, (
                firm_id,
                case_id,
                f"Attachment: {f['original_name']}",
                _infer_doc_type(f["original_name"]),
                file_url,
                "matched" if case_id else "unmatched",
                f["content_hash"],
            ))
            row = cur.fetchone()
            doc_id = row["id"] if row else None
            logger.info(f"[Vault] Linked to case {case_id or 'unmatched'}: {f['original_name']} doc_id={doc_id}")

            if doc_id and EMAIL_OCR_ENABLED:
                ocr_status = _run_ocr_on_attachment(
                    firm_id, doc_id, f["original_name"], file_bytes,
                    case_id, f["content_hash"], conn
                )
                f["ocr"] = ocr_status
        except Exception as e:
            logger.error(f"[Vault] DB insert/OCR failed for {f['original_name']}: {e}")

    logger.info(
        f"[Vault] {intake_id}: {summary['clean']} clean, "
        f"{summary['rejected']} rejected, {summary['quarantined']} quarantined"
    )
    return summary


def _expand_zip(zip_path: Path, original_name: str) -> list[tuple[Path, str]]:
    """Expand zip one level. Returns list of (quarantine_path, original_name)."""
    results = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]

            if len(members) > MAX_ZIP_FILES:
                logger.warning(f"[Vault] Zip {original_name} has {len(members)} files — rejected")
                return []

            total_uncompressed = sum(m.file_size for m in members)
            if total_uncompressed > MAX_ZIP_MB * 1024 * 1024:
                logger.warning(f"[Vault] Zip {original_name} uncompressed size too large — rejected")
                return []

            for member in members:
                inner_name = Path(member.filename).name
                safe_name = f"{uuid.uuid4().hex}_{inner_name}"
                out_path = QUARANTINE / safe_name
                out_path.write_bytes(zf.read(member.filename))
                results.append((out_path, inner_name))

    except zipfile.BadZipFile:
        logger.warning(f"[Vault] {original_name} is not a valid zip file")
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as e:
        logger.error(f"[Vault] Zip expansion error for {original_name}: {e}")

    return results
