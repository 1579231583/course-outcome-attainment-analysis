"""达成度终极 4-Sheet 归档报表导出模块

融合学校正式《目标达成评价表》规范版式与系统高精度明细计算优势，一键生成可直接打印签字存档的 Excel 工作簿：
  1. Sheet1「目标达成评价表」：
     封面主表！包含课程基本信息（课程名称/类别/任课教师/学分/代码/学时）、样本信息、
     带跨表公式联动的课程目标评价达成情况表（直接引用 Sheet2「达成度计算表」均值行）、
     达标/未达标高亮结论，以及底部的「达成情况分析」「拟改进的措施」「评价人（签字）」栏。
  2. Sheet2「达成度计算表」：
     逐人逐目标逐环节折算明细 + 最右侧「总评折算分（=SUM）」列 + 底部「各子项得分（=AVERAGE）」
     「各目标实际得分（=SUM）」「达成度」动态公式。
  3. Sheet3「大纲与权重依据」：
     清晰展示成绩评定方法、大纲原始对应比例矩阵、列归一化产出权重与理论满分（带 Excel 公式），方便教务审计溯源。
  4. Sheet4「全班学生得分明细表」：
     包含平时原始得分、期末各小题原始得分、各目标卷面总分及个人各目标达成度。
"""

import io

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)
HEAD_FILL = PatternFill("solid", fgColor="EEF2FF")
SUB_FILL = PatternFill("solid", fgColor="F8FAFC")
PASS_FILL = PatternFill("solid", fgColor="DCFCE7")
FAIL_FILL = PatternFill("solid", fgColor="FEE2E2")


def _student_link_score(student, target, link, output, questions, paper_full):
    """单个学生在某目标某环节的折算得分。"""
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


def _apply_border(ws, r1, c1, r2, c2, fill=None):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(r, c).border = BORDER
            if fill is not None:
                ws.cell(r, c).fill = fill


