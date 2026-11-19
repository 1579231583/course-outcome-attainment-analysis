"""达成度报表导出模块

生成包含 3 个工作表的标准归档 Excel 工作簿：
  1. Sheet1「达成度计算表」：
     按学校现有《达成度计算表》格式逐格对齐（标题 / 课程信息 / 目标表头 / 各环节理论满分 /
     学生逐人逐环节折算得分 / 各子项均分公式 / 各目标实际得分公式 / 达成度公式）。
  2. Sheet2「课程目标评价汇总表」：
     按《达成度计算流程.md》第三节的评价终表样式排版（环节总分行 + 各目标的理论满分行与实际得分行 + 达成度与达标结论），
     供教师直接复制进课程达成度分析 Word/PPT 报告。
  3. Sheet3「全班学生得分明细表」：
     包含每位学生的平时原始得分、期末各小题原始得分、各目标期末卷面得分及个人各目标达成度，供工程认证备查。
"""

import io

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
HEAD_FILL = PatternFill("solid", fgColor="EEF2FF")
SUB_FILL = PatternFill("solid", fgColor="F8FAFC")
PASS_FILL = PatternFill("solid", fgColor="DCFCE7")
FAIL_FILL = PatternFill("solid", fgColor="FEE2E2")


def _student_link_score(student, target, link, output, questions, paper_full):
    """单个学生在某目标某环节的折算得分。

    平时环节：原始百分制分 × 产出权重
    期末考试：(该目标卷面实得 ÷ 该目标卷面满分) × 该目标期末设定分值
              （若该目标不考期末，即期末产出权重或卷面满分为 0，则返回 0.0）
    """
    if link != "期末考试":
        return float(student["平时"][link]) * output[target][link]

    if output[target].get("期末考试", 0) <= 0 or paper_full.get(target, 0) <= 0:
        return 0.0

    target_qs = [q["题号"] for q in questions if q["目标"] == target]
    got = sum(
        float(student["期末"].get(qn, student["期末"].get(str(qn), 0)))
        for qn in target_qs
    )
    return got / paper_full[target] * (output[target]["期末考试"] * 100)


