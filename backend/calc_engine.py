"""达成度计算引擎（配置驱动版）

设计要点：
- 试卷结构不再从 Excel 里解析，而是由系统配置（PAPER_STRUCTURE）提供
- 教师上传的期末成绩表是简单结构：学号 | 姓名 | 第1题 | 第2题 | ...
- 平时成绩表沿用原结构：学号 | 姓名 | 各平时环节

运行：python backend/calc_engine.py
"""

from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "示例"

# ============================================================
# 一、系统配置（对应网页端配置的内容）
# ============================================================

# 1. 成绩评定方法：平时 40%（作业40/表现40/测验20），期末 60%
METHOD = {
    "平时占比": 0.4,
    "期末占比": 0.6,
    "平时环节": {"作业": 0.4, "课堂表现": 0.4, "测验": 0.2},
}

# 2. 课程目标与考核环节对应关系（大纲原始比例）
MATRIX = {
    "课程目标1": {"作业": 0.2, "课堂表现": 0.2, "测验": 0.1, "期末考试": 0.5},
    "课程目标2": {"作业": 0.4, "课堂表现": 0.3, "测验": 0.2, "期末考试": 0.1},
}

# 3. 试卷结构：大题 → 小题，每题满分 + 课程目标
PAPER_STRUCTURE = [
    {"大题": "一、选择题", "小题": [
        {"题号": 1, "满分": 3, "目标": "课程目标1"},
        {"题号": 2, "满分": 3, "目标": "课程目标2"},
        {"题号": 3, "满分": 3, "目标": "课程目标1"},
        {"题号": 4, "满分": 3, "目标": "课程目标1"},
        {"题号": 5, "满分": 3, "目标": "课程目标1"},
        {"题号": 6, "满分": 3, "目标": "课程目标1"},
    ]},
    {"大题": "二、填空题", "小题": [
        {"题号": 7, "满分": 6, "目标": "课程目标1"},
        {"题号": 8, "满分": 6, "目标": "课程目标1"},
        {"题号": 9, "满分": 6, "目标": "课程目标1"},
        {"题号": 10, "满分": 6, "目标": "课程目标1"},
        {"题号": 11, "满分": 6, "目标": "课程目标1"},
        {"题号": 12, "满分": 6, "目标": "课程目标1"},
    ]},
    {"大题": "三、计算题", "小题": [
        {"题号": 13, "满分": 6, "目标": "课程目标2"},
        {"题号": 14, "满分": 6, "目标": "课程目标1"},
        {"题号": 15, "满分": 10, "目标": "课程目标2"},
    ]},
    {"大题": "四、综合题", "小题": [
        {"题号": 16, "满分": 10, "目标": "课程目标1"},
        {"题号": 17, "满分": 14, "目标": "课程目标1"},
    ]},
]


# ============================================================
# 二、工具函数
# ============================================================

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


def normalize(name):
    """列名归一化：去空格、特殊符号、括号内容，用于模糊匹配。"""
    if not name:
        return ""
    s = str(name).replace("\xa0", "").replace(" ", "")
    # 去掉括号及其内容，如 “作业（20%）” -> “作业”
    for left, right in (("（", "）"), ("(", ")")):
        while left in s and right in s:
            a, b = s.index(left), s.index(right)
            if b > a:
                s = s[:a] + s[b + 1:]
            else:
                break
    return s.strip()


def find_header(rows, required):
    """动态锚点扫描：找到同时包含所有 required 列名的行。

    支持模糊匹配：列名归一化后包含关键字即视为命中。
    """
    for i, r in enumerate(rows):
        names = [clean(c) for c in r]
        normed = [normalize(c) for c in names]
        if all(any(req in n for n in normed) for req in required):
            return i, names
    raise ValueError(f"未找到包含 {required} 的表头行")


def match_column(names, keyword, aliases=()):
    """在表头中定位列：先精确匹配，再别名匹配，最后模糊包含匹配。

    返回列索引，找不到返回 None。
    """
    normed = [normalize(n) for n in names]
    key = normalize(keyword)

    # 1. 精确匹配
    if key in normed:
        return normed.index(key)

    # 2. 别名匹配
    for alias in aliases:
        a = normalize(alias)
        if a in normed:
            return normed.index(a)

    # 3. 模糊包含匹配（列名包含关键字，或关键字包含列名）
    for i, n in enumerate(normed):
        if n and (key in n or n in key):
            return i
    return None


