"""把示例数据填入下载的两个模板，便于直接上传测试。

读取：
  示例/平时成绩表.xlsx
  示例/期末小题成绩录入模板.xlsx
写入：
  项目根目录/daily_template.xlsx
  项目根目录/final_template.xlsx
"""
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "示例"

DAILY_SRC = SAMPLE / "平时成绩表.xlsx"
FINAL_SRC = SAMPLE / "期末小题成绩录入模板.xlsx"
DAILY_DST = ROOT / "平时成绩录入模板.xlsx"
FINAL_DST = ROOT / "期末小题成绩录入模板.xlsx"


def read_rows(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    return [list(r) for r in ws.iter_rows(values_only=True)]


def clean(v):
    if v is None:
        return None
    s = str(v).replace("\xa0", "").strip()
    return s or None


def find_header(rows, required):
    for i, r in enumerate(rows):
        names = [clean(c) or "" for c in r]
        if all(any(req in n for n in names) for req in required):
            return i, names
    raise ValueError(f"未找到表头 {required}")


def fill_daily():
    rows = read_rows(DAILY_SRC)
    idx, names = find_header(rows, ["学号", "姓名"])

    def col(keyword):
        for i, n in enumerate(names):
            if keyword in n:
                return i
        raise ValueError(f"缺少列 {keyword}")

    c_id, c_name = col("学号"), col("姓名")
    c_hw, c_perf, c_quiz = col("作业"), col("课堂表现"), col("测验")

    wb = openpyxl.load_workbook(DAILY_DST)
    ws = wb.active
    n = 0
    for r in rows[idx + 1:]:
        sid, name = clean(r[c_id]), clean(r[c_name])
        if not sid or not name:
            continue
        if any(k in name for k in ("平均", "合计", "统计", "最高", "最低")):
            continue
        ws.append([sid, name, r[c_hw], r[c_perf], r[c_quiz]])
        n += 1
    wb.save(DAILY_DST)
    print(f"平时成绩模板已写入 {n} 人 -> {DAILY_DST.name}")


def fill_final():
    rows = read_rows(FINAL_SRC)
    idx, names = find_header(rows, ["学号", "姓名"])

    # 源表列名形如 “第1题(3分/课程目标1)”，按题号定位
    col_of = {}
    for c, name in enumerate(names):
        if not name or not name.startswith("第"):
            continue
        num = ""
        for ch in name[1:]:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            col_of[int(num)] = c

    c_id = next(i for i, n in enumerate(names) if "学号" in n)
    c_name = next(i for i, n in enumerate(names) if "姓名" in n)

    wb = openpyxl.load_workbook(FINAL_DST)
    ws = wb.active
    # 目标模板表头里的题号顺序
    dst_nums = []
    for c in range(3, ws.max_column + 1):
        h = ws.cell(1, c).value or ""
        num = ""
        for ch in str(h)[1:]:
            if ch.isdigit():
                num += ch
            else:
                break
        dst_nums.append(int(num) if num else None)

    n = 0
    for r in rows[idx + 1:]:
        sid, name = clean(r[c_id]), clean(r[c_name])
        if not sid or not name:
            continue
        ws.append([sid, name] + [r[col_of[q]] for q in dst_nums])
        n += 1
    wb.save(FINAL_DST)
    print(f"期末成绩模板已写入 {n} 人 -> {FINAL_DST.name}")


if __name__ == "__main__":
    fill_daily()
    fill_final()
