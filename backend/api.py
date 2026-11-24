"""课程目标达成度分析系统 — FastAPI 后端服务（三层清晰架构）

架构边界：
  1. 认证与账号：/api/auth/*，/api/admin/users/*
  2. 公共教学大纲库（无学期/无班级）：/api/syllabuses/*（管理员传 PDF 预览微调发布、编辑、删除；所有人可读）
  3. 统考期末试卷库（按 大纲+学期 挂接）：/api/syllabuses/{id}/paper-template、paper-preview、papers
  4. 教师班级分析任务（合并授课课程与历史报告）：/api/tasks/*
     - 创建任务（从大纲选课自动挂接同学期统考试卷，或新建自定义任务）
     - 下载平时/期末模板、下载/上传本班 4 列试卷模板、保存规则微调
     - 解析成绩（兼容 .xlsx / .xls）、在线纠错计算、OBE 4 维诊断、保存三段分析文本
     - 一键导出双文档归档文件夹 ZIP（《达成度数据分析表.xlsx》+《考试试卷分析表.xlsx》）
  5. 全院监控：/api/admin/overview

启动：python -m uvicorn api:app --reload --port 8000
"""

import io
import json
import tempfile
import urllib.parse
import zipfile
from pathlib import Path

import openpyxl
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import calc_engine as eng
import course_template
import db
import diagnostics
import export_exam_analysis
import export_report
import syllabus_parser

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_VUE_DIST = ROOT / "frontend-vue" / "dist"

app = FastAPI(title="课程目标达成度分析系统", version="4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 通用工具与鉴权依赖
# ============================================================

def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "请先登录账号")
    token = authorization.split(" ", 1)[1].strip()
    parsed = db.verify_token(token)
    if not parsed:
        raise HTTPException(401, "登录凭证无效或已过期，请重新登录")
    uid, _, _ = parsed
    user = db.get_user_by_id(uid)
    if not user:
        raise HTTPException(401, "账号不存在，请重新登录")
    if not user["is_active"]:
        raise HTTPException(403, "该账号已被管理员禁用")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "仅教务管理员有权执行此操作")
    return user


def _save_upload(file: UploadFile) -> Path:
    suffix = Path(file.filename or "upload.xlsx").suffix or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file.file.read())
    tmp.close()
    return Path(tmp.name)


def _read_rows(path: Path) -> list[list]:
    if path.suffix.lower() == ".xls":
        import xlrd

        book = xlrd.open_workbook(str(path))
        sheet = book.sheet_by_index(0)
        return [
            [sheet.cell_value(r, c) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)
        ]
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _validate_method_and_matrix(method: dict, matrix: dict, threshold: float):
    if not (0 < threshold <= 1.0):
        raise ValueError("达成度合格阈值应在 (0, 1] 之间，例如 0.65")
    if not method.get("平时环节"):
        raise ValueError("请至少保留一个平时考核环节")
    daily_sum = sum(float(v or 0) for v in method["平时环节"].values())
    if abs(daily_sum - 1.0) > 1e-6:
        raise ValueError(f"平时环节占比之和应为 1.00，当前为 {daily_sum:.2f}")
    if abs(float(method.get("平时占比") or 0) + float(method.get("期末占比") or 0) - 1.0) > 1e-6:
        raise ValueError("平时占比 + 期末占比 应为 1.00")
    if not matrix:
        raise ValueError("请至少配置一个课程目标")
    lw = eng.step1_link_weights(method)
    eng.step2_output_weights(lw, matrix)


def _renumber_paper(paper: list[dict]) -> int:
    seq = 1
    for g in paper:
        for q in g.get("小题", []):
            q["题号"] = seq
            seq += 1
    return seq - 1


