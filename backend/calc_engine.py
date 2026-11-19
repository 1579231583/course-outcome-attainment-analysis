"""达成度计算引擎（配置驱动版）

设计要点：
- 试卷结构不再从 Excel 里解析，而是由系统配置（PAPER_STRUCTURE）提供
- 教师上传的期末成绩表是简单结构：学号 | 姓名 | 第1题 | 第2题 | ...
- 平时成绩表沿用原结构：学号 | 姓名 | 各平时环节
- 支持两种工作模式：
  1. 严格模式（load_daily_students + load_final_scores）：发现异常立即抛 ValueError
  2. 预览纠错模式（parse_sheets_for_preview + calculate_from_records）：
     返回列映射详情、全量学生数据及单元格级错误列表，供前端在线预览、双击纠错与实时重算

运行：python backend/calc_engine.py
"""

from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "示例"

# ============================================================
# 一、系统默认配置（对应网页端配置的内容）
# ============================================================

# 0. 达成度合格阈值（默认 0.65，支持课程级自定义）
PASS_THRESHOLD = 0.65

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


def extract_question_col_map(names):
    """从期末表头中提取 题号(int) -> 列索引(int) 映射。"""
    col_of = {}
    for c, name in enumerate(names):
        if not name:
            continue
        s = str(name).strip()
        if not s.startswith("第"):
            continue
        num = ""
        for ch in s[1:]:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            col_of[int(num)] = c
    return col_of


# ============================================================
# 三、试卷结构校验与派生数据
# ============================================================

def validate_structure():
    """校验试卷结构：总分 100、每题只归一个目标、题号连续、期末权重目标有题。"""
    if not MATRIX:
        raise ValueError("课程目标矩阵不能为空")

    questions = [q for g in PAPER_STRUCTURE for q in g["小题"]]
    if not questions:
        raise ValueError("试卷结构不能为空，请至少配置一道小题")

    total = sum(q["满分"] for q in questions)
    if abs(total - 100) > 1e-6:
        raise ValueError(f"试卷总分应为 100，实际 {total}")

    numbers = [q["题号"] for q in questions]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("题号必须从 1 连续编号")

    targets = set(MATRIX.keys())
    for q in questions:
        if q["满分"] <= 0:
            raise ValueError(f"第{q['题号']}题满分必须大于 0")
        if q["目标"] not in targets:
            raise ValueError(f"第{q['题号']}题目标 {q['目标']} 无效")

    # 检查：若某目标在矩阵中有期末考试权重（且期末总占比 > 0），试卷中必须至少有一道该目标的题
    p_full = paper_target_full(questions)
    if METHOD.get("期末占比", 0) > 0:
        for t in targets:
            if MATRIX[t].get("期末考试", 0) > 0 and p_full.get(t, 0) <= 0:
                raise ValueError(
                    f"「{t}」在对应关系矩阵中设有期末考试比例，但试卷中未分配任何属于该目标的小题"
                )

    return questions


def paper_target_full(questions):
    """试卷中各课程目标的卷面满分（包含卷面为 0 的目标键）。"""
    result = {t: 0 for t in MATRIX}
    for q in questions:
        result[q["目标"]] = result.get(q["目标"], 0) + q["满分"]
    return result


# ============================================================
# 四、五步计算
# ============================================================

def step1_link_weights():
    """第一步：各环节在总成绩中的实际权重（分值比例 0~1）。"""
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
        col_sum = sum(MATRIX[t].get(link, 0) for t in targets)
        if link_score > 0 and col_sum <= 0:
            raise ValueError(
                f"考核环节「{link}」在对应关系矩阵中的整列比例之和为 0，无法分配该环节权重"
            )
        for t in targets:
            output[t][link] = (
                link_score * MATRIX[t].get(link, 0) / col_sum if col_sum > 0 else 0.0
            )
    full = {t: sum(output[t].values()) * 100 for t in targets}
    return output, full


# 平时环节列名别名表：教师表里的常见写法
DAILY_ALIASES = {
    "作业": ("平时作业", "作业成绩", "课后作业", "作业分"),
    "课堂表现": ("表现", "课堂", "平时表现", "课堂参与", "考勤", "出勤"),
    "测验": ("小测验", "随堂测验", "测验成绩", "测试", "小测", "阶段测验"),
    "实验": ("实验成绩", "上机", "实践", "实验得分"),
}

# 统计行关键字：这些行不是学生数据
STAT_KEYS = ("平均", "合计", "统计", "最高", "最低", "及格率", "标准差", "汇总", "人数")


def _is_stat_row(sid, name):
    """判断是否为末尾统计行或无效空行。"""
    if not sid or not name:
        return True
    s_sid, s_name = str(sid), str(name)
    return any(k in s_name or k in s_sid for k in STAT_KEYS)


