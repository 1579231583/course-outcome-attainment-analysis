"""数据库持久化层（多用户隔离 + 公共模板只读克隆 + 学校评价表扩展字段）

核心特性（P0-1 / P0-2 / P0-3）：
  1. 无全局变量副作用：get_course_by_id / save_course 等函数纯数据返回，绝不修改 calc_engine 全局变量；
  2. 严格按 user_id 隔离私有课程与班级历史报告，管理员可全局查看监控；
  3. Copy-on-Write 公共模板保护：普通教师选用或修改公共模板时自动克隆私有副本，绝不污染原公共模板；
  4. 扩展课程元信息（任课教师 / 课程类别 / 学分 / 授课学时）及分离的达成情况分析与拟改进措施，
     完美对接终极 4-Sheet《目标达成评价表》归档导出。
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


def make_token(user_id: int, username: str, role: str = "teacher") -> str:
    payload = f"{user_id}:{username}:{role}"
    sig = hmac.new(
        SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:24]
    return f"{payload}:{sig}"


def verify_token(token: str) -> dict | None:
    if not token or token.count(":") != 3:
        return None
    uid_str, username, role, sig = token.split(":")
    expected = hmac.new(
        SECRET_KEY.encode("utf-8"),
        f"{uid_str}:{username}:{role}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:24]
    if not hmac.compare_digest(sig, expected):
        return None
    return {"id": int(uid_str), "username": username, "role": role}


def _ensure_column(conn, table: str, column: str, col_def: str):
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


def init_db():
    """初始化数据库表与平滑字段迁移，并注入默认管理员、教师账号及默认公共课程模板。"""
    with _conn() as conn:
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

            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                is_public INTEGER DEFAULT 0,
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
                user_id INTEGER DEFAULT 1,
                course_id INTEGER NOT NULL,
                course_name TEXT NOT NULL,
                semester TEXT NOT NULL,
                class_name TEXT NOT NULL,
                student_count INTEGER NOT NULL,
                pass_threshold REAL DEFAULT 0.65,
                report_json TEXT NOT NULL,
                students_json TEXT NOT NULL,
                analysis_text TEXT DEFAULT '',
                improvement_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (course_id) REFERENCES courses(id)
            );
            """
        )

        _ensure_column(conn, "users", "role", "TEXT DEFAULT 'teacher'")
        _ensure_column(conn, "users", "is_active", "INTEGER DEFAULT 1")
        _ensure_column(conn, "courses", "is_public", "INTEGER DEFAULT 0")
        _ensure_column(conn, "class_reports", "user_id", "INTEGER DEFAULT 1")
        _ensure_column(conn, "class_reports", "analysis_text", "TEXT DEFAULT ''")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. 默认教师账号：teacher / 123456
        user = conn.execute("SELECT id FROM users WHERE username = ?", ("teacher",)).fetchone()
        if not user:
            conn.execute(
                "INSERT INTO users (username, password_hash, name, department, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 'teacher', 1, ?)",
                ("teacher", hash_password("123456"), "张老师", "智能制造学院", now),
            )

        # 2. 默认管理员账号：admin / admin123
        admin = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if not admin:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, name, department, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 'admin', 1, ?)",
                ("admin", hash_password("admin123"), "教务管理员", "教务处", now),
            )
            admin_uid = cur.lastrowid
        else:
            admin_uid = admin["id"]

        # 3. 默认公共课程模板：《高等数学A（II）》
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
                "meta_ext": {
                    "课程类别": "基础课",
                    "学分": 5.5,
                    "授课学时": 88,
                    "任课教师": "张老师",
                },
            }
            conn.execute(
                "INSERT INTO courses "
                "(user_id, is_public, course_name, course_code, semester, default_class, pass_threshold, config_json, updated_at) "
                "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)",
                (
                    admin_uid,
                    "高等数学A（II）",
                    "1230601002F",
                    "2023-2024-2",
                    "23智能制造1班",
                    0.65,
                    json.dumps(default_cfg, ensure_ascii=False),
                    now,
                ),
            )


def get_user_by_id(user_id: int) -> dict | None:
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, username, name, department, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


