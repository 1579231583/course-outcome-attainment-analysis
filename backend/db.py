"""课程目标达成度分析系统 — 三层清晰数据模型（SQLite 持久化）

彻底理顺高校真实业务对象，不再把大纲、试卷、班级分析混在一张表里：
  1. users       : 账号表（admin 教务管理员 / teacher 任课教师）
  2. syllabuses  : 公共教学大纲库（无学期、无班级、管多年标准：课程信息、平时/期末占比、目标矩阵、指标点）
  3. exam_papers : 统考期末试卷库（按「大纲 + 学期」挂接，管理员配 1 次，全院同课教师共用）
  4. class_tasks : 教师班级分析任务（合并原「我的授课课程」与「历史报告归档」：
                   状态 = pending_paper 待配试卷 / pending_scores 待传成绩 / completed 已出报告；
                   持久化学生成绩、达成度快照、达成情况分析、拟改进措施、试卷质量分析）
"""

import hashlib
import hmac
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

DB_PATH = Path(__file__).resolve().parent / "attainment.db"
TOKEN_SECRET = os.getenv("OBE_TOKEN_SECRET", "obe-course-attainment-jwt-secret-2026").encode("utf-8")
PWD_SALT = b"obe-pwd-salt-2026"


def get_database_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def is_mysql() -> bool:
    url = get_database_url().lower()
    return url.startswith("mysql://") or url.startswith("mysql+pymysql://")


def _parse_mysql_url(url: str) -> dict:
    norm = url.replace("mysql+pymysql://", "mysql://", 1)
    p = urlparse(norm)
    return {
        "host": p.hostname or "127.0.0.1",
        "port": p.port or 3306,
        "user": unquote(p.username or "root"),
        "password": unquote(p.password or ""),
        "database": (p.path or "/obe_attainment").lstrip("/"),
    }


def _to_mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class _MySQLConnWrapper:
    """将 PyMySQL 连接适配为与 sqlite3.Connection 一致的上下文与 execute 接口。"""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def execute(self, sql: str, params=()):
        cur = self._conn.cursor()
        cur.execute(_to_mysql_sql(sql), params or ())
        return cur

    def executescript(self, script: str):
        cur = self._conn.cursor()
        for stmt in script.split(";"):
            s = stmt.strip()
            if s:
                cur.execute(s)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False


def _conn():
    if is_mysql():
        import pymysql

        cfg = _parse_mysql_url(get_database_url())
        last_err = None
        for _ in range(5):
            try:
                raw = pymysql.connect(
                    host=cfg["host"],
                    port=cfg["port"],
                    user=cfg["user"],
                    password=cfg["password"],
                    database=cfg["database"],
                    charset="utf8mb4",
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False,
                    connect_timeout=5,
                )
                return _MySQLConnWrapper(raw)
            except Exception as e:
                last_err = e
                time.sleep(0.6)
        raise last_err

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    return hmac.new(PWD_SALT, password.encode("utf-8"), hashlib.sha256).hexdigest()