def load_daily_students(verbose=True):
    """读取平时成绩表：学号 | 姓名 | 各平时环节（严格模式）。"""
    rows = load_rows("平时成绩表.xlsx")
    idx, names = find_header(rows, ["学号", "姓名"])

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
        sid = clean(r[mapping["学号"]]) if mapping["学号"] < len(r) else None
        name = clean(r[mapping["姓名"]]) if mapping["姓名"] < len(r) else None
        if _is_stat_row(sid, name):
            continue

        daily = {}
        for link in METHOD["平时环节"]:
            col_idx = mapping[link]
            v = to_num(r[col_idx]) if col_idx < len(r) else None
            if v is None:
                raise ValueError(f"学号 {sid} 的「{link}」成绩为空或非数值")
            if not 0 <= v <= 100:
                raise ValueError(f"学号 {sid} 的「{link}」成绩 {v} 超出 0~100")
            daily[link] = v

        students.append({"学号": sid, "姓名": name, "平时": daily})

    ids = [s["学号"] for s in students]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"平时成绩表存在重复学号：{sorted(dup)}")

    return students


def load_final_scores(students, questions):
    """读取期末成绩表：学号 | 姓名 | 第1题 | 第2题 | ...（严格模式）。"""
    rows = load_rows("期末小题成绩录入模板.xlsx")
    idx, names = find_header(rows, ["学号", "姓名"])

    base, missing_base = build_column_mapping(names, ["学号", "姓名"])
    if missing_base:
        raise ValueError(f"期末成绩表缺少列：{missing_base}")

    col_of = extract_question_col_map(names)
    missing = [q["题号"] for q in questions if q["题号"] not in col_of]
    if missing:
        raise ValueError(f"期末成绩表缺少题目列：{missing}")

    by_id = {s["学号"]: s for s in students}
    matched, seen = 0, set()
    for r in rows[idx + 1:]:
        sid = clean(r[base["学号"]]) if base["学号"] < len(r) else None
        if sid not in by_id:
            continue
        if sid in seen:
            raise ValueError(f"期末成绩表存在重复学号：{sid}")
        seen.add(sid)
        matched += 1
        got = {}
        for q in questions:
            c = col_of[q["题号"]]
            v = to_num(r[c]) if c < len(r) else None
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

    no_final = [s["学号"] for s in students if "期末" not in s]
    if no_final:
        raise ValueError(f"以下学生缺少期末成绩：{no_final[:5]}...")
    return matched


def step5_report(students, output, full, questions, threshold=None):
    """第五步：汇总生成达成度报表。"""
    if threshold is None:
        threshold = PASS_THRESHOLD
    targets = list(MATRIX.keys())
    p_full = paper_target_full(questions)
    n = len(students)
    if n == 0:
        raise ValueError("有效学生人数为 0，无法计算达成度")
    result = {}

    for t in targets:
        # 平时贡献：原始百分制分 × 产出权重
        daily = {
            link: sum(s["平时"][link] for s in students) / n * output[t][link]
            for link in METHOD["平时环节"]
        }
        # 期末贡献：该目标实得 / 该目标卷面满分 × 该目标期末设定分值
        # 边界保护：若某目标不考期末（产出权重为 0 或卷面满分为 0），期末贡献为 0
        target_qs = [q["题号"] for q in questions if q["目标"] == t]
        if output[t].get("期末考试", 0) > 0 and p_full.get(t, 0) > 0 and target_qs:
            got_sum = sum(
                s["期末"].get(qn, s["期末"].get(str(qn), 0))
                for s in students
                for qn in target_qs
            )
            paper_avg = got_sum / n
            final = paper_avg / p_full[t] * (output[t]["期末考试"] * 100)
        else:
            paper_avg = 0.0
            final = 0.0

        total = sum(daily.values()) + final
        ach = total / full[t] if full[t] > 0 else 0.0
        result[t] = {
            "平时明细": daily,
            "期末": final,
            "卷面均分": paper_avg,
            "卷面满分": p_full.get(t, 0),
            "实得": total,
            "理论满分": full[t],
            "达成度": ach,
            "是否达标": ach >= threshold,
        }
    return result


# ============================================================
# 五、预览与在线纠错模式（支撑列映射抽屉 + 表格标红就地编辑）
# ============================================================

