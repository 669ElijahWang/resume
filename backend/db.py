import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .settings import DATA_DIR, DB_PATH, EXPORT_DIR, UPLOAD_DIR, DEFAULT_MODULES

DEFAULT_LABELS_ZH = {
    "SkillMatch": "技能匹配",
    "ProjectExperience": "项目经验",
    "YearsExperience": "工作年限",
    "Education": "教育背景",
    "Collaboration": "协作沟通",
    "Stability": "稳定性",
}


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


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _default_profile_modules() -> List[Dict[str, Any]]:
    if not DEFAULT_MODULES:
        return []
    weight = 1.0 / len(DEFAULT_MODULES)
    modules: List[Dict[str, Any]] = []
    for module in DEFAULT_MODULES:
        name = module.get("name", "")
        label = DEFAULT_LABELS_ZH.get(name, name)
        modules.append(
            {
                "name": name,
                "label": label,
                "desc": module.get("desc", ""),
                "weight": weight,
                "must_have": False,
                "threshold": None,
            }
        )
    total = sum(m["weight"] for m in modules)
    if modules and total != 1.0:
        modules[-1]["weight"] = modules[-1]["weight"] + (1.0 - total)
    return modules


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
        if not _table_has_column(conn, "jobs", "profile_id"):
            conn.execute("ALTER TABLE jobs ADD COLUMN profile_id TEXT")
        if not _table_has_column(conn, "jobs", "profile_json"):
            conn.execute("ALTER TABLE jobs ADD COLUMN profile_json TEXT")
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS score_profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version INTEGER NOT NULL,
                modules_json TEXT NOT NULL,
                rules_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_profile = conn.execute(
            "SELECT id FROM score_profiles LIMIT 1"
        ).fetchone()
        if not existing_profile:
            modules = _default_profile_modules()
            now = _now()
            conn.execute(
                """
                INSERT INTO score_profiles (
                    id, name, version, modules_json, rules_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "default",
                    "Default Profile",
                    1,
                    json.dumps(modules, ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    now,
                    now,
                ),
            )
        else:
            default_row = conn.execute(
                "SELECT id, name, modules_json FROM score_profiles WHERE id = ?",
                ("default",),
            ).fetchone()
            if default_row:
                needs_update = False
                new_name = default_row["name"]
                if new_name == "Default Profile":
                    new_name = "默认评分标准"
                    needs_update = True

                modules_raw = default_row["modules_json"]
                try:
                    modules = json.loads(modules_raw) if modules_raw else []
                except json.JSONDecodeError:
                    modules = []
                if isinstance(modules, list):
                    for module in modules:
                        if not isinstance(module, dict):
                            continue
                        name = (module.get("name") or "").strip()
                        if not name:
                            continue
                        label = module.get("label")
                        if not label or label == name:
                            mapped = DEFAULT_LABELS_ZH.get(name)
                            if mapped:
                                module["label"] = mapped
                                needs_update = True

                if needs_update:
                    conn.execute(
                        """
                        UPDATE score_profiles
                        SET name = ?, modules_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            new_name,
                            json.dumps(modules, ensure_ascii=False),
                            _now(),
                            "default",
                        ),
                    )


def create_job(
    job_id: str,
    jd_text: str,
    profile_id: Optional[str] = None,
    profile_json: Optional[str] = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, jd_text, profile_id, profile_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, jd_text, profile_id, profile_json, _now()),
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


def list_profiles() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM score_profiles ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM score_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        return dict(row) if row else None


def create_profile(
    profile_id: str,
    name: str,
    version: int,
    modules: List[Dict[str, Any]],
    rules: Optional[List[Dict[str, Any]]] = None,
) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO score_profiles (
                id, name, version, modules_json, rules_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                name,
                int(version),
                json.dumps(modules, ensure_ascii=False),
                json.dumps(rules or [], ensure_ascii=False),
                now,
                now,
            ),
        )


def update_profile(profile_id: str, fields: Dict[str, Any]) -> None:
    if not fields:
        return
    if "modules" in fields:
        fields["modules_json"] = json.dumps(
            fields.pop("modules"), ensure_ascii=False
        )
    if "rules" in fields:
        fields["rules_json"] = json.dumps(fields.pop("rules"), ensure_ascii=False)
    fields["updated_at"] = _now()
    columns = ", ".join([f"{key} = ?" for key in fields.keys()])
    values = list(fields.values()) + [profile_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE score_profiles SET {columns} WHERE id = ?",
            values,
        )


def delete_profile(profile_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM score_profiles WHERE id = ?", (profile_id,))


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
