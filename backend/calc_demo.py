"""达成度计算流程验证脚本（临时 Demo）

用 示例/ 下的真实 Excel 跑通《达成度计算流程.md》的五步算法，
核对结果是否与文档一致：目标1 达成度 55%、目标2 达成度 74%。

运行：python backend/calc_demo.py
"""

from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "示例"

# ---------- 1. 成绩评定方法（平时40%：作业40/表现40/测验20；期末60%） ----------
METHOD = {
    "平时": {"作业": 0.4, "课堂表现": 0.4, "测验": 0.2},
    "期末": 0.6,
}

# ---------- 2. 目标与环节对应关系（大纲原始比例） ----------
MATRIX = {
    "课程目标1": {"作业": 0.2, "课堂表现": 0.2, "测验": 0.1, "期末考试": 0.5},
    "课程目标2": {"作业": 0.4, "课堂表现": 0.3, "测验": 0.2, "期末考试": 0.1},
}

# 期末各目标设定分值（来自试卷分解表右侧“对应课程目标的分值”）
FINAL_TARGET_SCORE = {"课程目标1": 50.0, "课程目标2": 10.0}


def clean(v):
    """单元格清洗：去不换行空格，空值返回 None。"""
    if v is None:
        return None
    s = str(v).replace("\xa0", "").strip()
    return s or None


def to_num(v):
    s = clean(v)
    if s is None:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_rows(filename):
    wb = openpyxl.load_workbook(SAMPLE / filename, data_only=True)
    ws = wb.active
    return [list(r) for r in ws.iter_rows(values_only=True)]


# ---------- 第一步：各环节在总成绩中的实际权重 ----------
def step1_link_weights():
    weights = {name: 0.4 * ratio for name, ratio in METHOD["平时"].items()}
    weights["期末考试"] = METHOD["期末"]
    return weights


# ---------- 第二步：产出权重与理论满分 ----------
def step2_output_weights(link_weights):
    targets = list(MATRIX.keys())
    output = {t: {} for t in targets}
    for link, link_score in link_weights.items():
        col_sum = sum(MATRIX[t][link] for t in targets)
        for t in targets:
            output[t][link] = link_score * MATRIX[t][link] / col_sum
    full = {t: sum(output[t].values()) * 100 for t in targets}
    return output, full


# ---------- 第三步：平时成绩贡献 ----------
def step3_daily(rows, output):
    header_idx = next(
        i for i, r in enumerate(rows) if clean(r[0]) == "学号" and clean(r[1]) == "姓名"
    )
    header = [clean(c) for c in rows[header_idx]]
    col = {name: header.index(name) for name in METHOD["平时"]}

    students = []
    for r in rows[header_idx + 1:]:
        sid, name = clean(r[0]), clean(r[1])
        if not sid or not name:
            continue
        if any(k in name for k in ("平均", "合计", "统计")):
            continue
        scores = {k: to_num(r[i]) for k, i in col.items()}
        students.append({"学号": sid, "姓名": name, "平时": scores})
    return students


# ---------- 第四步：期末试卷贡献 ----------
def step4_final(rows, students):
    # 定位“小题号”行和“满分值”行
    sub_idx = next(i for i, r in enumerate(rows) if clean(r[1]) == "小题号")
    full_idx = next(i for i, r in enumerate(rows) if clean(r[1]) == "满分值")
    header_idx = next(
        i for i, r in enumerate(rows) if clean(r[0]) == "学号" and clean(r[1]) == "姓名"
    )

    # 每道小题的列号、满分、所属目标
    questions = []
    for c in range(2, len(rows[sub_idx])):
        qno = clean(rows[sub_idx][c])
        if not qno or not qno.isdigit():
            continue
        q_full = to_num(rows[full_idx][c])
        target = None
        for r in rows[sub_idx + 1:header_idx]:
            label = clean(r[1])
            if label and label.startswith("课程目标") and clean(r[c]):
                target = label
                break
        questions.append({"col": c, "no": qno, "full": q_full, "target": target})

    # 试卷中每个目标的卷面满分
    paper_full = {}
    for q in questions:
        paper_full[q["target"]] = paper_full.get(q["target"], 0) + q["full"]

    # 学生逐题得分
    by_id = {s["学号"]: s for s in students}
    for r in rows[header_idx + 1:]:
        sid = clean(r[0])
        if sid not in by_id:
            continue
        got = {}
        for q in questions:
            v = to_num(r[q["col"]])
            got[q["target"]] = got.get(q["target"], 0) + (v or 0)
        by_id[sid]["期末"] = got
    return questions, paper_full


# ---------- 第五步：汇总 ----------
def step5_report(students, output, full, paper_full):
    targets = list(MATRIX.keys())
    n = len(students)
    result = {}
    for t in targets:
        daily_avg = {
            link: sum(s["平时"][link] for s in students) / n * output[t][link]
            for link in METHOD["平时"]
        }
        final_avg = (
            sum(s["期末"][t] for s in students) / n / paper_full[t] * FINAL_TARGET_SCORE[t]
        )
        total = sum(daily_avg.values()) + final_avg
        result[t] = {
            "平时明细": daily_avg,
            "期末": final_avg,
            "实得": total,
            "理论满分": full[t],
            "达成度": total / full[t],
        }
    return result


def main():
    link_weights = step1_link_weights()
    output, full = step2_output_weights(link_weights)

    print("=" * 62)
    print("第一步 环节权重：", {k: round(v, 4) for k, v in link_weights.items()})
    print("第二步 产出权重：")
    for t in output:
        print(f"  {t}: " + ", ".join(f"{k}={v:.4f}" for k, v in output[t].items()))
        print(f"    理论满分 = {full[t]:.2f}")

    daily_rows = load_rows("平时成绩表.xlsx")
    students = step3_daily(daily_rows, output)
    print(f"\n平时成绩表解析学生数：{len(students)}")

    exam_rows = load_rows("试卷分解表.xlsx")
    questions, paper_full = step4_final(exam_rows, students)
    print(f"期末试卷小题数：{len(questions)}，各目标卷面满分：{paper_full}")
    print(f"期末成绩表匹配学生数：{sum(1 for s in students if '期末' in s)}")

    report = step5_report(students, output, full, paper_full)

    print("\n" + "=" * 62)
    print("最终报表（全班均值）")
    print("-" * 62)
    for t, r in report.items():
        detail = ", ".join(f"{k}={v:.2f}" for k, v in r["平时明细"].items())
        print(f"{t}: 平时[{detail}] 期末={r['期末']:.2f}")
        print(
            f"  实得={r['实得']:.2f} / 理论满分={r['理论满分']:.2f}"
            f" → 达成度={r['达成度'] * 100:.1f}%"
        )
    print("=" * 62)
    print("文档基准：目标1 = 55%，目标2 = 74%")


if __name__ == "__main__":
    main()
