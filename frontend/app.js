let CFG = null;

// ---------- 初始化 ----------
async function init() {
  const res = await fetch("/api/config");
  CFG = await res.json();
  renderDaily();
  renderMatrix();
  renderPaper();
}

// ---------- 步骤 1：平时环节 ----------
function renderDaily() {
  const tb = document.querySelector("#dailyTable tbody");
  tb.innerHTML = "";
  Object.entries(CFG.method["平时环节"]).forEach(([name, ratio]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="text" value="${name}" onchange="renameDaily(this, '${name}')"></td>
      <td><input type="number" step="0.01" value="${ratio}" onchange="setDailyRatio('${name}', this.value)"></td>
      <td><button class="btn ghost mini" onclick="removeDaily('${name}')">删除</button></td>`;
    tb.appendChild(tr);
  });
  document.getElementById("dailyRatio").value = CFG.method["平时占比"];
  document.getElementById("finalRatio").value = CFG.method["期末占比"];
  updateDailySum();
}

function updateDailySum() {
  const sum = Object.values(CFG.method["平时环节"]).reduce((a, b) => a + b, 0);
  const el = document.getElementById("dailySum");
  el.textContent = `平时环节占比之和：${sum.toFixed(2)}`;
  el.className = "hint " + (Math.abs(sum - 1) < 1e-6 ? "ok" : "err");
  renderOutputPreview();
}

function setDailyRatio(name, v) {
  CFG.method["平时环节"][name] = parseFloat(v) || 0;
  updateDailySum();
}

// 平时/期末总占比变化时，同步刷新环节权重预览
function setTotalRatio() {
  CFG.method["平时占比"] = parseFloat(document.getElementById("dailyRatio").value) || 0;
  CFG.method["期末占比"] = parseFloat(document.getElementById("finalRatio").value) || 0;
  renderOutputPreview();
}

function renameDaily(input, oldName) {
  const newName = input.value.trim();
  if (!newName || newName === oldName) return;
  const entries = Object.entries(CFG.method["平时环节"]).map(([k, v]) =>
    k === oldName ? [newName, v] : [k, v]
  );
  CFG.method["平时环节"] = Object.fromEntries(entries);
  // 同步矩阵里的列名
  Object.values(CFG.matrix).forEach(row => {
    if (oldName in row) { row[newName] = row[oldName]; delete row[oldName]; }
  });
  renderDaily(); renderMatrix();
}

function removeDaily(name) {
  delete CFG.method["平时环节"][name];
  Object.values(CFG.matrix).forEach(row => delete row[name]);
  renderDaily(); renderMatrix();
}

function addDaily() {
  const name = prompt("新环节名称：");
  if (!name) return;
  CFG.method["平时环节"][name] = 0;
  Object.values(CFG.matrix).forEach(row => row[name] = 0);
  renderDaily(); renderMatrix();
}

// ---------- 步骤 2：目标矩阵 ----------
function renderMatrix() {
  const links = [...Object.keys(CFG.method["平时环节"]), "期末考试"];
  const targets = Object.keys(CFG.matrix);
  const t = document.getElementById("matrixTable");
  let html = "<thead><tr><th>课程目标</th>" +
    links.map(l => `<th>${l}</th>`).join("") + "</tr></thead><tbody>";
  targets.forEach(tg => {
    html += `<tr><td>${tg}</td>` + links.map(l => {
      const v = CFG.matrix[tg][l] ?? 0;
      return `<td><input type="number" step="0.01" value="${v}"
        onchange="setMatrix('${tg}','${l}',this.value)"></td>`;
    }).join("") + "</tr>";
  });
  html += "</tbody>";
  t.innerHTML = html;
  renderOutputPreview();
}

function setMatrix(tg, link, v) {
  CFG.matrix[tg][link] = parseFloat(v) || 0;
  renderOutputPreview();
}

// 环节权重：平时各环节 = 平时占比 × 环节占比；期末 = 期末占比
function calcLinkWeights() {
  const w = {};
  Object.entries(CFG.method["平时环节"]).forEach(([name, ratio]) => {
    w[name] = (CFG.method["平时占比"] || 0) * (ratio || 0);
  });
  w["期末考试"] = CFG.method["期末占比"] || 0;
  return w;
}

// 产出权重（列归一化）与理论满分，与后端 step2_output_weights 保持一致
function calcOutputWeights() {
  const links = [...Object.keys(CFG.method["平时环节"]), "期末考试"];
  const targets = Object.keys(CFG.matrix);
  const linkW = calcLinkWeights();
  const output = {};
  targets.forEach(t => { output[t] = {}; });

  links.forEach(link => {
    const colSum = targets.reduce((a, t) => a + (CFG.matrix[t][link] || 0), 0);
    targets.forEach(t => {
      const m = CFG.matrix[t][link] || 0;
      output[t][link] = colSum > 0 ? linkW[link] * m / colSum : 0;
    });
  });

  const full = {};
  targets.forEach(t => {
    full[t] = Object.values(output[t]).reduce((a, b) => a + b, 0) * 100;
  });
  return { links, targets, linkW, output, full };
}

function renderOutputPreview() {
  const { links, targets, linkW, output, full } = calcOutputWeights();

  // 列和提示：帮助教师理解“列和不必为 1”
  const colSums = links.map(l =>
    targets.reduce((a, t) => a + (CFG.matrix[t][l] || 0), 0)
  );
  const sumEl = document.getElementById("matrixColSum");
  const bad = colSums.some(s => s <= 0);
  sumEl.textContent = "各列比例之和：" +
    links.map((l, i) => `${l} ${colSums[i].toFixed(2)}`).join("　") +
    (bad ? "　（存在全 0 的列，该环节无法分配）" : "");
  sumEl.className = "hint " + (bad ? "err" : "");

  // 产出权重表
  const t = document.getElementById("outputTable");
  let html = "<thead><tr><th>课程目标</th>" +
    links.map(l => `<th>${l}</th>`).join("") +
    "<th>理论满分</th></tr></thead><tbody>";

  // 环节权重行
  html += "<tr class='sub-row'><td>环节权重（分）</td>" +
    links.map(l => `<td>${(linkW[l] * 100).toFixed(2)}</td>`).join("") +
    "<td>100.00</td></tr>";

  targets.forEach(tg => {
    html += `<tr><td>${tg}</td>` +
      links.map(l => `<td>${output[tg][l].toFixed(2)}</td>`).join("") +
      `<td class="strong">${full[tg].toFixed(2)}</td></tr>`;
  });
  html += "</tbody>";
  t.innerHTML = html;
}

// ---------- 步骤 3：试卷结构 ----------
function renderPaper() {
  const area = document.getElementById("paperArea");
  area.innerHTML = "";
  CFG.paper.forEach((g, gi) => {
    const div = document.createElement("div");
    div.className = "group";
    let rows = g["小题"].map((q, qi) => `
      <tr>
        <td><input type="number" value="${q["题号"]}" onchange="setQ(${gi},${qi},'题号',this.value)"></td>
        <td><input type="number" value="${q["满分"]}" onchange="setQ(${gi},${qi},'满分',this.value)"></td>
        <td><select onchange="setQ(${gi},${qi},'目标',this.value)">
          ${Object.keys(CFG.matrix).map(t =>
            `<option ${t === q["目标"] ? "selected" : ""}>${t}</option>`).join("")}
        </select></td>
        <td><button class="btn ghost mini" onclick="removeQ(${gi},${qi})">删除</button></td>
      </tr>`).join("");
    div.innerHTML = `
      <div class="group-head">
        <input type="text" value="${g["大题"]}" onchange="CFG.paper[${gi}]['大题']=this.value">
        <button class="btn ghost mini" onclick="addQ(${gi})">+ 小题</button>
        <button class="btn ghost mini" onclick="removeGroup(${gi})">删除大题</button>
      </div>
      <table>
        <thead><tr><th>题号</th><th>满分</th><th>课程目标</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
    area.appendChild(div);
  });
  updatePaperSum();
}

