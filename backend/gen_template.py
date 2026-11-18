"""期末小题成绩录入模板生成器

根据系统配置的试卷结构，生成教师填分用的简单模板：
    学号 | 姓名 | 第1题(3分/目标1) | 第2题(3分/目标2) | ...

同时生成一份示例数据（模拟教师填好的成绩），用于验证计算链路。

运行：python backend/gen_template.py
"""

import random
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from calc_engine import PAPER_STRUCTURE, SAMPLE, load_daily_students

random.seed(20261118)

# 各题目标得分率（体现难度差异）
DIFFICULTY = {
    1: 0.90, 2: 0.80, 3: 0.86, 4: 0.80, 5: 0.83, 6: 0.78,
    7: 0.70, 8: 0.66, 9: 0.62, 10: 0.58, 11: 0.55, 12: 0.52,
    13: 0.68, 14: 0.48, 15: 0.52, 16: 0.44, 17: 0.40,
}


def flatten_questions():
    return [q for g in PAPER_STRUCTURE for q in g["小题"]]


def build_template(students, questions, fill_scores=False):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "期末成绩"

    header_fill = PatternFill("solid", fgColor="DDEBF7")
    center = Alignment(horizontal="center", vertical="center")

    # 表头：学号 | 姓名 | 第N题(满分/目标)
    headers = ["学号", "姓名"]
    for q in questions:
        headers.append(f"第{q['题号']}题({q['满分']}分/{q['目标']})")

    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = center

    # 学生行
    for r, s in enumerate(students, start=2):
        ws.cell(row=r, column=1, value=s["学号"])
        ws.cell(row=r, column=2, value=s["姓名"])
        if not fill_scores:
            continue
        ability = max(0.45, min(1.15, random.gauss(1.0, 0.18)))
        for c, q in enumerate(questions, start=3):
            raw = q["满分"] * DIFFICULTY[q["题号"]] * ability
            score = round(raw * 2) / 2 if q["满分"] <= 3 else round(raw)
            score = max(0, min(q["满分"], score))
            ws.cell(row=r, column=c, value=score)

    # 列宽
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 10
    for c in range(3, len(headers) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 16

    ws.freeze_panes = "C2"
    return wb


def main():
    questions = flatten_questions()
    students = load_daily_students()
    print(f"学生 {len(students)} 人，小题 {len(questions)} 道")

    # 1. 空白模板（教师实际使用）
    blank = build_template(students, questions, fill_scores=False)
    blank_path = SAMPLE / "期末小题成绩录入模板_空白.xlsx"
    blank.save(blank_path)
    print(f"已生成空白模板：{blank_path.name}")

    # 2. 示例数据（模拟教师填好，用于验证计算）
    filled = build_template(students, questions, fill_scores=True)
    filled_path = SAMPLE / "期末小题成绩录入模板.xlsx"
    filled.save(filled_path)
    print(f"已生成示例数据：{filled_path.name}")


if __name__ == "__main__":
    main()