def make_token(user_id: int, username: str, role: str = "teacher") -> str:
    payload = f"{user_id}:{username}:{role}"
    sig = hmac.new(TOKEN_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{payload}:{sig}"


def verify_token(token: str) -> tuple[int, str, str] | None:
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return None
        uid_s, username, role, sig = parts
        expected = hmac.new(
            TOKEN_SECRET, f"{uid_s}:{username}:{role}".encode("utf-8"), hashlib.sha256
        ).hexdigest()[:24]
        if hmac.compare_digest(sig, expected):
            return int(uid_s), username, role
    except Exception:
        pass
    return None


MYSQL_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(120) DEFAULT '',
    role VARCHAR(32) DEFAULT 'teacher',
    is_active TINYINT DEFAULT 1,
    created_at VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS syllabuses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_name VARCHAR(191) NOT NULL,
    course_code VARCHAR(64) DEFAULT '',
    course_category VARCHAR(64) DEFAULT '专业必修课',
    credits DOUBLE DEFAULT 3.0,
    hours INT DEFAULT 48,
    pass_threshold DOUBLE DEFAULT 0.65,
    method_json LONGTEXT NOT NULL,
    matrix_json LONGTEXT NOT NULL,
    target_descriptions_json LONGTEXT,
    created_by INT,
    updated_at VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS exam_papers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    syllabus_id INT NOT NULL,
    semester VARCHAR(64) NOT NULL,
    title VARCHAR(191) DEFAULT '期末统考试卷',
    paper_json LONGTEXT NOT NULL,
    question_count INT DEFAULT 0,
    created_by INT,
    updated_at VARCHAR(32) NOT NULL,
    UNIQUE KEY uq_syl_sem (syllabus_id, semester),
    CONSTRAINT fk_ep_syl FOREIGN KEY (syllabus_id) REFERENCES syllabuses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS class_tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    syllabus_id INT NULL,
    course_name VARCHAR(191) NOT NULL,
    course_code VARCHAR(64) DEFAULT '',
    semester VARCHAR(64) NOT NULL,
    class_name VARCHAR(128) NOT NULL,
    teacher_name VARCHAR(100) DEFAULT '',
    course_category VARCHAR(64) DEFAULT '专业必修课',
    credits DOUBLE DEFAULT 3.0,
    hours INT DEFAULT 48,
    pass_threshold DOUBLE DEFAULT 0.65,
    method_json LONGTEXT NOT NULL,
    matrix_json LONGTEXT NOT NULL,
    target_descriptions_json LONGTEXT,
    paper_json LONGTEXT,
    paper_source VARCHAR(32) DEFAULT 'none',
    student_count INT DEFAULT 0,
    students_json LONGTEXT,
    report_json LONGTEXT,
    analysis_text LONGTEXT,
    improvement_notes LONGTEXT,
    exam_analysis_text LONGTEXT,
    ratios_confirmed TINYINT DEFAULT 0,
    status VARCHAR(32) DEFAULT 'pending_ratios',
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    CONSTRAINT fk_ct_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_ct_syl FOREIGN KEY (syllabus_id) REFERENCES syllabuses(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def init_db():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        if is_mysql():
            conn.executescript(MYSQL_DDL)
        else:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    department TEXT DEFAULT '',
                    role TEXT DEFAULT 'teacher',
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS syllabuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_name TEXT NOT NULL,
                    course_code TEXT DEFAULT '',
                    course_category TEXT DEFAULT '专业必修课',
                    credits REAL DEFAULT 3.0,
                    hours INTEGER DEFAULT 48,
                    pass_threshold REAL DEFAULT 0.65,
                    method_json TEXT NOT NULL,
                    matrix_json TEXT NOT NULL,
                    target_descriptions_json TEXT DEFAULT '{}',
                    created_by INTEGER,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS exam_papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    syllabus_id INTEGER NOT NULL,
                    semester TEXT NOT NULL,
                    title TEXT DEFAULT '期末统考试卷',
                    paper_json TEXT NOT NULL,
                    question_count INTEGER DEFAULT 0,
                    created_by INTEGER,
                    updated_at TEXT NOT NULL,
                    UNIQUE(syllabus_id, semester),
                    FOREIGN KEY(syllabus_id) REFERENCES syllabuses(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS class_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    syllabus_id INTEGER,
                    course_name TEXT NOT NULL,
                    course_code TEXT DEFAULT '',
                    semester TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    teacher_name TEXT DEFAULT '',
                    course_category TEXT DEFAULT '专业必修课',
                    credits REAL DEFAULT 3.0,
                    hours INTEGER DEFAULT 48,
                    pass_threshold REAL DEFAULT 0.65,
                    method_json TEXT NOT NULL,
                    matrix_json TEXT NOT NULL,
                    target_descriptions_json TEXT DEFAULT '{}',
                    paper_json TEXT DEFAULT '[]',
                    paper_source TEXT DEFAULT 'none',
                    student_count INTEGER DEFAULT 0,
                    students_json TEXT DEFAULT '[]',
                    report_json TEXT DEFAULT '',
                    analysis_text TEXT DEFAULT '',
                    improvement_notes TEXT DEFAULT '',
                    exam_analysis_text TEXT DEFAULT '',
                    ratios_confirmed INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending_ratios',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(syllabus_id) REFERENCES syllabuses(id) ON DELETE SET NULL
                );
                """
            )
            tcols = {r["name"] for r in conn.execute("PRAGMA table_info(class_tasks)").fetchall()}
            if "ratios_confirmed" not in tcols:
                conn.execute("ALTER TABLE class_tasks ADD COLUMN ratios_confirmed INTEGER DEFAULT 0")

        # 默认仅预置两个干净账号：teacher / 123456 与 admin / admin123
        if not conn.execute("SELECT id FROM users WHERE username = 'teacher'").fetchone():
            conn.execute(
                "INSERT INTO users (username, password_hash, name, department, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 'teacher', 1, ?)",
                ("teacher", hash_password("123456"), "张老师", "智能制造学院", now),
            )
        if not conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone():
            conn.execute(
                "INSERT INTO users (username, password_hash, name, department, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 'admin', 1, ?)",
                ("admin", hash_password("admin123"), "教务管理员", "教务处", now),
            )


# ============================================================
# 一、用户与账号管理
# ============================================================

def get_user_by_id(user_id: int) -> dict | None:
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, username, name, department, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def authenticate_user(username: str, password: str) -> dict | None:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row or row["password_hash"] != hash_password(password):
        return None
    if not row["is_active"]:
        raise PermissionError("该账号已被管理员禁用，请联系教务处")
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "department": row["department"],
        "role": row["role"],
    }


def list_users() -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, username, name, department, role, is_active, created_at "
            "FROM users ORDER BY role ASC, id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def create_user(username: str, password: str, name: str, department: str = "", role: str = "teacher") -> dict:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if role not in ("teacher", "admin"):
        raise ValueError("角色只能为 teacher 或 admin")
    with _conn() as conn:
        if conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            raise ValueError(f"账号「{username}」已存在")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, name, department, role, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (username, hash_password(password), name, department, role, now),
        )
        row = conn.execute(
            "SELECT id, username, name, department, role, is_active, created_at FROM users WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return dict(row)


def toggle_user_active(user_id: int) -> dict:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到用户 ID={user_id}")
        if row["username"] == "admin":
            raise ValueError("不能禁用内置超级管理员账号")
        new_state = 0 if row["is_active"] else 1
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_state, user_id))
        updated = conn.execute(
            "SELECT id, username, name, department, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(updated)


def reset_user_password(user_id: int, new_password: str = "123456"):
    init_db()
    if len(new_password) < 4:
        raise ValueError("新密码至少 4 位")
    with _conn() as conn:
        if not conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone():
            raise ValueError(f"未找到用户 ID={user_id}")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )


# ============================================================
# 二、第一层：公共教学大纲库（无学期、无班级）
# ============================================================

def _paper_stats(paper: list[dict]) -> tuple[int, bool]:
    qs = [q for g in (paper or []) for q in (g.get("小题") or [])]
    total = sum(float(q.get("满分") or 0) for q in qs)
    return len(qs), len(qs) > 0 and abs(total - 100) < 1e-6


def _row_to_syllabus(row, papers: list[dict] | None = None) -> dict:
    method = json.loads(row["method_json"])
    matrix = json.loads(row["matrix_json"])
    descs = json.loads(row["target_descriptions_json"] or "{}")
    papers = papers if papers is not None else []
    return {
        "id": row["id"],
        "course_name": row["course_name"],
        "course_code": row["course_code"] or "",
        "course_category": row["course_category"] or "专业必修课",
        "credits": float(row["credits"] if row["credits"] is not None else 3.0),
        "hours": int(row["hours"] if row["hours"] is not None else 48),
        "pass_threshold": float(row["pass_threshold"] or 0.65),
        "method": method,
        "matrix": matrix,
        "target_descriptions": descs,
        "target_count": len(matrix),
        "daily_ratio": float(method.get("平时占比") or 0),
        "final_ratio": float(method.get("期末占比") or 0),
        "daily_links": list((method.get("平时环节") or {}).keys()),
        "exam_papers": papers,
        "paper_count": len(papers),
        "has_paper": len(papers) > 0,
        "updated_at": row["updated_at"],
    }


def _list_papers_for_syllabus(conn, syllabus_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM exam_papers WHERE syllabus_id = ? ORDER BY semester DESC, id DESC",
        (syllabus_id,),
    ).fetchall()
    out = []
    for r in rows:
        paper = json.loads(r["paper_json"])
        q_cnt, ready = _paper_stats(paper)
        out.append({
            "id": r["id"],
            "syllabus_id": r["syllabus_id"],
            "semester": r["semester"],
            "title": r["title"],
            "paper": paper,
            "question_count": q_cnt,
            "is_ready": ready,
            "updated_at": r["updated_at"],
        })
    return out


def list_syllabuses() -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM syllabuses ORDER BY updated_at DESC, id DESC").fetchall()
        return [_row_to_syllabus(r, _list_papers_for_syllabus(conn, r["id"])) for r in rows]


def get_syllabus(syllabus_id: int) -> dict:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM syllabuses WHERE id = ?", (syllabus_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到公共大纲 ID={syllabus_id}")
        return _row_to_syllabus(row, _list_papers_for_syllabus(conn, row["id"]))


def create_syllabus(payload: dict, admin_id: int) -> dict:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = payload.get("meta") or {}
    cname = (payload.get("course_name") or meta.get("课程名称") or "").strip()
    if not cname:
        raise ValueError("课程名称不能为空")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO syllabuses "
            "(course_name, course_code, course_category, credits, hours, pass_threshold, "
            "method_json, matrix_json, target_descriptions_json, created_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cname,
                (payload.get("course_code") or meta.get("课程代码") or "").strip(),
                (payload.get("course_category") or meta.get("课程类别") or "专业必修课").strip(),
                float(payload.get("credits", meta.get("学分", 3.0)) or 3.0),
                int(payload.get("hours", meta.get("授课学时", 48)) or 48),
                float(payload.get("pass_threshold", payload.get("threshold", 0.65)) or 0.65),
                json.dumps(payload["method"], ensure_ascii=False),
                json.dumps(payload["matrix"], ensure_ascii=False),
                json.dumps(payload.get("target_descriptions") or {}, ensure_ascii=False),
                admin_id,
                now,
            ),
        )
        sid = cur.lastrowid
    return get_syllabus(sid)


def update_syllabus(syllabus_id: int, payload: dict) -> dict:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = payload.get("meta") or {}
    with _conn() as conn:
        row = conn.execute("SELECT * FROM syllabuses WHERE id = ?", (syllabus_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到公共大纲 ID={syllabus_id}")
        conn.execute(
            "UPDATE syllabuses SET course_name=?, course_code=?, course_category=?, credits=?, hours=?, "
            "pass_threshold=?, method_json=?, matrix_json=?, target_descriptions_json=?, updated_at=? WHERE id=?",
            (
                (payload.get("course_name") or meta.get("课程名称") or row["course_name"]).strip(),
                (payload.get("course_code") if "course_code" in payload else meta.get("课程代码", row["course_code"])) or "",
                (payload.get("course_category") or meta.get("课程类别") or row["course_category"]),
                float(payload.get("credits", meta.get("学分", row["credits"])) or 3.0),
                int(payload.get("hours", meta.get("授课学时", row["hours"])) or 48),
                float(payload.get("pass_threshold", payload.get("threshold", row["pass_threshold"])) or 0.65),
                json.dumps(payload.get("method") or json.loads(row["method_json"]), ensure_ascii=False),
                json.dumps(payload.get("matrix") or json.loads(row["matrix_json"]), ensure_ascii=False),
                json.dumps(
                    payload.get("target_descriptions")
                    if "target_descriptions" in payload
                    else json.loads(row["target_descriptions_json"] or "{}"),
                    ensure_ascii=False,
                ),
                now,
                syllabus_id,
            ),
        )
    return get_syllabus(syllabus_id)


def delete_syllabus(syllabus_id: int):
    init_db()
    with _conn() as conn:
        if not conn.execute("SELECT id FROM syllabuses WHERE id = ?", (syllabus_id,)).fetchone():
            raise ValueError(f"未找到公共大纲 ID={syllabus_id}")
        conn.execute("DELETE FROM syllabuses WHERE id = ?", (syllabus_id,))


# ============================================================
# 三、第二层：统考期末试卷库（按 大纲 + 学期 挂接）
# ============================================================

def upsert_exam_paper(
    syllabus_id: int,
    semester: str,
    paper: list[dict],
    admin_id: int,
    title: str = "期末统考试卷",
) -> dict:
    init_db()
    sem = (semester or "").strip()
    if not sem:
        raise ValueError("请填写试卷所属学期，例如 2025-2026-1")
    q_cnt, _ = _paper_stats(paper)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        if not conn.execute("SELECT id FROM syllabuses WHERE id = ?", (syllabus_id,)).fetchone():
            raise ValueError(f"未找到公共大纲 ID={syllabus_id}")
        existing = conn.execute(
            "SELECT id FROM exam_papers WHERE syllabus_id = ? AND semester = ?",
            (syllabus_id, sem),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE exam_papers SET title=?, paper_json=?, question_count=?, updated_at=? WHERE id=?",
                (title, json.dumps(paper, ensure_ascii=False), q_cnt, now, existing["id"]),
            )
            pid = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO exam_papers (syllabus_id, semester, title, paper_json, question_count, created_by, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (syllabus_id, sem, title, json.dumps(paper, ensure_ascii=False), q_cnt, admin_id, now),
            )
            pid = cur.lastrowid
        conn.execute("UPDATE syllabuses SET updated_at = ? WHERE id = ?", (now, syllabus_id))
        row = conn.execute("SELECT * FROM exam_papers WHERE id = ?", (pid,)).fetchone()
    return {
        "id": row["id"],
        "syllabus_id": row["syllabus_id"],
        "semester": row["semester"],
        "title": row["title"],
        "paper": json.loads(row["paper_json"]),
        "question_count": row["question_count"],
        "updated_at": row["updated_at"],
    }


def delete_exam_paper(paper_id: int):
    init_db()
    with _conn() as conn:
        if not conn.execute("SELECT id FROM exam_papers WHERE id = ?", (paper_id,)).fetchone():
            raise ValueError(f"未找到统考试卷 ID={paper_id}")
        conn.execute("DELETE FROM exam_papers WHERE id = ?", (paper_id,))


def find_exam_paper(syllabus_id: int, semester: str) -> dict | None:
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM exam_papers WHERE syllabus_id = ? AND semester = ?",
            (syllabus_id, semester.strip()),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "syllabus_id": row["syllabus_id"],
        "semester": row["semester"],
        "title": row["title"],
        "paper": json.loads(row["paper_json"]),
        "question_count": row["question_count"],
        "updated_at": row["updated_at"],
    }


# ============================================================
# 四、第三层：教师班级分析任务（统一替代课程副本 + 历史报告）
# ============================================================

def _compute_status(paper: list[dict], has_report: bool, ratios_confirmed: bool = False) -> str:
    if has_report:
        return "completed"
    if not ratios_confirmed:
        return "pending_ratios"
    _, ready = _paper_stats(paper)
    return "pending_scores" if ready else "pending_paper"


def _row_to_task(row, include_detail: bool = False) -> dict:
    method = json.loads(row["method_json"])
    matrix = json.loads(row["matrix_json"])
    paper = json.loads(row["paper_json"] or "[]")
    descs = json.loads(row["target_descriptions_json"] or "{}")
    q_cnt, paper_ready = _paper_stats(paper)
    report_blob = json.loads(row["report_json"]) if row["report_json"] else None
    ratios_confirmed = bool(row["ratios_confirmed"]) if "ratios_confirmed" in row.keys() else False

    item = {
        "id": row["id"],
        "user_id": row["user_id"],
        "syllabus_id": row["syllabus_id"],
        "course_name": row["course_name"],
        "course_code": row["course_code"] or "",
        "semester": row["semester"],
        "class_name": row["class_name"],
        "teacher_name": row["teacher_name"] or "",
        "pass_threshold": float(row["pass_threshold"] or 0.65),
        "threshold": float(row["pass_threshold"] or 0.65),
        "meta": {
            "课程名称": row["course_name"],
            "课程代码": row["course_code"] or "",
            "学期": row["semester"],
            "班级": row["class_name"],
            "任课教师": row["teacher_name"] or "",
            "课程类别": row["course_category"] or "专业必修课",
            "学分": float(row["credits"] if row["credits"] is not None else 3.0),
            "授课学时": int(row["hours"] if row["hours"] is not None else 48),
        },
        "method": method,
        "matrix": matrix,
        "target_descriptions": descs,
        "paper": paper,
        "paper_source": row["paper_source"] or "none",
        "question_count": q_cnt,
        "paper_ready": paper_ready,
        "ratios_confirmed": ratios_confirmed,
        "target_count": len(matrix),
        "daily_ratio": float(method.get("平时占比") or 0),
        "final_ratio": float(method.get("期末占比") or 0),
        "student_count": int(row["student_count"] or 0),
        "status": row["status"],
        "target_summary": (report_blob.get("report") if report_blob else None),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_detail:
        item["students"] = json.loads(row["students_json"] or "[]")
        item["report"] = report_blob
        item["analysis_text"] = row["analysis_text"] or ""
        item["improvement_notes"] = row["improvement_notes"] or ""
        item["exam_analysis_text"] = row["exam_analysis_text"] or ""
    return item


def list_tasks_for_user(user_id: int, role: str) -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM class_tasks WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()
    return [_row_to_task(r, include_detail=False) for r in rows]


def get_task(task_id: int, user_id: int, role: str) -> dict:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM class_tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise ValueError(f"未找到班级分析任务 ID={task_id}")
    if role != "admin" and row["user_id"] != user_id:
        raise PermissionError("无权访问其他教师的班级分析任务")
    return _row_to_task(row, include_detail=True)


def create_task_from_syllabus(
    user_id: int,
    teacher_name: str,
    syllabus_id: int,
    semester: str,
    class_name: str,
) -> dict:
    init_db()
    sem = (semester or "").strip()
    cls = (class_name or "").strip()
    if not sem or not cls:
        raise ValueError("请填写开课学期与教学班级")

    syl = get_syllabus(syllabus_id)
    unified = find_exam_paper(syllabus_id, sem)
    paper = unified["paper"] if unified else []
    paper_source = "unified" if unified else "none"
    # 新建班级任务时，不替教师预设平时/期末占比，留待教师进入后自行填写确认
    daily_links = list((syl["method"].get("平时环节") or {}).keys())
    blank_method = {
        "平时占比": 0,
        "期末占比": 0,
        "平时环节": {l: 0 for l in daily_links},
    }
    status = _compute_status(paper, has_report=False, ratios_confirmed=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO class_tasks "
            "(user_id, syllabus_id, course_name, course_code, semester, class_name, teacher_name, "
            "course_category, credits, hours, pass_threshold, method_json, matrix_json, "
            "target_descriptions_json, paper_json, paper_source, ratios_confirmed, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (
                user_id,
                syl["id"],
                syl["course_name"],
                syl["course_code"],
                sem,
                cls,
                teacher_name,
                syl["course_category"],
                syl["credits"],
                syl["hours"],
                syl["pass_threshold"],
                json.dumps(blank_method, ensure_ascii=False),
                json.dumps(syl["matrix"], ensure_ascii=False),
                json.dumps(syl["target_descriptions"], ensure_ascii=False),
                json.dumps(paper, ensure_ascii=False),
                paper_source,
                status,
                now,
                now,
            ),
        )
        tid = cur.lastrowid
    return get_task(tid, user_id, "teacher")


def create_custom_task(
    user_id: int,
    teacher_name: str,
    course_name: str,
    semester: str,
    class_name: str,
) -> dict:
    init_db()
    cname = (course_name or "").strip()
    sem = (semester or "").strip()
    cls = (class_name or "").strip()
    if not cname or not sem or not cls:
        raise ValueError("请填写课程名称、开课学期与教学班级")

    method = {"平时占比": 0.4, "期末占比": 0.6, "平时环节": {"作业": 0.5, "课堂表现": 0.5}}
    matrix = {
        "课程目标1": {"作业": 0.5, "课堂表现": 0.5, "期末考试": 0.5},
        "课程目标2": {"作业": 0.5, "课堂表现": 0.5, "期末考试": 0.5},
    }
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO class_tasks "
            "(user_id, syllabus_id, course_name, course_code, semester, class_name, teacher_name, "
            "course_category, credits, hours, pass_threshold, method_json, matrix_json, "
            "target_descriptions_json, paper_json, paper_source, status, created_at, updated_at) "
            "VALUES (?, NULL, ?, '', ?, ?, ?, '专业必修课', 3.0, 48, 0.65, ?, ?, '{}', '[]', 'none', 'pending_paper', ?, ?)",
            (
                user_id,
                cname,
                sem,
                cls,
                teacher_name,
                json.dumps(method, ensure_ascii=False),
                json.dumps(matrix, ensure_ascii=False),
                now,
                now,
            ),
        )
        tid = cur.lastrowid
    return get_task(tid, user_id, "teacher")


def update_task_rules(task_id: int, user_id: int, role: str, payload: dict) -> dict:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        row = conn.execute("SELECT * FROM class_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到班级分析任务 ID={task_id}")
        if role != "admin" and row["user_id"] != user_id:
            raise PermissionError("无权修改其他教师的班级分析任务")

        meta = payload.get("meta") or {}
        method = payload.get("method") or json.loads(row["method_json"])
        matrix = payload.get("matrix") or json.loads(row["matrix_json"])
        paper = payload["paper"] if "paper" in payload else json.loads(row["paper_json"] or "[]")
        paper_source = payload.get("paper_source") or (
            "custom" if "paper" in payload and paper else row["paper_source"]
        )
        has_report = bool(row["report_json"])
        ratios_confirmed = True if ("method" in payload) else bool(row["ratios_confirmed"])
        status = _compute_status(paper, has_report=has_report, ratios_confirmed=ratios_confirmed)

        conn.execute(
            "UPDATE class_tasks SET course_name=?, course_code=?, semester=?, class_name=?, teacher_name=?, "
            "course_category=?, credits=?, hours=?, pass_threshold=?, method_json=?, matrix_json=?, "
            "paper_json=?, paper_source=?, ratios_confirmed=?, status=?, updated_at=? WHERE id=?",
            (
                meta.get("课程名称") or row["course_name"],
                meta.get("课程代码", row["course_code"]) or "",
                meta.get("学期") or row["semester"],
                meta.get("班级") or row["class_name"],
                meta.get("任课教师") or row["teacher_name"],
                meta.get("课程类别") or row["course_category"],
                float(meta.get("学分", row["credits"]) or 3.0),
                int(meta.get("授课学时", row["hours"]) or 48),
                float(payload.get("threshold", row["pass_threshold"]) or 0.65),
                json.dumps(method, ensure_ascii=False),
                json.dumps(matrix, ensure_ascii=False),
                json.dumps(paper, ensure_ascii=False),
                paper_source,
                1 if ratios_confirmed else 0,
                status,
                now,
                task_id,
            ),
        )
    return get_task(task_id, user_id, role)


def save_task_result(
    task_id: int,
    user_id: int,
    role: str,
    students: list[dict],
    report_data: dict,
    class_name: str | None = None,
    analysis_text: str | None = None,
    improvement_notes: str | None = None,
    exam_analysis_text: str | None = None,
) -> dict:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        row = conn.execute("SELECT * FROM class_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到班级分析任务 ID={task_id}")
        if role != "admin" and row["user_id"] != user_id:
            raise PermissionError("无权修改其他教师的班级分析任务")

        conn.execute(
            "UPDATE class_tasks SET class_name=?, student_count=?, students_json=?, report_json=?, "
            "analysis_text=?, improvement_notes=?, exam_analysis_text=?, status='completed', updated_at=? WHERE id=?",
            (
                (class_name or "").strip() or row["class_name"],
                len(students),
                json.dumps(students, ensure_ascii=False),
                json.dumps(report_data, ensure_ascii=False),
                analysis_text if analysis_text is not None else row["analysis_text"],
                improvement_notes if improvement_notes is not None else row["improvement_notes"],
                exam_analysis_text if exam_analysis_text is not None else row["exam_analysis_text"],
                now,
                task_id,
            ),
        )
    return get_task(task_id, user_id, role)


def update_task_notes(
    task_id: int,
    user_id: int,
    role: str,
    analysis_text: str = "",
    improvement_notes: str = "",
    exam_analysis_text: str = "",
):
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        row = conn.execute("SELECT user_id FROM class_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到班级分析任务 ID={task_id}")
        if role != "admin" and row["user_id"] != user_id:
            raise PermissionError("无权修改其他教师的分析文本")
        conn.execute(
            "UPDATE class_tasks SET analysis_text=?, improvement_notes=?, exam_analysis_text=?, updated_at=? WHERE id=?",
            (analysis_text, improvement_notes, exam_analysis_text, now, task_id),
        )


def delete_task(task_id: int, user_id: int, role: str):
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT user_id FROM class_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到班级分析任务 ID={task_id}")
        if role != "admin" and row["user_id"] != user_id:
            raise PermissionError("无权删除其他教师的班级分析任务")
        conn.execute("DELETE FROM class_tasks WHERE id = ?", (task_id,))


def get_admin_overview() -> dict:
    """管理员全院达成度汇总监控。"""
    init_db()
    with _conn() as conn:
        user_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'teacher'").fetchone()["cnt"]
        syl_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM syllabuses").fetchone()["cnt"]
        paper_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM exam_papers").fetchone()["cnt"]
        rows = conn.execute(
            "SELECT t.*, u.name AS owner_name, u.department AS owner_dept "
            "FROM class_tasks t LEFT JOIN users u ON t.user_id = u.id "
            "WHERE t.status = 'completed' ORDER BY t.updated_at DESC"
        ).fetchall()

    items = []
    passed_classes = 0
    for r in rows:
        rep_blob = json.loads(r["report_json"]) if r["report_json"] else {}
        rep = rep_blob.get("report") or {}
        th = float(r["pass_threshold"] or 0.65)
        all_passed = bool(rep) and all(v.get("达成度", 0) >= th for v in rep.values())
        if all_passed:
            passed_classes += 1
        items.append({
            "id": r["id"],
            "course_name": r["course_name"],
            "semester": r["semester"],
            "class_name": r["class_name"],
            "teacher_name": r["owner_name"] or r["teacher_name"] or "未知",
            "department": r["owner_dept"] or "",
            "student_count": r["student_count"],
            "pass_threshold": th,
            "all_passed": all_passed,
            "targets": {k: round(v.get("达成度", 0) * 100, 1) for k, v in rep.items()},
            "updated_at": r["updated_at"],
        })

    return {
        "teacher_count": user_cnt,
        "syllabus_count": syl_cnt,
        "exam_paper_count": paper_cnt,
        "report_count": len(items),
        "passed_class_count": passed_classes,
        "pass_rate": round(passed_classes / len(items) * 100, 1) if items else 0.0,
        "reports": items,
    }