def parse_sheets_for_preview(
    daily_rows,
    final_rows,
    custom_daily_map=None,
    custom_final_map=None,
):
    """非阻断式解析平时成绩表与期末小题成绩表。

    返回：
    - daily_meta: 平时表头、自动/自定义列映射、缺失字段、前5行预览
    - final_meta: 期末表头、自动/自定义列映射、缺失题目列、前5行预览
    - students: 合并后的学生列表 [{"学号", "姓名", "平时": {...}, "期末": {...}, "状态": ...}]
    - errors: 结构化异常列表（精确到学号、字段、当前值、合法范围、错误类型）
    """
    questions = validate_structure()
    daily_links = list(METHOD["平时环节"].keys())

    # 1. 定位平时表头与列映射
    d_idx, d_names = find_header(daily_rows, ["学号", "姓名"])
    d_fields = ["学号", "姓名"] + daily_links
    d_map, d_missing = build_column_mapping(d_names, d_fields, DAILY_ALIASES)
    if custom_daily_map:
        for k, v in custom_daily_map.items():
            if v is not None and 0 <= int(v) < len(d_names):
                d_map[k] = int(v)
                if k in d_missing:
                    d_missing.remove(k)

    # 2. 定位期末表头与列映射
    f_idx, f_names = find_header(final_rows, ["学号", "姓名"])
    f_base, f_missing_base = build_column_mapping(f_names, ["学号", "姓名"])
    f_qmap = extract_question_col_map(f_names)
    if custom_final_map:
        for k, v in custom_final_map.items():
            if v is not None and 0 <= int(v) < len(f_names):
                if k in ("学号", "姓名"):
                    f_base[k] = int(v)
                    if k in f_missing_base:
                        f_missing_base.remove(k)
                else:
                    # 题号映射，支持 "1" 或 "第1题"
                    qn = int(str(k).replace("第", "").replace("题", ""))
                    f_qmap[qn] = int(v)

    f_missing_qs = [q["题号"] for q in questions if q["题号"] not in f_qmap]

    daily_meta = {
        "header_row": d_idx + 1,
        "headers": [n or f"列{i + 1}" for i, n in enumerate(d_names)],
        "mapping": d_map,
        "missing": d_missing,
        "sample_rows": [
            [clean(c) for c in r[:len(d_names)]]
            for r in daily_rows[d_idx + 1:d_idx + 6]
        ],
    }
    final_meta = {
        "header_row": f_idx + 1,
        "headers": [n or f"列{i + 1}" for i, n in enumerate(f_names)],
        "base_mapping": f_base,
        "question_mapping": {str(k): v for k, v in f_qmap.items()},
        "missing_base": f_missing_base,
        "missing_questions": f_missing_qs,
        "sample_rows": [
            [clean(c) for c in r[:len(f_names)]]
            for r in final_rows[f_idx + 1:f_idx + 6]
        ],
    }

    errors = []
    students = []
    by_id = {}

    # 若核心列尚未映射全，先返回列映射信息让前端弹窗确认
    if d_missing or f_missing_base or f_missing_qs:
        if d_missing:
            errors.append({
                "type": "mapping",
                "source": "daily",
                "message": f"平时成绩表未识别到以下列：{d_missing}，请在列映射中手动指定",
            })
        if f_missing_base or f_missing_qs:
            errors.append({
                "type": "mapping",
                "source": "final",
                "message": f"期末成绩表缺少列：{f_missing_base + [f'第{q}题' for q in f_missing_qs]}",
            })
        return {
            "ok": False,
            "need_mapping": True,
            "daily_meta": daily_meta,
            "final_meta": final_meta,
            "students": [],
            "errors": errors,
        }

    # 3. 逐行解析平时成绩表
    seen_daily = set()
    for row_no, r in enumerate(daily_rows[d_idx + 1:], start=d_idx + 2):
        sid = clean(r[d_map["学号"]]) if d_map["学号"] < len(r) else None
        name = clean(r[d_map["姓名"]]) if d_map["姓名"] < len(r) else None
        if _is_stat_row(sid, name):
            continue

        if sid in seen_daily:
            errors.append({
                "type": "duplicate",
                "source": "daily",
                "sid": sid,
                "name": name,
                "field": "学号",
                "message": f"平时成绩表中存在重复学号 {sid}（第 {row_no} 行）",
            })
            continue
        seen_daily.add(sid)

        daily_scores = {}
        for link in daily_links:
            c = d_map[link]
            raw_val = r[c] if c < len(r) else None
            v = to_num(raw_val)
            daily_scores[link] = v if v is not None else clean(raw_val)
            if v is None:
                errors.append({
                    "type": "score",
                    "source": "daily",
                    "sid": sid,
                    "name": name,
                    "field": link,
                    "value": clean(raw_val),
                    "min": 0,
                    "max": 100,
                    "message": f"学号 {sid}（{name}）的「{link}」成绩为空或非数值",
                })
            elif not (0 <= v <= 100):
                errors.append({
                    "type": "score",
                    "source": "daily",
                    "sid": sid,
                    "name": name,
                    "field": link,
                    "value": v,
                    "min": 0,
                    "max": 100,
                    "message": f"学号 {sid}（{name}）的「{link}」成绩 {v} 超出 0~100 范围",
                })

        stu = {
            "学号": sid,
            "姓名": name,
            "平时": daily_scores,
            "期末": {},
            "期末缺失": True,
        }
        students.append(stu)
        by_id[sid] = stu

    # 4. 逐行解析期末成绩表
    seen_final = set()
    extra_final_students = []
    for row_no, r in enumerate(final_rows[f_idx + 1:], start=f_idx + 2):
        sid = clean(r[f_base["学号"]]) if f_base["学号"] < len(r) else None
        name = clean(r[f_base["姓名"]]) if f_base["姓名"] < len(r) else None
        if _is_stat_row(sid, name):
            continue

        if sid in seen_final:
            errors.append({
                "type": "duplicate",
                "source": "final",
                "sid": sid,
                "name": name,
                "field": "学号",
                "message": f"期末成绩表中存在重复学号 {sid}（第 {row_no} 行）",
            })
            continue
        seen_final.add(sid)

        if sid not in by_id:
            extra_final_students.append({"学号": sid, "姓名": name})
            continue

        stu = by_id[sid]
        stu["期末缺失"] = False
        got = {}
        for q in questions:
            qn = q["题号"]
            c = f_qmap[qn]
            raw_val = r[c] if c < len(r) else None
            v = to_num(raw_val)
            got[qn] = v if v is not None else clean(raw_val)
            if v is None:
                errors.append({
                    "type": "score",
                    "source": "final",
                    "sid": sid,
                    "name": stu["姓名"],
                    "field": f"第{qn}题",
                    "question_no": qn,
                    "value": clean(raw_val),
                    "min": 0,
                    "max": q["满分"],
                    "message": f"学号 {sid}（{stu['姓名']}）第{qn}题成绩为空或非数值",
                })
            elif v < 0 or v > q["满分"]:
                errors.append({
                    "type": "score",
                    "source": "final",
                    "sid": sid,
                    "name": stu["姓名"],
                    "field": f"第{qn}题",
                    "question_no": qn,
                    "value": v,
                    "min": 0,
                    "max": q["满分"],
                    "message": (
                        f"学号 {sid}（{stu['姓名']}）第{qn}题得分 {v} "
                        f"超出合法范围 0~{q['满分']}"
                    ),
                })
        stu["期末"] = got

    # 5. 检查平时表有但期末表缺失的学生
    for stu in students:
        if stu["期末缺失"]:
            # 默认用 None 占位，方便前端表格渲染与一键补 0 或剔除
            stu["期末"] = {q["题号"]: None for q in questions}
            errors.append({
                "type": "missing_final",
                "source": "final",
                "sid": stu["学号"],
                "name": stu["姓名"],
                "field": "期末成绩",
                "message": f"学号 {stu['学号']}（{stu['姓名']}）在期末成绩表中缺失（可选择补0分或剔除）",
            })

    return {
        "ok": len(errors) == 0,
        "need_mapping": False,
        "daily_meta": daily_meta,
        "final_meta": final_meta,
        "students": students,
        "extra_final_students": extra_final_students,
        "errors": errors,
    }


