import os, io, subprocess, tempfile, logging
import json as _json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _BM

from backend.demo1.pg import get_conn

router = APIRouter(prefix="/media", tags=["Media Transcription"])
logger = logging.getLogger(__name__)

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR",
    str(Path(__file__).parent.parent.parent / "uploads" / "media")))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".aac"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm"}


def init_transcription_table():
    """No-op — table exists in Supabase Postgres."""
    print("[Media] Transcription table initialized ✓")


def get_client():
    from openai import OpenAI
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_audio_from_video(video_path: Path) -> Path:
    out = video_path.with_suffix(".extracted.mp3")
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ar", "16000", "-ac", "1", "-q:a", "4", str(out)
    ], capture_output=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr.decode()[:300]}")
    return out


def whisper_transcribe(audio_path: Path) -> dict:
    with open(audio_path, "rb") as f:
        response = get_client().audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )
    segments = []
    if hasattr(response, "segments") and response.segments:
        for s in response.segments:
            segments.append({
                "start": round(s.start, 2),
                "end":   round(s.end, 2),
                "text":  s.text.strip(),
            })
    return {
        "text":     response.text,
        "language": getattr(response, "language", "en"),
        "duration": round(getattr(response, "duration", 0), 2),
        "segments": segments,
    }


def save_transcription(filename, file_type, result, case_number,
                       firm_id: str = "default"):
    with get_conn(firm_id) as conn:
        cur = conn.execute("""
            INSERT INTO transcriptions
              (firm_id, filename, file_type, duration_s, case_number, language,
               transcript, segments, word_count, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            firm_id, filename, file_type,
            result.get("duration"), case_number,
            result.get("language"), result.get("text"),
            _json.dumps(result.get("segments", [])),
            len(result.get("text", "").split()),
            datetime.now(timezone.utc).isoformat(),
        ))
        return cur.fetchone()["id"]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/transcribe/audio")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    case_number: Optional[str] = Form(None)
):
    firm_id = getattr(request.state, "firm_id", "default")
    ext = Path(file.filename).suffix.lower()
    if ext not in AUDIO_EXTS:
        raise HTTPException(400, f"Unsupported audio format '{ext}'")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    save_path = MEDIA_DIR / f"{ts}_{file.filename}"
    save_path.write_bytes(data)

    try:
        result = whisper_transcribe(save_path)
    except Exception as e:
        logger.warning(f"[Media] audio transcription failed for {file.filename}: {e}")
        raise HTTPException(500, "Transcription failed")

    row_id = save_transcription(file.filename, "audio", result, case_number, firm_id)

    return {
        "success":     True,
        "id":          row_id,
        "filename":    file.filename,
        "file_type":   "audio",
        "language":    result["language"],
        "duration_s":  result["duration"],
        "word_count":  len(result["text"].split()),
        "transcript":  result["text"],
        "segments":    result["segments"],
        "case_number": case_number,
    }


@router.post("/transcribe/video")
async def transcribe_video(
    request: Request,
    file: UploadFile = File(...),
    case_number: Optional[str] = Form(None)
):
    firm_id = getattr(request.state, "firm_id", "default")
    ext = Path(file.filename).suffix.lower()
    if ext not in VIDEO_EXTS:
        raise HTTPException(400, f"Unsupported video format '{ext}'")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    video_path = MEDIA_DIR / f"{ts}_{file.filename}"
    video_path.write_bytes(data)

    try:
        audio_path = extract_audio_from_video(video_path)
    except Exception as e:
        logger.warning(f"[Media] audio extraction failed for {file.filename}: {e}")
        raise HTTPException(500, "Audio extraction failed")

    try:
        result = whisper_transcribe(audio_path)
    except Exception as e:
        logger.warning(f"[Media] video transcription failed for {file.filename}: {e}")
        raise HTTPException(500, "Transcription failed")
    finally:
        audio_path.unlink(missing_ok=True)

    row_id = save_transcription(file.filename, "video", result, case_number, firm_id)

    return {
        "success":     True,
        "id":          row_id,
        "filename":    file.filename,
        "file_type":   "video",
        "language":    result["language"],
        "duration_s":  result["duration"],
        "word_count":  len(result["text"].split()),
        "transcript":  result["text"],
        "segments":    result["segments"],
        "case_number": case_number,
    }


@router.get("/transcriptions")
def list_transcriptions(
    request: Request,
    case_number: Optional[str] = None,
    limit: int = 50
):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        if case_number:
            rows = conn.execute(
                """SELECT id,filename,file_type,duration_s,case_number,language,
                          word_count,created_at FROM transcriptions
                   WHERE firm_id=%s AND case_number=%s ORDER BY id DESC LIMIT %s""",
                (firm_id, case_number, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id,filename,file_type,duration_s,case_number,language,
                          word_count,created_at FROM transcriptions
                   WHERE firm_id=%s ORDER BY id DESC LIMIT %s""",
                (firm_id, limit)
            ).fetchall()
    return {"transcriptions": [dict(r) for r in rows], "total": len(rows)}