# ============================================================
# 管理员：教师账号管理
# ============================================================

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
        uid = cur.lastrowid
        row = conn.execute(
            "SELECT id, username, name, department, role, is_active, created_at FROM users WHERE id = ?",
            (uid,),
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
# 课程与公共模板库（严格按 user_id 隔离 + Copy-on-Write）
# ============================================================

def _row_to_course(row, fallback_teacher: str = "") -> dict:
    cfg = json.loads(row["config_json"])
    ext = cfg.get("meta_ext") or {}
    return {
        "course_id": row["id"],
        "user_id": row["user_id"],
        "is_public": bool(row["is_public"]),
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
            "任课教师": ext.get("任课教师") or fallback_teacher,
            "课程类别": ext.get("课程类别") or "专业必修课",
            "学分": ext.get("学分") if ext.get("学分") is not None else 3.0,
            "授课学时": ext.get("授课学时") if ext.get("授课学时") is not None else 48,
        },
        "updated_at": row["updated_at"],
    }


def get_course_for_user(user_id: int, role: str, course_id: int | None = None, teacher_name: str = "") -> dict:
    """获取当前用户可见的课程配置（无全局副作用）。"""
    init_db()
    with _conn() as conn:
        if course_id:
            row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
            if not row:
                raise ValueError(f"未找到课程配置 ID={course_id}")
            if role != "admin" and not row["is_public"] and row["user_id"] != user_id:
                raise PermissionError("无权访问其他教师的私有课程配置")
        else:
            # 优先返回该用户自己的最近课程；若暂无则返回最近发布的公共模板
            row = conn.execute(
                "SELECT * FROM courses WHERE user_id = ? AND is_public = 0 ORDER BY updated_at DESC, id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM courses WHERE is_public = 1 ORDER BY updated_at DESC, id DESC LIMIT 1"
                ).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM courses ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        raise ValueError("暂无可用课程配置")
    return _row_to_course(row, fallback_teacher=teacher_name)


def save_course_for_user(payload: dict, user_id: int, role: str, teacher_name: str = "") -> tuple[dict, bool]:
    """保存课程配置；若普通教师尝试修改公共模板，自动 Copy-on-Write 克隆为私有副本。

    返回 (saved_course_dict, cloned_from_public: bool)
    """
    init_db()
    meta = payload.get("meta") or {}
    threshold = float(payload.get("threshold", 0.65))
    cfg_json = json.dumps(
        {
            "method": payload["method"],
            "matrix": payload["matrix"],
            "paper": payload["paper"],
            "target_descriptions": payload.get("target_descriptions") or {},
            "meta_ext": {
                "任课教师": meta.get("任课教师") or teacher_name,
                "课程类别": meta.get("课程类别") or "专业必修课",
                "学分": meta.get("学分", 3.0),
                "授课学时": meta.get("授课学时", 48),
            },
        },
        ensure_ascii=False,
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cid = payload.get("course_id")
    cloned = False

    with _conn() as conn:
        existing = (
            conn.execute("SELECT * FROM courses WHERE id = ?", (cid,)).fetchone()
            if cid
            else None
        )

        # P0-3 核心：普通教师修改公共模板时，绝不覆盖原公共模板，自动克隆私有副本！
        if existing and existing["is_public"] and role != "admin":
            cloned = True
            cur = conn.execute(
                "INSERT INTO courses "
                "(user_id, is_public, course_name, course_code, semester, default_class, pass_threshold, config_json, updated_at) "
                "VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    meta.get("课程名称") or existing["course_name"],
                    meta.get("课程代码") or existing["course_code"],
                    meta.get("学期") or existing["semester"],
                    meta.get("班级") or "",
                    threshold,
                    cfg_json,
                    now,
                ),
            )
            cid = cur.lastrowid
        elif existing:
            if role != "admin" and existing["user_id"] != user_id:
                raise PermissionError("无权修改其他教师的私有课程配置")
            keep_public = (1 if payload.get("is_public") else 0) if ("is_public" in payload and role == "admin") else existing["is_public"]
            conn.execute(
                "UPDATE courses SET is_public=?, course_name=?, course_code=?, semester=?, "
                "default_class=?, pass_threshold=?, config_json=?, updated_at=? WHERE id=?",
                (
                    keep_public,
                    meta.get("课程名称") or "未命名课程",
                    meta.get("课程代码") or "",
                    meta.get("学期") or "2024-2025-1",
                    meta.get("班级") or "",
                    threshold,
                    cfg_json,
                    now,
                    cid,
                ),
            )
        else:
            pub = 1 if (role == "admin" and payload.get("is_public")) else 0
            cur = conn.execute(
                "INSERT INTO courses "
                "(user_id, is_public, course_name, course_code, semester, default_class, pass_threshold, config_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    pub,
                    meta.get("课程名称") or "未命名课程",
                    meta.get("课程代码") or "",
                    meta.get("学期") or "2024-2025-1",
                    meta.get("班级") or "",
                    threshold,
                    cfg_json,
                    now,
                ),
            )
            cid = cur.lastrowid

    return get_course_for_user(user_id, role, cid, teacher_name=teacher_name), cloned


