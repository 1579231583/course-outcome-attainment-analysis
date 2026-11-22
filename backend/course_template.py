"""公共课程规则模板 Excel 生成与导入模块

【新版格式：一个工作表 = 一门课程】
一个 Excel 文件里可以放任意多门课程，底部每个工作表（Sheet）就是一门课，
每页从上到下依次填写：
  一、课程基本信息（配置项 | 数值）
  二、平时环节构成（环节名称 | 占平时比例）
  三、课程目标与考核环节对应矩阵（课程目标 | 目标说明 | 各环节... | 期末考试）
  四、期末试卷结构（大题名称 | 题号 | 小题满分 | 所属课程目标）
新增课程：右键工作表标签 → 移动或复制 → 勾选“建立副本”，改数字即可。
名为「使用说明」或不含“课程基本信息”区块的工作表会被自动跳过。

【兼容旧版】单课程竖表（3 个 Sheet，Sheet1 的 A1 为“配置项”）。
"""

import io
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import calc_engine as eng

THIN = Side(style="thin", color="CBD5E1")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="E0E7FF")
SECTION_FILL = PatternFill("solid", fgColor="1E3A8A")
TIP_FILL = PatternFill("solid", fgColor="FEF9C3")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

# 区块标题关键字（解析时据此定位）
SEC1, SEC2, SEC3, SEC4 = "课程基本信息", "平时环节构成", "对应矩阵", "期末试卷结构"

BASIC_FIELDS = [
    ("课程名称", "必填"),
    ("课程代码", "选填"),
    ("开课学期", "必填，如 2025-2026-1"),
    ("默认班级", "选填，教师选用后可改"),
    ("课程类别", "选填，如 基础课 / 专业必修课"),
    ("学分", "选填"),
    ("授课学时", "选填"),
    ("合格阈值", "0~1，默认 0.65"),
    ("平时占比", "与期末占比之和须为 1"),
    ("期末占比", "与平时占比之和须为 1"),
]

SAMPLE_COURSES = [
    {
        "meta": {"课程名称": "高等数学A（II）", "课程代码": "1230601002F", "学期": "2023-2024-2",
                 "班级": "23智能制造1班", "课程类别": "基础课", "学分": 5.5, "授课学时": 88},
        "threshold": 0.65,
        "method": eng.METHOD,
        "matrix": eng.MATRIX,
        "target_descriptions": {
            "课程目标1": "掌握微积分与常微分方程的基本概念、理论与计算方法",
            "课程目标2": "能够运用高等数学工具建立模型并解决工程与几何实际问题",
        },
        "paper": eng.PAPER_STRUCTURE,
    },
    {
        "meta": {"课程名称": "数据结构与算法", "课程代码": "CS201", "学期": "2025-2026-1",
                 "班级": "24计算机科学与技术2班", "课程类别": "专业必修课", "学分": 4.0, "授课学时": 64},
        "threshold": 0.70,
        "method": {"平时占比": 0.5, "期末占比": 0.5, "平时环节": {"作业": 0.3, "实验": 0.5, "课堂表现": 0.2}},
        "matrix": {
            "课程目标1": {"作业": 0.4, "实验": 0.1, "课堂表现": 0.5, "期末考试": 0.6},
            "课程目标2": {"作业": 0.4, "实验": 0.3, "课堂表现": 0.3, "期末考试": 0.4},
            "课程目标3": {"作业": 0.2, "实验": 0.6, "课堂表现": 0.2, "期末考试": 0.0},
        },
        "target_descriptions": {
            "课程目标1": "掌握线性表、树、图等常用数据结构的概念与存储实现",
            "课程目标2": "能够分析算法时间与空间复杂度并设计高效求解算法",
            "课程目标3": "具备独立完成综合实验编码与调试的工程实践能力",
        },
        "paper": [
            {"大题": "一、选择题", "小题": [
                {"题号": 1, "满分": 5, "目标": "课程目标1"}, {"题号": 2, "满分": 5, "目标": "课程目标1"},
                {"题号": 3, "满分": 5, "目标": "课程目标1"}, {"题号": 4, "满分": 5, "目标": "课程目标2"}]},
            {"大题": "二、填空与简答题", "小题": [
                {"题号": 5, "满分": 10, "目标": "课程目标1"}, {"题号": 6, "满分": 10, "目标": "课程目标2"},
                {"题号": 7, "满分": 10, "目标": "课程目标2"}]},
            {"大题": "三、算法设计题", "小题": [
                {"题号": 8, "满分": 15, "目标": "课程目标1"}, {"题号": 9, "满分": 15, "目标": "课程目标2"},
                {"题号": 10, "满分": 20, "目标": "课程目标2"}]},
        ],
    },
    {
        "meta": {"课程名称": "大学物理B", "课程代码": "PHYS102", "学期": "2025-2026-1",
                 "班级": "24智能制造1班", "课程类别": "基础课", "学分": 4.0, "授课学时": 64},
        "threshold": 0.65,
        "method": {"平时占比": 0.3, "期末占比": 0.7, "平时环节": {"作业": 0.5, "实验": 0.3, "课堂表现": 0.2}},
        "matrix": {
            "课程目标1": {"作业": 0.3, "实验": 0.1, "课堂表现": 0.2, "期末考试": 0.6},
            "课程目标2": {"作业": 0.2, "实验": 0.4, "课堂表现": 0.2, "期末考试": 0.4},
        },
        "target_descriptions": {
            "课程目标1": "掌握力学与电磁学基本规律",
            "课程目标2": "具备物理实验测量与工程建模能力",
        },
        "paper": [
            {"大题": "一、基础题", "小题": [
                {"题号": 1, "满分": 10, "目标": "课程目标1"}, {"题号": 2, "满分": 10, "目标": "课程目标1"},
                {"题号": 3, "满分": 10, "目标": "课程目标2"}]},
            {"大题": "二、综合计算题", "小题": [
                {"题号": 4, "满分": 20, "目标": "课程目标1"}, {"题号": 5, "满分": 20, "目标": "课程目标2"},
                {"题号": 6, "满分": 30, "目标": "课程目标1"}]},
        ],
    },
]