function updatePaperSum() {
  const qs = CFG.paper.flatMap(g => g["小题"]);
  const total = qs.reduce((a, q) => a + (parseFloat(q["满分"]) || 0), 0);
  const el = document.getElementById("paperSum");
  el.textContent = `共 ${qs.length} 道小题，试卷总分：${total}`;
  el.className = "hint " + (total === 100 ? "ok" : "err");
}

function setQ(gi, qi, key, v) {
  CFG.paper[gi]["小题"][qi][key] = key === "目标" ? v : (parseFloat(v) || 0);
  updatePaperSum();
}

function addQ(gi) {
  const qs = CFG.paper[gi]["小题"];
  const last = qs.length ? qs[qs.length - 1]["题号"] : 0;
  qs.push({ 题号: last + 1, 满分: 5, 目标: Object.keys(CFG.matrix)[0] });
  renderPaper();
}

function removeQ(gi, qi) {
  CFG.paper[gi]["小题"].splice(qi, 1);
  renderPaper();
}

function addGroup() {
  CFG.paper.push({ 大题: "新大题", 小题: [] });
  renderPaper();
}

function removeGroup(gi) {
  CFG.paper.splice(gi, 1);
  renderPaper();
}

// ---------- 步骤 4：保存配置 ----------
async function saveConfig() {
  CFG.method["平时占比"] = parseFloat(document.getElementById("dailyRatio").value) || 0;
  CFG.method["期末占比"] = parseFloat(document.getElementById("finalRatio").value) || 0;
  const msg = document.getElementById("saveMsg");
  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(CFG),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "保存失败");
    msg.textContent = "配置已保存，可以下载模板了";
    msg.className = "hint ok";
  } catch (e) {
    msg.textContent = e.message;
    msg.className = "hint err";
  }
}

