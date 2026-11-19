"""公共课程规则模板 Excel 生成与导入模块

供管理员下载标准《课程规则配置模板.xlsx》填写后一键上传，发布为全院公共课程模板。
工作簿包含 3 个清晰工作表：
  - Sheet1「1_课程与评定方法」：课程名称、代码、学期、合格阈值、平时/期末占比、平时细项环节及占比
  - Sheet2「2_目标与环节矩阵」：各课程目标名称、目标说明、在各考核环节中的相对比例
  - Sheet3「3_期末试卷结构」：每行一道小题（大题名称、题号、小题满分、所属课程目标）
"""

import io
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

import calc_engine as eng

THIN = Side(style="thin", color="CCCCCC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="E0E7FF")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def build_course_config_template(
    meta: dict | None = None,
    threshold: float = 0.65,
    method: dict | None = None,
    matrix: dict | None = None,
    paper: list | None = None,
    target_descriptions: dict | None = None,
) -> io.BytesIO:
    """生成标准《课程规则配置模板.xlsx》（预填当前配置作为示例，管理员改完即可上传）。"""
    meta = meta or {"课程名称": "高等数学A（II）", "课程代码": "MATH1002", "学期": "2023-2024-2", "班级": "23智能制造1班"}
    method = method or eng.METHOD
    matrix = matrix or eng.MATRIX
    paper = paper or eng.PAPER_STRUCTURE
    target_descriptions = target_descriptions or {}

    wb = openpyxl.Workbook()

    # ---------- Sheet 1: 1_课程与评定方法 ----------
    ws1 = wb.active
    ws1.title = "1_课程与评定方法"
    rows1 = [
        ["配置项", "数值", "填写说明"],
        ["课程名称", meta.get("课程名称", ""), "必填，如：高等数学A（II）"],
        ["课程代码", meta.get("课程代码", ""), "选填，如：MATH1002"],
        ["开课学期", meta.get("学期", ""), "必填，如：2024-2025-1"],
        ["默认班级", meta.get("班级", ""), "选填，教师选用后可自行修改班级"],
        ["合格阈值", threshold, "0~1 之间，默认 0.65（即 65%）"],
        ["平时占比", method["平时占比"], "与期末占比之和须为 1"],
        ["期末占比", method["期末占比"], "与平时占比之和须为 1"],
        [],
        ["平时环节名称", "占平时比例", "说明（所有平时环节比例之和须为 1）"],
    ]
    for link_name, ratio in method["平时环节"].items():
        rows1.append([link_name, ratio, "可增删行，需与 Sheet2 列名一致"])

    for r_idx, row in enumerate(rows1, 1):
        for c_idx, val in enumerate(row, 1):
            cell = ws1.cell(r_idx, c_idx, val)
            cell.border = BORDER
            if r_idx in (1, 10):
                cell.font = Font(bold=True)
                cell.fill = HEAD_FILL
                cell.alignment = CENTER
    ws1.column_dimensions["A"].width = 18
    ws1.column_dimensions["B"].width = 22
    ws1.column_dimensions["C"].width = 42

    # ---------- Sheet 2: 2_目标与环节矩阵 ----------
    ws2 = wb.create_sheet("2_目标与环节矩阵")
    links = list(method["平时环节"].keys()) + ["期末考试"]
    headers2 = ["课程目标", "目标说明"] + links
    for c_idx, h in enumerate(headers2, 1):
        cell = ws2.cell(1, c_idx, h)
        cell.font = Font(bold=True)
        cell.fill = HEAD_FILL
        cell.alignment = CENTER
        cell.border = BORDER

    for r_idx, (tg, row_map) in enumerate(matrix.items(), start=2):
        ws2.cell(r_idx, 1, tg).alignment = CENTER
        ws2.cell(r_idx, 2, target_descriptions.get(tg, ""))
        for j, l in enumerate(links, start=3):
            ws2.cell(r_idx, j, row_map.get(l, 0)).alignment = CENTER
        for c_idx in range(1, len(headers2) + 1):
            ws2.cell(r_idx, c_idx).border = BORDER

    ws2.column_dimensions["A"].width = 16
    ws2.column_dimensions["B"].width = 40
    for c_idx in range(3, len(headers2) + 1):
        ws2.column_dimensions[openpyxl.utils.get_column_letter(c_idx)].width = 14

    # ---------- Sheet 3: 3_期末试卷结构 ----------
    ws3 = wb.create_sheet("3_期末试卷结构")
    headers3 = ["大题名称", "题号", "小题满分", "所属课程目标"]
    for c_idx, h in enumerate(headers3, 1):
        cell = ws3.cell(1, c_idx, h)
        cell.font = Font(bold=True)
        cell.fill = HEAD_FILL
        cell.alignment = CENTER
        cell.border = BORDER

    r_idx = 2
    for grp in paper:
        for q in grp["小题"]:
            vals = [grp["大题"], q["题号"], q["满分"], q["目标"]]
            for c_idx, val in enumerate(vals, 1):
                cell = ws3.cell(r_idx, c_idx, val)
                cell.alignment = CENTER
                cell.border = BORDER
            r_idx += 1

    ws3.column_dimensions["A"].width = 18
    ws3.column_dimensions["B"].width = 10
    ws3.column_dimensions["C"].width = 12
    ws3.column_dimensions["D"].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def parse_course_config_excel(path: Path) -> dict:
    """解析管理员上传的《课程规则配置模板.xlsx》，返回可直接入库的配置字典。"""
    wb = openpyxl.load_workbook(path, data_only=True)
    sheet_names = wb.sheetnames
    if len(sheet_names) < 3:
        raise ValueError(
            "课程规则模板必须包含 3 个工作表：1_课程与评定方法、2_目标与环节矩阵、3_期末试卷结构"
        )

    ws1, ws2, ws3 = wb[sheet_names[0]], wb[sheet_names[1]], wb[sheet_names[2]]

    # ---------- 解析 Sheet 1 ----------
    kv = {}
    daily_links = {}
    in_links_section = False
    for r in ws1.iter_rows(values_only=True):
        k = eng.clean(r[0]) if len(r) > 0 else None
        v = r[1] if len(r) > 1 else None
        if not k:
            continue
        if "平时环节" in k:
            in_links_section = True
            continue
        if k == "配置项":
            continue
        if in_links_section:
            num = eng.to_num(v)
            if num is None or num < 0:
                raise ValueError(f"平时环节「{k}」的比例无效：{v}")
            daily_links[k] = num
        else:
            kv[k] = v

    if not daily_links:
        raise ValueError("Sheet1 未配置任何平时考核环节")

    daily_ratio = eng.to_num(kv.get("平时占比"))
    final_ratio = eng.to_num(kv.get("期末占比"))
    if daily_ratio is None or final_ratio is None:
        raise ValueError("Sheet1 缺少平时占比或期末占比")
    if abs(daily_ratio + final_ratio - 1.0) > 1e-6:
        raise ValueError(f"平时占比({daily_ratio}) + 期末占比({final_ratio}) 必须等于 1")
    if abs(sum(daily_links.values()) - 1.0) > 1e-6:
        raise ValueError(f"平时各细项环节比例之和必须为 1，实际为 {sum(daily_links.values()):.2f}")

    threshold = eng.to_num(kv.get("合格阈值"))
    threshold = threshold if (threshold is not None and 0 < threshold <= 1) else 0.65

    meta = {
        "课程名称": eng.clean(kv.get("课程名称")) or "导入课程模板",
        "课程代码": eng.clean(kv.get("课程代码")) or "",
        "学期": eng.clean(kv.get("开课学期")) or eng.clean(kv.get("学期")) or "2024-2025-1",
        "班级": eng.clean(kv.get("默认班级")) or "",
    }
    method = {
        "平时占比": daily_ratio,
        "期末占比": final_ratio,
        "平时环节": daily_links,
    }

    # ---------- 解析 Sheet 2 ----------
    rows2 = [list(r) for r in ws2.iter_rows(values_only=True)]
    if len(rows2) < 2:
        raise ValueError("Sheet2 目标与环节矩阵不能为空")
    headers2 = [eng.clean(c) or "" for c in rows2[0]]
    expected_links = list(daily_links.keys()) + ["期末考试"]
    link_col_map = {}
    for link in expected_links:
        idx = eng.match_column(headers2, link)
        if idx is None:
            raise ValueError(f"Sheet2 缺少考核环节列：「{link}」")
        link_col_map[link] = idx

    desc_col = eng.match_column(headers2, "目标说明")
    matrix = {}
    target_descriptions = {}
    for r in rows2[1:]:
        tg = eng.clean(r[0]) if len(r) > 0 else None
        if not tg:
            continue
        row_map = {}
        for link, c_idx in link_col_map.items():
            v = eng.to_num(r[c_idx]) if c_idx < len(r) else 0.0
            row_map[link] = v if v is not None else 0.0
        matrix[tg] = row_map
        if desc_col is not None and desc_col < len(r):
            target_descriptions[tg] = eng.clean(r[desc_col]) or ""

    if not matrix:
        raise ValueError("Sheet2 未解析到任何课程目标")

    # ---------- 解析 Sheet 3 ----------
    rows3 = [list(r) for r in ws3.iter_rows(values_only=True)]
    if len(rows3) < 2:
        raise ValueError("Sheet3 期末试卷结构不能为空")

    groups_order = []
    groups_map = {}
    q_seq = 1
    for r in rows3[1:]:
        grp_name = eng.clean(r[0]) if len(r) > 0 else None
        full_score = eng.to_num(r[2]) if len(r) > 2 else None
        target = eng.clean(r[3]) if len(r) > 3 else None
        if not grp_name and full_score is None and not target:
            continue
        if not grp_name or full_score is None or not target:
            raise ValueError(f"Sheet3 存在不完整的题目行：{r[:4]}")
        if target not in matrix:
            raise ValueError(f"Sheet3 第 {q_seq} 题的课程目标「{target}」不在 Sheet2 矩阵中")
        if grp_name not in groups_map:
            groups_order.append(grp_name)
            groups_map[grp_name] = []
        groups_map[grp_name].append(
            {"题号": q_seq, "满分": full_score, "目标": target}
        )
        q_seq += 1

    paper = [{"大题": g, "小题": groups_map[g]} for g in groups_order]

    # 用引擎做一次全量逻辑校验（总分100、列和不为0、期末权重目标有题）
    old_m, old_mat, old_p = eng.METHOD, eng.MATRIX, eng.PAPER_STRUCTURE
    try:
        eng.METHOD, eng.MATRIX, eng.PAPER_STRUCTURE = method, matrix, paper
        eng.validate_structure()
        lw = eng.step1_link_weights()
        eng.step2_output_weights(lw)
    finally:
        eng.METHOD, eng.MATRIX, eng.PAPER_STRUCTURE = old_m, old_mat, old_p

    return {
        "meta": meta,
        "threshold": threshold,
        "method": method,
        "matrix": matrix,
        "paper": paper,
        "target_descriptions": target_descriptions,
    }
