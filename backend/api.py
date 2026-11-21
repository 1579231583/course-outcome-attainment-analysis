"""达成度计算 Web 服务（无状态并发安全 + Token 鉴权隔离 + 管理员批量导入 + 终极 4-Sheet 归档导出）

启动：python -m uvicorn api:app --reload --port 8000
访问：http://127.0.0.1:8000
"""

import io
import json
import tempfile
from datetime import datetime
from pathlib import Path

import openpyxl
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import calc_engine as eng
import course_template
import db
import diagnostics
import export_report

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_VUE_DIST = ROOT / "frontend-vue" / "dist"
FRONTEND = FRONTEND_VUE_DIST if FRONTEND_VUE_DIST.exists() else (ROOT / "frontend")
SAMPLE = ROOT / "示例"

app = FastAPI(title="课程目标达成度分析系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

# 按用户 ID 隔离的最近提取名单缓存（彻底消灭全局单态 CURRENT_ROSTER）
USER_ROSTERS: dict[int, list[dict]] = {}


# ============================================================
# 鉴权依赖（P0-2：真实 Token 校验与角色隔离）
# ============================================================

def get_current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> dict:
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif token:
        raw = token.strip()
    if not raw:
        raise HTTPException(401, "未登录或登录已过期，请先登录")

    parsed = db.verify_token(raw)
    if not parsed:
        raise HTTPException(401, "无效的登录凭证，请重新登录")

    user = db.get_user_by_id(parsed["id"])
    if not user or not user["is_active"]:
        raise HTTPException(403, "该账号已被禁用或不存在")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "仅教务管理员可执行此操作")
    return user


# ============================================================
# 一、用户认证接口
# ============================================================

@app.post("/api/auth/login")
def login(payload: dict):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        raise HTTPException(400, "请输入账号和密码")

    db.init_db()
    with db._conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user or not db.verify_password(password, user["password_hash"]):
        raise HTTPException(401, "账号或密码错误")
    if not user["is_active"]:
        raise HTTPException(403, "该账号已被管理员禁用，请联系教务管理员")

    role = user["role"] or "teacher"
    token = db.make_token(user["id"], user["username"], role)
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "department": user["department"],
            "role": role,
        },
    }


@app.post("/api/auth/register")
def register(payload: dict):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    name = (payload.get("name") or username).strip()
    department = (payload.get("department") or "").strip()
    if not username or len(password) < 4:
        raise HTTPException(400, "账号不能为空且密码至少 4 位")

    db.init_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with db._conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, name, department, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 'teacher', 1, ?)",
                (username, db.hash_password(password), name, department, now),
            )
            uid = cur.lastrowid
    except Exception:
        raise HTTPException(400, f"账号 {username} 已存在")

    token = db.make_token(uid, username, "teacher")
    return {
        "ok": True,
        "token": token,
        "user": {
            "id": uid,
            "username": username,
            "name": name,
            "department": department,
            "role": "teacher",
        },
    }


# ============================================================
# 二、课程与规则配置读写（无状态 + 按用户隔离 + Copy-on-Write）
# ============================================================