def validate_and_normalize_records(students, questions):
    """对前端传回的（已在线纠错的）学生 JSON 记录做最终校验并标准化键类型。"""
    if not students:
        raise ValueError("学生名单为空，无法计算")

    daily_links = list(METHOD["平时环节"].keys())
    normalized = []
    seen = set()

    for s in students:
        sid = clean(s.get("学号"))
        name = clean(s.get("姓名"))
        if not sid or not name:
            continue
        if sid in seen:
            raise ValueError(f"存在重复学号：{sid}")
        seen.add(sid)

        raw_daily = s.get("平时") or {}
        daily = {}
        for link in daily_links:
            v = to_num(raw_daily.get(link))
            if v is None:
                raise ValueError(f"学号 {sid}（{name}）的「{link}」成绩为空或非数值")
            if not (0 <= v <= 100):
                raise ValueError(f"学号 {sid}（{name}）的「{link}」成绩 {v} 超出 0~100")
            daily[link] = v

        raw_final = s.get("期末") or {}
        final = {}
        for q in questions:
            qn = q["题号"]
            # JSON 序列化后键可能是字符串 "1" 或整数 1
            raw_v = raw_final.get(qn, raw_final.get(str(qn)))
            v = to_num(raw_v)
            if v is None:
                raise ValueError(f"学号 {sid}（{name}）第{qn}题成绩为空或非数值")
            if v < 0:
                raise ValueError(f"学号 {sid}（{name}）第{qn}题得分为负数 {v}")
            if v > q["满分"]:
                raise ValueError(
                    f"学号 {sid}（{name}）第{qn}题得分 {v} 超过满分 {q['满分']}"
                )
            final[qn] = v

        normalized.append({"学号": sid, "姓名": name, "平时": daily, "期末": final})

    return normalized


# ============================================================
# 六、命令行主流程（回归测试基准）
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