def _build_calc_sheet(ws, students, output, full, questions, paper_full, meta):
    """Sheet 2：《达成度计算表》，返回 (sub_avg_row, sub_avg_col_map) 供 Sheet 1 跨表公式引用。"""
    targets = list(output.keys())
    links = list(output[targets[0]].keys())
    score_cols = len(targets) * len(links)
    total_col = 4 + score_cols  # 最右侧总评折算分列
    n_cols = total_col

    # 第1行：标题
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    c = ws.cell(1, 1, "达成度计算表")
    c.font = Font(size=16, bold=True)
    c.alignment = CENTER
    ws.row_dimensions[1].height = 30

    # 第2行：课程信息
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
                ws.merge_cells(start_row=2, start_column=start, end_row=2, end_column=actual_end)
            cell = ws.cell(2, start, text)
            cell.alignment = Alignment(horizontal="left", vertical="center")

    # 第3~4行：表头
    for col, name in ((1, "序号"), (2, "学号"), (3, "姓名")):
        ws.merge_cells(start_row=3, start_column=col, end_row=4, end_column=col)
        cell = ws.cell(3, col, name)
        cell.font = Font(bold=True)
        cell.alignment = CENTER
        _apply_border(ws, 3, col, 4, col, HEAD_FILL)

    col = 4
    for t in targets:
        end = col + len(links) - 1
        if end > col:
            ws.merge_cells(start_row=3, start_column=col, end_row=3, end_column=end)
        full_val = full[t]
        full_str = f"{full_val:.0f}" if abs(full_val - round(full_val)) < 1e-4 else f"{full_val:.2f}"
        cell = ws.cell(3, col, f"{t}（{full_str}分）")
        cell.font = Font(bold=True)
        cell.alignment = CENTER
        _apply_border(ws, 3, col, 3, end, HEAD_FILL)
        col = end + 1

    ws.merge_cells(start_row=3, start_column=total_col, end_row=4, end_column=total_col)
    t_head = ws.cell(3, total_col, "总评折算分")
    t_head.font = Font(bold=True)
    t_head.alignment = CENTER
    _apply_border(ws, 3, total_col, 4, total_col, HEAD_FILL)

    # 第4行：各环节理论满分
    col = 4
    for t in targets:
        for link in links:
            cell = ws.cell(4, col, f"{link}{output[t][link] * 100:.2f}分")
            cell.alignment = CENTER
            cell.border = BORDER
            cell.fill = SUB_FILL
            col += 1

    # 第5行起：学生明细
    row = 5
    last_score_letter = get_column_letter(total_col - 1)
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
        sum_cell = ws.cell(row, total_col, f"=SUM(D{row}:{last_score_letter}{row})")
        sum_cell.number_format = "0.00"
        sum_cell.alignment = CENTER
        _apply_border(ws, row, 1, row, n_cols)
        row += 1

    first_data, last_data = 5, row - 1

    # 各子项得分（全班均分）
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = ws.cell(row, 1, "各子项得分")
    cell.font = Font(bold=True)
    cell.alignment = CENTER
    _apply_border(ws, row, 1, row, 3, SUB_FILL)

    sub_avg = {}
    col = 4
    for t in targets:
        for link in links:
            letter = get_column_letter(col)
            c_avg = ws.cell(row, col, f"=AVERAGE({letter}{first_data}:{letter}{last_data})")
            c_avg.number_format = "0.0000"
            c_avg.alignment = CENTER
            c_avg.border = BORDER
            sub_avg[(t, link)] = col
            col += 1

    tot_letter = get_column_letter(total_col)
    tot_avg = ws.cell(row, total_col, f"=AVERAGE({tot_letter}{first_data}:{tot_letter}{last_data})")
    tot_avg.number_format = "0.00"
    tot_avg.alignment = CENTER
    tot_avg.border = BORDER
    sub_row = row
    row += 1

    # 各目标实际得分
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = ws.cell(row, 1, "各目标实际得分")
    cell.font = Font(bold=True)
    cell.alignment = CENTER
    _apply_border(ws, row, 1, row, 3, SUB_FILL)

    total_row = row
    col = 4
    for t in targets:
        end = col + len(links) - 1
        if end > col:
            ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=end)
        s_letter = get_column_letter(col)
        e_letter = get_column_letter(end)
        c_sum = ws.cell(row, col, f"=SUM({s_letter}{sub_row}:{e_letter}{sub_row})")
        c_sum.number_format = "0.0000"
        c_sum.alignment = CENTER
        _apply_border(ws, row, col, row, end)
        col = end + 1
    ws.cell(row, total_col, "").border = BORDER
    row += 1

    # 达成度
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = ws.cell(row, 1, "达成度")
    cell.font = Font(bold=True)
    cell.alignment = CENTER
    _apply_border(ws, row, 1, row, 3, SUB_FILL)

    col = 4
    for t in targets:
        end = col + len(links) - 1
        if end > col:
            ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=end)
        letter = get_column_letter(col)
        denom = full[t] if full[t] > 0 else 1.0
        c_ach = ws.cell(row, col, f"={letter}{total_row}/{denom:.4f}")
        c_ach.number_format = "0.0%"
        c_ach.font = Font(bold=True)
        c_ach.alignment = CENTER
        _apply_border(ws, row, col, row, end)
        col = end + 1
    ws.cell(row, total_col, "").border = BORDER

    # 列宽
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 10
    for cc in range(4, n_cols + 1):
        ws.column_dimensions[get_column_letter(cc)].width = 13.5

    return sub_row, sub_avg


