"""达成度计算 Web 服务

启动：python -m uvicorn api:app --reload --port 8000
访问：http://127.0.0.1:8000
"""

import io
import tempfile
from pathlib import Path

import openpyxl
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import calc_engine as eng

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="课程目标达成度分析系统")


# ============================================================
# 配置读写：把 calc_engine 里的硬编码配置暴露给前端
# ============================================================

def get_config():
    return {
        "method": eng.METHOD,
        "matrix": eng.MATRIX,
        "paper": eng.PAPER_STRUCTURE,
    }


@app.get("/api/config")
def read_config():
    return get_config()


@app.post("/api/config")
def save_config(payload: dict):
    """保存配置到引擎模块（内存态，重启后恢复默认）。"""
    try:
        method = payload["method"]
        matrix = payload["matrix"]
        paper = payload["paper"]

        # 基本校验
        daily_sum = sum(method["平时环节"].values())
        if abs(daily_sum - 1.0) > 1e-6:
            raise ValueError(f"平时环节占比之和应为 1，实际 {daily_sum}")
        if abs(method["平时占比"] + method["期末占比"] - 1.0) > 1e-6:
            raise ValueError("平时占比 + 期末占比 应为 1")

        questions = [q for g in paper for q in g["小题"]]
        total = sum(q["满分"] for q in questions)
        if total != 100:
            raise ValueError(f"试卷总分应为 100，实际 {total}")

        eng.METHOD = method
        eng.MATRIX = matrix
        eng.PAPER_STRUCTURE = paper
        return {"ok": True, "message": "配置已保存"}
    except KeyError as e:
        raise HTTPException(400, f"配置缺少字段：{e}")
    except ValueError as e:
        raise HTTPException(400, str(e))


# ============================================================
# 模板生成
# ============================================================

def _save_upload(file: UploadFile) -> Path:
    """把上传文件落到临时目录，返回路径。"""
    suffix = Path(file.filename or "upload.xlsx").suffix or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file.file.read())
    tmp.close()
    return Path(tmp.name)


@app.get("/api/template/daily")
def template_daily():
    """生成平时成绩录入模板。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "平时成绩"
    headers = ["学号", "姓名"] + list(eng.METHOD["平时环节"].keys())
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        ws.cell(1, c).font = openpyxl.styles.Font(bold=True)
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 14
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=daily_template.xlsx; filename*=UTF-8''%E5%B9%B3%E6%97%B6%E6%88%90%E7%BB%A9%E5%BD%95%E5%85%A5%E6%A8%A1%E6%9D%BF.xlsx"},
    )


@app.get("/api/template/final")
def template_final():
    """生成期末小题成绩录入模板。"""
    questions = eng.validate_structure()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "期末成绩"
    headers = ["学号", "姓名"] + [
        f"第{q['题号']}题({q['满分']}分/{q['目标']})" for q in questions
    ]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        ws.cell(1, c).font = openpyxl.styles.Font(bold=True)
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=final_template.xlsx; filename*=UTF-8''%E6%9C%9F%E6%9C%AB%E5%B0%8F%E9%A2%98%E6%88%90%E7%BB%A9%E5%BD%95%E5%85%A5%E6%A8%A1%E6%9D%BF.xlsx"},
    )


# ============================================================
# 计算
# ============================================================

@app.post("/api/calculate")
async def calculate(
    daily_file: UploadFile = File(...),
    final_file: UploadFile = File(...),
):
    """上传两个成绩表，返回达成度报表。"""
    daily_path = _save_upload(daily_file)
    final_path = _save_upload(final_file)
    try:
        questions = eng.validate_structure()
        link_weights = eng.step1_link_weights()
        output, full = eng.step2_output_weights(link_weights)

        # 临时把引擎的读取路径指向上传文件
        orig = eng.load_rows
        eng.load_rows = lambda name: _read_rows(
            daily_path if "平时" in name else final_path
        )
        try:
            students = eng.load_daily_students(verbose=False)
            matched = eng.load_final_scores(students, questions)
        finally:
            eng.load_rows = orig

        report = eng.step5_report(students, output, full, questions)

        return {
            "ok": True,
            "student_count": len(students),
            "matched": matched,
            "link_weights": link_weights,
            "output_weights": output,
            "full_scores": full,
            "paper_target_full": eng.paper_target_full(questions),
            "report": report,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        daily_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)


def _read_rows(path: Path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    return [list(r) for r in ws.iter_rows(values_only=True)]


# ============================================================
# 静态页面
# ============================================================

if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="static")