def _load_course_or_400(user: dict, course_id: int | None) -> dict:
    try:
        return db.get_course_for_user(
            user["id"], user["role"], course_id=course_id, teacher_name=user["name"]
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/config")
def read_config(
    course_id: int | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    course = _load_course_or_400(user, course_id)
    course["roster_count"] = len(USER_ROSTERS.get(user["id"], []))
    return course


@app.post("/api/config")
def save_config(payload: dict, user: dict = Depends(get_current_user)):
    """无状态校验并保存配置；普通教师修改公共模板时自动克隆私有副本。"""
    try:
        method = payload["method"]
        matrix = payload["matrix"]
        paper = payload["paper"]
        threshold = float(payload.get("threshold", 0.65))

        if not (0 < threshold <= 1.0):
            raise ValueError("达成度合格阈值应在 (0, 1] 之间，例如 0.65")
        if not method.get("平时环节"):
            raise ValueError("请至少保留一个平时考核环节")
        daily_sum = sum(method["平时环节"].values())
        if abs(daily_sum - 1.0) > 1e-6:
            raise ValueError(f"平时环节占比之和应为 1，实际 {daily_sum:.2f}")
        if abs(method["平时占比"] + method["期末占比"] - 1.0) > 1e-6:
            raise ValueError("平时占比 + 期末占比 应为 1")
        if not matrix:
            raise ValueError("请至少配置一个课程目标")

        q_idx = 1
        for g in paper:
            for q in g.get("小题", []):
                q["题号"] = q_idx
                q_idx += 1

        # 无状态纯函数校验
        eng.validate_structure(method, matrix, paper)
        lw = eng.step1_link_weights(method)
        eng.step2_output_weights(lw, matrix)

        saved, cloned = db.save_course_for_user(
            payload, user["id"], user["role"], teacher_name=user["name"]
        )
        msg = (
            "已自动为您创建私有课程副本并保存（原公共模板保持不变）"
            if cloned
            else "配置已保存"
        )
        return {
            "ok": True,
            "message": msg,
            "cloned": cloned,
            "course_id": saved["course_id"],
            "config": saved,
            "paper": saved["paper"],
        }
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except KeyError as e:
        raise HTTPException(400, f"配置缺少字段：{e}")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/courses")
def get_courses(user: dict = Depends(get_current_user)):
    return {"ok": True, "courses": db.list_courses_for_user(user["id"], user["role"])}


@app.post("/api/courses")
def add_course(payload: dict, user: dict = Depends(get_current_user)):
    is_pub = bool(payload.get("is_public")) and user["role"] == "admin"
    created = db.create_course(
        payload, user_id=user["id"], is_public=is_pub, teacher_name=user["name"]
    )
    return {"ok": True, "course": created}


@app.delete("/api/courses/{course_id}")
def remove_course(course_id: int, user: dict = Depends(get_current_user)):
    try:
        db.delete_course(course_id, user["id"], user["role"])
        return {"ok": True}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ============================================================
# 三、模板生成（按用户隔离名单缓存 + 显式 course_id）
# ============================================================

def _save_upload(file: UploadFile) -> Path:
    suffix = Path(file.filename or "upload.xlsx").suffix or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file.file.read())
    tmp.close()
    return Path(tmp.name)


def _read_rows(path: Path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    return [list(r) for r in ws.iter_rows(values_only=True)]


@app.post("/api/roster/upload")
async def upload_roster(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    path = _save_upload(file)
    try:
        rows = _read_rows(path)
        idx, names = eng.find_header(rows, ["学号", "姓名"])
        mapping, missing = eng.build_column_mapping(names, ["学号", "姓名"])
        if missing:
            raise ValueError(f"未找到列：{missing}")
        roster = []
        seen = set()
        for r in rows[idx + 1:]:
            sid = eng.clean(r[mapping["学号"]]) if mapping["学号"] < len(r) else None
            name = eng.clean(r[mapping["姓名"]]) if mapping["姓名"] < len(r) else None
            if eng._is_stat_row(sid, name) or sid in seen:
                continue
            seen.add(sid)
            roster.append({"学号": sid, "姓名": name})
        if not roster:
            raise ValueError("未提取到有效学生名单")
        USER_ROSTERS[user["id"]] = roster
        return {"ok": True, "count": len(roster), "roster": roster}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        path.unlink(missing_ok=True)


@app.get("/api/template/daily")
def template_daily(
    course_id: int | None = Query(default=None),
    with_roster: bool = Query(default=True),
    user: dict = Depends(get_current_user),
):
    course = _load_course_or_400(user, course_id)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "平时成绩"
    headers = ["学号", "姓名"] + list(course["method"]["平时环节"].keys())
    ws.append(headers)
    header_fill = openpyxl.styles.PatternFill("solid", fgColor="DDEBF7")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c)
        cell.font = openpyxl.styles.Font(bold=True)
        cell.fill = header_fill
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 15

    roster = USER_ROSTERS.get(user["id"], [])
    if with_roster and roster:
        for stu in roster:
            ws.append([stu["学号"], stu["姓名"]])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                "attachment; filename=daily_template.xlsx; "
                "filename*=UTF-8''%E5%B9%B3%E6%97%B6%E6%88%90%E7%BB%A9%E5%BD%95%E5%85%A5%E6%A8%A1%E6%9D%BF.xlsx"
            )
        },
    )