def _build_archive_bundle_zip(task: dict) -> tuple[io.BytesIO, str]:
    method, matrix, paper = task["method"], task["matrix"], task["paper"]
    meta = dict(task["meta"])
    th = float(task["pass_threshold"] or 0.65)
    students = task.get("students") or []

    questions = eng.validate_structure(method, matrix, paper)
    lw = eng.step1_link_weights(method)
    output, full = eng.step2_output_weights(lw, matrix)
    paper_full = eng.paper_target_full(questions, matrix)
    norm_students = eng.validate_and_normalize_records(students, questions, method)

    prefix = f"{meta.get('班级') or ''}{meta.get('课程名称') or '课程'}".strip() or "课程归档"
    safe_prefix = "".join(ch for ch in prefix if ch not in '\\/:*?"<>|') or "课程归档"
    folder = f"{safe_prefix}_归档材料"

    buf_att = export_report.build_workbook(
        norm_students,
        output,
        full,
        questions,
        paper_full,
        meta=meta,
        threshold=th,
        method=method,
        matrix=matrix,
        analysis_text=task.get("analysis_text") or "",
        improvement_notes=task.get("improvement_notes") or "",
    )
    buf_exam = export_exam_analysis.build_exam_analysis_workbook(
        norm_students,
        paper,
        meta=meta,
        exam_analysis_text=task.get("exam_analysis_text") or "",
    )

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{folder}/{safe_prefix}达成度数据分析表.xlsx", buf_att.getvalue())
        zf.writestr(f"{folder}/{safe_prefix}考试试卷分析表.xlsx", buf_exam.getvalue())
    zbuf.seek(0)
    return zbuf, f"{folder}.zip"


# ============================================================
# 一、认证与教师账号管理
# ============================================================

@app.post("/api/auth/login")
def login(payload: dict):
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    try:
        user = db.authenticate_user(username, password)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    if not user:
        raise HTTPException(401, "账号或密码错误")
    return {"ok": True, "token": db.make_token(user["id"], user["username"], user["role"]), "user": user}


@app.post("/api/auth/register")
def register(payload: dict):
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    name = (payload.get("name") or username).strip()
    department = (payload.get("department") or "").strip()
    if len(username) < 2 or len(password) < 4:
        raise HTTPException(400, "账号至少 2 位，密码至少 4 位")
    try:
        user = db.create_user(username, password, name, department, role="teacher")
        return {
            "ok": True,
            "token": db.make_token(user["id"], user["username"], "teacher"),
            "user": user,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/users")
def admin_list_users(admin: dict = Depends(require_admin)):
    return {"ok": True, "users": db.list_users()}


@app.post("/api/admin/users")
def admin_create_user(payload: dict, admin: dict = Depends(require_admin)):
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "123456").strip()
    name = (payload.get("name") or username).strip()
    department = (payload.get("department") or "").strip()
    role = (payload.get("role") or "teacher").strip()
    if len(username) < 2 or len(password) < 4:
        raise HTTPException(400, "账号至少 2 位，密码至少 4 位")
    try:
        user = db.create_user(username, password, name, department, role=role)
        return {"ok": True, "user": user}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/admin/users/{user_id}/toggle")
