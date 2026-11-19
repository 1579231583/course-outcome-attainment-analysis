"""数据库持久化层（轻重解耦设计）

存储三张核心表：
  1. users         — 教师账号表（工号/账号、加密密码、姓名）
  2. courses       — 课程与达成度规则配置表（课程元信息 + method/matrix/paper JSON，支持跨班级复用）
  3. class_reports — 班级达成度历史报告表（班级名、人数、达成度汇总 JSON、确认后的学生成绩快照 JSON、持续改进记录）

说明：
- 默认使用内置 SQLite（backend/attainment.db），开箱即用无需额外部署数据库服务；
- 表结构符合标准关系型数据库规范（主键、外键、JSON 文本、时间戳），可无缝迁移至 MySQL。
"""

import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

import calc_engine as eng

DB_PATH = Path(__file__).resolve().parent / "attainment.db"
SECRET_KEY = "obe-course-attainment-secret-key"


def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hmac.new(
        salt.encode("utf-8"), password.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, salt), stored)


def make_token(user_id: int, username: str) -> str:
    payload = f"{user_id}:{username}"
    sig = hmac.new(
        SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:24]
    return f"{payload}:{sig}"


def verify_token(token: str) -> dict | None:
    if not token or token.count(":") != 2:
        return None
    uid_str, username, sig = token.split(":")
    expected = hmac.new(
        SECRET_KEY.encode("utf-8"),
        f"{uid_str}:{username}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:24]
    if not hmac.compare_digest(sig, expected):
        return None
    return {"id": int(uid_str), "username": username}


def init_db():
    """初始化数据库表，并注入默认教师账号与默认示例课程。"""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                department TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_name TEXT NOT NULL,
                course_code TEXT DEFAULT '',
                semester TEXT NOT NULL,
                default_class TEXT DEFAULT '',
                pass_threshold REAL DEFAULT 0.65,
                config_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS class_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                course_name TEXT NOT NULL,
                semester TEXT NOT NULL,
                class_name TEXT NOT NULL,
                student_count INTEGER NOT NULL,
                pass_threshold REAL DEFAULT 0.65,
                report_json TEXT NOT NULL,
                students_json TEXT NOT NULL,
                improvement_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (course_id) REFERENCES courses(id)
            );
            """
        )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 默认教师账号：teacher / 123456
        user = conn.execute(
            "SELECT id FROM users WHERE username = ?", ("teacher",)
        ).fetchone()
        if not user:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, name, department, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("teacher", hash_password("123456"), "张老师", "智能制造学院", now),
            )
            uid = cur.lastrowid
        else:
            uid = user["id"]

        # 默认课程：《高等数学A（II）》
        course = conn.execute("SELECT id FROM courses LIMIT 1").fetchone()
        if not course:
            default_cfg = {
                "method": eng.METHOD,
                "matrix": eng.MATRIX,
                "paper": eng.PAPER_STRUCTURE,
                "target_descriptions": {
                    "课程目标1": "掌握微积分与常微分方程的基本概念、理论与计算方法",
                    "课程目标2": "能够运用高等数学工具建立模型并解决工程与几何实际问题",
                },
            }
            conn.execute(
                "INSERT INTO courses "
                "(user_id, course_name, course_code, semester, default_class, pass_threshold, config_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uid,
                    "高等数学A（II）",
                    "MATH1002",
                    "2023-2024-2",
                    "23智能制造1班",
                    0.65,
                    json.dumps(default_cfg, ensure_ascii=False),
                    now,
                ),
            )


def get_active_course(course_id: int | None = None) -> dict:
    """读取指定课程（或最近更新的默认课程），并同步到 calc_engine 运行时配置。"""
    init_db()
    with _conn() as conn:
        if course_id:
            row = conn.execute(
                "SELECT * FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM courses ORDER BY updated_at DESC, id DESC LIMIT 1"
            ).fetchone()

    if not row:
        raise ValueError("未找到课程配置")

    cfg = json.loads(row["config_json"])
    eng.METHOD = cfg["method"]
    eng.MATRIX = cfg["matrix"]
    eng.PAPER_STRUCTURE = cfg["paper"]
    eng.PASS_THRESHOLD = float(row["pass_threshold"] or 0.65)

    return {
        "course_id": row["id"],
        "method": cfg["method"],
        "matrix": cfg["matrix"],
        "paper": cfg["paper"],
        "target_descriptions": cfg.get("target_descriptions", {}),
        "threshold": float(row["pass_threshold"] or 0.65),
        "meta": {
            "课程名称": row["course_name"],
            "课程代码": row["course_code"] or "",
            "学期": row["semester"],
            "班级": row["default_class"] or "",
        },
        "updated_at": row["updated_at"],
    }


def save_active_course(payload: dict, course_id: int | None = None) -> dict:
    """保存课程配置到数据库并同步 calc_engine。"""
    init_db()
    method = payload["method"]
    matrix = payload["matrix"]
    paper = payload["paper"]
    meta = payload.get("meta") or {}
    threshold = float(payload.get("threshold", eng.PASS_THRESHOLD))
    target_descriptions = payload.get("target_descriptions") or {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg_json = json.dumps(
        {
            "method": method,
            "matrix": matrix,
            "paper": paper,
            "target_descriptions": target_descriptions,
        },
        ensure_ascii=False,
    )

    course_name = meta.get("课程名称") or "未命名课程"
    course_code = meta.get("课程代码") or ""
    semester = meta.get("学期") or "2024-2025-1"
    default_class = meta.get("班级") or ""

    cid = course_id or payload.get("course_id")
    with _conn() as conn:
        if cid:
            exists = conn.execute(
                "SELECT id FROM courses WHERE id = ?", (cid,)
            ).fetchone()
        else:
            exists = conn.execute(
                "SELECT id FROM courses ORDER BY updated_at DESC, id DESC LIMIT 1"
            ).fetchone()

        if exists:
            cid = exists["id"]
            conn.execute(
                "UPDATE courses SET course_name=?, course_code=?, semester=?, "
                "default_class=?, pass_threshold=?, config_json=?, updated_at=? WHERE id=?",
                (
                    course_name,
                    course_code,
                    semester,
                    default_class,
                    threshold,
                    cfg_json,
                    now,
                    cid,
                ),
            )
        else:
            cur = conn.execute(
                "INSERT INTO courses "
                "(user_id, course_name, course_code, semester, default_class, pass_threshold, config_json, updated_at) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
                (
                    course_name,
                    course_code,
                    semester,
                    default_class,
                    threshold,
                    cfg_json,
                    now,
                ),
            )
            cid = cur.lastrowid

    return get_active_course(cid)


def list_courses() -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, course_name, course_code, semester, default_class, pass_threshold, updated_at "
            "FROM courses ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def create_course(payload: dict) -> dict:
    """新建一门课程配置。"""
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    method = payload.get("method") or eng.METHOD
    matrix = payload.get("matrix") or eng.MATRIX
    paper = payload.get("paper") or eng.PAPER_STRUCTURE
    target_descriptions = payload.get("target_descriptions") or {}
    cfg_json = json.dumps(
        {
            "method": method,
            "matrix": matrix,
            "paper": paper,
            "target_descriptions": target_descriptions,
        },
        ensure_ascii=False,
    )
    meta = payload.get("meta") or {}
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO courses "
            "(user_id, course_name, course_code, semester, default_class, pass_threshold, config_json, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
            (
                meta.get("课程名称") or "新课程",
                meta.get("课程代码") or "",
                meta.get("学期") or "2024-2025-1",
                meta.get("班级") or "",
                float(payload.get("threshold", 0.65)),
                cfg_json,
                now,
            ),
        )
        cid = cur.lastrowid
    return get_active_course(cid)


def delete_course(course_id: int):
    init_db()
    with _conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM courses").fetchone()["c"]
        if count <= 1:
            raise ValueError("至少需要保留一门课程配置")
        conn.execute("DELETE FROM class_reports WHERE course_id = ?", (course_id,))
        conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))


def save_class_report(
    course_id: int,
    meta: dict,
    threshold: float,
    report_data: dict,
    students: list,
    improvement_notes: str = "",
) -> int:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    course_name = meta.get("课程名称") or "未命名课程"
    semester = meta.get("学期") or ""
    class_name = meta.get("班级") or "默认班级"
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO class_reports "
            "(course_id, course_name, semester, class_name, student_count, pass_threshold, "
            "report_json, students_json, improvement_notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                course_id,
                course_name,
                semester,
                class_name,
                len(students),
                threshold,
                json.dumps(report_data, ensure_ascii=False),
                json.dumps(students, ensure_ascii=False),
                improvement_notes,
                now,
            ),
        )
        return cur.lastrowid


def list_class_reports(course_id: int | None = None) -> list[dict]:
    init_db()
    with _conn() as conn:
        if course_id:
            rows = conn.execute(
                "SELECT id, course_id, course_name, semester, class_name, student_count, "
                "pass_threshold, report_json, improvement_notes, created_at "
                "FROM class_reports WHERE course_id = ? ORDER BY id DESC",
                (course_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, course_id, course_name, semester, class_name, student_count, "
                "pass_threshold, report_json, improvement_notes, created_at "
                "FROM class_reports ORDER BY id DESC"
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["report"] = json.loads(d.pop("report_json"))
        result.append(d)
    return result


def get_class_report(report_id: int) -> dict:
    init_db()
    with _conn() as conn:
        r = conn.execute(
            "SELECT * FROM class_reports WHERE id = ?", (report_id,)
        ).fetchone()
    if not r:
        raise ValueError(f"未找到报告 ID={report_id}")
    d = dict(r)
    d["report"] = json.loads(d.pop("report_json"))
    d["students"] = json.loads(d.pop("students_json"))
    return d


def delete_class_report(report_id: int):
    init_db()
    with _conn() as conn:
        conn.execute("DELETE FROM class_reports WHERE id = ?", (report_id,))