# ============================================================
# 生成模板
# ============================================================

def _safe_title(name: str, used: set) -> str:
    s = "".join(ch for ch in (name or "课程") if ch not in '[]:*?/\\')[:28] or "课程"
    base, i = s, 2
    while s in used:
        s = f"{base[:25]}_{i}"
        i += 1
    used.add(s)
    return s


def _section(ws, r, text, ncols):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    c = ws.cell(r, 1, text)
    c.font = Font(bold=True, color="FFFFFF")
    c.fill = SECTION_FILL
    c.alignment = LEFT
    ws.row_dimensions[r].height = 22


def _header(ws, r, values):
    for i, v in enumerate(values, 1):
        c = ws.cell(r, i, v)
        c.font = Font(bold=True)
        c.fill = HEAD_FILL
        c.alignment = CENTER
        c.border = BORDER


def _row(ws, r, values, left_cols=()):
    for i, v in enumerate(values, 1):
        c = ws.cell(r, i, v)
        c.alignment = LEFT if i in left_cols else CENTER
        c.border = BORDER


def _write_course_sheet(ws, c):
    m, method = c["meta"], c["method"]
    links = list(method["平时环节"].keys()) + ["期末考试"]
    ncols = max(6, 2 + len(links))

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    t = ws.cell(1, 1, f"《{m.get('课程名称', '')}》课程达成度规则配置")
    t.font = Font(size=14, bold=True)
    t.alignment = CENTER
    ws.row_dimensions[1].height = 28
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    tip = ws.cell(2, 1, "提示：一个工作表 = 一门课程。新增课程请右键底部工作表标签 → 移动或复制 → 勾选“建立副本”，再修改内容。")
    tip.fill = TIP_FILL
    tip.alignment = LEFT

    r = 4
    _section(ws, r, f"一、{SEC1}", ncols)
    r += 1
    _header(ws, r, ["配置项", "数值", "填写说明"])
    values = {
        "课程名称": m.get("课程名称"), "课程代码": m.get("课程代码"), "开课学期": m.get("学期"),
        "默认班级": m.get("班级"), "课程类别": m.get("课程类别"), "学分": m.get("学分"),
        "授课学时": m.get("授课学时"), "合格阈值": c.get("threshold", 0.65),
        "平时占比": method["平时占比"], "期末占比": method["期末占比"],
    }
    for key, note in BASIC_FIELDS:
        r += 1
        _row(ws, r, [key, values.get(key), note], left_cols=(3,))

    r += 2
    _section(ws, r, f"二、{SEC2}（各环节占平时成绩的比例，合计须为 1；可增删行）", ncols)
    r += 1
    _header(ws, r, ["环节名称", "占平时比例"])
    for name, ratio in method["平时环节"].items():
        r += 1
        _row(ws, r, [name, ratio])

    r += 2
    _section(ws, r, f"三、课程目标与考核环节{SEC3}（填大纲相对比例，同列之和不必为 1；可增删目标行）", ncols)
    r += 1
    _header(ws, r, ["课程目标", "目标说明"] + links)
    for tg, row_map in c["matrix"].items():
        r += 1
        _row(ws, r, [tg, c.get("target_descriptions", {}).get(tg, "")] + [row_map.get(l, 0) for l in links],
             left_cols=(2,))

    r += 2
    _section(ws, r, f"四、{SEC4}（一行一道小题，总分须为 100；题号系统会自动重排）", ncols)
    r += 1
    _header(ws, r, ["大题名称", "题号", "小题满分", "所属课程目标"])
    for grp in c["paper"]:
        for q in grp["小题"]:
            r += 1
            _row(ws, r, [grp["大题"], q["题号"], q["满分"], q["目标"]])

    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 36
    ws.column_dimensions["C"].width = 26
    for cc in range(4, ncols + 1):
        ws.column_dimensions[get_column_letter(cc)].width = 12
    ws.sheet_view.showGridLines = False