def clone_public_template(template_id: int, user_id: int, teacher_name: str = "") -> dict:
    """教师一键选用公共模板：自动克隆一份属于自己的私有副本。"""
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM courses WHERE id = ?", (template_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到模板 ID={template_id}")
        cfg = json.loads(row["config_json"])
        ext = cfg.get("meta_ext") or {}
        if teacher_name:
            ext["任课教师"] = teacher_name
        cfg["meta_ext"] = ext
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "INSERT INTO courses "
            "(user_id, is_public, course_name, course_code, semester, default_class, pass_threshold, config_json, updated_at) "
            "VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                row["course_name"],
                row["course_code"],
                row["semester"],
                row["default_class"],
                row["pass_threshold"],
                json.dumps(cfg, ensure_ascii=False),
                now,
            ),
        )
        new_id = cur.lastrowid
    return get_course_for_user(user_id, "teacher", new_id, teacher_name=teacher_name)


def list_courses_for_user(user_id: int, role: str, only_public: bool = False) -> list[dict]:
    init_db()
    with _conn() as conn:
        if only_public:
            rows = conn.execute(
                "SELECT id, user_id, is_public, course_name, course_code, semester, default_class, "
                "pass_threshold, updated_at FROM courses WHERE is_public = 1 ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        elif role == "admin":
            rows = conn.execute(
                "SELECT id, user_id, is_public, course_name, course_code, semester, default_class, "
                "pass_threshold, updated_at FROM courses ORDER BY is_public DESC, updated_at DESC, id DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, user_id, is_public, course_name, course_code, semester, default_class, "
                "pass_threshold, updated_at FROM courses WHERE user_id = ? OR is_public = 1 "
                "ORDER BY is_public ASC, updated_at DESC, id DESC",
                (user_id,),
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["is_public"] = bool(d["is_public"])
        result.append(d)
    return result


def create_course(payload: dict, user_id: int, is_public: bool = False, teacher_name: str = "") -> dict:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = payload.get("meta") or {}
    cfg_json = json.dumps(
        {
            "method": payload.get("method") or eng.METHOD,
            "matrix": payload.get("matrix") or eng.MATRIX,
            "paper": payload.get("paper") or eng.PAPER_STRUCTURE,
            "target_descriptions": payload.get("target_descriptions") or {},
            "meta_ext": {
                "任课教师": meta.get("任课教师") or teacher_name,
                "课程类别": meta.get("课程类别") or "专业必修课",
                "学分": meta.get("学分", 3.0),
                "授课学时": meta.get("授课学时", 48),
            },
        },
        ensure_ascii=False,
    )
    pub_flag = 1 if (is_public or payload.get("is_public")) else 0
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO courses "
            "(user_id, is_public, course_name, course_code, semester, default_class, pass_threshold, config_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                pub_flag,
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
    return get_course_for_user(user_id, "admin" if pub_flag else "teacher", cid, teacher_name=teacher_name)


def delete_course(course_id: int, user_id: int, role: str):
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not row:
            raise ValueError(f"未找到课程 ID={course_id}")
        if role != "admin" and (row["is_public"] or row["user_id"] != user_id):
            raise PermissionError("无权删除公共模板或其他教师的课程")
        count = conn.execute("SELECT COUNT(*) AS c FROM courses").fetchone()["c"]
        if count <= 1:
            raise ValueError("至少需要保留一门课程配置")
        conn.execute("DELETE FROM class_reports WHERE course_id = ?", (course_id,))
        conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))


# ============================================================
# 历史报告与全院监控（严格按 user_id 隔离）
# ============================================================

