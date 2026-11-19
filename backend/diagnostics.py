"""OBE 教学诊断下钻分析工具模块（为 OBE 诊断 Agent 预留 Tool-Calling 底层工具）

包含 4 个直连真实数据的诊断工具：
  1. analyze_weak_links          — 环节得分率下钻，定位拖累每个目标的薄弱考核环节
  2. analyze_hard_questions      — 期末小题下钻，找出全班得分率最低的 Top N 难题
  3. analyze_student_distribution — 全班学情分布画像（个人达标率、分段分布、平时高期末低反差生）
  4. compare_with_history        — 调取同课程历史/平行班报告做横向对比

同时提供 generate_diagnostic_report()，汇总 4 维真实指标并生成结构化中文诊断与持续改进草稿；
后续接入大模型（DeepSeek / 通义千问 / OpenAI）时，可直接将这 4 个函数注册为 Agent Tools。
"""

import db
import export_report


def analyze_weak_links(report: dict, output_weights: dict) -> dict:
    """工具 1：计算各目标下每个考核环节的得分率，找出最薄弱环节。"""
    result = {}
    for target, info in report.items():
        link_rates = []
        for link, actual in info["平时明细"].items():
            full_s = output_weights[target][link] * 100
            if full_s > 0:
                link_rates.append(
                    {
                        "环节": link,
                        "实际得分": round(actual, 2),
                        "理论满分": round(full_s, 2),
                        "得分率": round(actual / full_s, 4),
                    }
                )
        final_full = output_weights[target].get("期末考试", 0) * 100
        if final_full > 0:
            link_rates.append(
                {
                    "环节": "期末考试",
                    "实际得分": round(info["期末"], 2),
                    "理论满分": round(final_full, 2),
                    "得分率": round(info["期末"] / final_full, 4),
                }
            )
        link_rates.sort(key=lambda x: x["得分率"])
        result[target] = {
            "达成度": round(info["达成度"], 4),
            "是否达标": info["是否达标"],
            "最薄弱环节": link_rates[0] if link_rates else None,
            "环节得分率明细": link_rates,
        }
    return result


def analyze_hard_questions(students: list[dict], questions: list[dict], top_n: int = 5) -> list[dict]:
    """工具 2：下钻期末各小题，统计全班均分与得分率，按得分率从低到高排序。"""
    n = len(students)
    if n == 0 or not questions:
        return []
    stats = []
    for q in questions:
        qn = q["题号"]
        q_full = float(q["满分"])
        avg_got = (
            sum(float(s["期末"].get(qn, s["期末"].get(str(qn), 0))) for s in students) / n
        )
        rate = avg_got / q_full if q_full > 0 else 0.0
        stats.append(
            {
                "题号": qn,
                "满分": q_full,
                "所属目标": q["目标"],
                "全班均分": round(avg_got, 2),
                "得分率": round(rate, 4),
            }
        )
    stats.sort(key=lambda x: x["得分率"])
    return stats[:top_n]


def analyze_student_distribution(
    students: list[dict],
    output_weights: dict,
    full_scores: dict,
    questions: list[dict],
    paper_full: dict,
    threshold: float = 0.65,
) -> dict:
    """工具 3：统计全班个人达成度分布与“平时高分但期末低分”反差学生数量。"""
    targets = list(output_weights.keys())
    all_links = list(output_weights[targets[0]].keys())
    daily_links = [l for l in all_links if l != "期末考试"]
    n = len(students)
    if n == 0:
        return {}

    per_target = {}
    contrast_students = []  # 平时均分 >= 80 但期末卷面总分 < 60 的学生

    for s in students:
        d_avg = (
            sum(float(s["平时"][l]) for l in daily_links) / len(daily_links)
            if daily_links
            else 0.0
        )
        f_total = sum(
            float(s["期末"].get(q["题号"], s["期末"].get(str(q["题号"]), 0)))
            for q in questions
        )
        if d_avg >= 80 and f_total < 60:
            contrast_students.append(
                {
                    "学号": s["学号"],
                    "姓名": s["姓名"],
                    "平时均分": round(d_avg, 1),
                    "期末卷面分": round(f_total, 1),
                }
            )

    for t in targets:
        achs = []
        for s in students:
            got = sum(
                export_report._student_link_score(
                    s, t, l, output_weights, questions, paper_full
                )
                for l in all_links
            )
            achs.append(got / full_scores[t] if full_scores[t] > 0 else 0.0)
        passed_cnt = sum(1 for a in achs if a >= threshold)
        buckets = {
            "优秀(>=85%)": sum(1 for a in achs if a >= 0.85),
            "良好(75%~85%)": sum(1 for a in achs if 0.75 <= a < 0.85),
            "达标(阈值~75%)": sum(1 for a in achs if threshold <= a < 0.75),
            "未达标(<阈值)": sum(1 for a in achs if a < threshold),
        }
        per_target[t] = {
            "达标人数": passed_cnt,
            "未达标人数": n - passed_cnt,
            "个人达标率": round(passed_cnt / n, 4),
            "最高达成度": round(max(achs), 4),
            "最低达成度": round(min(achs), 4),
            "分段分布": buckets,
        }

    return {
        "样本人数": n,
        "各目标分布": per_target,
        "平时高期末低反差人数": len(contrast_students),
        "反差学生示例": contrast_students[:5],
    }


