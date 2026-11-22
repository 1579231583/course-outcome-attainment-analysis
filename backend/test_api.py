"""后端全功能一键验收测试脚本（P0 安全隔离 + Copy-on-Write + 4-Sheet 归档导出 + 诊断）

运行：python backend/test_api.py
"""

import copy
import sys
import tempfile
from pathlib import Path

import openpyxl
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import api
import calc_engine as eng
import course_template
import db
import export_report


def run_all_tests():
    print("=" * 66)
    print("开始执行后端全流程自动化验收测试（含 P0 并发安全与 4-Sheet 校验）...")
    print("=" * 66)

    # 1. 双角色登录与真实 Token 鉴权验收 (P0-2)
    res_teacher = api.login({"username": "teacher", "password": "123456"})
    res_admin = api.login({"username": "admin", "password": "admin123"})
    t_user = api.get_current_user(authorization=f"Bearer {res_teacher['token']}")
    a_user = api.get_current_user(authorization=f"Bearer {res_admin['token']}")
    assert t_user["role"] == "teacher" and a_user["role"] == "admin"

    # 未登录拦截 401
    try:
        api.get_current_user(authorization=None, token=None)
        raise AssertionError("未登录应返回 401")
    except HTTPException as e:
        assert e.status_code == 401

    # 普通教师越权调管理员接口拦截 403
    try:
        api.require_admin(user=t_user)
        raise AssertionError("普通教师调管理员接口应返回 403")
    except HTTPException as e:
        assert e.status_code == 403
    print("[PASS] 1. 双角色登录与 Token 鉴权隔离验证通过（401 / 403 拦截生效）")

    # 2. 公共课程模板只读保护（Copy-on-Write）验收 (P0-3)
    pub_list = api.list_public_course_templates(user=t_user)["templates"]
    created_temp_pub = False
    if not pub_list:
        tmp_pub = db.create_course(
            {"meta": {"课程名称": "高等数学A（II）", "学期": "2023-2024-2", "班级": "23智能制造1班"}},
            user_id=a_user["id"],
            is_public=True,
        )
        pub_id = tmp_pub["course_id"]
        created_temp_pub = True
    else:
        math_tpl = next((c for c in pub_list if "高等数学" in c["course_name"]), pub_list[0])
        pub_id = math_tpl["id"]
    orig_pub = db.get_course_for_user(a_user["id"], "admin", course_id=pub_id)

    # 教师选用公共模板 -> 自动克隆为自己的私有副本
    applied = api.apply_public_template(pub_id, user=t_user)
    cloned_cfg = applied["config"]
    assert cloned_cfg["course_id"] != pub_id
    assert cloned_cfg["is_public"] is False

    # 教师直接对原公共模板 ID 提交修改 -> 自动触发 Copy-on-Write，原公共模板绝不被改坏！
    mod_payload = copy.deepcopy(orig_pub)
    mod_payload["meta"]["班级"] = "测试防误改班级"
    save_res = api.save_config(mod_payload, user=t_user)
    assert save_res["cloned"] is True
    assert save_res["course_id"] != pub_id
    recheck_pub = db.get_course_for_user(a_user["id"], "admin", course_id=pub_id)
    assert recheck_pub["meta"]["班级"] == orig_pub["meta"]["班级"]

    # 清理测试创建的两个临时私有副本
    db.delete_course(cloned_cfg["course_id"], t_user["id"], "teacher")
    db.delete_course(save_res["course_id"], t_user["id"], "teacher")
    print("[PASS] 2. 公共课程模板 Copy-on-Write 防误改验证通过")

    # 3. 公共课程规则模板 Excel 生成 -> 无状态解析闭环
    cfg_buf = course_template.build_course_config_template(
        meta=orig_pub["meta"],
        threshold=orig_pub["threshold"],
        method=orig_pub["method"],
        matrix=orig_pub["matrix"],
        paper=orig_pub["paper"],
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(cfg_buf.getvalue())
        tmp_path = Path(tmp.name)
    try:
        parsed_tpl = course_template.parse_course_config_excel(tmp_path)
        assert parsed_tpl["meta"]["课程名称"] == orig_pub["meta"]["课程名称"]
        assert abs(sum(parsed_tpl["method"]["平时环节"].values()) - 1.0) < 1e-6
    finally:
        tmp_path.unlink(missing_ok=True)
    print("[PASS] 3. 《课程规则配置模板.xlsx》生成与无状态解析验证通过")

    # 4. 44 人真实数据无状态解析 + 边界保护 (P0-1)（使用独立高数回归测试课程，不依赖库中已有数据）
    math_course = db.create_course(
        {
            "meta": {
                "课程名称": "高等数学A（II）",
                "课程代码": "1230601002F",
                "学期": "2023-2024-2",
                "班级": "23智能制造1班",
                "任课教师": "张老师",
                "课程类别": "基础课",
                "学分": 5.5,
                "授课学时": 88,
            },
            "threshold": 0.65,
            "method": eng.METHOD,
            "matrix": eng.MATRIX,
            "paper": eng.PAPER_STRUCTURE,
        },
        user_id=t_user["id"],
        is_public=False,
    )
    math_cid = math_course["course_id"]
    try:
        parsed = api.parse_sample_data(course_id=math_cid, user=t_user)
        assert parsed["ok"] is True and len(parsed["students"]) == 44

        # 模拟边界保护：不考期末目标（纯函数传参，不污染全局）
        mat3 = copy.deepcopy(math_course["matrix"])
        mat3["课程目标3"] = {"作业": 0.2, "课堂表现": 0.0, "测验": 0.0, "期末考试": 0.0}
        qs3 = eng.validate_structure(math_course["method"], mat3, math_course["paper"])
        lw3 = eng.step1_link_weights(math_course["method"])
        out3, full3 = eng.step2_output_weights(lw3, mat3)
        rep3 = eng.step5_report(parsed["students"], out3, full3, qs3, math_course["method"], mat3)
        assert rep3["课程目标3"]["期末"] == 0.0 and rep3["课程目标3"]["达成度"] > 0
        print("[PASS] 4. 无状态纯函数解析与边界保护验证通过")

        # 5. 计算基准 + 终极 4-Sheet 归档报表导出验收（含跨表公式与签字栏）
        calc_res = api.calculate_records(
            {
                "course_id": math_cid,
                "students": parsed["students"],
                "threshold": 0.65,
                "save_report": False,
            },
            user=t_user,
        )
        t1_pct = round(calc_res["report"]["课程目标1"]["达成度"] * 100, 1)
        t2_pct = round(calc_res["report"]["课程目标2"]["达成度"] * 100, 1)
        assert t1_pct == 62.9 and t2_pct == 77.0

        diag_res = api.diagnostics_analyze(
            {"course_id": math_cid, "students": parsed["students"], "threshold": 0.65},
            user=t_user,
        )
        diag = diag_res["diagnostics"]
        assert diag["analysis_text"] and diag["improvement_text"]

        qs = eng.validate_structure(math_course["method"], math_course["matrix"], math_course["paper"])
        lw = eng.step1_link_weights(math_course["method"])
        out, full = eng.step2_output_weights(lw, math_course["matrix"])
        p_full = eng.paper_target_full(qs, math_course["matrix"])

        wb_buf = export_report.build_workbook(
            calc_res["students"],
            out,
            full,
            qs,
            p_full,
            meta=math_course["meta"],
            threshold=0.65,
            method=math_course["method"],
            matrix=math_course["matrix"],
            analysis_text=diag["analysis_text"],
            improvement_notes=diag["improvement_text"],
        )
        wb = openpyxl.load_workbook(wb_buf, data_only=False)
        assert wb.sheetnames == ["目标达成评价表", "达成度计算表", "大纲与权重依据", "全班学生得分明细表"]
        ws_eval = wb["目标达成评价表"]
        assert str(ws_eval["C12"].value).startswith("='达成度计算表'!")
        assert "评价人（签字）" in [ws_eval.cell(r, 1).value for r in range(1, ws_eval.max_row + 1)]
        print(f"[PASS] 5. 回归基准({t1_pct}%/{t2_pct}%) + 终极 4-Sheet 归档表（跨表公式 + 签字栏）验证通过")
    finally:
        db.delete_course(math_cid, t_user["id"], "teacher")

    # 6. 管理员全院监控汇总验收
    ov = api.admin_overview(admin=a_user)["overview"]
    assert ov["teacher_count"] >= 1 and ov["public_template_count"] >= 1
    print(f"[PASS] 6. 管理员全院监控验收通过（教师 {ov['teacher_count']} 人，公共模板 {ov['public_template_count']} 套）")

    print("\n" + "=" * 66)
    print("全部 6 项 P0 级安全隔离与 4-Sheet 报表验收测试 100% 通过！")
    print("=" * 66)


if __name__ == "__main__":
    run_all_tests()