def save_class_report(
    user_id: int,
    course_id: int,
    meta: dict,
    threshold: float,
    report_data: dict,
    students: list,
    analysis_text: str = "",
    improvement_notes: str = "",
) -> int:
    init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO class_reports "
            "(user_id, course_id, course_name, semester, class_name, student_count, pass_threshold, "
            "report_json, students_json, analysis_text, improvement_notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                course_id,
                meta.get("课程名称") or "未命名课程",
                meta.get("学期") or "",
                meta.get("班级") or "默认班级",
                len(students),
                threshold,
                json.dumps(report_data, ensure_ascii=False),
                json.dumps(students, ensure_ascii=False),
                analysis_text,
                improvement_notes,
                now,
            ),
        )
        return cur.lastrowid


def list_class_reports(user_id: int, role: str, course_id: int | None = None) -> list[dict]:
    init_db()
    with _conn() as conn:
        conds = []
        params = []
        if role != "admin":
            conds.append("user_id = ?")
            params.append(user_id)
        if course_id:
            conds.append("course_id = ?")
            params.append(course_id)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = conn.execute(
            f"SELECT id, user_id, course_id, course_name, semester, class_name, student_count, "
            f"pass_threshold, report_json, analysis_text, improvement_notes, created_at "
            f"FROM class_reports {where} ORDER BY id DESC",
            tuple(params),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["report"] = json.loads(d.pop("report_json"))
        result.append(d)
    return result


def get_class_report(report_id: int, user_id: int, role: str) -> dict:
    init_db()
    with _conn() as conn:
        r = conn.execute("SELECT * FROM class_reports WHERE id = ?", (report_id,)).fetchone()
    if not r:
        raise ValueError(f"未找到报告 ID={report_id}")
    if role != "admin" and r["user_id"] != user_id:
        raise PermissionError("无权查看其他教师的历史报告")
    d = dict(r)
    d["report"] = json.loads(d.pop("report_json"))
    d["students"] = json.loads(d.pop("students_json"))
    return d


def update_report_notes(report_id: int, user_id: int, role: str, analysis_text: str, improvement_notes: str):
    init_db()
    with _conn() as conn:
        r = conn.execute("SELECT user_id FROM class_reports WHERE id = ?", (report_id,)).fetchone()
        if not r:
            raise ValueError(f"未找到报告 ID={report_id}")
        if role != "admin" and r["user_id"] != user_id:
            raise PermissionError("无权修改其他教师的报告")
        conn.execute(
            "UPDATE class_reports SET analysis_text = ?, improvement_notes = ? WHERE id = ?",
            (analysis_text, improvement_notes, report_id),
        )


def delete_class_report(report_id: int, user_id: int, role: str):
    init_db()
    with _conn() as conn:
        r = conn.execute("SELECT user_id FROM class_reports WHERE id = ?", (report_id,)).fetchone()
        if not r:
            return
        if role != "admin" and r["user_id"] != user_id:
            raise PermissionError("无权删除其他教师的报告")
        conn.execute("DELETE FROM class_reports WHERE id = ?", (report_id,))


def get_college_overview() -> dict:
    """管理员全院达成度汇总统计。"""
    init_db()
    users = list_users()
    courses = list_courses_for_user(0, "admin")
    reports = list_class_reports(0, "admin")

    total_targets = 0
    passed_targets = 0
    unpassed_items = []
    for rep in reports:
        rep_detail = rep["report"].get("report", rep["report"])
        for t_name, t_val in rep_detail.items():
            if not isinstance(t_val, dict) or "达成度" not in t_val:
                continue
            total_targets += 1
            ach = float(t_val["达成度"])
            th = float(rep["pass_threshold"] or 0.65)
            if ach >= th:
                passed_targets += 1
            else:
                unpassed_items.append(
                    {
                        "report_id": rep["id"],
                        "course_name": rep["course_name"],
                        "semester": rep["semester"],
                        "class_name": rep["class_name"],
                        "target": t_name,
                        "achievement": round(ach, 4),
                        "threshold": th,
                    }
                )

    return {
        "teacher_count": sum(1 for u in users if u["role"] == "teacher"),
        "public_template_count": sum(1 for c in courses if c["is_public"]),
        "course_count": len(courses),
        "report_count": len(reports),
        "total_targets_evaluated": total_targets,
        "passed_targets_count": passed_targets,
        "overall_pass_rate": round(passed_targets / total_targets, 4) if total_targets else 0.0,
        "unpassed_alerts": unpassed_items,
        "recent_reports": reports[:10],
    }