def _build_evaluation_sheet(
    ws,
    students,
    output,
    full,
    questions,
    paper_full,
    meta,
    threshold,
    sub_row,
    sub_avg,
    analysis_text="",
    improvement_notes="",
):
    """Sheet 1：《目标达成评价表》（学校正式存档打印封面主表，含跨表公式联动与签字栏）。"""
    targets = list(output.keys())
    links = list(output[targets[0]].keys())
    n_students = len(students)
    # 列：课程目标(1) | 评价依据(2) | 各环节(3..2+L) | 合计(3+L) | 评价结果(4+L) | 达标结论(5+L)
    n_cols = max(8, 5 + len(links))
    sum_col = 3 + len(links)
    ach_col = 4 + len(links)
    res_col = 5 + len(links)

    # 第1行：主标题
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    t1 = ws.cell(1, 1, "课程目标达成评价表")
    t1.font = Font(size=16, bold=True)
    t1.alignment = CENTER
    ws.row_dimensions[1].height = 30

    # 第3~5行：课程基本信息（严格对齐学校原表）
    ws.merge_cells("A3:A5")
    c_info = ws.cell(3, 1, "课程基本信息")
    c_info.font = Font(bold=True)
    c_info.alignment = CENTER
    _apply_border(ws, 3, 1, 5, 1, SUB_FILL)

    mid_end = max(5, n_cols - 3)
    right_lbl_start = mid_end + 1
    right_lbl_end = n_cols - 1

    info_rows = [
        (3, "课程名称", meta.get("课程名称", ""), "课程类别", meta.get("课程类别", "专业必修课")),
        (4, "任课教师", meta.get("任课教师", ""), "学分", meta.get("学分", "")),
        (5, "课程代码", meta.get("课程代码", ""), "授课学时", meta.get("授课学时", "")),
    ]
    for r, l1, v1, l2, v2 in info_rows:
        ws.cell(r, 2, l1).alignment = CENTER
        ws.cell(r, 2).font = Font(bold=True)
        ws.cell(r, 2).fill = SUB_FILL
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=mid_end)
        ws.cell(r, 3, v1).alignment = CENTER

        if right_lbl_end > right_lbl_start:
            ws.merge_cells(start_row=r, start_column=right_lbl_start, end_row=r, end_column=right_lbl_end)
        ws.cell(r, right_lbl_start, l2).alignment = CENTER
        ws.cell(r, right_lbl_start).font = Font(bold=True)
        ws.cell(r, right_lbl_start).fill = SUB_FILL
        ws.cell(r, n_cols, v2).alignment = CENTER
        _apply_border(ws, r, 2, r, n_cols)
        ws.row_dimensions[r].height = 22

    # 第6~7行：考核内容与考核样本
    ws.merge_cells(start_row=6, start_column=1, end_row=6, end_column=n_cols)
    s6 = ws.cell(6, 1, "考核内容与考核样本")
    s6.font = Font(bold=True)
    s6.alignment = CENTER
    _apply_border(ws, 6, 1, 6, n_cols, HEAD_FILL)

    ws.cell(7, 1, "样本份数").alignment = CENTER
    ws.cell(7, 1).font = Font(bold=True)
    ws.cell(7, 1).fill = SUB_FILL
    ws.cell(7, 2, n_students).alignment = CENTER

    ws.merge_cells("C7:D7")
    ws.cell(7, 3, "样本来源（班级）").alignment = CENTER
    ws.cell(7, 3).font = Font(bold=True)
    ws.cell(7, 3).fill = SUB_FILL
    ws.merge_cells(start_row=7, start_column=5, end_row=7, end_column=max(6, n_cols - 2))
    ws.cell(7, 5, f"{meta.get('班级', '')}（{meta.get('学期', '')}）").alignment = CENTER

    ws.cell(7, n_cols - 1, "达标阈值").alignment = CENTER
    ws.cell(7, n_cols - 1).font = Font(bold=True)
    ws.cell(7, n_cols - 1).fill = SUB_FILL
    ws.cell(7, n_cols, f"{threshold * 100:.0f}%").alignment = CENTER
    _apply_border(ws, 7, 1, 7, n_cols)
    ws.row_dimensions[7].height = 22

    # 第8行：分节标题
    ws.merge_cells(start_row=8, start_column=1, end_row=8, end_column=n_cols)
    s8 = ws.cell(8, 1, "课程目标评价达成情况")
    s8.font = Font(bold=True)
    s8.alignment = CENTER
    _apply_border(ws, 8, 1, 8, n_cols, HEAD_FILL)

    # 第9~10行：评价表头与环节总分行
    headers = ["课程目标", "评价依据"] + links + ["合计", "评价结果", "达标结论"]
    for idx, h in enumerate(headers, 1):
        c_h = ws.cell(9, idx, h)
        c_h.font = Font(bold=True)
        c_h.alignment = CENTER
        c_h.fill = SUB_FILL
        c_h.border = BORDER

    ws.merge_cells("A9:A10")
    ws.merge_cells(start_row=9, start_column=ach_col, end_row=10, end_column=ach_col)
    ws.merge_cells(start_row=9, start_column=res_col, end_row=10, end_column=res_col)
    ws.cell(10, 2, "环节总分").alignment = CENTER
    ws.cell(10, 2).font = Font(bold=True)
    for j, link in enumerate(links, start=3):
        link_total = sum(output[t][link] for t in targets) * 100
        c_lt = ws.cell(10, j, round(link_total, 2))
        c_lt.number_format = "0.00"
        c_lt.alignment = CENTER
    first_l = get_column_letter(3)
    last_l = get_column_letter(2 + len(links))
    c_lsum = ws.cell(10, sum_col, f"=SUM({first_l}10:{last_l}10)")
    c_lsum.number_format = "0.00"
    c_lsum.font = Font(bold=True)
    c_lsum.alignment = CENTER
    _apply_border(ws, 9, 1, 10, n_cols)

    # 第11行起：各课程目标（理论满分行 + 实际得分行，实际得分跨表公式引用 Sheet2！）
    row = 11
    sum_col_letter = get_column_letter(sum_col)
    for t in targets:
        ws.merge_cells(start_row=row, start_column=1, end_row=row + 1, end_column=1)
        ws.cell(row, 1, t).font = Font(bold=True)
        ws.cell(row, 1).alignment = CENTER

        # 理论满分行
        ws.cell(row, 2, "理论满分").alignment = CENTER
        for j, link in enumerate(links, start=3):
            c_f = ws.cell(row, j, round(output[t][link] * 100, 4))
            c_f.number_format = "0.00"
            c_f.alignment = CENTER
        c_fsum = ws.cell(row, sum_col, f"=SUM({first_l}{row}:{last_l}{row})")
        c_fsum.number_format = "0.00"
        c_fsum.font = Font(bold=True)
        c_fsum.alignment = CENTER

        # 实际得分行（直接跨表公式引用 Sheet2「达成度计算表」均值行！）
        ws.cell(row + 1, 2, "实际得分").alignment = CENTER
        actual_val_sum = 0.0
        for j, link in enumerate(links, start=3):
            calc_col_letter = get_column_letter(sub_avg[(t, link)])
            c_a = ws.cell(row + 1, j, f"='达成度计算表'!{calc_col_letter}{sub_row}")
            c_a.number_format = "0.00"
            c_a.alignment = CENTER
            actual_val_sum += (
                sum(_student_link_score(s, t, link, output, questions, paper_full) for s in students)
                / n_students
            )

        c_asum = ws.cell(row + 1, sum_col, f"=SUM({first_l}{row + 1}:{last_l}{row + 1})")
        c_asum.number_format = "0.00"
        c_asum.font = Font(bold=True)
        c_asum.alignment = CENTER

        # 评价结果（达成度动态公式）与达标结论
        ws.merge_cells(start_row=row, start_column=ach_col, end_row=row + 1, end_column=ach_col)
        ws.merge_cells(start_row=row, start_column=res_col, end_row=row + 1, end_column=res_col)
        c_ach = ws.cell(row, ach_col, f"={sum_col_letter}{row + 1}/{sum_col_letter}{row}")
        c_ach.number_format = "0.0%"
        c_ach.font = Font(bold=True)
        c_ach.alignment = CENTER

        passed = (actual_val_sum / full[t] >= threshold) if full[t] > 0 else False
        c_res = ws.cell(row, res_col, "达标" if passed else "未达标")
        c_res.font = Font(bold=True, color="065F46" if passed else "991B1B")
        c_res.alignment = CENTER
        _apply_border(ws, row, 1, row + 1, n_cols)
        ws.cell(row, res_col).fill = PASS_FILL if passed else FAIL_FILL
        ws.cell(row + 1, res_col).fill = PASS_FILL if passed else FAIL_FILL

        ws.row_dimensions[row].height = 22
        ws.row_dimensions[row + 1].height = 22
        row += 2

    # 底部三栏：达成情况分析 / 拟改进的措施 / 评价人（签字）
    bottom_blocks = [
        ("达成情况分析", analysis_text or "（请填写本学期课程目标达成情况分析，或在系统中点击「一键生成诊断草稿」）", 76),
        ("拟改进的措施", improvement_notes or "（请填写下一轮教学持续改进措施）", 66),
        ("评价人（签字）", f"任课教师签字：________________        日期：____年__月__日", 30),
    ]
    for label, content, height in bottom_blocks:
        lbl = ws.cell(row, 1, label)
        lbl.font = Font(bold=True)
        lbl.alignment = CENTER
        lbl.fill = SUB_FILL
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=n_cols)
        val = ws.cell(row, 2, content)
        val.alignment = LEFT_WRAP
        _apply_border(ws, row, 1, row, n_cols)
        ws.row_dimensions[row].height = height
        row += 1

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 13
    for cc in range(3, n_cols + 1):
        ws.column_dimensions[get_column_letter(cc)].width = 13


