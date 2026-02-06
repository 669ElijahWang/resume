import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .settings import DATA_DIR, DB_PATH, EXPORT_DIR, UPLOAD_DIR


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_dirs()
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                jd_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resumes (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                name TEXT,
                phone TEXT,
                email TEXT,
                total_score REAL,
                modules_json TEXT,
                summary TEXT,
                raw_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_resumes_job_id ON resumes(job_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_resumes_status ON resumes(status)"
        )


def create_job(job_id: str, jd_text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, jd_text, created_at) VALUES (?, ?, ?)",
            (job_id, jd_text, _now()),
        )


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def create_resume(
    resume_id: str, job_id: str, file_name: str, file_path: str, status: str
) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO resumes (
                id, job_id, file_name, file_path, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (resume_id, job_id, file_name, file_path, status, now, now),
        )


def update_resume(resume_id: str, fields: Dict[str, Any]) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    columns = ", ".join([f"{key} = ?" for key in fields.keys()])
    values = list(fields.values()) + [resume_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE resumes SET {columns} WHERE id = ?",
            values,
        )


def get_resume(resume_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        return dict(row) if row else None


def list_resumes(job_id: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM resumes WHERE job_id = ?", (job_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def count_resumes(job_id: str) -> Dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(1) as cnt
            FROM resumes
            WHERE job_id = ?
            GROUP BY status
            """,
            (job_id,),
        ).fetchall()
        counts = {row["status"]: row["cnt"] for row in rows}
        total = conn.execute(
            "SELECT COUNT(1) as cnt FROM resumes WHERE job_id = ?", (job_id,)
        ).fetchone()["cnt"]
        counts["total"] = total
        return counts


def loads_modules(raw: Optional[str]) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