@app.get("/api/template/final")
def template_final(
    course_id: int | None = Query(default=None),
    with_roster: bool = Query(default=True),
    user: dict = Depends(get_current_user),
):
    course = _load_course_or_400(user, course_id)
    try:
        questions = eng.validate_structure(course["method"], course["matrix"], course["paper"])
    except ValueError as e:
        raise HTTPException(400, str(e))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "期末成绩"
    headers = ["学号", "姓名"] + [
        f"第{q['题号']}题({q['满分']}分/{q['目标']})" for q in questions
    ]
    ws.append(headers)
    header_fill = openpyxl.styles.PatternFill("solid", fgColor="DDEBF7")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c)
        cell.font = openpyxl.styles.Font(bold=True)
        cell.fill = header_fill
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 18

    roster = USER_ROSTERS.get(user["id"], [])
    if with_roster and roster:
        for stu in roster:
            ws.append([stu["学号"], stu["姓名"]])

    ws.freeze_panes = "C2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                "attachment; filename=final_template.xlsx; "
                "filename*=UTF-8''%E6%9C%9F%E6%9C%AB%E5%B0%8F%E9%A2%98%E6%88%90%E7%BB%A9%E5%BD%95%E5%85%A5%E6%A8%A1%E6%9D%BF.xlsx"
            )
        },
    )


# ============================================================
# 四、成绩解析预览、在线纠错计算与终极 4-Sheet 导出（完全无状态）
# ============================================================

@app.post("/api/parse")
async def parse_files(
    daily_file: UploadFile = File(...),
    final_file: UploadFile = File(...),
    course_id: int | None = Form(default=None),
    daily_map: str | None = Form(default=None),
    final_map: str | None = Form(default=None),
    user: dict = Depends(get_current_user),
):
    course = _load_course_or_400(user, course_id)
    daily_path = _save_upload(daily_file)
    final_path = _save_upload(final_file)
    try:
        d_rows = _read_rows(daily_path)
        f_rows = _read_rows(final_path)
        c_dmap = json.loads(daily_map) if daily_map else None
        c_fmap = json.loads(final_map) if final_map else None
        parsed = eng.parse_sheets_for_preview(
            d_rows,
            f_rows,
            c_dmap,
            c_fmap,
            method=course["method"],
            matrix=course["matrix"],
            paper=course["paper"],
        )
        if parsed["students"]:
            USER_ROSTERS[user["id"]] = [
                {"学号": s["学号"], "姓名": s["姓名"]} for s in parsed["students"]
            ]
        return parsed
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        daily_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)