def _build_outline_sheet(ws, method, matrix, output):
    """Sheet 3：《大纲与权重依据》（对应学校原表「大纲」Sheet，带归一化公式）。"""
    targets = list(matrix.keys())
    daily_links = list(method["平时环节"].keys())
    all_links = daily_links + ["期末考试"]

    # 块1：成绩评定方法
    ws.cell(1, 1, "一、成绩评定方法").font = Font(size=12, bold=True)
    ws.cell(2, 1, "考核环节").font = Font(bold=True)
    ws.cell(2, 1).alignment = CENTER
    ws.cell(2, 1).fill = HEAD_FILL
    for j, l in enumerate(all_links, start=2):
        c = ws.cell(2, j, l)
        c.font = Font(bold=True)
        c.alignment = CENTER
        c.fill = HEAD_FILL

    ws.cell(3, 1, "细项占平时比例").alignment = CENTER
    for j, l in enumerate(daily_links, start=2):
        ws.cell(3, j, method["平时环节"][l]).alignment = CENTER
    ws.cell(3, 2 + len(daily_links), "—").alignment = CENTER

    ws.cell(4, 1, "平时 / 期末总占比").alignment = CENTER
    if len(daily_links) > 1:
        ws.merge_cells(start_row=4, start_column=2, end_row=4, end_column=1 + len(daily_links))
    ws.cell(4, 2, method["平时占比"]).alignment = CENTER
    ws.cell(4, 2 + len(daily_links), method["期末占比"]).alignment = CENTER

    ws.cell(5, 1, "各环节实际权重").alignment = CENTER
    ws.cell(5, 1).font = Font(bold=True)
    for j, l in enumerate(daily_links, start=2):
        col_l = get_column_letter(j)
        c = ws.cell(5, j, f"={col_l}3*$B$4")
        c.number_format = "0.0000"
        c.alignment = CENTER
    final_col_l = get_column_letter(2 + len(daily_links))
    c_fw = ws.cell(5, 2 + len(daily_links), f"={final_col_l}4")
    c_fw.number_format = "0.0000"
    c_fw.alignment = CENTER
    _apply_border(ws, 2, 1, 5, 1 + len(all_links))

    # 块2：教学大纲原始对应比例矩阵
    m_start = 7
    ws.cell(m_start, 1, "二、课程目标与考核环节对应关系（大纲相对比例）").font = Font(size=12, bold=True)
    ws.cell(m_start + 1, 1, "课程目标").font = Font(bold=True)
    ws.cell(m_start + 1, 1).alignment = CENTER
    ws.cell(m_start + 1, 1).fill = HEAD_FILL
    for j, l in enumerate(all_links, start=2):
        c = ws.cell(m_start + 1, j, l)
        c.font = Font(bold=True)
        c.alignment = CENTER
        c.fill = HEAD_FILL

    r = m_start + 2
    mat_first_row = r
    for t in targets:
        ws.cell(r, 1, t).alignment = CENTER
        for j, l in enumerate(all_links, start=2):
            ws.cell(r, j, matrix[t].get(l, 0)).alignment = CENTER
        r += 1
    mat_last_row = r - 1
    ws.cell(r, 1, "列比例之和").font = Font(bold=True)
    ws.cell(r, 1).alignment = CENTER
    for j in range(2, 2 + len(all_links)):
        col_l = get_column_letter(j)
        c = ws.cell(r, j, f"=SUM({col_l}{mat_first_row}:{col_l}{mat_last_row})")
        c.number_format = "0.00"
        c.alignment = CENTER
    mat_sum_row = r
    _apply_border(ws, m_start + 1, 1, mat_sum_row, 1 + len(all_links))

    # 块3：产出权重与理论满分（列归一化公式）
    o_start = mat_sum_row + 2
    ws.cell(o_start, 1, "三、产出权重与理论满分（列归一化公式推导）").font = Font(size=12, bold=True)
    headers3 = ["课程目标"] + all_links + ["理论满分(分)"]
    for j, h in enumerate(headers3, 1):
        c = ws.cell(o_start + 1, j, h)
        c.font = Font(bold=True)
        c.alignment = CENTER
        c.fill = HEAD_FILL

    r = o_start + 2
    out_first_row = r
    for idx, t in enumerate(targets):
        ws.cell(r, 1, t).alignment = CENTER
        mat_r = mat_first_row + idx
        for j, l in enumerate(all_links, start=2):
            col_l = get_column_letter(j)
            c = ws.cell(r, j, f"=IF({col_l}${mat_sum_row}>0, {col_l}$5*{col_l}{mat_r}/{col_l}${mat_sum_row}, 0)")
            c.number_format = "0.0000"
            c.alignment = CENTER
        last_l = get_column_letter(1 + len(all_links))
        c_full = ws.cell(r, 2 + len(all_links), f"=SUM(B{r}:{last_l}{r})*100")
        c_full.number_format = "0.00"
        c_full.font = Font(bold=True)
        c_full.alignment = CENTER
        r += 1
    out_last_row = r - 1
    ws.cell(r, 1, "小计").font = Font(bold=True)
    ws.cell(r, 1).alignment = CENTER
    for j in range(2, 3 + len(all_links)):
        col_l = get_column_letter(j)
        c = ws.cell(r, j, f"=SUM({col_l}{out_first_row}:{col_l}{out_last_row})")
        c.number_format = "0.00" if j == 2 + len(all_links) else "0.0000"
        c.font = Font(bold=True)
        c.alignment = CENTER
    _apply_border(ws, o_start + 1, 1, r, 2 + len(all_links))

    ws.column_dimensions["A"].width = 20
    for cc in range(2, 3 + len(all_links)):
        ws.column_dimensions[get_column_letter(cc)].width = 14