def _write_guide_sheet(ws, n):
    lines = [
        "课程规则配置批量导入 · 使用说明",
        "",
        "1. 本文件中「使用说明」以外的每一个工作表 = 一门课程，可放任意多门课。",
        f"2. 已内置 {n} 门示例课程，可直接修改；新增课程：右键底部工作表标签 → 移动或复制 → 勾选“建立副本”。",
        "3. 每个课程工作表从上到下依次填写：一、课程基本信息；二、平时环节构成；三、目标与环节对应矩阵；四、期末试卷结构。",
        "4. 二中的环节名称必须与三中的列名一致（期末考试列固定保留）；某目标不考期末时，期末考试列填 0。",
        "5. 四中题号可随意填写，系统会按顺序自动重排为 1..N；所有小题满分之和须为 100。",
        "6. 上传后系统逐门校验，导入结果会逐门列出成功/失败原因，失败的课程不影响其它课程发布。",
    ]
    for i, text in enumerate(lines, 1):
        c = ws.cell(i, 1, text)
        c.alignment = LEFT
        if i == 1:
            c.font = Font(size=14, bold=True)
    ws.column_dimensions["A"].width = 110
    ws.sheet_view.showGridLines = False


def build_course_config_template(
    meta: dict | None = None,
    threshold: float = 0.65,
    method: dict | None = None,
    matrix: dict | None = None,
    paper: list | None = None,
    target_descriptions: dict | None = None,
) -> io.BytesIO:
    """生成「一个工作表 = 一门课程」的批量配置模板。

    若传入当前课程配置，则其作为第一门课程，其后附带内置示例课程（同名的跳过）。
    """
    courses = []
    if meta and method and matrix and paper:
        courses.append({
            "meta": meta, "threshold": threshold, "method": method, "matrix": matrix,
            "paper": paper, "target_descriptions": target_descriptions or {},
        })
    names = {c["meta"].get("课程名称") for c in courses}
    courses += [c for c in SAMPLE_COURSES if c["meta"]["课程名称"] not in names]

    wb = openpyxl.Workbook()
    _write_guide_sheet(wb.active, len(courses))
    wb.active.title = "使用说明"
    used = {"使用说明"}
    for c in courses:
        ws = wb.create_sheet(_safe_title(c["meta"].get("课程名称"), used))
        _write_course_sheet(ws, c)
    wb.active = 1

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ============================================================
# 解析：一个工作表 = 一门课程
# ============================================================

def _cell_a(row):
    return eng.clean(row[0]) if row else None


def _is_course_sheet(title: str, rows) -> bool:
    if "说明" in (title or ""):
        return False
    return any((_cell_a(r) or "").startswith("一、") and SEC1 in (_cell_a(r) or "") for r in rows)


def _collect_course_errors(course: dict, allow_empty_paper: bool = False) -> list[str]:
    """对提取出的课程结构做非阻断式完整规则校验，返回错误列表（供前端实时预览与在线修改）。"""
    errs = []
    meta = course.get("meta") or {}
    method = course.get("method") or {}
    matrix = course.get("matrix") or {}
    paper = course.get("paper") or []

    if not (meta.get("课程名称") or "").strip():
        errs.append("课程名称不能为空")
    d_r = float(method.get("平时占比") or 0)
    f_r = float(method.get("期末占比") or 0)
    if abs(d_r + f_r - 1.0) > 1e-6:
        errs.append(f"平时占比({d_r:g}) + 期末占比({f_r:g}) 之和为 {d_r + f_r:g}，须等于 1")

    d_links = method.get("平时环节") or {}
    if not d_links:
        errs.append("至少需保留 1 个平时环节")
    else:
        d_sum = sum(float(v or 0) for v in d_links.values())
        if abs(d_sum - 1.0) > 1e-6:
            errs.append(f"平时各环节比例之和为 {d_sum:.2f}，须等于 1")

    if not matrix:
        errs.append("至少需配置 1 个课程目标")
    else:
        try:
            lw = eng.step1_link_weights(method)
            eng.step2_output_weights(lw, matrix)
        except ValueError as e:
            errs.append(str(e))

    # 若允许仅大纲入库且尚未配置试卷，则跳过试卷结构校验
    has_qs = any(g.get("小题") for g in paper)
    if has_qs or not allow_empty_paper:
        try:
            eng.validate_structure(method, matrix, paper)
        except ValueError as e:
            errs.append(str(e))

    return errs