@app.post("/api/parse-sample")
def parse_sample_data(
    course_id: int | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    course = _load_course_or_400(user, course_id)
    try:
        d_rows = _read_rows(SAMPLE / "平时成绩表.xlsx")
        f_rows = _read_rows(SAMPLE / "期末小题成绩录入模板.xlsx")
        parsed = eng.parse_sheets_for_preview(
            d_rows,
            f_rows,
            method=course["method"],
            matrix=course["matrix"],
            paper=course["paper"],
        )
        if parsed["students"]:
            USER_ROSTERS[user["id"]] = [
                {"学号": s["学号"], "姓名": s["姓名"]} for s in parsed["students"]
            ]
        return parsed
    except ValueError as e:
        raise HTTPException(400, str(e))


def _resolve_runtime_cfg(payload: dict, user: dict) -> tuple[dict, dict, dict, list, dict, float]:
    course = _load_course_or_400(user, payload.get("course_id"))
    method = payload.get("method") or course["method"]
    matrix = payload.get("matrix") or course["matrix"]
    paper = payload.get("paper") or course["paper"]
    meta = dict(course["meta"])
    if payload.get("meta"):
        meta.update(payload["meta"])
    if not meta.get("任课教师"):
        meta["任课教师"] = user["name"]
    th = float(payload.get("threshold", course["threshold"]))
    return course, method, matrix, paper, meta, th


@app.post("/api/calculate-records")
def calculate_records(payload: dict, user: dict = Depends(get_current_user)):
    try:
        course, method, matrix, paper, meta, th = _resolve_runtime_cfg(payload, user)
        students = payload.get("students") or []

        questions = eng.validate_structure(method, matrix, paper)
        lw = eng.step1_link_weights(method)
        output, full = eng.step2_output_weights(lw, matrix)
        paper_full = eng.paper_target_full(questions, matrix)
        norm_students = eng.validate_and_normalize_records(students, questions, method)
        report = eng.step5_report(norm_students, output, full, questions, method, matrix, threshold=th)

        res = {
            "ok": True,
            "course_id": course["course_id"],
            "student_count": len(norm_students),
            "matched": len(norm_students),
            "threshold": th,
            "meta": meta,
            "link_weights": lw,
            "output_weights": output,
            "full_scores": full,
            "paper_target_full": paper_full,
            "report": report,
            "students": norm_students,
        }

        if payload.get("save_report", True):
            report_id = db.save_class_report(
                user_id=user["id"],
                course_id=course["course_id"],
                meta=meta,
                threshold=th,
                report_data={
                    "link_weights": lw,
                    "output_weights": output,
                    "full_scores": full,
                    "paper_target_full": paper_full,
                    "report": report,
                    "method": method,
                    "matrix": matrix,
                    "paper": paper,
                    "meta": meta,
                },
                students=norm_students,
                analysis_text=payload.get("analysis_text") or "",
                improvement_notes=payload.get("improvement_notes") or "",
            )
            res["report_id"] = report_id

        return res
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/export-records")
def export_records(payload: dict, user: dict = Depends(get_current_user)):
    """导出终极 4-Sheet《目标达成评价与计算表.xlsx》。"""
    try:
        _, method, matrix, paper, meta, th = _resolve_runtime_cfg(payload, user)
        students = payload.get("students") or []

        questions = eng.validate_structure(method, matrix, paper)
        lw = eng.step1_link_weights(method)
        output, full = eng.step2_output_weights(lw, matrix)
        paper_full = eng.paper_target_full(questions, matrix)
        norm_students = eng.validate_and_normalize_records(students, questions, method)

        buf = export_report.build_workbook(
            norm_students,
            output,
            full,
            questions,
            paper_full,
            meta=meta,
            threshold=th,
            method=method,
            matrix=matrix,
            analysis_text=payload.get("analysis_text") or "",
            improvement_notes=payload.get("improvement_notes") or "",
        )
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    "attachment; filename=report.xlsx; "
                    "filename*=UTF-8''%E8%BE%BE%E6%88%90%E5%BA%A6%E6%95%B0%E6%8D%AE%E5%88%86%E6%9E%90%E8%A1%A8.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


# ============================================================
# 五、历史班级达成度报告（按用户严格隔离）
# ============================================================

@app.get("/api/reports")
def get_reports(
    course_id: int | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    return {"ok": True, "reports": db.list_class_reports(user["id"], user["role"], course_id)}


@app.get("/api/reports/{report_id}")
def get_report_detail(report_id: int, user: dict = Depends(get_current_user)):
    try:
        return {"ok": True, "data": db.get_class_report(report_id, user["id"], user["role"])}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/reports/{report_id}")
def remove_report(report_id: int, user: dict = Depends(get_current_user)):
    try:
        db.delete_class_report(report_id, user["id"], user["role"])
        return {"ok": True}
    except PermissionError as e:
        raise HTTPException(403, str(e))


@app.patch("/api/reports/{report_id}/notes")
def update_notes(report_id: int, payload: dict, user: dict = Depends(get_current_user)):
    try:
        db.update_report_notes(
            report_id,
            user["id"],
            user["role"],
            analysis_text=payload.get("analysis_text", ""),
            improvement_notes=payload.get("improvement_notes", ""),
        )
        return {"ok": True}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/reports/{report_id}/export")
def export_history_report(report_id: int, user: dict = Depends(get_current_user)):
    """根据历史报告快照一键重新导出终极 4-Sheet 归档表。"""
    try:
        rec = db.get_class_report(report_id, user["id"], user["role"])
        rep_blob = rec["report"]
        if "method" in rep_blob and "matrix" in rep_blob and "paper" in rep_blob:
            method, matrix, paper = rep_blob["method"], rep_blob["matrix"], rep_blob["paper"]
            meta = rep_blob.get("meta") or {}
        else:
            course = db.get_course_for_user(user["id"], user["role"], course_id=rec["course_id"], teacher_name=user["name"])
            method, matrix, paper = course["method"], course["matrix"], course["paper"]
            meta = dict(course["meta"])
        meta.setdefault("课程名称", rec["course_name"])
        meta.setdefault("学期", rec["semester"])
        meta.setdefault("班级", rec["class_name"])
        meta.setdefault("任课教师", user["name"])

        questions = eng.validate_structure(method, matrix, paper)
        lw = eng.step1_link_weights(method)
        output, full = eng.step2_output_weights(lw, matrix)
        paper_full = eng.paper_target_full(questions, matrix)

        buf = export_report.build_workbook(
            rec["students"],
            output,
            full,
            questions,
            paper_full,
            meta=meta,
            threshold=float(rec["pass_threshold"] or 0.65),
            method=method,
            matrix=matrix,
            analysis_text=rec.get("analysis_text") or "",
            improvement_notes=rec.get("improvement_notes") or "",
        )
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    "attachment; filename=history_report.xlsx; "
                    "filename*=UTF-8''%E8%BE%BE%E6%88%90%E5%BA%A6%E6%95%B0%E6%8D%AE%E5%88%86%E6%9E%90%E8%A1%A8.xlsx"
                )
            },
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


