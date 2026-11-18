"""生成一份合理的期末小题成绩示例数据

保持 示例/试卷分解表.xlsx 的原有表头结构（题号/小题号/满分值/课程目标勾选/学号姓名），
只重新生成学生得分，使数据符合真实考试分布：
- 每题得分不超过满分
- 学生水平有差异，整体呈正态分布
- 难题（如最后几道解答题）得分率偏低
- 无空白单元格

输出：示例/试卷分解表.xlsx（覆盖原文件）
"""

import random
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "示例"
SRC = SAMPLE / "试卷分解表.xlsx"

random.seed(20261118)

# 17 道小题：(题号, 小题号, 满分, 课程目标)
QUESTIONS = [
    ("一", "1", 3, 1), ("一", "2", 3, 2), ("一", "3", 3, 1),
    ("一", "4", 3, 1), ("一", "5", 3, 1), ("一", "6", 3, 1),
    ("二", "7", 6, 1), ("二", "8", 6, 1), ("二", "9", 6, 1),
    ("二", "10", 6, 1), ("二", "11", 6, 1), ("二", "12", 6, 1),
    ("三", "13", 6, 2), ("三", "14", 6, 1), ("三", "15", 10, 2),
    ("四", "16", 10, 1), ("四", "17", 14, 1),
]

# 每题的目标得分率基准（0~1），体现难度差异
DIFFICULTY = {
    "1": 0.90, "2": 0.80, "3": 0.86, "4": 0.80, "5": 0.83, "6": 0.78,
    "7": 0.70, "8": 0.66, "9": 0.62, "10": 0.58, "11": 0.55, "12": 0.52,
    "13": 0.68, "14": 0.48, "15": 0.52, "16": 0.44, "17": 0.40,
}


def load_students():
    """从原表读取学号姓名，保持学生名单不变。"""
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    header_idx = next(
        i for i, r in enumerate(rows)
        if r[0] and str(r[0]).replace("\xa0", "").strip() == "学号"
    )
    students = []
    for r in rows[header_idx + 1:]:
        sid = str(r[0]).replace("\xa0", "").strip() if r[0] else ""
        name = str(r[1]).strip() if r[1] else ""
        if sid and name:
            students.append((sid, name))
    return students


def gen_score(full, rate, ability):
    """按满分、难度基准、学生能力生成得分，并做取整与边界约束。"""
    raw = full * rate * ability
    # 小题满分 3 分按 0.5 取整，其余按整数取整
    if full <= 3:
        score = round(raw * 2) / 2
    else:
        score = round(raw)
    return max(0, min(full, score))


def main():
    students = load_students()
    print(f"读取学生 {len(students)} 人")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    n = len(QUESTIONS)
    # 第 1 行：标题
    ws.cell(row=1, column=3, value="试卷各题得分")
    ws.cell(row=1, column=21, value="对应课程目标的分值")

    # 第 2 行：大题号（合并单元格）
    ws.cell(row=2, column=2, value="题号")
    groups = []
    for i, q in enumerate(QUESTIONS):
        col = 3 + i
        if not groups or groups[-1][0] != q[0]:
            groups.append([q[0], col, col])
        else:
            groups[-1][2] = col
    for label, start, end in groups:
        ws.cell(row=2, column=start, value=label)
        if end > start:
            ws.merge_cells(start_row=2, start_column=start, end_row=2, end_column=end)
    ws.cell(row=2, column=20, value="合计")

    # 第 3 行：小题号
    ws.cell(row=3, column=2, value="小题号")
    for i, q in enumerate(QUESTIONS):
        ws.cell(row=3, column=3 + i, value=q[1])

    # 第 4 行：满分值
    ws.cell(row=4, column=2, value="满分值")
    for i, q in enumerate(QUESTIONS):
        ws.cell(row=4, column=3 + i, value=q[2])
    ws.cell(row=4, column=20, value=sum(q[2] for q in QUESTIONS))

    # 第 5、6 行：课程目标勾选
    ws.cell(row=5, column=2, value="课程目标1")
    ws.cell(row=6, column=2, value="课程目标2")
    for i, q in enumerate(QUESTIONS):
        ws.cell(row=5 + (q[3] - 1), column=3 + i, value="v")

    # 右侧：各目标卷面满分与设定分值
    t1_full = sum(q[2] for q in QUESTIONS if q[3] == 1)
    t2_full = sum(q[2] for q in QUESTIONS if q[3] == 2)
    ws.cell(row=4, column=21, value=t1_full)
    ws.cell(row=4, column=22, value=t2_full)
    ws.cell(row=5, column=21, value="课程目标1")
    ws.cell(row=5, column=22, value="课程目标2")
    ws.cell(row=6, column=21, value=0.5)
    ws.cell(row=6, column=22, value=0.1)

    # 第 7 行：表头
    ws.cell(row=7, column=1, value="学号")
    ws.cell(row=7, column=2, value="姓名")

    # 学生数据
    for idx, (sid, name) in enumerate(students):
        row = 8 + idx
        ws.cell(row=row, column=1, value=sid)
        ws.cell(row=row, column=2, value=name)
        # 学生能力系数：正态分布，均值 1.0，标准差 0.18
        ability = max(0.45, min(1.15, random.gauss(1.0, 0.18)))
        total = 0
        for i, q in enumerate(QUESTIONS):
            score = gen_score(q[2], DIFFICULTY[q[1]], ability)
            ws.cell(row=row, column=3 + i, value=score)
            total += score
        ws.cell(row=row, column=20, value=total)

    wb.save(SRC)
    print(f"已生成 {len(students)} 名学生 × {n} 道小题的成绩")
    print(f"目标1卷面满分 {t1_full}，目标2卷面满分 {t2_full}，试卷总分 {t1_full + t2_full}")


if __name__ == "__main__":
    main()