def _parse_course_sheet(rows, strict: bool = True) -> dict:
    marks = {}
    for i, r in enumerate(rows):
        a = _cell_a(r) or ""
        if SEC1 in a and "s1" not in marks:
            marks["s1"] = i
        elif SEC2 in a and "s2" not in marks:
            marks["s2"] = i
        elif SEC3 in a and "s3" not in marks:
            marks["s3"] = i
        elif SEC4 in a and "s4" not in marks:
            marks["s4"] = i
    missing = [n for k, n in (("s1", SEC1), ("s2", SEC2), ("s3", SEC3), ("s4", SEC4)) if k not in marks]
    if missing:
        raise ValueError(f"缺少区块：{missing}（请勿删除区块标题行）")
    s1, s2, s3, s4 = marks["s1"], marks["s2"], marks["s3"], marks["s4"]
    if not (s1 < s2 < s3 < s4):
        raise ValueError("四个区块顺序应为：一、课程基本信息 → 二、平时环节构成 → 三、对应矩阵 → 四、期末试卷结构")

    # 一、基本信息
    kv = {}
    for r in rows[s1 + 1:s2]:
        k = _cell_a(r)
        if k and k != "配置项":
            kv[k] = r[1] if len(r) > 1 else None

    cname = eng.clean(kv.get("课程名称")) or ""
    if strict and not cname:
        raise ValueError("课程名称不能为空")
    daily_ratio = eng.to_num(kv.get("平时占比"))
    final_ratio = eng.to_num(kv.get("期末占比"))
    if strict and (daily_ratio is None or final_ratio is None):
        raise ValueError("请填写平时占比和期末占比")
    daily_ratio = daily_ratio if daily_ratio is not None else 0.4
    final_ratio = final_ratio if final_ratio is not None else 0.6
    if strict and abs(daily_ratio + final_ratio - 1) > 1e-6:
        raise ValueError(f"平时占比({daily_ratio:g}) + 期末占比({final_ratio:g}) 必须等于 1")

    # 二、平时环节
    daily_links = {}
    for r in rows[s2 + 1:s3]:
        k = _cell_a(r)
        if not k or k == "环节名称":
            continue
        v = eng.to_num(r[1] if len(r) > 1 else None)
        if strict and (v is None or v < 0):
            raise ValueError(f"平时环节「{k}」的比例无效")
        daily_links[k] = v if (v is not None and v >= 0) else 0.0
    if strict and not daily_links:
        raise ValueError("请至少填写一个平时环节")
    if strict and abs(sum(daily_links.values()) - 1) > 1e-6:
        raise ValueError(f"平时环节比例之和须为 1，当前为 {sum(daily_links.values()):.2f}")

    # 三、对应矩阵
    block3 = [r for r in rows[s3 + 1:s4] if any(eng.clean(c) for c in r)]
    if not block3 or _cell_a(block3[0]) != "课程目标":
        raise ValueError("对应矩阵区块缺少表头行（第一列应为“课程目标”）")
    h3 = [eng.clean(c) or "" for c in block3[0]]
    link_cols = {}
    for l in list(daily_links) + ["期末考试"]:
        idx = eng.match_column(h3, l)
        if idx is None or idx < 2:
            if strict:
                raise ValueError(f"对应矩阵缺少环节列「{l}」（须与平时环节名称一致）")
        else:
            link_cols[l] = idx
    desc_col = eng.match_column(h3, "目标说明")
    matrix, descs = {}, {}
    for r in block3[1:]:
        tg = _cell_a(r)
        if not tg:
            continue
        matrix[tg] = {
            l: (
                eng.to_num(r[link_cols[l]])
                if (l in link_cols and link_cols[l] < len(r) and eng.to_num(r[link_cols[l]]) is not None)
                else 0.0
            )
            for l in list(daily_links) + ["期末考试"]
        }
        if desc_col is not None and desc_col < len(r):
            descs[tg] = eng.clean(r[desc_col]) or ""
    if strict and not matrix:
        raise ValueError("请至少填写一个课程目标")

    # 四、试卷结构
    block4 = [r for r in rows[s4 + 1:] if any(eng.clean(c) for c in r)]
    if not block4 or _cell_a(block4[0]) != "大题名称":
        raise ValueError("期末试卷结构区块缺少表头行（第一列应为“大题名称”）")
    order, groups, seq = [], {}, 1
    default_tg = next(iter(matrix.keys()), "课程目标1")
    for r in block4[1:]:
        grp = _cell_a(r)
        full_s = eng.to_num(r[2]) if len(r) > 2 else None
        tg = eng.clean(r[3]) if len(r) > 3 else None
        if not grp and full_s is None and not tg:
            continue
        if strict and (not grp or full_s is None or not tg):
            raise ValueError(f"期末试卷第 {seq} 题信息不完整（需填大题名称、小题满分、所属课程目标）")
        if strict and tg not in matrix:
            raise ValueError(f"期末试卷第 {seq} 题的目标「{tg}」不在对应矩阵中")
        grp = grp or "未命名大题"
        full_s = full_s if (full_s is not None and full_s > 0) else 5.0
        tg = tg if (tg and tg in matrix) else default_tg
        if grp not in groups:
            order.append(grp)
            groups[grp] = []
        groups[grp].append({"题号": seq, "满分": full_s, "目标": tg})
        seq += 1
    paper = [{"大题": g, "小题": groups[g]} for g in order]

    method = {"平时占比": daily_ratio, "期末占比": final_ratio, "平时环节": daily_links}
    if strict:
        eng.validate_structure(method, matrix, paper)
        eng.step2_output_weights(eng.step1_link_weights(method), matrix)

    th = eng.to_num(kv.get("合格阈值"))
    return {
        "meta": {
            "课程名称": cname or "未命名课程",
            "课程代码": eng.clean(kv.get("课程代码")) or "",
            "学期": eng.clean(kv.get("开课学期")) or "2024-2025-1",
            "班级": eng.clean(kv.get("默认班级")) or "",
            "课程类别": eng.clean(kv.get("课程类别")) or "专业必修课",
            "学分": eng.to_num(kv.get("学分")) if eng.to_num(kv.get("学分")) is not None else 3.0,
            "授课学时": eng.to_num(kv.get("授课学时")) if eng.to_num(kv.get("授课学时")) is not None else 48,
        },
        "threshold": th if (th is not None and 0 < th <= 1) else 0.65,
        "method": method,
        "matrix": matrix,
        "paper": paper,
        "target_descriptions": descs,
    }


