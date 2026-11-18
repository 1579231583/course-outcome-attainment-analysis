"""接口冒烟测试：上传示例数据，打印达成度。"""
import json
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "示例"

files = {
    "daily_file": SAMPLE / "平时成绩表.xlsx",
    "final_file": SAMPLE / "期末小题成绩录入模板.xlsx",
}

boundary = uuid.uuid4().hex
body = b""
for field, path in files.items():
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'.encode()
    body += b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    body += path.read_bytes() + b"\r\n"
body += f"--{boundary}--\r\n".encode()

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/calculate",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
)
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.loads(resp.read().decode("utf-8"))

print(f"学生数 {data['student_count']}，期末匹配 {data['matched']} 人")
for t, r in data["report"].items():
    print(f"{t}: 实得 {r['实得']:.2f} / 满分 {r['理论满分']:.2f} "
          f"→ 达成度 {r['达成度'] * 100:.1f}%")
