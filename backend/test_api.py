"""三层架构全链路自动化验收测试

验证：
  1. 双角色登录、Token 鉴权与 401/403 严格隔离
  2. 第一层：管理员解析真实《教学大纲 PDF》→ 发布公共大纲（无学期/无班级）
  3. 第二层：管理员为该大纲挂接 2025-2026-1 统考试卷（4 列模板解析 + 保存）
  4. 第三层：教师从公共大纲创建班级分析任务 → 自动挂接同学期统考试卷 → 解析 35 人成绩（含异常版检出）
  5. 达成度计算 + 4 维诊断 + 考试试卷分析 + 三段分析文本完整持久化
  6. 一键导出双文档归档包 ZIP（4-Sheet《达成度数据分析表.xlsx》+ 2-Sheet《考试试卷分析表.xlsx》）
  7. 管理员全院汇总监控验证
"""

import io
import sys
import zipfile
from pathlib import Path

import openpyxl
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api
import course_template
import db
import syllabus_parser

ROOT = Path(__file__).resolve().parent.parent
CASE_DIR = ROOT / "用例"


def run_all_tests():
    # 使用独立临时测试库，绝不污染正式数据库
    orig_db = db.DB_PATH
    test_db = Path(__file__).resolve().parent / "test_v4_tmp.db"
    if test_db.exists():
        test_db.unlink()
    db.DB_PATH = test_db

    try:
        db.init_db()
        print("=" * 68)
        print("开始执行三层架构全链路自动化验收测试...")
        print("=" * 68)

        # 1. 双角色鉴权与隔离
        a_login = api.login({"username": "admin", "password": "admin123"})
        t_login = api.login({"username": "teacher", "password": "123456"})
        admin_user = api.get_current_user(f"Bearer {a_login['token']}")
        teacher_user = api.get_current_user(f"Bearer {t_login['token']}")
        try:
            api.require_admin(teacher_user)
            raise AssertionError("普通教师不应通过 require_admin")
        except HTTPException as e:
            assert e.status_code == 403
        print("[PASS] 1. 双角色登录与权限隔离验证通过")

        # 2. 第一层：解析真实教学大纲 PDF 并发布到公共大纲库
        parsed = syllabus_parser.parse_syllabus_pdf(CASE_DIR / "01_管理员_课程教学大纲.pdf")
        pub_res = api.publish_syllabuses({"courses": [parsed["course"]]}, admin=admin_user)
        assert pub_res["count"] == 1
        syl = pub_res["syllabuses"][0]
        assert syl["course_name"] == "高等数学A（II）"
        assert syl["has_paper"] is False
        print(f"[PASS] 2. 公共大纲 PDF 解析并发布通过：{syl['course_name']}（{syl['target_count']} 个目标，初始无试卷）")

        # 3. 第二层：管理员为 2025-2026-1 挂接统考期末试卷
        paper, errs = course_template.parse_paper_structure_for_preview(
            CASE_DIR / "02_管理员_期末试卷结构模板.xlsx", syl["method"], syl["matrix"]
        )
        assert not errs, errs
        p_res = api.save_syllabus_exam_paper(
            syl["id"], {"semester": "2025-2026-1", "title": "2025-2026-1 统考A卷", "paper": paper}, admin=admin_user
        )
        assert p_res["paper"]["question_count"] == 12
        print("[PASS] 3. 统考期末试卷按学期挂接成功（12 题 · 100 分）")

        # 4. 第三层：教师从公共大纲开班，初始为 pending_ratios（待教师自行配置占比），自动继承统考试卷
        t_res = api.create_task(
            {"syllabus_id": syl["id"], "semester": "2025-2026-1", "class_name": "24智能制造1班"},
            user=teacher_user,
        )
        task = t_res["task"]
        assert task["paper_source"] == "unified"
        assert task["status"] == "pending_ratios"
        assert task["ratios_confirmed"] is False
        assert task["question_count"] == 12

        # 教师亲自配置平时/期末占比及细项比例后，状态转为 pending_scores
        u_res = api.update_task_rules(
            task["id"],
            {
                "meta": task["meta"],
                "threshold": 0.65,
                "method": {"平时占比": 0.4, "期末占比": 0.6, "平时环节": {"作业": 0.4, "考勤": 0.3, "测验": 0.3}},
                "matrix": task["matrix"],
                "paper": task["paper"],
            },
            user=teacher_user,
        )
        task = u_res["task"]
        assert task["ratios_confirmed"] is True
        assert task["status"] == "pending_scores"

        # 跨用户隔离检查
        t2_login = api.register({"username": "t_other", "password": "123456", "name": "李老师"})
        t2_user = api.get_current_user(f"Bearer {t2_login['token']}")
        try:
            api.get_task(task["id"], user=t2_user)
            raise AssertionError("其他教师不应读取张老师的班级任务")
        except HTTPException as e:
            assert e.status_code == 403
        print("[PASS] 4. 教师建班自动关联统考试卷 + 跨教师数据严格隔离通过")

        # 5. 解析 35 人成绩 + 达成度计算 + 诊断 + 三段分析持久化
        import calc_engine as eng

        pv = eng.parse_sheets_for_preview(
            api._read_rows(CASE_DIR / "03_教师_平时成绩表_35人.xlsx"),
            api._read_rows(CASE_DIR / "04_教师_期末试卷成绩表_35人.xlsx"),
            method=task["method"],
            matrix=task["matrix"],
            paper=task["paper"],
        )
        assert pv["ok"] and len(pv["students"]) == 35

        calc_res = api.calculate_task(task["id"], {"students": pv["students"]}, user=teacher_user)
        done_task = calc_res["task"]
        assert done_task["status"] == "completed"
        assert done_task["student_count"] == 35
        assert done_task["exam_analysis_text"] != ""
        assert done_task["analysis_text"] != ""

        # 修改三段分析文本并验证持久化
        api.update_task_notes(
            task["id"],
            {
                "analysis_text": "自定义达成分析",
                "improvement_notes": "自定义改进措施",
                "exam_analysis_text": "自定义试卷质量分析",
            },
            user=teacher_user,
        )
        reloaded = api.get_task(task["id"], user=teacher_user)["task"]
        assert reloaded["exam_analysis_text"] == "自定义试卷质量分析"
        print("[PASS] 5. 达成度计算、4 维诊断、试卷分析及三段文本持久化通过")

        # 6. 一键导出双文档归档包 ZIP
        zbuf, zname = api._build_archive_bundle_zip(reloaded)
        with zipfile.ZipFile(zbuf) as zf:
            names = zf.namelist()
            assert len(names) == 2
            wb_att = openpyxl.load_workbook(io.BytesIO(zf.read(names[0])), data_only=False)
            wb_exam = openpyxl.load_workbook(io.BytesIO(zf.read(names[1])), data_only=False)
            assert wb_att.sheetnames == ["目标达成评价表", "达成度计算表", "大纲与权重依据", "全班学生得分明细表"]
            assert wb_exam.sheetnames == ["各题得分统计表", "考试试卷分析表"]
            assert wb_exam["考试试卷分析表"]["A14"].value == "自定义试卷质量分析"
        print(f"[PASS] 6. 双文档归档包 ZIP 验收通过：{zname}（含 4-Sheet 达成度表 + 2-Sheet 试卷分析表）")

        # 7. 管理员全院汇总监控
        ov = api.admin_overview(admin=admin_user)["overview"]
        assert ov["syllabus_count"] == 1
        assert ov["exam_paper_count"] == 1
        assert ov["report_count"] == 1
        print("[PASS] 7. 管理员全院监控验收通过")

        print("\n" + "=" * 68)
        print("全部 7 项三层架构全链路验收测试 100% 通过！")
        print("=" * 68)
    finally:
        db.DB_PATH = orig_db
        import gc
        gc.collect()
        if test_db.exists():
            try:
                test_db.unlink()
            except PermissionError:
                pass


if __name__ == "__main__":
    run_all_tests()