def _build_calc_sheet(ws, students, output, full, questions, paper_full, meta):
    """Sheet 1：按学校标准格式生成《达成度计算表》。"""
    targets = list(output.keys())
    links = list(output[targets[0]].keys())
    n_cols = 3 + len(targets) * len(links)

    # ---------- 第1行：标题 ----------
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    c = ws.cell(1, 1, "达成度计算表")
    c.font = Font(size=16, bold=True)
    c.alignment = CENTER
    ws.row_dimensions[1].height = 30

    # ---------- 第2行：课程信息 ----------
    c1_end = max(2, min(4, n_cols // 3))
    c2_end = max(c1_end + 1, min(8, (n_cols * 2) // 3))
    info = [
        (1, c1_end, f"课程名称：{meta.get('课程名称', '')}"),
        (c1_end + 1, c2_end, f"学期：{meta.get('学期', '')}"),
        (c2_end + 1, n_cols, f"班级：{meta.get('班级', '')}"),
    ]
    for start, end, text in info:
        if end >= start and start <= n_cols:
            actual_end = min(end, n_cols)
            if actual_end > start:
                ws.merge_cells(
                    start_row=2, start_column=start, end_row=2, end_column=actual_end
                )
            cell = ws.cell(2, start, text)
            cell.alignment = Alignment(horizontal="left", vertical="center")

    # ---------- 第3行：目标表头（合并） ----------
    for col, name in ((1, "序号"), (2, "学号"), (3, "姓名")):
        ws.merge_cells(start_row=3, start_column=col, end_row=4, end_column=col)
        cell = ws.cell(3, col, name)
        cell.font = Font(bold=True)
        cell.alignment = CENTER
        cell.fill = HEAD_FILL
        ws.cell(3, col).border = BORDER
        ws.cell(4, col).border = BORDER

    col = 4
    for t in targets:
        end = col + len(links) - 1
        if end > col:
            ws.merge_cells(start_row=3, start_column=col, end_row=3, end_column=end)
        # 若理论满分为整数则显示整数，否则保留 2 位小数，消除 64 vs 64.40 歧义
        full_val = full[t]
        full_str = f"{full_val:.0f}" if abs(full_val - round(full_val)) < 1e-4 else f"{full_val:.2f}"
        cell = ws.cell(3, col, f"{t}（{full_str}分）")
        cell.font = Font(bold=True)
        cell.alignment = CENTER
        cell.fill = HEAD_FILL
        for cc in range(col, end + 1):
            ws.cell(3, cc).border = BORDER
            ws.cell(3, cc).fill = HEAD_FILL
        col = end + 1

    # ---------- 第4行：各环节理论满分 ----------
    col = 4
    for t in targets:
        for link in links:
            cell = ws.cell(4, col, f"{link}{output[t][link] * 100:.2f}分")
            cell.alignment = CENTER
            cell.border = BORDER
            cell.fill = SUB_FILL
            col += 1

    # ---------- 第5行起：学生明细 ----------
    row = 5
    for i, s in enumerate(students, 1):
        ws.cell(row, 1, i).alignment = CENTER
        ws.cell(row, 2, s["学号"]).alignment = CENTER
        ws.cell(row, 3, s["姓名"]).alignment = CENTER
        col = 4
        for t in targets:
            for link in links:
                v = _student_link_score(s, t, link, output, questions, paper_full)
                cell = ws.cell(row, col, round(v, 4))
                cell.alignment = CENTER
                col += 1
        for cc in range(1, n_cols + 1):
            ws.cell(row, cc).border = BORDER
        row += 1

    first_data, last_data = 5, row - 1

    # ---------- 各子项得分（全班均分） ----------
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = ws.cell(row, 1, "各子项得分")
    cell.font = Font(bold=True)
    cell.alignment = CENTER
    for cc in range(1, 4):
        ws.cell(row, cc).border = BORDER

    sub_avg = {}
    col = 4
    for t in targets:
        for link in links:
            letter = get_column_letter(col)
            cell = ws.cell(row, col, f"=AVERAGE({letter}{first_data}:{letter}{last_data})")
            cell.number_format = "0.0000"
            cell.alignment = CENTER
            cell.border = BORDER
            sub_avg[(t, link)] = col
            col += 1
    sub_row = row
    row += 1

    # ---------- 各目标实际得分 ----------
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = ws.cell(row, 1, "各目标实际得分")
    cell.font = Font(bold=True)
    cell.alignment = CENTER
    for cc in range(1, 4):
        ws.cell(row, cc).border = BORDER

    total_row = row
    col = 4
    for t in targets:
        end = col + len(links) - 1
        if end > col:
            ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=end)
        parts = "+".join(
            f"{get_column_letter(sub_avg[(t, l)])}{sub_row}" for l in links
        )
        cell = ws.cell(row, col, f"={parts}")
        cell.number_format = "0.0000"
        cell.alignment = CENTER
        for cc in range(col, end + 1):
            ws.cell(row, cc).border = BORDER
        col = end + 1
    row += 1

    # ---------- 达成度 ----------
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = ws.cell(row, 1, "达成度")
    cell.font = Font(bold=True)
    cell.alignment = CENTER
    for cc in range(1, 4):
        ws.cell(row, cc).border = BORDER

    col = 4
    for t in targets:
        end = col + len(links) - 1
        if end > col:
            ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=end)
        letter = get_column_letter(col)
        denom = full[t] if full[t] > 0 else 1.0
        cell = ws.cell(row, col, f"={letter}{total_row}/{denom:.4f}")
        cell.number_format = "0.0000"
        cell.alignment = CENTER
        for cc in range(col, end + 1):
            ws.cell(row, cc).border = BORDER
        col = end + 1

    # ---------- 列宽 ----------
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 10
    for cc in range(4, n_cols + 1):
        ws.column_dimensions[get_column_letter(cc)].width = 14


def _build_summary_sheet(ws, students, output, full, questions, paper_full, meta, threshold):
    """Sheet 2：《课程目标评价汇总表》（对应文档第三节的最终报表展示）。"""
    targets = list(output.keys())
    links = list(output[targets[0]].keys())
    n_students = len(students)
    # 列：课程目标 | 评价依据 | 各环节... | 合计 | 达成度 | 评价结果
    n_cols = 2 + len(links) + 3

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    c = ws.cell(1, 1, "课程目标评价达成情况汇总表")
    c.font = Font(size=15, bold=True)
    c.alignment = CENTER
    ws.row_dimensions[1].height = 28

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    meta_str = (
        f"课程名称：{meta.get('课程名称', '')}    "
        f"学期：{meta.get('学期', '')}    "
        f"班级：{meta.get('班级', '')}    "
        f"样本人数：{n_students}人    "
        f"达标阈值：{threshold * 100:.0f}%"
    )
    c2 = ws.cell(2, 1, meta_str)
    c2.alignment = Alignment(horizontal="left", vertical="center")

    headers = ["课程目标", "评价依据"] + links + ["合计", "达成度", "评价结果"]
    for idx, h in enumerate(headers, 1):
        cell = ws.cell(3, idx, h)
        cell.font = Font(bold=True)
        cell.alignment = CENTER
        cell.fill = HEAD_FILL
        cell.border = BORDER

    # 第4行：环节总分
    ws.cell(4, 1, "—").alignment = CENTER
    ws.cell(4, 2, "环节总分").alignment = CENTER
    ws.cell(4, 2).font = Font(bold=True)
    for j, link in enumerate(links, start=3):
        link_total = sum(output[t][link] for t in targets) * 100
        ws.cell(4, j, round(link_total, 2)).alignment = CENTER
    ws.cell(4, 3 + len(links), 100.0).alignment = CENTER
    ws.cell(4, 4 + len(links), "—").alignment = CENTER
    ws.cell(4, 5 + len(links), "—").alignment = CENTER
    for cc in range(1, n_cols + 1):
        ws.cell(4, cc).border = BORDER
        ws.cell(4, cc).fill = SUB_FILL

    row = 5
    for t in targets:
        # 理论满分行
        ws.merge_cells(start_row=row, start_column=1, end_row=row + 1, end_column=1)
        t_cell = ws.cell(row, 1, t)
        t_cell.font = Font(bold=True)
        t_cell.alignment = CENTER

        ws.cell(row, 2, "理论满分").alignment = CENTER
        for j, link in enumerate(links, start=3):
            c_cell = ws.cell(row, j, round(output[t][link] * 100, 2))
            c_cell.number_format = "0.00"
            c_cell.alignment = CENTER
        f_cell = ws.cell(row, 3 + len(links), round(full[t], 2))
        f_cell.number_format = "0.00"
        f_cell.font = Font(bold=True)
        f_cell.alignment = CENTER

        # 实际得分行
        ws.cell(row + 1, 2, "实际得分").alignment = CENTER
        actual_sum = 0.0
        for j, link in enumerate(links, start=3):
            avg_score = (
                sum(_student_link_score(s, t, link, output, questions, paper_full) for s in students)
                / n_students
            )
            actual_sum += avg_score
            a_cell = ws.cell(row + 1, j, round(avg_score, 2))
            a_cell.number_format = "0.00"
            a_cell.alignment = CENTER

        tot_cell = ws.cell(row + 1, 3 + len(links), round(actual_sum, 2))
        tot_cell.number_format = "0.00"
        tot_cell.font = Font(bold=True)
        tot_cell.alignment = CENTER

        # 达成度与结论（跨两行合并）
        ach = actual_sum / full[t] if full[t] > 0 else 0.0
        passed = ach >= threshold

        ach_col = 4 + len(links)
        res_col = 5 + len(links)
        ws.merge_cells(start_row=row, start_column=ach_col, end_row=row + 1, end_column=ach_col)
        ws.merge_cells(start_row=row, start_column=res_col, end_row=row + 1, end_column=res_col)

        ach_cell = ws.cell(row, ach_col, f"{ach * 100:.1f}%")
        ach_cell.font = Font(bold=True)
        ach_cell.alignment = CENTER

        res_cell = ws.cell(row, res_col, "达标" if passed else "未达标")
        res_cell.font = Font(bold=True, color="065F46" if passed else "991B1B")
        res_cell.alignment = CENTER
        res_cell.fill = PASS_FILL if passed else FAIL_FILL
        ws.cell(row + 1, res_col).fill = PASS_FILL if passed else FAIL_FILL

        for r_idx in (row, row + 1):
            for cc in range(1, n_cols + 1):
                ws.cell(r_idx, cc).border = BORDER

        row += 2

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 12
    for cc in range(3, n_cols + 1):
        ws.column_dimensions[get_column_letter(cc)].width = 14


def _build_detail_sheet(ws, students, output, full, questions, paper_full):
    """Sheet 3：《全班学生得分明细表》（平时原始分 + 期末各小题原始分 + 个人各目标达成度）。"""
    targets = list(output.keys())
    all_links = list(output[targets[0]].keys())
    daily_links = [l for l in all_links if l != "期末考试"]

    headers = (
        ["序号", "学号", "姓名"]
        + [f"平时-{l}(100分)" for l in daily_links]
        + [f"第{q['题号']}题({q['满分']}分/{q['目标']})" for q in questions]
        + [f"{t}卷面实得({paper_full.get(t, 0)}分)" for t in targets]
        + [f"{t}折算总分({full[t]:.2f}分)" for t in targets]
        + [f"{t}个人达成度" for t in targets]
    )

    for c_idx, h in enumerate(headers, 1):
        cell = ws.cell(1, c_idx, h)
        cell.font = Font(bold=True)
        cell.alignment = CENTER
        cell.fill = HEAD_FILL
        cell.border = BORDER

    for i, s in enumerate(students, 1):
        r = i + 1
        row_vals = [i, s["学号"], s["姓名"]]
        for l in daily_links:
            row_vals.append(round(float(s["平时"][l]), 2))
        for q in questions:
            qn = q["题号"]
            v = float(s["期末"].get(qn, s["期末"].get(str(qn), 0)))
            row_vals.append(round(v, 2))

        # 各目标卷面实得
        for t in targets:
            t_qs = [q["题号"] for q in questions if q["目标"] == t]
            got = sum(float(s["期末"].get(qn, s["期末"].get(str(qn), 0))) for qn in t_qs)
            row_vals.append(round(got, 2))

        # 各目标折算总分与个人达成度
        tot_scores = {}
        for t in targets:
            t_tot = sum(
                _student_link_score(s, t, l, output, questions, paper_full)
                for l in all_links
            )
            tot_scores[t] = t_tot
            row_vals.append(round(t_tot, 2))

        for t in targets:
            ach = (tot_scores[t] / full[t] * 100) if full[t] > 0 else 0.0
            row_vals.append(f"{ach:.1f}%")

        for c_idx, val in enumerate(row_vals, 1):
            cell = ws.cell(r, c_idx, val)
            cell.alignment = CENTER
            cell.border = BORDER

    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 10
    for cc in range(4, len(headers) + 1):
        ws.column_dimensions[get_column_letter(cc)].width = 16


def build_workbook(students, output, full, questions, paper_full, meta=None, threshold=0.65):
    """生成包含 3 个工作表的达成度报表工作簿，返回 BytesIO。"""
    meta = meta or {}
    wb = openpyxl.Workbook()

    # Sheet 1：达成度计算表（学校标准格式）
    ws_calc = wb.active
    ws_calc.title = "达成度计算表"
    _build_calc_sheet(ws_calc, students, output, full, questions, paper_full, meta)

    # Sheet 2：课程目标评价汇总表（终表）
    ws_sum = wb.create_sheet(title="课程目标评价汇总表")
    _build_summary_sheet(
        ws_sum, students, output, full, questions, paper_full, meta, threshold
    )

    # Sheet 3：全班学生得分明细表
    ws_detail = wb.create_sheet(title="全班学生得分明细表")
    _build_detail_sheet(ws_detail, students, output, full, questions, paper_full)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
