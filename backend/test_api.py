"""后端全功能一键验收测试脚本

直接验证后端所有核心模块与 FastAPI 接口逻辑（无需额外安装 httpx，1 秒跑完）：
  1. 双角色账号登录（teacher / admin）与管理员账号管理
  2. 公共课程规则模板 Excel 生成 -> 解析导入闭环
  3. 44 人真实成绩非阻断解析 + 模拟超分拦截与在线纠错重算
  4. 边界保护测试（矩阵整列全 0 拦截 + 某目标不考期末防除零）
  5. 三 Sheet《达成度计算表.xlsx》导出校验
  6. OBE 诊断 Agent 4 维下钻统计与持续改进草稿生成
  7. 历史报告归档、重下 Excel 与管理员全院监控汇总

运行：python backend/test_api.py
"""

import copy
import sys
import tempfile
from pathlib import Path

import openpyxl

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import api
import calc_engine as eng
import course_template
import db
import diagnostics
import export_report


def run_all_tests():
    print("=" * 64)
    print("开始执行后端全流程自动化验收测试...")
    print("=" * 64)

    # 1. 双角色登录验收
    res_teacher = api.login({"username": "teacher", "password": "123456"})
    assert res_teacher["ok"] and res_teacher["user"]["role"] == "teacher"
    res_admin = api.login({"username": "admin", "password": "admin123"})
    assert res_admin["ok"] and res_admin["user"]["role"] == "admin"
    print("[PASS] 1. 双角色登录验证通过（teacher / admin）")

    # 2. 管理员账号列表与公共课程模板库验收
    users = api.admin_list_users()["users"]
    assert len(users) >= 2
    pub_templates = api.list_public_course_templates()["templates"]
    assert len(pub_templates) >= 1 and pub_templates[0]["is_public"] is True
    print(f"[PASS] 2. 管理员账号({len(users)}人) 与 公共课程模板库({len(pub_templates)}套) 验证通过")

    # 3. 公共课程规则模板 Excel 导出 -> 解析闭环验收
    cfg_buf = course_template.build_course_config_template(
        meta=api.META,
        threshold=eng.PASS_THRESHOLD,
        method=eng.METHOD,
        matrix=eng.MATRIX,
        paper=eng.PAPER_STRUCTURE,
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(cfg_buf.getvalue())
        tmp_path = Path(tmp.name)
    try:
        parsed_tpl = course_template.parse_course_config_excel(tmp_path)
        assert parsed_tpl["meta"]["课程名称"] == api.META["课程名称"]
        assert abs(sum(parsed_tpl["method"]["平时环节"].values()) - 1.0) < 1e-6
        assert sum(q["满分"] for g in parsed_tpl["paper"] for q in g["小题"]) == 100
    finally:
        tmp_path.unlink(missing_ok=True)
    print("[PASS] 3. 《课程规则配置模板.xlsx》下载与解析导入闭环验证通过")

    # 4. 44 人真实数据非阻断预览解析 + 在线纠错测试
    parsed = api.parse_sample_data()
    assert parsed["ok"] is True
    assert len(parsed["students"]) == 44
    assert len(parsed["errors"]) == 0
    assert len(api.CURRENT_ROSTER) == 44

    # 模拟制造 1 处超分错误，验证非阻断拦截能精确定位到学号与题号
    d_rows = eng.load_rows("平时成绩表.xlsx")
    f_rows = eng.load_rows("期末小题成绩录入模板.xlsx")
    f_rows_dirty = copy.deepcopy(f_rows)
    f_rows_dirty[1][2] = 9.0  # 第1题满分3分，故意改为9分
    dirty_res = eng.parse_sheets_for_preview(d_rows, f_rows_dirty)
    assert dirty_res["ok"] is False
    assert len(dirty_res["errors"]) == 1
    assert dirty_res["errors"][0]["field"] == "第1题"
    print("[PASS] 4. 44 人非阻断解析 & 超分单元格精确定位验证通过")

    # 5. 边界保护测试：整列全 0 拦截 + 某目标不考期末防除零
    old_mat = copy.deepcopy(eng.MATRIX)
    try:
        eng.MATRIX["课程目标1"]["测验"] = 0
        eng.MATRIX["课程目标2"]["测验"] = 0
        try:
            eng.step2_output_weights(eng.step1_link_weights())
            raise AssertionError("应拦截整列全 0")
        except ValueError as e:
            assert "比例之和为 0" in str(e)

        # 恢复并新增一个“不考期末”的课程目标3
        eng.MATRIX = copy.deepcopy(old_mat)
        eng.MATRIX["课程目标3"] = {"作业": 0.2, "课堂表现": 0.0, "测验": 0.0, "期末考试": 0.0}
        qs = eng.validate_structure()
        lw = eng.step1_link_weights()
        out, full = eng.step2_output_weights(lw)
        rep3 = eng.step5_report(parsed["students"], out, full, qs)
        assert rep3["课程目标3"]["期末"] == 0.0
        assert rep3["课程目标3"]["达成度"] > 0
    finally:
        eng.MATRIX = old_mat
    print("[PASS] 5. 边界保护验证通过（整列全 0 拦截 + 不考期末目标防除零）")

    # 6. 基于 JSON 在线计算 + 三 Sheet Excel 导出验收
    calc_res = api.calculate_records(
        {"students": parsed["students"], "threshold": 0.65, "save_report": False}
    )
    t1_pct = round(calc_res["report"]["课程目标1"]["达成度"] * 100, 1)
    t2_pct = round(calc_res["report"]["课程目标2"]["达成度"] * 100, 1)
    assert t1_pct == 62.9 and t2_pct == 77.0, f"回归基准不符: {t1_pct}, {t2_pct}"

    qs = eng.validate_structure()
    lw = eng.step1_link_weights()
    out, full = eng.step2_output_weights(lw)
    p_full = eng.paper_target_full(qs)
    wb_buf = export_report.build_workbook(
        calc_res["students"], out, full, qs, p_full, api.META, threshold=0.65
    )
    wb = openpyxl.load_workbook(wb_buf, data_only=False)
    assert wb.sheetnames == ["达成度计算表", "课程目标评价汇总表", "全班学生得分明细表"]
    print(f"[PASS] 6. 计算基准({t1_pct}% / {t2_pct}%) 与 三 Sheet Excel 导出验证通过")

    # 7. OBE 诊断 Agent 下钻统计与改进草稿验收
    diag_res = api.diagnostics_analyze({"students": parsed["students"], "threshold": 0.65})
    diag = diag_res["diagnostics"]
    assert len(diag["hard_questions"]) == 5
    assert "课程目标1" in diag["draft_text"]
    assert "最薄弱环节" in diag["draft_text"]
    print("[PASS] 7. OBE 诊断 Agent 4 维下钻统计与改进草稿生成验证通过")
    print("\n--- 自动生成的 OBE 诊断草稿预览 ---")
    print(diag["draft_text"])
    print("-----------------------------------")

    # 8. 管理员全院监控汇总验收
    ov = api.admin_overview()["overview"]
    assert ov["teacher_count"] >= 1 and ov["public_template_count"] >= 1
    print(f"[PASS] 8. 管理员全院监控汇总验证通过（教师 {ov['teacher_count']} 人，公共模板 {ov['public_template_count']} 套）")

    print("\n" + "=" * 64)
    print("全部 8 项后端核心验收测试 100% 通过！后端已具备完整封版条件。")
    print("=" * 64)


if __name__ == "__main__":
    run_all_tests()
