import os, io, sqlite3, subprocess, tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/media", tags=["Media Transcription"])

DB_PATH    = "/root/nlp-portfolio/backend/demo1/analyses.db"
MEDIA_DIR  = Path("/root/nlp-portfolio/uploads/media")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

def get_client():
    from openai import OpenAI
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)

AUDIO_EXTS = {".mp3",".wav",".m4a",".ogg",".flac",".webm",".aac"}
VIDEO_EXTS = {".mp4",".mov",".avi",".mkv",".wmv",".webm"}

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_transcription_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            filename      TEXT NOT NULL,
            file_type     TEXT NOT NULL,
            duration_s    REAL,
            case_number   TEXT,
            language      TEXT,
            transcript    TEXT,
            segments      TEXT,
            word_count    INTEGER,
            created_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_transcription_table()

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_audio_from_video(video_path: Path) -> Path:
    """Use ffmpeg to extract audio track as mp3."""
    out = video_path.with_suffix(".extracted.mp3")
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ar", "16000", "-ac", "1", "-q:a", "4",
        str(out)
    ], capture_output=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr.decode()[:300]}")
    return out

def whisper_transcribe(audio_path: Path) -> dict:
    """Send audio to OpenAI Whisper and return transcript + segments."""
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

import json as _json

def save_transcription(filename, file_type, result, case_number):
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO transcriptions
          (filename, file_type, duration_s, case_number, language,
           transcript, segments, word_count)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        filename, file_type,
        result.get("duration"), case_number,
        result.get("language"), result.get("text"),
        _json.dumps(result.get("segments",[])),
        len(result.get("text","").split())
    ))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/transcribe/audio")
async def transcribe_audio(
    file: UploadFile = File(...),
    case_number: Optional[str] = Form(None)
):
    ext = Path(file.filename).suffix.lower()
    if ext not in AUDIO_EXTS:
        raise HTTPException(400, f"Unsupported audio format '{ext}'. Supported: {', '.join(AUDIO_EXTS)}")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "Uploaded file is empty")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    save_path = MEDIA_DIR / f"{ts}_{file.filename}"
    save_path.write_bytes(data)

    try:
        result = whisper_transcribe(save_path)
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {str(e)}")

    row_id = save_transcription(file.filename, "audio", result, case_number)

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
    file: UploadFile = File(...),
    case_number: Optional[str] = Form(None)
):
    ext = Path(file.filename).suffix.lower()
    if ext not in VIDEO_EXTS:
        raise HTTPException(400, f"Unsupported video format '{ext}'. Supported: {', '.join(VIDEO_EXTS)}")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "Uploaded file is empty")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    video_path = MEDIA_DIR / f"{ts}_{file.filename}"
    video_path.write_bytes(data)

    try:
        audio_path = extract_audio_from_video(video_path)
    except Exception as e:
        raise HTTPException(500, f"Audio extraction failed: {str(e)}")

    try:
        result = whisper_transcribe(audio_path)
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {str(e)}")
    finally:
        audio_path.unlink(missing_ok=True)

    row_id = save_transcription(file.filename, "video", result, case_number)

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
def list_transcriptions(case_number: Optional[str] = None, limit: int = 50):
    conn = get_conn()
    if case_number:
        rows = conn.execute(
            "SELECT id,filename,file_type,duration_s,case_number,language,word_count,created_at FROM transcriptions WHERE case_number=? ORDER BY id DESC LIMIT ?",
            (case_number, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id,filename,file_type,duration_s,case_number,language,word_count,created_at FROM transcriptions ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return {"transcriptions": [dict(r) for r in rows], "total": len(rows)}

@router.get("/transcriptions/{tid}")
def get_transcription(tid: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM transcriptions WHERE id=?", (tid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Transcription not found")
    r = dict(row)
    try:
        r["segments"] = _json.loads(r["segments"] or "[]")
    except Exception:
        r["segments"] = []
    return r

@router.delete("/transcriptions/{tid}")
def delete_transcription(tid: int):
    conn = get_conn()
    conn.execute("DELETE FROM transcriptions WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    return {"success": True}


# ── Transcribe directly from discovery queue (no re-upload) ───────────────────
from pydantic import BaseModel as _BM

@router.post("/transcribe/discovery/{file_id}")
async def transcribe_from_discovery(file_id: int, case_number: Optional[str] = None):
    """Transcribe a discovery file already on disk by its queue ID."""
    import sqlite3 as _sq
    DISC_DIR = Path("/root/nlp-portfolio/uploads/discovery")

    # Look up file record
    try:
        con = _sq.connect("/root/nlp-portfolio/backend/demo1/analyses.db")
        con.row_factory = _sq.Row
        row = con.execute(
            "SELECT * FROM discovery_files WHERE id = ?", (file_id,)
        ).fetchone()
        con.close()
    except Exception as e:
        raise HTTPException(500, f"DB error: {e}")

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
        raise HTTPException(500, f"Transcription failed: {e}")

    # Save transcription record
    cn = case_number or row["case_number"] or None
    row_id = save_transcription(row["original_name"], "audio", result, cn)

    # Update discovery status + write transcript into case_documents
    try:
        con = _sq.connect("/root/nlp-portfolio/backend/demo1/analyses.db")
        con.execute(
            "UPDATE discovery_files SET status = 'transcribed' WHERE id = ?",
            (file_id,)
        )
        con.commit()
        con.close()
    except Exception:
        pass
    try:
        cases_con = _sq.connect("/root/nlp-portfolio/analyses.db")
        cases_con.execute(
            "UPDATE case_documents SET doc_text = ? WHERE document_name = ?",
            (result["text"], row["original_name"])
        )
        cases_con.commit()
        cases_con.close()
    except Exception:
        pass

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