// ---------- 步骤 5：计算 ----------
async function calculate() {
  const df = document.getElementById("dailyFile").files[0];
  const ff = document.getElementById("finalFile").files[0];
  const msg = document.getElementById("calcMsg");
  if (!df || !ff) {
    msg.textContent = "请先选择两个成绩表";
    msg.className = "hint err";
    return;
  }
  const fd = new FormData();
  fd.append("daily_file", df);
  fd.append("final_file", ff);
  msg.textContent = "计算中…";
  msg.className = "hint";
  try {
    const res = await fetch("/api/calculate", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "计算失败");
    msg.textContent = `计算完成：${data.student_count} 人`;
    msg.className = "hint ok";
    renderResult(data);
  } catch (e) {
    msg.textContent = e.message;
    msg.className = "hint err";
  }
}

async function exportReport() {
  const df = document.getElementById("dailyFile").files[0];
  const ff = document.getElementById("finalFile").files[0];
  const msg = document.getElementById("calcMsg");
  if (!df || !ff) {
    msg.textContent = "请先选择两个成绩表";
    msg.className = "hint err";
    return;
  }
  const fd = new FormData();
  fd.append("daily_file", df);
  fd.append("final_file", ff);
  msg.textContent = "正在生成…";
  msg.className = "hint";
  try {
    const res = await fetch("/api/export", { method: "POST", body: fd });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || "导出失败");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "达成度计算表.xlsx";
    a.click();
    URL.revokeObjectURL(url);
    msg.textContent = "已导出达成度计算表.xlsx";
    msg.className = "hint ok";
  } catch (e) {
    msg.textContent = e.message;
    msg.className = "hint err";
  }
}

function renderResult(data) {
  const card = document.getElementById("resultCard");
  const area = document.getElementById("resultArea");
  card.style.display = "block";

  let html = `<p class="hint">学生数 ${data.student_count}，期末匹配 ${data.matched} 人</p>`;
  html += `<table class="result-table">
    <thead><tr>
      <th>课程目标</th><th>平时贡献</th><th>期末贡献</th>
      <th>实得</th><th>理论满分</th><th>达成度</th>
    </tr></thead><tbody>`;
  Object.entries(data.report).forEach(([t, r]) => {
    const daily = Object.values(r["平时明细"]).reduce((a, b) => a + b, 0);
    const pct = (r["达成度"] * 100).toFixed(1);
    const pass = r["达成度"] >= 0.65;
    html += `<tr>
      <td>${t}</td>
      <td>${daily.toFixed(2)}</td>
      <td>${r["期末"].toFixed(2)}</td>
      <td>${r["实得"].toFixed(2)}</td>
      <td>${r["理论满分"].toFixed(2)}</td>
      <td><span class="badge ${pass ? "pass" : "fail"}">${pct}%</span></td>
    </tr>`;
  });
  html += "</tbody></table>";

  html += `<h3>环节权重</h3><table><thead><tr><th>环节</th><th>权重</th></tr></thead><tbody>`;
  Object.entries(data.link_weights).forEach(([k, v]) => {
    html += `<tr><td>${k}</td><td>${(v * 100).toFixed(1)}%</td></tr>`;
  });
  html += "</tbody></table>";

  area.innerHTML = html;
}

init();
