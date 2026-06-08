"""
backend/demo1/database.py  (Postgres version)
=============================================
Drop-in replacement for the original SQLite database.py.
Public API is identical — all callers in main.py continue to work unchanged.
"""

import json
from datetime import datetime
from backend.demo1.pg import get_conn


def init_db() -> None:
    """No-op — tables already exist in Supabase. Kept so main.py startup works."""
    pass


def save_analysis(text: str, result: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO analyses
                (created_at, text, word_count, sentiment, score, tone, entities, keywords, summary)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            datetime.utcnow().isoformat(),
            text[:500],
            len(text.split()),
            result.get("sentiment", {}).get("label", ""),
            result.get("sentiment", {}).get("score", 0.0),
            json.dumps(result.get("tone", [])),
            json.dumps(result.get("entities", [])),
            json.dumps(result.get("keywords", [])),
            result.get("summary", ""),
        ))
        row = cur.fetchone()
        return row["id"]


def save_feedback(analysis_id: int, text: str, predicted: str,
                  predicted_score: float, corrected: str,
                  feedback_type: str, notes: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO feedback
                (created_at, analysis_id, text, predicted, predicted_score,
                 corrected, feedback_type, reviewed, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s)
            RETURNING id
        """, (
            datetime.utcnow().isoformat(),
            analysis_id, text, predicted, predicted_score,
            corrected, feedback_type, notes,
        ))
        row = cur.fetchone()
        return row["id"]


def get_feedback_queue(reviewed: bool = False) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback WHERE reviewed = %s ORDER BY created_at DESC",
            (reviewed,)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_reviewed(feedback_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE feedback SET reviewed = TRUE WHERE id = %s", (feedback_id,))


def get_retraining_data() -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT text, corrected AS label FROM feedback
            WHERE corrected IS NOT NULL AND corrected != ''
            ORDER BY created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def query_analyses(sentiment=None, keyword=None, limit=20) -> list:
    sql = "SELECT * FROM analyses WHERE TRUE"
    params = []
    if sentiment:
        sql += " AND sentiment = %s"
        params.append(sentiment)
    if keyword:
        sql += " AND (text ILIKE %s OR keywords::text ILIKE %s)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        results.append({
            "id":         r["id"],
            "created_at": r["created_at"],
            "text":       r["text"][:100] + "..." if len(r["text"]) > 100 else r["text"],
            "word_count": r["word_count"],
            "sentiment":  r["sentiment"],
            "score":      r["score"],
            "tone":       r["tone"] if isinstance(r["tone"], list) else json.loads(r["tone"] or "[]"),
            "entities":   r["entities"] if isinstance(r["entities"], list) else json.loads(r["entities"] or "[]"),
            "keywords":   r["keywords"] if isinstance(r["keywords"], list) else json.loads(r["keywords"] or "[]"),
            "summary":    r["summary"],
        })
    return results


def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM analyses").fetchone()["n"]
        sentiment_rows = conn.execute("""
            SELECT sentiment, COUNT(*) AS count
            FROM analyses GROUP BY sentiment ORDER BY count DESC
        """).fetchall()
        agg = conn.execute(
            "SELECT AVG(score) AS avg_score, AVG(word_count) AS avg_words FROM analyses"
        ).fetchone()
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM feedback WHERE reviewed = FALSE"
        ).fetchone()["n"]

    return {
        "total_analyses":      total,
        "avg_sentiment_score": round(agg["avg_score"] or 0, 3),
        "avg_word_count":      round(agg["avg_words"] or 0, 1),
        "sentiment_breakdown": {r["sentiment"]: r["count"] for r in sentiment_rows},
        "pending_feedback":    pending,
    }