def build_column_mapping(names, fields, aliases_map=None):
    """构建字段 -> 列索引的映射，返回 (mapping, missing)。

    对应文档中的“列映射确认抽屉”：系统先自动匹配，
    未识别的字段交给教师确认。
    """
    aliases_map = aliases_map or {}
    mapping, missing = {}, []
    for field in fields:
        idx = match_column(names, field, aliases_map.get(field, ()))
        if idx is None:
            missing.append(field)
        else:
            mapping[field] = idx
    return mapping, missing


# ============================================================
# 三、试卷结构校验与派生数据
# ============================================================

def validate_structure():
    """校验试卷结构：总分 100、每题只归一个目标、题号连续。"""
    questions = [q for g in PAPER_STRUCTURE for q in g["小题"]]
    total = sum(q["满分"] for q in questions)
    assert total == 100, f"试卷总分应为 100，实际 {total}"

    numbers = [q["题号"] for q in questions]
    assert numbers == list(range(1, len(numbers) + 1)), "题号必须从 1 连续编号"

    targets = set(MATRIX.keys())
    for q in questions:
        assert q["目标"] in targets, f"第{q['题号']}题目标 {q['目标']} 无效"
    return questions


def paper_target_full(questions):
    """试卷中各课程目标的卷面满分。"""
    result = {}
    for q in questions:
        result[q["目标"]] = result.get(q["目标"], 0) + q["满分"]
    return result


# ============================================================
# 四、五步计算
# ============================================================

def step1_link_weights():
    """第一步：各环节在总成绩中的实际权重（分值）。"""
    weights = {
        name: METHOD["平时占比"] * ratio
        for name, ratio in METHOD["平时环节"].items()
    }
    weights["期末考试"] = METHOD["期末占比"]
    return weights


def step2_output_weights(link_weights):
    """第二步：产出权重（列归一化）与理论满分。"""
    targets = list(MATRIX.keys())
    output = {t: {} for t in targets}
    for link, link_score in link_weights.items():
        col_sum = sum(MATRIX[t][link] for t in targets)
        for t in targets:
            output[t][link] = link_score * MATRIX[t][link] / col_sum
    full = {t: sum(output[t].values()) * 100 for t in targets}
    return output, full


# 平时环节列名别名表：教师表里的常见写法
DAILY_ALIASES = {
    "作业": ("平时作业", "作业成绩", "课后作业", "作业分"),
    "课堂表现": ("表现", "课堂", "平时表现", "课堂参与", "考勤"),
    "测验": ("小测验", "随堂测验", "测验成绩", "测试", "小测"),
}

# 统计行关键字：这些行不是学生数据
STAT_KEYS = ("平均", "合计", "统计", "最高", "最低", "及格率", "标准差", "汇总")


def load_daily_students(verbose=True):
    """读取平时成绩表：学号 | 姓名 | 各平时环节。

    对应文档的“高容错解析”：
    - 动态锚点扫描找表头（忽略顶部标题行、空行）
    - 列名模糊匹配 + 别名容错
    - 过滤统计行
    - 分数合法性校验（0~100）
    """
    rows = load_rows("平时成绩表.xlsx")
    idx, names = find_header(rows, ["学号", "姓名"])

    # 列映射：学号、姓名 + 各平时环节
    fields = ["学号", "姓名"] + list(METHOD["平时环节"].keys())
    mapping, missing = build_column_mapping(names, fields, DAILY_ALIASES)
    if missing:
        raise ValueError(
            f"平时成绩表缺少列：{missing}。"
            f"表头为 {[n for n in names if n]}，请确认列名或使用系统模板"
        )

    if verbose:
        print("  列映射确认：")
        for field, c in mapping.items():
            print(f"    {field} ← 第{c + 1}列「{names[c]}」")

    students = []
    for r in rows[idx + 1:]:
        sid = clean(r[mapping["学号"]])
        name = clean(r[mapping["姓名"]])
        if not sid or not name:
            continue
        if any(k in name for k in STAT_KEYS):
            continue

        daily = {}
        for link in METHOD["平时环节"]:
            v = to_num(r[mapping[link]])
            if v is None:
                raise ValueError(f"学号 {sid} 的「{link}」成绩为空或非数值")
            if not 0 <= v <= 100:
                raise ValueError(f"学号 {sid} 的「{link}」成绩 {v} 超出 0~100")
            daily[link] = v

        students.append({"学号": sid, "姓名": name, "平时": daily})

    # 学号重复检查
    ids = [s["学号"] for s in students]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"平时成绩表存在重复学号：{sorted(dup)}")

    return students


