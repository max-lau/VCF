"""
attachment_handler.py
Vault-first attachment processing pipeline:
  1. Save to quarantine
  2. Validate file type (whitelist)
  3. Virus scan (ClamAV)
  4. Unzip one level (if zip)
  5. Move cleared files to cleared/
  6. Write records into case_documents
"""
import os, uuid, shutil, subprocess, zipfile, logging, json
from pathlib import Path
from typing import Optional

import magic

logger = logging.getLogger(__name__)

QUARANTINE = Path("/root/nlp-portfolio/uploads/email_attachments/quarantine")
CLEARED    = Path("/root/nlp-portfolio/uploads/email_attachments/cleared")

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
    try:
        return magic.from_file(str(path), mime=True)
    except Exception:
        return "application/octet-stream"


def _virus_scan(path: Path) -> tuple[bool, str]:
    """Returns (is_clean, detail). Treats scan errors as unclean."""
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
    except Exception as e:
        return False, f"scan exception: {e}"


def _process_single_file(src: Path, original_name: str) -> dict:
    """Validate + scan one file already in quarantine. Returns status dict."""
    result = {
        "original_name": original_name,
        "path": str(src),
        "status": "rejected",
        "reason": None,
        "cleared_path": None,
        "mime": None,
        "size_kb": round(src.stat().st_size / 1024, 1),
    }

    # Extension check — block double extensions like invoice.pdf.exe
    name_parts = original_name.split(".")
    if len(name_parts) > 2:
        ext1 = "." + name_parts[-2].lower()
        ext2 = "." + name_parts[-1].lower()
        if ext1 in ALLOWED_EXTENSIONS and ext2 not in ALLOWED_EXTENSIONS:
            result["reason"] = f"double extension blocked: {original_name}"
            return result

    if _ext(original_name) not in ALLOWED_EXTENSIONS:
        result["reason"] = f"file type not allowed: {_ext(original_name)}"
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

    # Move to cleared
    cleared_path = CLEARED / src.name
    shutil.move(str(src), str(cleared_path))
    result["status"]       = "clean"
    result["cleared_path"] = str(cleared_path)
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
    Writes cleared files into case_documents.
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
    total_mb = sum(len(a["data"]) for a in attachments) / (1024 * 1024)
    if total_mb > MAX_TOTAL_MB:
        summary["manual_review"] = True
        logger.warning(f"[Vault] {intake_id}: total size {total_mb:.1f}MB exceeds limit")
        return summary

    files_to_process = []

    # Stage all files into quarantine first
    for att in attachments:
        filename = att.get("filename") or "attachment"
        data     = att.get("data", b"")
        safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
        q_path    = QUARANTINE / safe_name
        q_path.write_bytes(data)
        files_to_process.append((q_path, filename))

    # Expand zips one level
    expanded = []
    for q_path, original_name in files_to_process:
        if _ext(original_name) == ".zip":
            zip_results = _expand_zip(q_path, original_name)
            expanded.extend(zip_results)
            # Remove the zip itself from quarantine after expansion
            try:
                q_path.unlink()
            except Exception:
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
            # Clean up rejected file from quarantine
            try:
                q_path.unlink()
            except Exception:
                pass

    # Write cleared files into case_documents
    if case_id and cleared_files:
        for f in cleared_files:
            try:
                conn.execute("""
                    INSERT INTO case_documents
                        (firm_id, case_id, document_name, source, source_type,
                         source_ref, upload_date)
                    VALUES (%s, %s, %s, 'email', 'email_attachment', %s, NOW())
                    ON CONFLICT DO NOTHING
                """, (
                    firm_id,
                    case_id,
                    f"Attachment: {f['original_name']}",
                    intake_id,
                ))
                logger.info(f"[Vault] Linked to case {case_id}: {f['original_name']}")
            except Exception as e:
                logger.error(f"[Vault] DB insert failed for {f['original_name']}: {e}")

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

            # Zip bomb: too many files
            if len(members) > MAX_ZIP_FILES:
                logger.warning(f"[Vault] Zip {original_name} has {len(members)} files — rejected")
                return []

            # Zip bomb: total uncompressed size
            total_uncompressed = sum(m.file_size for m in members)
            if total_uncompressed > MAX_ZIP_MB * 1024 * 1024:
                logger.warning(f"[Vault] Zip {original_name} uncompressed size too large — rejected")
                return []

            for member in members:
                inner_name = Path(member.filename).name  # strip any path traversal
                safe_name  = f"{uuid.uuid4().hex}_{inner_name}"
                out_path   = QUARANTINE / safe_name
                out_path.write_bytes(zf.read(member.filename))
                results.append((out_path, inner_name))

    except zipfile.BadZipFile:
        logger.warning(f"[Vault] {original_name} is not a valid zip file")
    except Exception as e:
        logger.error(f"[Vault] Zip expansion error for {original_name}: {e}")

    return results
