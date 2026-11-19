"""达成度计算 Web 服务

启动：python -m uvicorn api:app --reload --port 8000
访问：http://127.0.0.1:8000
"""

import io
import json
import tempfile
from datetime import datetime
from pathlib import Path

import openpyxl
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import calc_engine as eng
import course_template
import db
import diagnostics
import export_report

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
SAMPLE = ROOT / "示例"

app = FastAPI(title="课程目标达成度分析系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 启动时初始化数据库并加载当前激活课程配置
ACTIVE_STATE = db.get_active_course()
META = ACTIVE_STATE["meta"]
# 最近一次解析或提取的学生名单缓存 [{"学号": ..., "姓名": ...}]，用于生成带名单的期末录入模板
CURRENT_ROSTER: list[dict] = []


def _sync_active(course_id: int | None = None) -> dict:
    global ACTIVE_STATE, META
    ACTIVE_STATE = db.get_active_course(course_id)
    META = ACTIVE_STATE["meta"]
    return ACTIVE_STATE


# ============================================================
# 一、用户认证接口（轻重解耦：教师登录/注册）
# ============================================================

@app.post("/api/auth/login")
def login(payload: dict):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        raise HTTPException(400, "请输入账号和密码")

    db.init_db()
    with db._conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
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
                "INSERT INTO users (username, password_hash, name, department, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, db.hash_password(password), name, department, now),
            )
            uid = cur.lastrowid
    except Exception:
        raise HTTPException(400, f"账号 {username} 已存在")

    token = db.make_token(uid, username)
    return {
        "ok": True,
        "token": token,
        "user": {"id": uid, "username": username, "name": name, "department": department},
    }


# ============================================================
# 二、课程与规则配置读写（支持多课程持久化复用）
# ============================================================

@app.get("/api/config")
def read_config(course_id: int | None = Query(default=None)):
    state = _sync_active(course_id)
    return {
        "course_id": state["course_id"],
        "method": eng.METHOD,
        "matrix": eng.MATRIX,
        "paper": eng.PAPER_STRUCTURE,
        "target_descriptions": state.get("target_descriptions", {}),
        "threshold": eng.PASS_THRESHOLD,
        "meta": META,
        "roster_count": len(CURRENT_ROSTER),
    }


@app.post("/api/config")
def save_config(payload: dict):
    """校验并保存配置到数据库与引擎运行时。"""
    global META, ACTIVE_STATE
    try:
        method = payload["method"]
        matrix = payload["matrix"]
        paper = payload["paper"]
        threshold = float(payload.get("threshold", eng.PASS_THRESHOLD))

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

        # 自动重排小题题号（1..N 连续），减轻教师手工改题号负担
        q_idx = 1
        for g in paper:
            for q in g.get("小题", []):
                q["题号"] = q_idx
                q_idx += 1

        # 暂存旧配置以便校验失败时回滚
        old_m, old_mat, old_p, old_th = (
            eng.METHOD,
            eng.MATRIX,
            eng.PAPER_STRUCTURE,
            eng.PASS_THRESHOLD,
        )
        eng.METHOD = method
        eng.MATRIX = matrix
        eng.PAPER_STRUCTURE = paper
        eng.PASS_THRESHOLD = threshold
        try:
            eng.validate_structure()
            lw = eng.step1_link_weights()
            eng.step2_output_weights(lw)
        except Exception:
            eng.METHOD, eng.MATRIX, eng.PAPER_STRUCTURE, eng.PASS_THRESHOLD = (
                old_m,
                old_mat,
                old_p,
                old_th,
            )
            raise

        ACTIVE_STATE = db.save_active_course(payload, payload.get("course_id"))
        META = ACTIVE_STATE["meta"]
        return {
            "ok": True,
            "message": "配置已保存（已持久化）",
            "course_id": ACTIVE_STATE["course_id"],
            "paper": eng.PAPER_STRUCTURE,
        }
    except KeyError as e:
        raise HTTPException(400, f"配置缺少字段：{e}")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/courses")
def get_courses():
    return {"ok": True, "courses": db.list_courses()}


@app.post("/api/courses")
def add_course(payload: dict):
    state = db.create_course(payload)
    _sync_active(state["course_id"])
    return {"ok": True, "course": state}


@app.delete("/api/courses/{course_id}")
def remove_course(course_id: int):
    try:
        db.delete_course(course_id)
        state = _sync_active()
        return {"ok": True, "active_course_id": state["course_id"]}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ============================================================
# 三、模板生成（支持预填已上传的学生名单）
# ============================================================