@router.get("/transcriptions/{tid}")
def get_transcription(tid: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM transcriptions WHERE id=%s AND firm_id=%s",
            (tid, firm_id)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Transcription not found")
    r = dict(row)
    try:
        r["segments"] = _json.loads(r["segments"] or "[]")
    except (_json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning(f"[Media] failed to parse segments for transcription {tid}: {e}")
        r["segments"] = []
    return r


@router.delete("/transcriptions/{tid}")
def delete_transcription(tid: int, request: Request):
    firm_id = getattr(request.state, "firm_id", "default")
    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT id FROM transcriptions WHERE id=%s AND firm_id=%s",
            (tid, firm_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Transcription not found")
        conn.execute(
            "DELETE FROM transcriptions WHERE id=%s AND firm_id=%s",
            (tid, firm_id)
        )
    return {"success": True}


@router.post("/transcribe/discovery/{file_id}")
async def transcribe_from_discovery(
    request: Request,
    file_id: int,
    case_number: Optional[str] = None
):
    """Transcribe a discovery file already on disk by its queue ID."""
    firm_id = getattr(request.state, "firm_id", "default")
    DISC_DIR = Path(os.environ.get("DISCOVERY_UPLOAD_DIR",
        str(Path(__file__).parent.parent.parent / "uploads" / "discovery")))

    with get_conn(firm_id) as conn:
        row = conn.execute(
            "SELECT * FROM discovery_files WHERE id=%s AND firm_id=%s",
            (file_id, firm_id)
        ).fetchone()

    if not row:
        raise HTTPException(404, f"Discovery file {file_id} not found")

    file_path = DISC_DIR / row["filename"]
    if not file_path.exists():
        raise HTTPException(404, f"File not found on disk: {row['filename']}")

    ext = file_path.suffix.lower()
    if ext not in AUDIO_EXTS:
        raise HTTPException(400, f"Not an audio file: {ext}")

    try:
        result = whisper_transcribe(file_path)
    except Exception as e:
        logger.warning(f"[Media] discovery transcription failed for {row['original_name']}: {e}")
        raise HTTPException(500, "Transcription failed")

    cn = case_number or row.get("case_number") or None
    row_id = save_transcription(row["original_name"], "audio", result, cn, firm_id)

    with get_conn(firm_id) as conn:
        conn.execute(
            "UPDATE discovery_files SET status='transcribed' WHERE id=%s AND firm_id=%s",
            (file_id, firm_id)
        )
        conn.execute(
            "UPDATE case_documents SET doc_text=%s WHERE document_name=%s AND firm_id=%s",
            (result["text"], row["original_name"], firm_id)
        )

    return {
        "success":      True,
        "id":           row_id,
        "discovery_id": file_id,
        "filename":     row["original_name"],
        "language":     result["language"],
        "duration_s":   result["duration"],
        "word_count":   len(result["text"].split()),
        "transcript":   result["text"],
        "case_number":  cn,
    }
