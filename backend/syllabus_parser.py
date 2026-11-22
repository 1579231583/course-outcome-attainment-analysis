"""课程教学大纲 PDF 智能解析模块（纯 Python pypdf，零 C 扩展依赖）

从高校标准《课程教学大纲.pdf》中自动提取：
  1. 课程基本信息（课程名称、课程编码、学分、总学时、课程类别）
  2. 课程目标详细描述 + 毕业要求指标点支撑关系（如 指标点 1.1、指标点 12.2）
  3. 课程目标与考核环节对应关系矩阵（如 作业 / 考勤 / 测验 / 期末考试）
  4. 课程目标与知识单元映射（供 OBE 诊断 Agent 生成精准章节改进建议）

返回的 course 草稿结构可直接进入管理员端「在线预览与实时修改工作区」，
管理员确认占比并补充试卷结构后即可一键发布为全院公共课程模板！
"""

import re
from pathlib import Path

from pypdf import PdfReader

import calc_engine as eng


def _parse_pct_or_num(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    if s.endswith("%"):
        num = eng.to_num(s[:-1])
        return round(num / 100.0, 4) if num is not None else None
    num = eng.to_num(s)
    if num is None:
        return None
    return round(num / 100.0, 4) if num > 1.0 else round(num, 4)


def _extract_course_name(full_text: str, fallback_filename: str = "") -> str:
    m = re.search(r"《([^》\n]+)》", full_text)
    if m:
        return re.sub(r"\s+", "", m.group(1)).strip()
    if fallback_filename:
        m2 = re.search(r"《([^》]+)》", fallback_filename)
        if m2:
            return m2.group(1).strip()
        return Path(fallback_filename).stem
    return "导入课程"


def _extract_basic_meta(full_text: str, filename: str) -> dict:
    meta = {
        "课程名称": _extract_course_name(full_text, filename),
        "课程代码": "",
        "学期": "2025-2026-1",
        "班级": "",
        "课程类别": "公共基础课",
        "学分": 3.0,
        "授课学时": 48,
    }

    head = full_text[:1500]
    m_code = re.search(r"课程编[码号]\s*([A-Za-z0-9_-]+)", head)
    if m_code:
        meta["课程代码"] = m_code.group(1).strip()

    m_credit = re.search(r"学\s*分\s*(\d+(?:\.\d+)?)", head)
    if m_credit:
        meta["学分"] = float(m_credit.group(1))

    m_hours = re.search(r"总学时\s*(\d+)", head)
    if m_hours:
        meta["授课学时"] = int(m_hours.group(1))

    m_cat = re.search(r"课程类别[^\n]*?[■☑√●]\s*([^\s□☐○\n]+)", head)
    if m_cat:
        meta["课程类别"] = m_cat.group(1).strip()

    return meta


def _extract_target_descriptions(full_text: str) -> dict:
    descs = {}
    pattern = re.compile(
        r"课程目标\s*(\d+)\s*[：:]\s*(.+?)(?=\n\s*课程目标\s*\d+\s*[：:]|\n\s*课程目标对毕业要求|\n\s*[二三四五六]、|$)",
        re.S,
    )
    for m in pattern.finditer(full_text):
        key = f"课程目标{m.group(1)}"
        text = re.sub(r"\s+", "", m.group(2)).strip()
        if text and key not in descs:
            descs[key] = text
    return descs


def _extract_graduation_indicators(full_text: str) -> dict:
    """从「课程目标对毕业要求的支撑关系」区域提取指标点与课程目标映射。"""
    indicators: dict[str, list[str]] = {}
    m_sec = re.search(
        r"课程目标对毕业要求的支撑关系(.+?)(?=三、课程目标与教学内容|$)",
        full_text,
        re.S,
    )
    if not m_sec:
        return {}
    block = m_sec.group(1)
    # 按指标点编号（如 1.1、12.2）切块，查找紧随其后的课程目标编号
    ind_matches = list(re.finditer(r"(?<!\d)(\d{1,2}\.\d{1,2})\s+", block))
    for i, m in enumerate(ind_matches):
        ind_code = m.group(1)
        end_pos = ind_matches[i + 1].start() if i + 1 < len(ind_matches) else len(block)
        chunk = block[m.start():end_pos]
        for num in re.findall(r"课程目标\s*(\d+)", chunk):
            k = f"课程目标{num}"
            lbl = f"指标点 {ind_code}"
            indicators.setdefault(k, [])
            if lbl not in indicators[k]:
                indicators[k].append(lbl)
    return {k: "、".join(v) for k, v in indicators.items()}


def _extract_assessment_matrix(full_text: str) -> tuple[dict, list[str]]:
    """提取第五节「课程目标与考核环节的对应关系」矩阵。"""
    m_sec = re.search(
        r"课程目标与考核环节的对应关系(.+?)(?=2[、.]\s*各考核环节|六、教学参考|$)",
        full_text,
        re.S,
    )
    if not m_sec:
        return {}, []

    lines = [re.sub(r"\s+", " ", ln).strip() for ln in m_sec.group(1).splitlines() if ln.strip()]
    links = []
    header_idx = None
    for idx, ln in enumerate(lines):
        if "期末考试" in ln and ("作业" in ln or "考勤" in ln or "测验" in ln or "实验" in ln):
            tokens = [t for t in ln.split(" ") if t and t not in ("课程目标", "考核环节", "合计", "总计")]
            if tokens:
                links = tokens
                header_idx = idx
                break

    if not links or header_idx is None:
        return {}, []

    matrix = {}
    for ln in lines[header_idx + 1:]:
        m_tg = re.match(r"课程目标\s*(\d+)\s+(.+)$", ln)
        if not m_tg:
            continue
        tg_key = f"课程目标{m_tg.group(1)}"
        val_tokens = m_tg.group(2).strip().split(" ")
        nums = [_parse_pct_or_num(tok) for tok in val_tokens]
        nums = [x for x in nums if x is not None]
        if len(nums) >= len(links):
            matrix[tg_key] = {links[i]: nums[i] for i in range(len(links))}

    return matrix, links


def _extract_knowledge_units(full_text: str) -> dict:
    """从「三、课程目标与教学内容的对应关系」提取各课程目标对应的主要知识点关键词。"""
    m_sec = re.search(
        r"三、课程目标与教学内容的对应关系(.+?)(?=四、教学方法|$)",
        full_text,
        re.S,
    )
    if not m_sec:
        return {}
    block = m_sec.group(1)
    # 按「课程目标 X」切分大段
    parts = re.split(r"课程目标\s*(\d+)", block)
    result: dict[str, list[str]] = {}
    for i in range(1, len(parts) - 1, 2):
        tg_key = f"课程目标{parts[i]}"
        body = parts[i + 1]
        # 提取形如 "1 向量代数"、"2 平面与直线" 的编号知识点
        topics = re.findall(r"(?:^|\n)\s*\d+\s*([\u4e00-\u9fa5A-Za-z、，]{2,18})", body)
        clean_topics = []
        for tp in topics:
            t = re.sub(r"\s+", "", tp).strip()
            if len(t) >= 2 and t not in clean_topics and not t.startswith("课程"):
                clean_topics.append(t)
        if clean_topics:
            result[tg_key] = clean_topics[:12]
    return result


def parse_syllabus_pdf(path: Path, filename: str = "") -> dict:
    """解析高校标准《课程教学大纲.pdf》，返回完整课程草稿字典与摘要。"""
    reader = PdfReader(str(path))
    full_text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not full_text.strip():
        raise ValueError("该 PDF 未检测到可提取文本（可能是纯扫描图片版 PDF）")

    meta = _extract_basic_meta(full_text, filename or path.name)
    descs = _extract_target_descriptions(full_text)
    indicators = _extract_graduation_indicators(full_text)
    matrix, links = _extract_assessment_matrix(full_text)
    knowledge_units = _extract_knowledge_units(full_text)

    if not matrix:
        tg_keys = list(descs.keys()) or ["课程目标1", "课程目标2"]
        links = ["作业", "课堂表现", "测验", "期末考试"]
        matrix = {t: {l: 0.25 for l in links} for t in tg_keys}

    has_final = "期末考试" in links
    daily_link_names = [l for l in links if l != "期末考试"] or ["作业", "考勤"]

    n_d = len(daily_link_names)
    base_r = round(1.0 / n_d, 2)
    daily_ratios = {l: base_r for l in daily_link_names}
    diff = round(1.0 - sum(daily_ratios.values()), 2)
    daily_ratios[daily_link_names[0]] = round(daily_ratios[daily_link_names[0]] + diff, 2)

    method = {
        "平时占比": 0.4 if has_final else 1.0,
        "期末占比": 0.6 if has_final else 0.0,
        "平时环节": daily_ratios,
    }

    # 不再强塞假试卷！大纲只负责课程底座，期末试卷结构留空（状态：仅大纲），后续由管理员（统考课）或教师补充
    paper = []

    merged_descs = {}
    for t in matrix:
        ind = indicators.get(t, "")
        desc = descs.get(t, "")
        merged_descs[t] = f"[{ind}] {desc}".strip() if ind else desc

    course = {
        "meta": meta,
        "threshold": 0.65,
        "method": method,
        "matrix": matrix,
        "paper": paper,
        "target_descriptions": merged_descs,
        "graduation_indicators": indicators,
        "knowledge_units": knowledge_units,
    }

    return {
        "course": course,
        "extracted_summary": {
            "course_name": meta["课程名称"],
            "course_code": meta["课程代码"],
            "credits": meta["学分"],
            "hours": meta["授课学时"],
            "category": meta["课程类别"],
            "targets_count": len(matrix),
            "indicators": indicators,
            "links": links,
            "knowledge_units": knowledge_units,
        },
    }