# ============================================================
# 六、公共课程规则模板库（管理员单个/批量 Excel 导入 + 教师克隆选用）
# ============================================================

@app.get("/api/templates/courses")
def list_public_course_templates(user: dict = Depends(get_current_user)):
    return {"ok": True, "templates": db.list_courses_for_user(user["id"], user["role"], only_public=True)}


@app.get("/api/templates/course-config-excel")
def download_course_config_excel(user: dict = Depends(get_current_user)):
    course = _load_course_or_400(user, None)
    buf = course_template.build_course_config_template(
        meta=course["meta"],
        threshold=course["threshold"],
        method=course["method"],
        matrix=course["matrix"],
        paper=course["paper"],
        target_descriptions=course.get("target_descriptions", {}),
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                "attachment; filename=course_config_template.xlsx; "
                "filename*=UTF-8''%E8%AF%BE%E7%A8%8B%E8%A7%84%E5%88%99%E9%85%8D%E7%BD%AE%E6%A8%A1%E6%9D%BF.xlsx"
            )
        },
    )


@app.post("/api/templates/import-excel")
async def import_course_config_excel(
    file: UploadFile = File(...),
    is_public: bool = Form(default=True),
    admin: dict = Depends(require_admin),
):
    path = _save_upload(file)
    try:
        parsed = course_template.parse_course_config_excel(path)
        created = db.create_course(parsed, user_id=admin["id"], is_public=is_public, teacher_name=admin["name"])
        return {"ok": True, "message": "课程规则模板导入成功", "course": created}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/templates/import-excel-batch")