def load_final_scores(students, questions):
    """读取期末成绩表：学号 | 姓名 | 第1题 | 第2题 | ...

    表头形如 “第1题(3分/目标1)”，按“第N题”前缀定位列。
    """
    rows = load_rows("期末小题成绩录入模板.xlsx")
    idx, names = find_header(rows, ["学号", "姓名"])

    # 学号、姓名列也走模糊匹配
    base, missing_base = build_column_mapping(names, ["学号", "姓名"])
    if missing_base:
        raise ValueError(f"期末成绩表缺少列：{missing_base}")

    # 建立 题号 -> 列号 映射
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

    missing = [q["题号"] for q in questions if q["题号"] not in col_of]
    if missing:
        raise ValueError(f"期末成绩表缺少题目列：{missing}")

    by_id = {s["学号"]: s for s in students}
    matched, seen = 0, set()
    for r in rows[idx + 1:]:
        sid = clean(r[base["学号"]])
        if sid not in by_id:
            continue
        if sid in seen:
            raise ValueError(f"期末成绩表存在重复学号：{sid}")
        seen.add(sid)
        matched += 1
        got = {}
        for q in questions:
            v = to_num(r[col_of[q["题号"]]])
            if v is None:
                raise ValueError(f"学号 {sid} 第{q['题号']}题成绩为空")
            if v < 0:
                raise ValueError(f"学号 {sid} 第{q['题号']}题得分为负数 {v}")
            if v > q["满分"]:
                raise ValueError(
                    f"学号 {sid} 第{q['题号']}题得分 {v} 超过满分 {q['满分']}"
                )
            got[q["题号"]] = v
        by_id[sid]["期末"] = got

    # 检查是否有学生缺少期末成绩
    no_final = [s["学号"] for s in students if "期末" not in s]
    if no_final:
        raise ValueError(f"以下学生缺少期末成绩：{no_final[:5]}...")
    return matched


def step5_report(students, output, full, questions):
    """第五步：汇总生成达成度报表。"""
    targets = list(MATRIX.keys())
    p_full = paper_target_full(questions)
    n = len(students)
    result = {}

    for t in targets:
        # 平时贡献：原始百分制分 × 产出权重
        daily = {
            link: sum(s["平时"][link] for s in students) / n * output[t][link]
            for link in METHOD["平时环节"]
        }
        # 期末贡献：该目标实得 / 该目标卷面满分 × 该目标期末设定分值
        target_qs = [q["题号"] for q in questions if q["目标"] == t]
        got_sum = sum(s["期末"][qn] for s in students for qn in target_qs)
        final = got_sum / n / p_full[t] * (output[t]["期末考试"] * 100)

        total = sum(daily.values()) + final
        result[t] = {
            "平时明细": daily,
            "期末": final,
            "实得": total,
            "理论满分": full[t],
            "达成度": total / full[t],
        }
    return result


# ============================================================
# 五、主流程
# ============================================================

def main():
    questions = validate_structure()
    print(f"试卷结构校验通过：{len(questions)} 道小题，总分 "
          f"{sum(q['满分'] for q in questions)}")

    link_weights = step1_link_weights()
    output, full = step2_output_weights(link_weights)

    print("\n第一步 环节权重：", {k: round(v, 4) for k, v in link_weights.items()})
    print("第二步 产出权重与理论满分：")
    for t in output:
        detail = ", ".join(f"{k}={v:.4f}" for k, v in output[t].items())
        print(f"  {t}: {detail}")
        print(f"    理论满分 = {full[t]:.2f}")

    students = load_daily_students()
    print(f"\n平时成绩表：{len(students)} 人")

    matched = load_final_scores(students, questions)
    print(f"期末成绩表：匹配 {matched} 人")
    print(f"试卷各目标卷面满分：{paper_target_full(questions)}")

    report = step5_report(students, output, full, questions)

    print("\n" + "=" * 62)
    print("最终报表（全班均值）")
    print("-" * 62)
    for t, r in report.items():
        detail = ", ".join(f"{k}={v:.2f}" for k, v in r["平时明细"].items())
        print(f"{t}: 平时[{detail}] 期末={r['期末']:.2f}")
        print(f"  实得={r['实得']:.2f} / 理论满分={r['理论满分']:.2f}"
              f" → 达成度={r['达成度'] * 100:.1f}%")
    print("=" * 62)


if __name__ == "__main__":
    main()