def admin_toggle_user(user_id: int, admin: dict = Depends(require_admin)):
    try:
        return {"ok": True, "user": db.toggle_user_active(user_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, payload: dict, admin: dict = Depends(require_admin)):
    try:
        db.reset_user_password(user_id, (payload.get("password") or "123456").strip())
        return {"ok": True, "message": "密码已重置"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/overview")
def admin_overview(admin: dict = Depends(require_admin)):
    return {"ok": True, "overview": db.get_admin_overview()}


# ============================================================
# 二、第一层：公共教学大纲库（无学期、无班级）
# ============================================================

@app.get("/api/syllabuses")
def list_syllabuses(user: dict = Depends(get_current_user)):
    return {"ok": True, "syllabuses": db.list_syllabuses()}


@app.post("/api/syllabuses/preview-pdf")
async def preview_syllabus_pdf(
    files: list[UploadFile] = File(...),
    admin: dict = Depends(require_admin),
):
    """管理员上传《课程教学大纲 PDF》，提取课程底座（含平时/期末占比与细项比例、目标与指标点、考核矩阵）。"""
    drafts = []
    for f in files:
        path = _save_upload(f)
        try:
            parsed = syllabus_parser.parse_syllabus_pdf(path, filename=f.filename or "")
            c = parsed["course"]
            errs = course_template._collect_course_errors(c, allow_empty_paper=True)
            drafts.append({
                "source_file": f.filename,
                "course": c,
                "summary": parsed["extracted_summary"],
                "errors": errs,
            })
        except Exception as e:
            drafts.append({
                "source_file": f.filename,
                "course": None,
                "summary": None,
                "errors": [str(e)],
            })
        finally:
            path.unlink(missing_ok=True)
    return {"ok": True, "drafts": drafts}


@app.post("/api/syllabuses/publish-batch")
def publish_syllabuses(payload: dict, admin: dict = Depends(require_admin)):
    items = payload.get("courses") or []
    if not items:
        raise HTTPException(400, "没有可发布的大纲")
    created_list = []
    for c in items:
        try:
            th = float(c.get("threshold", c.get("pass_threshold", 0.65)))
            _validate_method_and_matrix(c["method"], c["matrix"], th)
            created_list.append(db.create_syllabus(c, admin_id=admin["id"]))
        except (ValueError, KeyError) as e:
            raise HTTPException(400, f"发布失败：{e}")
    return {"ok": True, "count": len(created_list), "syllabuses": created_list}


@app.put("/api/syllabuses/{syllabus_id}")
def update_syllabus(syllabus_id: int, payload: dict, admin: dict = Depends(require_admin)):
    try:
        th = float(payload.get("pass_threshold", payload.get("threshold", 0.65)))
        _validate_method_and_matrix(payload["method"], payload["matrix"], th)
        updated = db.update_syllabus(syllabus_id, payload)
        return {"ok": True, "syllabus": updated}
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.delete("/api/syllabuses/{syllabus_id}")
def remove_syllabus(syllabus_id: int, admin: dict = Depends(require_admin)):
    try:
        db.delete_syllabus(syllabus_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


# ============================================================
# 三、第二层：统考期末试卷库（按 大纲 + 学期 挂接）
# ============================================================

@app.get("/api/syllabuses/{syllabus_id}/paper-template")
def download_syllabus_paper_template(
    syllabus_id: int,
    semester: str | None = None,
    user: dict = Depends(get_current_user),
):
    try:
        syl = db.get_syllabus(syllabus_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    existing = db.find_exam_paper(syllabus_id, semester) if semester else None
    buf = course_template.build_paper_structure_template(
        course_name=syl["course_name"],
        targets=list(syl["matrix"].keys()),
        existing_paper=existing["paper"] if existing else None,
    )
    encoded = urllib.parse.quote(f"{syl['course_name']}_期末试卷结构模板.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=paper_tpl.xlsx; filename*=UTF-8''{encoded}"},
    )


@app.post("/api/syllabuses/{syllabus_id}/paper-preview")
async def preview_syllabus_paper(
    syllabus_id: int,
    file: UploadFile = File(...),
    admin: dict = Depends(require_admin),
):
    try:
        syl = db.get_syllabus(syllabus_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    path = _save_upload(file)
    try:
        paper, errs = course_template.parse_paper_structure_for_preview(path, syl["method"], syl["matrix"])
        return {"ok": True, "paper": paper, "errors": errs, "targets": list(syl["matrix"].keys())}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/syllabuses/{syllabus_id}/papers")
def save_syllabus_exam_paper(
    syllabus_id: int,
    payload: dict,
    admin: dict = Depends(require_admin),
):
    try:
        syl = db.get_syllabus(syllabus_id)
        semester = (payload.get("semester") or "").strip()
        title = (payload.get("title") or "期末统考试卷").strip()
        paper = payload.get("paper") or []
        _renumber_paper(paper)
        eng.validate_structure(syl["method"], syl["matrix"], paper)
        saved = db.upsert_exam_paper(syllabus_id, semester, paper, admin_id=admin["id"], title=title)
        return {"ok": True, "paper": saved, "message": f"已保存 {semester} 统考试卷（{saved['question_count']} 题，100 分）"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/exam-papers/{paper_id}")
def remove_exam_paper(paper_id: int, admin: dict = Depends(require_admin)):
    try:
        db.delete_exam_paper(paper_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


# ============================================================
# 四、第三层：教师班级分析任务（统一授课与历史归档）
# ============================================================

@app.get("/api/tasks")
def list_tasks(user: dict = Depends(get_current_user)):
    return {"ok": True, "tasks": db.list_tasks_for_user(user["id"], user["role"])}


@app.post("/api/tasks")
def create_task(payload: dict, user: dict = Depends(get_current_user)):
    try:
        syllabus_id = payload.get("syllabus_id")
        semester = (payload.get("semester") or "").strip()
        class_name = (payload.get("class_name") or "").strip()
        if syllabus_id:
            task = db.create_task_from_syllabus(
                user["id"], user["name"], int(syllabus_id), semester, class_name
            )
        else:
            task = db.create_custom_task(
                user["id"], user["name"], (payload.get("course_name") or "").strip(), semester, class_name
            )
        return {"ok": True, "task": task}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int, user: dict = Depends(get_current_user)):
    try:
        return {"ok": True, "task": db.get_task(task_id, user["id"], user["role"])}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.put("/api/tasks/{task_id}/rules")
def update_task_rules(task_id: int, payload: dict, user: dict = Depends(get_current_user)):
    try:
        th = float(payload.get("threshold", 0.65))
        method = payload["method"]
        matrix = payload["matrix"]
        paper = payload.get("paper") or []
        _validate_method_and_matrix(method, matrix, th)
        if paper:
            _renumber_paper(paper)
            eng.validate_structure(method, matrix, paper)
        updated = db.update_task_rules(task_id, user["id"], user["role"], payload)
        return {"ok": True, "task": updated}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/tasks/{task_id}/paper-template")
def download_task_paper_template(task_id: int, user: dict = Depends(get_current_user)):
    try:
        task = db.get_task(task_id, user["id"], user["role"])
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    buf = course_template.build_paper_structure_template(
        course_name=task["course_name"],
        targets=list(task["matrix"].keys()),
        existing_paper=task["paper"] or None,
    )
    encoded = urllib.parse.quote(f"{task['course_name']}_期末试卷结构模板.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=paper_tpl.xlsx; filename*=UTF-8''{encoded}"},
    )


@app.post("/api/tasks/{task_id}/paper-import")
async def import_task_paper_excel(
    task_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    try:
        task = db.get_task(task_id, user["id"], user["role"])
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    path = _save_upload(file)
    try:
        paper = course_template.parse_paper_structure_excel(path, task["method"], task["matrix"])
        updated = db.update_task_rules(
            task_id, user["id"], user["role"], {"paper": paper, "paper_source": "custom"}
        )
        return {"ok": True, "task": updated, "message": f"已导入 {updated['question_count']} 道期末小题（100 分）"}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        path.unlink(missing_ok=True)


@app.get("/api/tasks/{task_id}/template/daily")
def download_task_daily_template(task_id: int, user: dict = Depends(get_current_user)):
    try:
        task = db.get_task(task_id, user["id"], user["role"])
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "平时成绩"
    ws.append(["学号", "姓名"] + list(task["method"]["平时环节"].keys()))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    encoded = urllib.parse.quote(f"{task['class_name']}_平时成绩模板.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=daily_tpl.xlsx; filename*=UTF-8''{encoded}"},
    )


@app.get("/api/tasks/{task_id}/template/final")
def download_task_final_template(task_id: int, user: dict = Depends(get_current_user)):
    try:
        task = db.get_task(task_id, user["id"], user["role"])
        questions = eng.validate_structure(task["method"], task["matrix"], task["paper"])
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "期末试卷成绩"
    ws.append(["学号", "姓名"] + [f"第{q['题号']}题({q['满分']}分)" for q in questions])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    encoded = urllib.parse.quote(f"{task['class_name']}_期末小题成绩模板.xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=final_tpl.xlsx; filename*=UTF-8''{encoded}"},
    )


@app.post("/api/tasks/{task_id}/parse-scores")
async def parse_task_scores(
    task_id: int,
    daily_file: UploadFile = File(...),
    final_file: UploadFile = File(...),
    daily_map: str | None = Form(default=None),
    final_map: str | None = Form(default=None),
    user: dict = Depends(get_current_user),
):
    try:
        task = db.get_task(task_id, user["id"], user["role"])
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))

    p_daily = _save_upload(daily_file)
    p_final = _save_upload(final_file)
    try:
        return eng.parse_sheets_for_preview(
            _read_rows(p_daily),
            _read_rows(p_final),
            custom_daily_map=json.loads(daily_map) if daily_map else None,
            custom_final_map=json.loads(final_map) if final_map else None,
            method=task["method"],
            matrix=task["matrix"],
            paper=task["paper"],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        p_daily.unlink(missing_ok=True)
        p_final.unlink(missing_ok=True)


@app.post("/api/tasks/{task_id}/calculate")
def calculate_task(task_id: int, payload: dict, user: dict = Depends(get_current_user)):
    try:
        task = db.get_task(task_id, user["id"], user["role"])
        method, matrix, paper = task["method"], task["matrix"], task["paper"]
        th = float(task["pass_threshold"] or 0.65)
        students = payload.get("students") or []

        questions = eng.validate_structure(method, matrix, paper)
        lw = eng.step1_link_weights(method)
        output, full = eng.step2_output_weights(lw, matrix)
        paper_full = eng.paper_target_full(questions, matrix)
        norm_students = eng.validate_and_normalize_records(students, questions, method)
        report = eng.step5_report(norm_students, output, full, questions, method, matrix, threshold=th)
        exam_stats = export_exam_analysis.compute_exam_analysis_stats(norm_students, paper)
        class_name = (payload.get("class_name") or task["class_name"]).strip()
        meta = dict(task["meta"], 班级=class_name)
        diag = diagnostics.generate_diagnostic_report(
            user_id=user["id"],
            role=user["role"],
            course_id=task["syllabus_id"] or task["id"],
            meta=meta,
            students=norm_students,
            report=report,
            output_weights=output,
            full_scores=full,
            questions=questions,
            paper_full=paper_full,
            threshold=th,
        )
        report_data = {
            "link_weights": lw,
            "output_weights": output,
            "full_scores": full,
            "paper_target_full": paper_full,
            "report": report,
            "exam_analysis": exam_stats,
            "diagnostics": diag,
            "meta": meta,
        }
        updated = db.save_task_result(
            task_id,
            user["id"],
            user["role"],
            students=norm_students,
            report_data=report_data,
            class_name=class_name,
            analysis_text=task["analysis_text"] or diag.get("analysis_text", ""),
            improvement_notes=task["improvement_notes"] or diag.get("improvement_text", ""),
            exam_analysis_text=task["exam_analysis_text"] or exam_stats.get("default_analysis_text", ""),
        )
        return {"ok": True, "task": updated}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/tasks/{task_id}/notes")
def update_task_notes(task_id: int, payload: dict, user: dict = Depends(get_current_user)):
    try:
        db.update_task_notes(
            task_id,
            user["id"],
            user["role"],
            analysis_text=payload.get("analysis_text", ""),
            improvement_notes=payload.get("improvement_notes", ""),
            exam_analysis_text=payload.get("exam_analysis_text", ""),
        )
        return {"ok": True}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/tasks/{task_id}/export-bundle")
def export_task_bundle(task_id: int, user: dict = Depends(get_current_user)):
    """一键导出完整双表归档文件夹 ZIP（《达成度数据分析表.xlsx》+《考试试卷分析表.xlsx》）。"""
    try:
        task = db.get_task(task_id, user["id"], user["role"])
        if not task.get("students"):
            raise ValueError("该班级尚未上传成绩，无法导出归档包")
        zbuf, zip_name = _build_archive_bundle_zip(task)
        encoded = urllib.parse.quote(zip_name)
        return StreamingResponse(
            zbuf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=archive.zip; filename*=UTF-8''{encoded}"},
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, user: dict = Depends(get_current_user)):
    try:
        db.delete_task(task_id, user["id"], user["role"])
        return {"ok": True}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


# 托管 Vue 3 构建产物
if FRONTEND_VUE_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_VUE_DIST), html=True), name="static")