def _build_detail_sheet(ws, students, output, full, questions, paper_full):
    """Sheet 4：《全班学生得分明细表》。"""
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
        for t in targets:
            t_qs = [q["题号"] for q in questions if q["目标"] == t]
            got = sum(float(s["期末"].get(qn, s["期末"].get(str(qn), 0))) for qn in t_qs)
            row_vals.append(round(got, 2))

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


def build_workbook(
    students,
    output,
    full,
    questions,
    paper_full,
    meta=None,
    threshold=0.65,
    method=None,
    matrix=None,
    analysis_text="",
    improvement_notes="",
):
    """生成终极 4-Sheet 归档工作簿，返回 BytesIO。"""
    meta = meta or {}
    wb = openpyxl.Workbook()

    # 先创建 4 个工作表并保持清晰顺序：目标达成评价表 -> 达成度计算表 -> 大纲与权重依据 -> 全班学生得分明细表
    ws_eval = wb.active
    ws_eval.title = "目标达成评价表"
    ws_calc = wb.create_sheet(title="达成度计算表")
    ws_outline = wb.create_sheet(title="大纲与权重依据")
    ws_detail = wb.create_sheet(title="全班学生得分明细表")

    # 先填 Sheet 2 获取均值行坐标，供 Sheet 1 跨表公式引用
    sub_row, sub_avg = _build_calc_sheet(
        ws_calc, students, output, full, questions, paper_full, meta
    )

    _build_evaluation_sheet(
        ws_eval,
        students,
        output,
        full,
        questions,
        paper_full,
        meta,
        threshold,
        sub_row,
        sub_avg,
        analysis_text=analysis_text,
        improvement_notes=improvement_notes,
    )

    if method and matrix:
        _build_outline_sheet(ws_outline, method, matrix, output)
    else:
        wb.remove(ws_outline)

    _build_detail_sheet(ws_detail, students, output, full, questions, paper_full)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