# ============================================================
# 兼容旧版：单课程竖表（3 个 Sheet）
# ============================================================

def _parse_legacy_vertical(wb) -> dict:
    ws1, ws2, ws3 = (wb[n] for n in wb.sheetnames[:3])
    kv, daily_links, in_links = {}, {}, False
    for r in ws1.iter_rows(values_only=True):
        k = eng.clean(r[0]) if r else None
        if not k or k == "配置项":
            continue
        if "平时环节" in k:
            in_links = True
            continue
        if in_links:
            daily_links[k] = eng.to_num(r[1]) or 0.0
        else:
            kv[k] = r[1] if len(r) > 1 else None

    rows2 = [list(r) for r in ws2.iter_rows(values_only=True)]
    h2 = [eng.clean(c) or "" for c in rows2[0]]
    link_cols = {l: eng.match_column(h2, l) for l in list(daily_links) + ["期末考试"]}
    if None in link_cols.values():
        raise ValueError("Sheet2 缺少与平时环节一致的列")
    desc_col = eng.match_column(h2, "目标说明")
    matrix, descs = {}, {}
    for r in rows2[1:]:
        tg = eng.clean(r[0]) if r else None
        if tg:
            matrix[tg] = {l: eng.to_num(r[ci]) or 0.0 for l, ci in link_cols.items()}
            if desc_col is not None:
                descs[tg] = eng.clean(r[desc_col]) or ""

    order, groups, seq = [], {}, 1
    for r in list(ws3.iter_rows(values_only=True))[1:]:
        grp, full_s, tg = eng.clean(r[0]), eng.to_num(r[2]), eng.clean(r[3])
        if not grp:
            continue
        groups.setdefault(grp, [])
        if grp not in order:
            order.append(grp)
        groups[grp].append({"题号": seq, "满分": full_s, "目标": tg})
        seq += 1
    paper = [{"大题": g, "小题": groups[g]} for g in order]

    method = {"平时占比": eng.to_num(kv.get("平时占比")), "期末占比": eng.to_num(kv.get("期末占比")),
              "平时环节": daily_links}
    if abs(sum(daily_links.values()) - 1) > 1e-6 or abs(method["平时占比"] + method["期末占比"] - 1) > 1e-6:
        raise ValueError("占比之和不为 1")
    eng.validate_structure(method, matrix, paper)
    eng.step2_output_weights(eng.step1_link_weights(method), matrix)
    th = eng.to_num(kv.get("合格阈值"))
    return {
        "meta": {
            "课程名称": eng.clean(kv.get("课程名称")) or "导入课程",
            "课程代码": eng.clean(kv.get("课程代码")) or "",
            "学期": eng.clean(kv.get("开课学期")) or "2024-2025-1",
            "班级": eng.clean(kv.get("默认班级")) or "",
            "课程类别": eng.clean(kv.get("课程类别")) or "专业必修课",
            "学分": eng.to_num(kv.get("学分")) or 3.0,
            "授课学时": eng.to_num(kv.get("授课学时")) or 48,
        },
        "threshold": th if (th is not None and 0 < th <= 1) else 0.65,
        "method": method, "matrix": matrix, "paper": paper, "target_descriptions": descs,
    }


