"""《考试试卷分析表.xlsx》2-Sheet 归档报表导出与统计模块

1:1 复刻高校真实《试卷分析表.xls》归档版式（带全套动态 Excel 公式）：
  1. Sheet 1「各题得分统计表」：
     - 课程/班级/学期/教师信息栏
     - 按试卷大题（一、二、三、四、五…）逐人汇总大题得分 + 最右侧「总分（=SUM）」
     - 底部三行汇总公式：「平均分（=AVERAGE）」「应得分」「得分率（=平均分/应得分）」
  2. Sheet 2「考试试卷分析表」：
     - 参加考试人数 / 应考人数
     - 5 档分数段统计（90~100分 / 80~89分 / 70~79分 / 60~69分 / 59分以下）人数与比率（跨表 COUNTIFS 动态公式）
     - 平均分 / 最高分 / 最低分 / 及格率（跨表动态公式）
     - 各大题（一 ~ 十）应得分 / 平均分 / 得分率汇总表（跨表动态引用 Sheet 1）
     - 教学质量分析与改进意见文本框 + 任课教师 / 教研室主任签字栏
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

CN_NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]


def _section_label(idx: int, raw_name: str) -> str:
    if idx < len(CN_NUMS):
        return CN_NUMS[idx]
    return raw_name or f"第{idx + 1}题"


def _apply_border(ws, r1: int, c1: int, r2: int, c2: int, fill=None):
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(r, c).border = BORDER
            if fill is not None:
                ws.cell(r, c).fill = fill


def compute_exam_analysis_stats(students: list[dict], paper: list[dict]) -> dict:
    """计算期末试卷分析统计指标，供前端大屏展示与 Excel 导出共用。"""
    n = len(students)
    sections_meta = []
    for idx, grp in enumerate(paper or []):
        qs = grp.get("小题") or []
        q_nums = [q["题号"] for q in qs]
        full = sum(float(q.get("满分") or 0) for q in qs)
        sections_meta.append({
            "index": idx,
            "short": _section_label(idx, grp.get("大题", "")),
            "name": grp.get("大题") or f"第{idx + 1}大题",
            "q_nums": q_nums,
            "full": round(full, 2),
        })

    student_section_rows = []
    totals = []
    sec_sums = [0.0] * len(sections_meta)

    for stu in students:
        f_map = stu.get("期末") or {}
        sec_scores = []
        for i, sm in enumerate(sections_meta):
            s_val = sum(float(f_map.get(qn, f_map.get(str(qn), 0)) or 0) for qn in sm["q_nums"])
            s_val = round(s_val, 2)
            sec_scores.append(s_val)
            sec_sums[i] += s_val
        tot = round(sum(sec_scores), 2)
        totals.append(tot)
        student_section_rows.append({
            "学号": stu.get("学号", ""),
            "姓名": stu.get("姓名", ""),
            "大题得分": sec_scores,
            "总分": tot,
        })

    avg_total = round(sum(totals) / n, 2) if n else 0.0
    max_total = round(max(totals), 2) if n else 0.0
    min_total = round(min(totals), 2) if n else 0.0
    pass_cnt = sum(1 for x in totals if x >= 60)
    pass_rate = round(pass_cnt / n, 4) if n else 0.0

    # 5 档分数段
    b_defs = [
        ("90~100分", lambda x: x >= 90),
        ("80~89分", lambda x: 80 <= x < 90),
        ("70~79分", lambda x: 70 <= x < 80),
        ("60~69分", lambda x: 60 <= x < 70),
        ("59分以下", lambda x: x < 60),
    ]
    buckets = []
    for label, fn in b_defs:
        cnt = sum(1 for x in totals if fn(x))
        buckets.append({
            "label": label,
            "count": cnt,
            "ratio": round(cnt / n, 4) if n else 0.0,
        })

    sections = []
    for i, sm in enumerate(sections_meta):
        avg_s = round(sec_sums[i] / n, 2) if n else 0.0
        rate = round(avg_s / sm["full"], 4) if sm["full"] > 0 else 0.0
        sections.append({
            "short": sm["short"],
            "name": sm["name"],
            "full": sm["full"],
            "avg": avg_s,
            "rate": rate,
        })

    # 自动生成贴合学校风格的试卷质量分析草稿
    sorted_secs = sorted(sections, key=lambda x: x["rate"])
    weak_sec = sorted_secs[0] if sorted_secs else None
    strong_sec = sorted_secs[-1] if sorted_secs else None
    fail_bucket = buckets[-1]
    lines = [
        f"本次期末考试实考 {n} 人，卷面平均分 {avg_total:.1f} 分（最高分 {max_total:.1f} 分，最低分 {min_total:.1f} 分），"
        f"及格率 {pass_rate * 100:.1f}%，不及格 {fail_bucket['count']} 人（占 {fail_bucket['ratio'] * 100:.1f}%）。"
    ]
    if strong_sec and weak_sec and strong_sec["name"] != weak_sec["name"]:
        lines.append(
            f"从各大题得分情况看，学生对「{strong_sec['name']}」掌握相对较好（平均得分率 {strong_sec['rate'] * 100:.1f}%）；"
            f"在「{weak_sec['name']}」失分最为集中（平均分 {weak_sec['avg']:.1f}/{weak_sec['full']:.0f}，得分率仅 {weak_sec['rate'] * 100:.1f}%），"
            f"反映出相关核心概念理解与综合计算训练仍有欠缺。"
        )
    lines.append(
        "改进意见：后续教学应强化基本概念的板书推导与典型例题演练，针对失分率偏高的大题题型增加随堂练习与过程性反馈，切实提升学生独立求解与综合应用能力。"
    )

    return {
        "total_count": n,
        "avg": avg_total,
        "max": max_total,
        "min": min_total,
        "pass_count": pass_cnt,
        "pass_rate": pass_rate,
        "buckets": buckets,
        "sections": sections,
        "student_rows": student_section_rows,
        "default_analysis_text": "\n".join(lines),
    }


def build_exam_analysis_workbook(
    students: list[dict],
    paper: list[dict],
    meta: dict | None = None,
    exam_analysis_text: str = "",
) -> io.BytesIO:
    """生成 2-Sheet《考试试卷分析表.xlsx》（全动态公式联动），返回 BytesIO。"""
    meta = meta or {}
    stats = compute_exam_analysis_stats(students, paper)
    sections = stats["sections"]
    n_sec = len(sections)
    n_stu = stats["total_count"]

    wb = openpyxl.Workbook()

    # ==========================================================
    # Sheet 1：各题得分统计表
    # ==========================================================
    ws1 = wb.active
    ws1.title = "各题得分统计表"
    ws1.views.sheetView[0].showGridLines = True

    total_col = 4 + n_sec  # A:序号 B:学号 C:姓名 D..:大题 最后:总分
    tot_letter = get_column_letter(total_col)

    ws1.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_col)
    t1 = ws1.cell(1, 1, "各题得分统计表")
    t1.font = Font(size=16, bold=True)
    t1.alignment = CENTER
    ws1.row_dimensions[1].height = 30

    ws1.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_col)
    info1 = ws1.cell(
        2,
        1,
        f"学期：{meta.get('学期', '')}    班级：{meta.get('班级', '')}    "
        f"教师：{meta.get('任课教师', '')}    课程名称：{meta.get('课程名称', '')}",
    )
    info1.font = Font(size=10.5)
    info1.alignment = LEFT_WRAP
    ws1.row_dimensions[2].height = 22

    headers1 = ["序号", "学号", "姓名"] + [s["short"] for s in sections] + ["总分"]
    for c_idx, h in enumerate(headers1, 1):
        cell = ws1.cell(3, c_idx, h)
        cell.font = Font(bold=True)
        cell.alignment = CENTER
        cell.fill = HEAD_FILL
        cell.border = BORDER
    ws1.row_dimensions[3].height = 24

    first_data_row = 4
    first_sec_letter = get_column_letter(4)
    last_sec_letter = get_column_letter(3 + n_sec) if n_sec > 0 else first_sec_letter

    for idx, srow in enumerate(stats["student_rows"], start=1):
        r = first_data_row + idx - 1
        ws1.cell(r, 1, idx).alignment = CENTER
        ws1.cell(r, 2, srow["学号"]).alignment = CENTER
        ws1.cell(r, 3, srow["姓名"]).alignment = CENTER
        for j, sc in enumerate(srow["大题得分"], start=4):
            c_sc = ws1.cell(r, j, sc)
            c_sc.alignment = CENTER
            c_sc.number_format = "0.##"
        c_tot = ws1.cell(r, total_col, f"=SUM({first_sec_letter}{r}:{last_sec_letter}{r})" if n_sec > 0 else 0)
        c_tot.alignment = CENTER
        c_tot.font = Font(bold=True)
        c_tot.number_format = "0.##"
        _apply_border(ws1, r, 1, r, total_col)
        ws1.row_dimensions[r].height = 20

    last_data_row = first_data_row + max(n_stu, 1) - 1
    avg_row = last_data_row + 1
    full_row = last_data_row + 2
    rate_row = last_data_row + 3

    for r_sum, label in ((avg_row, "平均分"), (full_row, "应得分"), (rate_row, "得分率")):
        ws1.merge_cells(start_row=r_sum, start_column=1, end_row=r_sum, end_column=3)
        lbl = ws1.cell(r_sum, 1, label)
        lbl.font = Font(bold=True)
        lbl.alignment = CENTER
        lbl.fill = SUB_FILL
        _apply_border(ws1, r_sum, 1, r_sum, total_col)
        ws1.row_dimensions[r_sum].height = 22

    for j, sec in enumerate(sections, start=4):
        col_l = get_column_letter(j)
        c_a = ws1.cell(avg_row, j, f"=AVERAGE({col_l}{first_data_row}:{col_l}{last_data_row})")
        c_a.number_format = "0.00"
        c_a.alignment = CENTER
        c_a.font = Font(bold=True)

        c_f = ws1.cell(full_row, j, sec["full"])
        c_f.number_format = "0.##"
        c_f.alignment = CENTER

        c_r = ws1.cell(rate_row, j, f"=IF({col_l}{full_row}>0,{col_l}{avg_row}/{col_l}{full_row},0)")
        c_r.number_format = "0.0%"
        c_r.alignment = CENTER
        c_r.font = Font(bold=True)

    # 总分列汇总
    c_ta = ws1.cell(avg_row, total_col, f"=AVERAGE({tot_letter}{first_data_row}:{tot_letter}{last_data_row})")
    c_ta.number_format = "0.00"
    c_ta.alignment = CENTER
    c_ta.font = Font(bold=True)

    c_tf = ws1.cell(full_row, total_col, f"=SUM({first_sec_letter}{full_row}:{last_sec_letter}{full_row})" if n_sec > 0 else 100)
    c_tf.number_format = "0.##"
    c_tf.alignment = CENTER
    c_tf.font = Font(bold=True)

    c_tr = ws1.cell(rate_row, total_col, f"=IF({tot_letter}{full_row}>0,{tot_letter}{avg_row}/{tot_letter}{full_row},0)")
    c_tr.number_format = "0.0%"
    c_tr.alignment = CENTER
    c_tr.font = Font(bold=True)

    ws1.column_dimensions["A"].width = 8
    ws1.column_dimensions["B"].width = 16
    ws1.column_dimensions["C"].width = 12
    for j in range(4, total_col + 1):
        ws1.column_dimensions[get_column_letter(j)].width = 11

    # ==========================================================
    # Sheet 2：考试试卷分析表（1:1 复刻学校正式归档表）
    # ==========================================================
    ws2 = wb.create_sheet("考试试卷分析表")
    ws2.views.sheetView[0].showGridLines = True
    n_cols2 = 13  # A..M，完美匹配学校 13 列标准版式

    ws2.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols2)
    t2 = ws2.cell(1, 1, "考试试卷分析表")
    t2.font = Font(size=16, bold=True)
    t2.alignment = CENTER
    ws2.row_dimensions[1].height = 32

    ws2.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols2)
    info2 = ws2.cell(
        2,
        1,
        f"班级：{meta.get('班级', '')}       任课教师：{meta.get('任课教师', '')}         "
        f"课程名称：{meta.get('课程名称', '')}       学期：{meta.get('学期', '')}",
    )
    info2.font = Font(size=10.5)
    info2.alignment = LEFT_WRAP
    ws2.row_dimensions[2].height = 24

    # 第 3~5 行：分数段分布表（跨表动态公式引用 Sheet 1 总分列）
    score_rng = f"'各题得分统计表'!${tot_letter}${first_data_row}:${tot_letter}${last_data_row}"
    ws2.cell(3, 1, "参加考试人数").font = Font(bold=True)
    ws2.cell(3, 1).alignment = CENTER
    ws2.cell(3, 2, "应考人数").font = Font(bold=True)
    ws2.cell(3, 2).alignment = CENTER
    ws2.cell(3, 3, "分数区间").font = Font(bold=True)
    ws2.cell(3, 3).alignment = CENTER

    bucket_specs = [
        (4, 5, "90~100分", f'=COUNTIF({score_rng},">=90")'),
        (6, 7, "80~89分", f'=COUNTIFS({score_rng},">=80",{score_rng},"<90")'),
        (8, 9, "70~79分", f'=COUNTIFS({score_rng},">=70",{score_rng},"<80")'),
        (10, 11, "60~69分", f'=COUNTIFS({score_rng},">=60",{score_rng},"<70")'),
        (12, 13, "59分以下", f'=COUNTIF({score_rng},"<60")'),
    ]
    for c1, c2, lbl, formula in bucket_specs:
        ws2.merge_cells(start_row=3, start_column=c1, end_row=3, end_column=c2)
        c_h = ws2.cell(3, c1, lbl)
        c_h.font = Font(bold=True)
        c_h.alignment = CENTER

        ws2.merge_cells(start_row=4, start_column=c1, end_row=4, end_column=c2)
        c_n = ws2.cell(4, c1, formula)
        c_n.alignment = CENTER

        ws2.merge_cells(start_row=5, start_column=c1, end_row=5, end_column=c2)
        c_l = get_column_letter(c1)
        c_r = ws2.cell(5, c1, f"=IF($A$4>0,{c_l}4/$A$4,0)")
        c_r.alignment = CENTER
        c_r.number_format = "0.0%"

    ws2.merge_cells("A4:A5")
    ws2.cell(4, 1, f"=COUNT({score_rng})").alignment = CENTER
    ws2.cell(4, 1).font = Font(bold=True)
    ws2.merge_cells("B4:B5")
    ws2.cell(4, 2, n_stu).alignment = CENTER
    ws2.cell(4, 2).font = Font(bold=True)

    ws2.cell(4, 3, "人数（人）").alignment = CENTER
    ws2.cell(4, 3).font = Font(bold=True)
    ws2.cell(5, 3, "比率").alignment = CENTER
    ws2.cell(5, 3).font = Font(bold=True)

    _apply_border(ws2, 3, 1, 3, n_cols2, HEAD_FILL)
    _apply_border(ws2, 4, 1, 5, n_cols2)
    ws2.row_dimensions[3].height = 24
    ws2.row_dimensions[4].height = 22
    ws2.row_dimensions[5].height = 22

    # 第 6 行：平均分 / 最高分 / 最低分 / 及格率
    ws2.merge_cells("A6:B6")
    ws2.cell(6, 1, "平均分").font = Font(bold=True)
    ws2.cell(6, 1).alignment = CENTER
    ws2.cell(6, 1).fill = SUB_FILL
    ws2.merge_cells("C6:D6")
    c_avg2 = ws2.cell(6, 3, f"='各题得分统计表'!{tot_letter}{avg_row}")
    c_avg2.alignment = CENTER
    c_avg2.number_format = "0.00"
    c_avg2.font = Font(bold=True)

    ws2.cell(6, 5, "最高分").font = Font(bold=True)
    ws2.cell(6, 5).alignment = CENTER
    ws2.cell(6, 5).fill = SUB_FILL
    ws2.merge_cells("F6:G6")
    c_max2 = ws2.cell(6, 6, f"=MAX({score_rng})")
    c_max2.alignment = CENTER
    c_max2.number_format = "0.##"

    ws2.cell(6, 8, "最低分").font = Font(bold=True)
    ws2.cell(6, 8).alignment = CENTER
    ws2.cell(6, 8).fill = SUB_FILL
    ws2.merge_cells("I6:J6")
    c_min2 = ws2.cell(6, 9, f"=MIN({score_rng})")
    c_min2.alignment = CENTER
    c_min2.number_format = "0.##"

    ws2.cell(6, 11, "及格率").font = Font(bold=True)
    ws2.cell(6, 11).alignment = CENTER
    ws2.cell(6, 11).fill = SUB_FILL
    ws2.merge_cells("L6:M6")
    c_pass2 = ws2.cell(6, 12, f'=IF($A$4>0,COUNTIF({score_rng},">=60")/$A$4,0)')
    c_pass2.alignment = CENTER
    c_pass2.number_format = "0.0%"
    c_pass2.font = Font(bold=True)

    _apply_border(ws2, 6, 1, 6, n_cols2)
    ws2.row_dimensions[6].height = 24

    # 第 8~11 行：各大题得分率汇总（一 ~ 十，跨表引用 Sheet 1）
    sec_start = 8
    for offset, title in enumerate(["大题序号", "应得分", "平均分", "得分率"]):
        r = sec_start + offset
        ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        c_t = ws2.cell(r, 1, title)
        c_t.font = Font(bold=True)
        c_t.alignment = CENTER
        c_t.fill = HEAD_FILL if offset == 0 else SUB_FILL
        ws2.row_dimensions[r].height = 22

    for k in range(10):  # 10 列对应 D..M（一 ~ 十）
        col = 4 + k
        ws2.cell(sec_start, col, CN_NUMS[k]).alignment = CENTER
        ws2.cell(sec_start, col).font = Font(bold=True)
        ws2.cell(sec_start, col).fill = HEAD_FILL
        if k < n_sec:
            s1_col = get_column_letter(4 + k)
            c_f2 = ws2.cell(sec_start + 1, col, f"='各题得分统计表'!{s1_col}{full_row}")
            c_f2.alignment = CENTER
            c_f2.number_format = "0.##"

            c_a2 = ws2.cell(sec_start + 2, col, f"='各题得分统计表'!{s1_col}{avg_row}")
            c_a2.alignment = CENTER
            c_a2.number_format = "0.00"

            c_r2 = ws2.cell(sec_start + 3, col, f"='各题得分统计表'!{s1_col}{rate_row}")
            c_r2.alignment = CENTER
            c_r2.number_format = "0.0%"
            c_r2.font = Font(bold=True)

    _apply_border(ws2, sec_start, 1, sec_start + 3, n_cols2)

    # 第 13~14 行：教学质量分析与改进意见
    ws2.merge_cells(start_row=13, start_column=1, end_row=13, end_column=n_cols2)
    q_prompt = ws2.cell(
        13,
        1,
        "教学质量有哪些提高？学生对哪些知识掌握较好？哪些较差？具体反映在哪里？有什么经验或教训？对今后教学的改进意见？",
    )
    q_prompt.font = Font(bold=True, size=10.5)
    q_prompt.alignment = LEFT_WRAP
    q_prompt.fill = HEAD_FILL
    _apply_border(ws2, 13, 1, 13, n_cols2)
    ws2.row_dimensions[13].height = 26

    ws2.merge_cells(start_row=14, start_column=1, end_row=15, end_column=n_cols2)
    q_body = ws2.cell(14, 1, (exam_analysis_text or "").strip() or stats["default_analysis_text"])
    q_body.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    _apply_border(ws2, 14, 1, 15, n_cols2)
    ws2.row_dimensions[14].height = 68
    ws2.row_dimensions[15].height = 44

    # 第 16 行：签字栏
    ws2.merge_cells("A16:C16")
    ws2.cell(16, 1, "任课教师（签名）：").font = Font(bold=True)
    ws2.cell(16, 1).alignment = Alignment(horizontal="right", vertical="center")
    ws2.merge_cells("D16:G16")
    ws2.cell(16, 4, "________________    年    月    日").alignment = CENTER

    ws2.merge_cells("H16:J16")
    ws2.cell(16, 8, "教研室主任（签名）：").font = Font(bold=True)
    ws2.cell(16, 8).alignment = Alignment(horizontal="right", vertical="center")
    ws2.merge_cells("K16:M16")
    ws2.cell(16, 11, "________________    年    月    日").alignment = CENTER
    _apply_border(ws2, 16, 1, 16, n_cols2)
    ws2.row_dimensions[16].height = 30

    col_widths = [13, 11, 11, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8]
    for i, w in enumerate(col_widths, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    ws1.page_setup.orientation = ws1.ORIENTATION_LANDSCAPE
    ws1.page_setup.fitToWidth = 1
    ws1.page_setup.fitToHeight = 0
    ws1.sheet_properties.pageSetUpPr.fitToPage = True

    ws2.page_setup.orientation = ws2.ORIENTATION_LANDSCAPE
    ws2.page_setup.fitToWidth = 1
    ws2.page_setup.fitToHeight = 1
    ws2.sheet_properties.pageSetUpPr.fitToPage = True

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
