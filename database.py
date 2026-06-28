import sqlite3
from datetime import datetime, timezone
import json
from config import DATABASE_PATH

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            content_id TEXT PRIMARY KEY,
            creator_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            text TEXT NOT NULL,
            attribution TEXT NOT NULL,
            confidence REAL NOT NULL,
            llm_score REAL NOT NULL,
            stylometric_score REAL,
            status TEXT NOT NULL DEFAULT 'classified',
            appeal_reasoning TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_submission(content_id, creator_id, text, attribution, confidence, llm_score, stylometric_score=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    cursor.execute("""
        INSERT INTO audit_log (
            content_id, creator_id, timestamp, text, attribution, confidence, llm_score, stylometric_score, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'classified')
    """, (content_id, creator_id, timestamp, text, attribution, confidence, llm_score, stylometric_score))
    conn.commit()
    conn.close()

def get_all_logs(limit=50):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT content_id, creator_id, timestamp, attribution, confidence, llm_score, stylometric_score, status, appeal_reasoning
        FROM audit_log
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    entries = []
    for r in rows:
        entries.append({
            "content_id": r["content_id"],
            "creator_id": r["creator_id"],
            "timestamp": r["timestamp"],
            "attribution": r["attribution"],
            "confidence": r["confidence"],
            "llm_score": r["llm_score"],
            "stylometric_score": r["stylometric_score"],
            "status": r["status"],
            "appeal_reasoning": r["appeal_reasoning"]
        })
    return entries

def get_log_by_id(content_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT content_id, creator_id, timestamp, attribution, confidence, llm_score, stylometric_score, status, appeal_reasoning
        FROM audit_log
        WHERE content_id = ?
    """, (content_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "content_id": row["content_id"],
            "creator_id": row["creator_id"],
            "timestamp": row["timestamp"],
            "attribution": row["attribution"],
            "confidence": row["confidence"],
            "llm_score": row["llm_score"],
            "stylometric_score": row["stylometric_score"],
            "status": row["status"],
            "appeal_reasoning": row["appeal_reasoning"]
        }
    return None

def submit_appeal(content_id, reasoning):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE audit_log
        SET status = 'under_review', appeal_reasoning = ?
        WHERE content_id = ?
    """, (reasoning, content_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0