# ============================================================
# 对外接口
# ============================================================

def parse_config_workbook_for_preview(path: Path) -> list[dict]:
    """非阻断式预览解析：即使某门课比例和 ≠ 1 或试卷总分 ≠ 100，也完整提取出 course 结构与 errors 列表，
    供管理员在网页上实时预览、直接修改配平后再一键批量入库发布！
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    results = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        if not _is_course_sheet(ws.title, rows):
            continue
        try:
            course = _parse_course_sheet(rows, strict=False)
            errs = _collect_course_errors(course)
            results.append(
                {
                    "sheet": ws.title,
                    "course": course,
                    "errors": errs,
                    "error": "；".join(errs) if errs else None,
                }
            )
        except ValueError as e:
            results.append(
                {"sheet": ws.title, "course": None, "errors": [str(e)], "error": str(e)}
            )

    if results:
        return results

    first = eng.clean(wb.worksheets[0].cell(1, 1).value) if wb.worksheets else None
    if first == "配置项" and len(wb.sheetnames) >= 3:
        try:
            c = _parse_legacy_vertical(wb)
            errs = _collect_course_errors(c)
            return [
                {
                    "sheet": wb.sheetnames[0],
                    "course": c,
                    "errors": errs,
                    "error": "；".join(errs) if errs else None,
                }
            ]
        except Exception as e:
            return [
                {
                    "sheet": wb.sheetnames[0],
                    "course": None,
                    "errors": [f"旧版格式解析失败：{e}"],
                    "error": f"旧版格式解析失败：{e}",
                }
            ]

    raise ValueError("未识别到课程配置：请使用系统下载的《课程规则配置模板.xlsx》（每个工作表需包含“一、课程基本信息”等四个区块）")


def parse_config_workbook_detailed(path: Path) -> list[dict]:
    """逐门解析，返回 [{"sheet": 工作表名, "course": dict|None, "error": str|None}]。"""
    items = parse_config_workbook_for_preview(path)
    out = []
    for it in items:
        if it["error"]:
            out.append({"sheet": it["sheet"], "course": None, "error": it["error"]})
        else:
            out.append({"sheet": it["sheet"], "course": it["course"], "error": None})
    return out


def parse_multi_course_config_excel(path: Path) -> list[dict]:
    """严格模式：任意一门出错即抛异常。"""
    items = parse_config_workbook_detailed(path)
    for it in items:
        if it["error"]:
            raise ValueError(f"工作表「{it['sheet']}」：{it['error']}")
    return [it["course"] for it in items]


def parse_course_config_excel(path: Path) -> dict:
    """兼容单课程调用：返回第一门课程。"""
    return parse_multi_course_config_excel(path)[0]


# ============================================================
# 专门的 4 列《期末试卷结构模板.xlsx》生成与解析
# ============================================================

def build_paper_structure_template(
    course_name: str,
    targets: list[str],
    existing_paper: list | None = None,
) -> io.BytesIO:
    """生成极度顺手的 4 列《期末试卷结构模板.xlsx》：
    - 每个大题之间预留 2 行空行，方便直接增删小题；
    - 同一大题下只需在首行写大题名称，下方小题第 1 列可留空（系统自动向下继承）；
    - 第 4 列「所属课程目标」内置 Excel 下拉选择框；
    - 底部自带「试卷总分合计 =SUM(...)」实时核对总分是否等于 100。
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "期末试卷结构"

    ws.merge_cells("A1:D1")
    t = ws.cell(1, 1, f"《{course_name}》期末试卷结构配置模板")
    t.font = Font(size=14, bold=True)
    t.alignment = CENTER
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:D2")
    tip = ws.cell(
        2,
        1,
        f"填写说明：① 每大题间已空出预留行，可直接增删小题；② 同一大题名称只需在首行填一次（下方可留空）；"
        f"③ 所属课程目标可直接下拉选择【{' / '.join(targets)}】；④ 底部总分合计凑满 100 分即可上传。",
    )
    tip.fill = TIP_FILL
    tip.alignment = LEFT
    ws.row_dimensions[2].height = 38

    _header(ws, 3, ["大题名称", "题号", "小题满分", "所属课程目标"])
    ws.row_dimensions[3].height = 24

    # 组织大题分组
    if existing_paper and any(g.get("小题") for g in existing_paper):
        groups = existing_paper
    else:
        t1 = targets[0] if targets else "课程目标1"
        t2 = targets[1] if len(targets) > 1 else t1
        groups = [
            {"大题": "一、选择题", "小题": [
                {"题号": 1, "满分": 5, "目标": t1},
                {"题号": 2, "满分": 5, "目标": t1},
                {"题号": 3, "满分": 5, "目标": t2},
                {"题号": 4, "满分": 5, "目标": t2},
            ]},
            {"大题": "二、填空题", "小题": [
                {"题号": 5, "满分": 10, "目标": t1},
                {"题号": 6, "满分": 10, "目标": t2},
            ]},
            {"大题": "三、计算与解答题", "小题": [
                {"题号": 7, "满分": 20, "目标": t1},
                {"题号": 8, "满分": 20, "目标": t1},
                {"题号": 9, "满分": 20, "目标": t2},
            ]},
        ]

    cur_row = 4
    first_data_row = cur_row
    for g_idx, grp in enumerate(groups):
        qs = grp.get("小题") or []
        for i, q in enumerate(qs):
            # 同一大题下，大题名称只在第一行显示，后续行留空更清爽
            grp_label = grp["大题"] if i == 0 else None
            _row(ws, cur_row, [grp_label, q.get("题号"), q.get("满分"), q.get("目标")])
            if i == 0:
                ws.cell(cur_row, 1).font = Font(bold=True)
            ws.row_dimensions[cur_row].height = 22
            cur_row += 1
        # 每个大题之间预留 2 行空白带边框编辑行，方便老师直接增题
        for _ in range(2):
            _row(ws, cur_row, [None, None, None, None])
            ws.row_dimensions[cur_row].height = 20
            cur_row += 1

    last_data_row = cur_row - 1

    # 底部实时总分合计行
    sum_row = cur_row
    ws.merge_cells(start_row=sum_row, start_column=1, end_row=sum_row, end_column=2)
    c_lbl = ws.cell(sum_row, 1, "试卷总分合计（须为 100）")
    c_lbl.font = Font(bold=True)
    c_lbl.alignment = CENTER
    c_lbl.fill = HEAD_FILL
    ws.cell(sum_row, 1).border = BORDER
    ws.cell(sum_row, 2).border = BORDER

    c_sum = ws.cell(sum_row, 3, f"=SUM(C{first_data_row}:C{last_data_row})")
    c_sum.font = Font(bold=True, color="1D4ED8")
    c_sum.alignment = CENTER
    c_sum.fill = HEAD_FILL
    c_sum.border = BORDER

    c_hint = ws.cell(sum_row, 4, "自动校验")
    c_hint.alignment = CENTER
    c_hint.fill = HEAD_FILL
    c_hint.border = BORDER
    ws.row_dimensions[sum_row].height = 24

    # 给第 4 列「所属课程目标」加上 Excel 原生下拉菜单
    if targets:
        dv = DataValidation(
            type="list",
            formula1='"' + ",".join(targets) + '"',
            allow_blank=True,
        )
        ws.add_data_validation(dv)
        dv.add(f"D{first_data_row}:D{last_data_row + 20}")

    for col_i, w in enumerate([22, 10, 14, 20], 1):
        ws.column_dimensions[get_column_letter(col_i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def parse_paper_structure_for_preview(path: Path, method: dict, matrix: dict) -> tuple[list[dict], list[str]]:
    """非阻断式解析 4 列《期末试卷结构模板.xlsx》，返回 (paper, errors)，供弹窗实时预览与手工调整。"""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]

    header_idx = None
    for i, r in enumerate(rows):
        cells = [eng.clean(c) or "" for c in r]
        if any("大题" in c for c in cells) and any("满分" in c for c in cells):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("未找到表头行（需包含「大题名称」「小题满分」「所属课程目标」）")

    h = [eng.clean(c) or "" for c in rows[header_idx]]
    c_grp = eng.match_column(h, "大题名称", ("大题", "题型"))
    c_score = eng.match_column(h, "小题满分", ("满分", "分值"))
    c_target = eng.match_column(h, "所属课程目标", ("课程目标", "目标"))
    if None in (c_grp, c_score, c_target):
        raise ValueError("表头缺少必需列：大题名称、小题满分、所属课程目标")

    order, groups, seq = [], {}, 1
    current_grp = None
    default_tg = next(iter(matrix.keys()), "课程目标1")
    for r in rows[header_idx + 1:]:
        grp_cell = eng.clean(r[c_grp]) if c_grp < len(r) else None
        if grp_cell and any(k in grp_cell for k in ("合计", "总分", "小计", "统计")):
            continue
        full_s = eng.to_num(r[c_score]) if c_score < len(r) else None
        tg = eng.clean(r[c_target]) if c_target < len(r) else None
        if not grp_cell and full_s is None and not tg:
            continue
        if grp_cell:
            current_grp = grp_cell
        grp = current_grp or "未命名大题"
        if full_s is None:
            full_s = 5.0
        if not tg or tg not in matrix:
            tg = default_tg
        if grp not in groups:
            order.append(grp)
            groups[grp] = []
        groups[grp].append({"题号": seq, "满分": full_s, "目标": tg})
        seq += 1

    paper = [{"大题": g, "小题": groups[g]} for g in order]
    errs = []
    try:
        eng.validate_structure(method, matrix, paper)
    except ValueError as e:
        errs.append(str(e))
    return paper, errs


def parse_paper_structure_excel(path: Path, method: dict, matrix: dict) -> list[dict]:
    """解析 4 列《期末试卷结构模板.xlsx》：
    - 自动跳过大题之间的空行及底部「合计/总分」汇总行；
    - 同一大题下若第 1 列「大题名称」留空，自动向下继承上一个大题名称；
    - 自动连续重排题号 1..N 并校验总分 100 与课程目标合法性。
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]

    header_idx = None
    for i, r in enumerate(rows):
        cells = [eng.clean(c) or "" for c in r]
        if any("大题" in c for c in cells) and any("满分" in c for c in cells):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("未找到表头行（需包含「大题名称」「小题满分」「所属课程目标」）")

    h = [eng.clean(c) or "" for c in rows[header_idx]]
    c_grp = eng.match_column(h, "大题名称", ("大题", "题型"))
    c_score = eng.match_column(h, "小题满分", ("满分", "分值"))
    c_target = eng.match_column(h, "所属课程目标", ("课程目标", "目标"))
    if None in (c_grp, c_score, c_target):
        raise ValueError("表头缺少必需列：大题名称、小题满分、所属课程目标")

    order, groups, seq = [], {}, 1
    current_grp = None
    for r in rows[header_idx + 1:]:
        grp_cell = eng.clean(r[c_grp]) if c_grp < len(r) else None
        # 自动跳过底部的“合计 / 总分”行
        if grp_cell and any(k in grp_cell for k in ("合计", "总分", "小计", "统计")):
            continue

        full_s = eng.to_num(r[c_score]) if c_score < len(r) else None
        tg = eng.clean(r[c_target]) if c_target < len(r) else None

        # 纯空行（大题之间的预留空行）直接跳过
        if not grp_cell and full_s is None and not tg:
            continue

        if grp_cell:
            current_grp = grp_cell
        grp = current_grp

        if not grp or full_s is None or not tg:
            raise ValueError(f"第 {seq} 题信息不完整，请填写大题名称、小题满分和所属课程目标")
        if tg not in matrix:
            raise ValueError(f"第 {seq} 题的课程目标「{tg}」不在当前课程目标中（可选：{list(matrix.keys())}）")
        if grp not in groups:
            order.append(grp)
            groups[grp] = []
        groups[grp].append({"题号": seq, "满分": full_s, "目标": tg})
        seq += 1

    paper = [{"大题": g, "小题": groups[g]} for g in order]
    eng.validate_structure(method, matrix, paper)
    return paper