async def import_course_config_excel_batch(
    files: list[UploadFile] = File(...),
    admin: dict = Depends(require_admin),
):
    """支持「1 个 Excel 内每个工作表一门课」及多选多个 Excel；逐门校验，单门失败不影响其他课程。"""
    results = []
    success_count = 0
    fail_count = 0
    for f in files:
        path = _save_upload(f)
        try:
            for item in course_template.parse_config_workbook_detailed(path):
                label = f"{f.filename} / {item['sheet']}"
                if item["error"]:
                    fail_count += 1
                    results.append({"filename": label, "ok": False, "course_name": item["sheet"],
                                    "semester": "—", "message": item["error"]})
                    continue
                created = db.create_course(
                    item["course"], user_id=admin["id"], is_public=True, teacher_name=admin["name"]
                )
                success_count += 1
                results.append({"filename": label, "ok": True, "course_name": created["meta"]["课程名称"],
                                "semester": created["meta"]["学期"], "message": "发布成功"})
        except Exception as e:
            fail_count += 1
            results.append(
                {
                    "filename": f.filename,
                    "ok": False,
                    "course_name": "—",
                    "semester": "—",
                    "message": str(e),
                }
            )
        finally:
            path.unlink(missing_ok=True)

    return {
        "ok": True,
        "total": success_count + fail_count,
        "success_count": success_count,
        "fail_count": fail_count,
        "results": results,
    }


@app.post("/api/templates/{course_id}/apply")
def apply_public_template(course_id: int, user: dict = Depends(get_current_user)):
    """教师一键选用公共模板：自动 Copy-on-Write 克隆一份属于自己的私有副本！"""
    try:
        if user["role"] == "admin":
            state = db.get_course_for_user(user["id"], "admin", course_id=course_id, teacher_name=user["name"])
            return {"ok": True, "message": f"已加载公共模板：{state['meta']['课程名称']}", "config": state}
        cloned = db.clone_public_template(course_id, user["id"], teacher_name=user["name"])
        return {
            "ok": True,
            "message": f"已选用模板「{cloned['meta']['课程名称']}」（已自动生成您的私有副本，修改不影响原公共模板）",
            "config": cloned,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


# ============================================================
# 七、管理员端（严格 require_admin 鉴权）
# ============================================================

@app.get("/api/admin/users")
def admin_list_users(admin: dict = Depends(require_admin)):
    return {"ok": True, "users": db.list_users()}


@app.post("/api/admin/users")
def admin_create_user(payload: dict, admin: dict = Depends(require_admin)):
    try:
        u = db.create_user(
            username=(payload.get("username") or "").strip(),
            password=payload.get("password") or "123456",
            name=(payload.get("name") or "").strip() or payload.get("username", ""),
            department=(payload.get("department") or "").strip(),
            role=payload.get("role") or "teacher",
        )
        return {"ok": True, "user": u}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/admin/users/{user_id}/toggle")
def admin_toggle_user(user_id: int, admin: dict = Depends(require_admin)):
    try:
        return {"ok": True, "user": db.toggle_user_active(user_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, payload: dict | None = None, admin: dict = Depends(require_admin)):
    try:
        new_pwd = (payload or {}).get("password") or "123456"
        db.reset_user_password(user_id, new_pwd)
        return {"ok": True, "message": f"密码已重置为 {new_pwd}"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/overview")
def admin_overview(admin: dict = Depends(require_admin)):
    return {"ok": True, "overview": db.get_college_overview()}


# ============================================================
# 八、OBE 教学诊断 Agent 下钻分析接口
# ============================================================

@app.post("/api/diagnostics/analyze")
def diagnostics_analyze(payload: dict, user: dict = Depends(get_current_user)):
    try:
        course, method, matrix, paper, meta, th = _resolve_runtime_cfg(payload, user)
        students = payload.get("students") or []

        questions = eng.validate_structure(method, matrix, paper)
        lw = eng.step1_link_weights(method)
        output, full = eng.step2_output_weights(lw, matrix)
        paper_full = eng.paper_target_full(questions, matrix)
        norm_students = eng.validate_and_normalize_records(students, questions, method)
        report = eng.step5_report(norm_students, output, full, questions, method, matrix, threshold=th)

        diag = diagnostics.generate_diagnostic_report(
            user_id=user["id"],
            role=user["role"],
            course_id=course["course_id"],
            meta=meta,
            students=norm_students,
            report=report,
            output_weights=output,
            full_scores=full,
            questions=questions,
            paper_full=paper_full,
            threshold=th,
        )
        return {"ok": True, "diagnostics": diag}
    except ValueError as e:
        raise HTTPException(400, str(e))


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="static")