def _save_upload(file: UploadFile) -> Path:
    """把上传文件落到临时目录，返回路径。"""
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
async def upload_roster(file: UploadFile = File(...)):
    """从平时成绩表或任意含「学号、姓名」的 Excel 中提取全班学生名单并缓存，
    供后续下载带名单的《期末小题成绩录入模板.xlsx》。
    """
    global CURRENT_ROSTER
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
        CURRENT_ROSTER = roster
        return {"ok": True, "count": len(roster), "roster": roster}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        path.unlink(missing_ok=True)


@app.get("/api/template/daily")
def template_daily(with_roster: bool = Query(default=True)):
    """生成平时成绩录入模板（若已缓存名单且 with_roster=True，则自动预填学号姓名）。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "平时成绩"
    headers = ["学号", "姓名"] + list(eng.METHOD["平时环节"].keys())
    ws.append(headers)
    header_fill = openpyxl.styles.PatternFill("solid", fgColor="DDEBF7")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c)
        cell.font = openpyxl.styles.Font(bold=True)
        cell.fill = header_fill
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 15

    if with_roster and CURRENT_ROSTER:
        for stu in CURRENT_ROSTER:
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
def template_final(with_roster: bool = Query(default=True)):
    """生成期末小题成绩录入模板（若已缓存名单且 with_roster=True，则自动预填学号姓名）。"""
    try:
        questions = eng.validate_structure()
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

    if with_roster and CURRENT_ROSTER:
        for stu in CURRENT_ROSTER:
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
# 四、成绩解析预览、在线纠错计算与报表导出
# ============================================================

@app.post("/api/parse")
async def parse_files(
    daily_file: UploadFile = File(...),
    final_file: UploadFile = File(...),
    daily_map: str | None = Form(default=None),
    final_map: str | None = Form(default=None),
):
    """非阻断式解析两份成绩 Excel，返回列映射信息、学生明细数据及单元格级错误列表。"""
    global CURRENT_ROSTER
    daily_path = _save_upload(daily_file)
    final_path = _save_upload(final_file)
    try:
        d_rows = _read_rows(daily_path)
        f_rows = _read_rows(final_path)
        c_dmap = json.loads(daily_map) if daily_map else None
        c_fmap = json.loads(final_map) if final_map else None
        parsed = eng.parse_sheets_for_preview(d_rows, f_rows, c_dmap, c_fmap)
        if parsed["students"]:
            CURRENT_ROSTER = [
                {"学号": s["学号"], "姓名": s["姓名"]} for s in parsed["students"]
            ]
        return parsed
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        daily_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)


@app.post("/api/parse-sample")
def parse_sample_data():
    """一键加载 示例/ 目录下的 44 人真实数据进入在线预览与计算状态，方便演示与测试。"""
    global CURRENT_ROSTER
    try:
        d_rows = _read_rows(SAMPLE / "平时成绩表.xlsx")
        f_rows = _read_rows(SAMPLE / "期末小题成绩录入模板.xlsx")
        parsed = eng.parse_sheets_for_preview(d_rows, f_rows)
        if parsed["students"]:
            CURRENT_ROSTER = [
                {"学号": s["学号"], "姓名": s["姓名"]} for s in parsed["students"]
            ]
        return parsed
    except ValueError as e:
        raise HTTPException(400, str(e))


def _compute_full_response(students: list[dict], threshold: float | None = None) -> dict:
    th = float(threshold if threshold is not None else eng.PASS_THRESHOLD)
    questions = eng.validate_structure()
    link_weights = eng.step1_link_weights()
    output, full = eng.step2_output_weights(link_weights)
    norm_students = eng.validate_and_normalize_records(students, questions)
    report = eng.step5_report(norm_students, output, full, questions, threshold=th)

    return {
        "ok": True,
        "student_count": len(norm_students),
        "matched": len(norm_students),
        "threshold": th,
        "meta": META,
        "link_weights": link_weights,
        "output_weights": output,
        "full_scores": full,
        "paper_target_full": eng.paper_target_full(questions),
        "report": report,
        "students": norm_students,
    }


@app.post("/api/calculate-records")
def calculate_records(payload: dict):
    """基于前端在线确认/双击纠错后的学生成绩 JSON 数据直接计算达成度，并可自动归档历史报告。"""
    try:
        students = payload.get("students") or []
        threshold = payload.get("threshold", eng.PASS_THRESHOLD)
        if payload.get("meta"):
            META.update(payload["meta"])

        res = _compute_full_response(students, threshold=threshold)

        # 若请求要求保存报告快照（默认保存）
        if payload.get("save_report", True):
            report_id = db.save_class_report(
                course_id=ACTIVE_STATE["course_id"],
                meta=META,
                threshold=res["threshold"],
                report_data={
                    "link_weights": res["link_weights"],
                    "output_weights": res["output_weights"],
                    "full_scores": res["full_scores"],
                    "paper_target_full": res["paper_target_full"],
                    "report": res["report"],
                },
                students=res["students"],
                improvement_notes=payload.get("improvement_notes") or "",
            )
            res["report_id"] = report_id

        return res
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/export-records")
def export_records(payload: dict):
    """基于前端在线确认/双击纠错后的学生成绩 JSON 数据，生成 3-Sheet《达成度计算表.xlsx》。"""
    try:
        students = payload.get("students") or []
        threshold = float(payload.get("threshold", eng.PASS_THRESHOLD))
        meta = dict(META)
        if payload.get("meta"):
            meta.update(payload["meta"])

        questions = eng.validate_structure()
        link_weights = eng.step1_link_weights()
        output, full = eng.step2_output_weights(link_weights)
        paper_full = eng.paper_target_full(questions)
        norm_students = eng.validate_and_normalize_records(students, questions)

        buf = export_report.build_workbook(
            norm_students, output, full, questions, paper_full, meta, threshold=threshold
        )
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    "attachment; filename=report.xlsx; "
                    "filename*=UTF-8''%E8%BE%BE%E6%88%90%E5%BA%A6%E8%AE%A1%E7%AE%97%E8%A1%A8.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/calculate")
async def calculate(
    daily_file: UploadFile = File(...),
    final_file: UploadFile = File(...),
):
    """兼容原有直接上传两份 Excel 计算接口。"""
    global CURRENT_ROSTER
    daily_path = _save_upload(daily_file)
    final_path = _save_upload(final_file)
    try:
        questions = eng.validate_structure()
        link_weights = eng.step1_link_weights()
        output, full = eng.step2_output_weights(link_weights)

        orig = eng.load_rows
        eng.load_rows = lambda name: _read_rows(
            daily_path if "平时" in name else final_path
        )
        try:
            students = eng.load_daily_students(verbose=False)
            matched = eng.load_final_scores(students, questions)
        finally:
            eng.load_rows = orig

        CURRENT_ROSTER = [{"学号": s["学号"], "姓名": s["姓名"]} for s in students]
        report = eng.step5_report(students, output, full, questions)

        return {
            "ok": True,
            "student_count": len(students),
            "matched": matched,
            "threshold": eng.PASS_THRESHOLD,
            "meta": META,
            "link_weights": link_weights,
            "output_weights": output,
            "full_scores": full,
            "paper_target_full": eng.paper_target_full(questions),
            "report": report,
            "students": students,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        daily_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)


@app.post("/api/export")
async def export(
    daily_file: UploadFile = File(...),
    final_file: UploadFile = File(...),
):
    """兼容原有直接上传两份 Excel 导出《达成度计算表》接口。"""
    daily_path = _save_upload(daily_file)
    final_path = _save_upload(final_file)
    try:
        questions = eng.validate_structure()
        link_weights = eng.step1_link_weights()
        output, full = eng.step2_output_weights(link_weights)
        paper_full = eng.paper_target_full(questions)

        orig = eng.load_rows
        eng.load_rows = lambda name: _read_rows(
            daily_path if "平时" in name else final_path
        )
        try:
            students = eng.load_daily_students(verbose=False)
            eng.load_final_scores(students, questions)
        finally:
            eng.load_rows = orig

        buf = export_report.build_workbook(
            students, output, full, questions, paper_full, META, threshold=eng.PASS_THRESHOLD
        )
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    "attachment; filename=report.xlsx; "
                    "filename*=UTF-8''%E8%BE%BE%E6%88%90%E5%BA%A6%E8%AE%A1%E7%AE%97%E8%A1%A8.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        daily_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)


# ============================================================
# 五、历史班级达成度报告管理
# ============================================================

@app.get("/api/reports")
def get_reports(course_id: int | None = Query(default=None)):
    return {"ok": True, "reports": db.list_class_reports(course_id)}


@app.get("/api/reports/{report_id}")
def get_report_detail(report_id: int):
    try:
        return {"ok": True, "data": db.get_class_report(report_id)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/reports/{report_id}")
def remove_report(report_id: int):
    db.delete_class_report(report_id)
    return {"ok": True}


@app.patch("/api/reports/{report_id}/notes")
def update_notes(report_id: int, payload: dict):
    db.update_report_notes(report_id, payload.get("improvement_notes", ""))
    return {"ok": True}


@app.get("/api/reports/{report_id}/export")
def export_history_report(report_id: int):
    """根据历史报告快照一键重新导出三 Sheet《达成度计算表.xlsx》。"""
    try:
        rec = db.get_class_report(report_id)
        course = db.get_active_course(rec["course_id"])
        questions = eng.validate_structure()
        lw = eng.step1_link_weights()
        output, full = eng.step2_output_weights(lw)
        paper_full = eng.paper_target_full(questions)
        meta = {
            "课程名称": rec["course_name"],
            "学期": rec["semester"],
            "班级": rec["class_name"],
        }
        buf = export_report.build_workbook(
            rec["students"],
            output,
            full,
            questions,
            paper_full,
            meta,
            threshold=float(rec["pass_threshold"] or 0.65),
        )
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    "attachment; filename=history_report.xlsx; "
                    "filename*=UTF-8''%E8%BE%BE%E6%88%90%E5%BA%A6%E8%AE%A1%E7%AE%97%E8%A1%A8.xlsx"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


# ============================================================
# 六、公共课程规则模板库（管理员 Excel 导入发布 + 教师一键选用）
# ============================================================

@app.get("/api/templates/courses")
def list_public_course_templates():
    """获取全院公共课程规则模板库列表，供教师一键选用。"""
    return {"ok": True, "templates": db.list_courses(only_public=True)}


@app.get("/api/templates/course-config-excel")
def download_course_config_excel():
    """下载标准《课程规则配置模板.xlsx》（管理员填写后可一键导入发布）。"""
    buf = course_template.build_course_config_template(
        meta=META,
        threshold=eng.PASS_THRESHOLD,
        method=eng.METHOD,
        matrix=eng.MATRIX,
        paper=eng.PAPER_STRUCTURE,
        target_descriptions=ACTIVE_STATE.get("target_descriptions", {}),
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
):
    """管理员上传《课程规则配置模板.xlsx》，一键校验并发布到公共课程模板库。"""
    path = _save_upload(file)
    try:
        parsed = course_template.parse_course_config_excel(path)
        created = db.create_course(parsed, is_public=is_public)
        return {"ok": True, "message": "课程规则模板导入成功", "course": created}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/templates/{course_id}/apply")
def apply_public_template(course_id: int):
    """教师一键选用某个公共课程模板（加载到当前工作台）。"""
    try:
        state = _sync_active(course_id)
        return {"ok": True, "message": f"已选用模板：{state['meta']['课程名称']}", "config": state}
    except ValueError as e:
        raise HTTPException(404, str(e))


# ============================================================
# 七、管理员端：教师账号管理与全院达成度汇总监控
# ============================================================

@app.get("/api/admin/users")
def admin_list_users():
    return {"ok": True, "users": db.list_users()}


@app.post("/api/admin/users")
def admin_create_user(payload: dict):
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
def admin_toggle_user(user_id: int):
    try:
        return {"ok": True, "user": db.toggle_user_active(user_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, payload: dict | None = None):
    try:
        new_pwd = (payload or {}).get("password") or "123456"
        db.reset_user_password(user_id, new_pwd)
        return {"ok": True, "message": f"密码已重置为 {new_pwd}"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/overview")
def admin_overview():
    return {"ok": True, "overview": db.get_college_overview()}


# ============================================================
# 八、OBE 教学诊断 Agent 下钻分析接口（预留大模型接入点）
# ============================================================

@app.post("/api/diagnostics/analyze")
def diagnostics_analyze(payload: dict):
    """基于 4 维下钻统计工具生成达成情况诊断数据与持续改进措施草稿。"""
    try:
        students = payload.get("students") or []
        threshold = float(payload.get("threshold", eng.PASS_THRESHOLD))
        meta = dict(META)
        if payload.get("meta"):
            meta.update(payload["meta"])

        questions = eng.validate_structure()
        lw = eng.step1_link_weights()
        output, full = eng.step2_output_weights(lw)
        paper_full = eng.paper_target_full(questions)
        norm_students = eng.validate_and_normalize_records(students, questions)
        report = eng.step5_report(norm_students, output, full, questions, threshold=threshold)

        diag = diagnostics.generate_diagnostic_report(
            course_id=ACTIVE_STATE["course_id"],
            meta=meta,
            students=norm_students,
            report=report,
            output_weights=output,
            full_scores=full,
            questions=questions,
            paper_full=paper_full,
            threshold=threshold,
        )
        return {"ok": True, "diagnostics": diag}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ============================================================
# 六、静态页面托管
# ============================================================

if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="static")