def compare_with_history(course_id: int, current_report: dict) -> list[dict]:
    """工具 4：调取同课程历史/平行班报告做横向对比。"""
    history = db.list_class_reports(course_id=course_id)
    comparisons = []
    for h in history[:5]:
        h_rep = h["report"].get("report", h["report"])
        row = {
            "report_id": h["id"],
            "班级": h["class_name"],
            "学期": h["semester"],
            "人数": h["student_count"],
            "各目标达成度": {
                t: round(v["达成度"], 4)
                for t, v in h_rep.items()
                if isinstance(v, dict) and "达成度" in v
            },
        }
        comparisons.append(row)
    return comparisons


def generate_diagnostic_report(
    course_id: int,
    meta: dict,
    students: list[dict],
    report: dict,
    output_weights: dict,
    full_scores: dict,
    questions: list[dict],
    paper_full: dict,
    threshold: float = 0.65,
) -> dict:
    """汇总 4 维下钻诊断工具输出，并自动生成 OBE 持续改进建议草稿。"""
    weak_links = analyze_weak_links(report, output_weights)
    hard_questions = analyze_hard_questions(students, questions, top_n=5)
    distribution = analyze_student_distribution(
        students, output_weights, full_scores, questions, paper_full, threshold
    )
    history_cmp = compare_with_history(course_id, report)

    # 拼装专业、有数据支撑的中文诊断与持续改进草稿
    lines = [
        f"【{meta.get('课程名称', '本课程')} · {meta.get('班级', '')} 课程目标达成情况诊断】",
        f"本次评价有效样本 {len(students)} 人，合格基准线为 {threshold * 100:.0f}%。",
    ]

    unpassed_targets = []
    for t, info in weak_links.items():
        status = "达标" if info["是否达标"] else "未达标（需重点改进）"
        wl = info["最薄弱环节"]
        wl_desc = (
            f"最薄弱环节为「{wl['环节']}」（得分率 {wl['得分率'] * 100:.1f}%）"
            if wl
            else ""
        )
        dist_t = distribution.get("各目标分布", {}).get(t, {})
        pass_rate_str = (
            f"，个人达标率 {dist_t.get('个人达标率', 0) * 100:.1f}%"
            f"（{dist_t.get('达标人数', 0)}/{len(students)} 人）"
            if dist_t
            else ""
        )
        lines.append(
            f"- {t}：达成度 {info['达成度'] * 100:.1f}%（{status}）{pass_rate_str}；{wl_desc}。"
        )
        if not info["是否达标"]:
            unpassed_targets.append(t)

    if hard_questions:
        top3 = hard_questions[:3]
        q_str = "、".join(
            f"第{q['题号']}题（{q['所属目标']}，均分 {q['全班均分']}/{q['满分']:g}，得分率 {q['得分率'] * 100:.1f}%）"
            for q in top3
        )
        lines.append(f"\n【期末试题薄弱点下钻】全班得分率最低的 3 道小题为：{q_str}。")

    contrast_cnt = distribution.get("平时高期末低反差人数", 0)
    if contrast_cnt > 0:
        lines.append(
            f"【学情预警】共有 {contrast_cnt} 名学生呈现“平时均分 ≥ 80 分但期末卷面 < 60 分”的反差现象，"
            "建议加强过程性作业/测验的独立性核查与考前综合训练。"
        )

    lines.append("\n【持续改进措施建议】")
    if unpassed_targets:
        lines.append(
            f"1. 针对未达标的 {'、'.join(unpassed_targets)}，下学期需结合上述低得分率题型（如第"
            + "、".join(str(q["题号"]) for q in hard_questions[:2])
            + "题）增加课堂例题拆解与阶段性小测验覆盖；"
        )
    else:
        lines.append("1. 本次各课程目标均已达标，建议继续巩固现有过程考核节奏，针对得分率相对较低的小题进一步优化习题梯度；")
    lines.append(
        "2. 对未达标学生群体建立期中预警与课后答疑跟踪机制，缩小平时成绩与期末闭卷考试之间的能力落差。"
    )

    return {
        "mode": "rule_agent_v1",
        "weak_links": weak_links,
        "hard_questions": hard_questions,
        "distribution": distribution,
        "history_comparison": history_cmp,
        "draft_text": "\n".join(lines),
    }
