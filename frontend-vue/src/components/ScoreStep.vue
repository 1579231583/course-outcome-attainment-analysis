<template>
  <div v-if="task">
    <div class="page-header">
      <div class="title-area">
        <div class="title-row">
          <h1>{{ task.course_name }}</h1>
          <span class="class-chip">{{ task.class_name }}</span>
          <span class="meta-badge tabular-nums">{{ task.semester }}</span>
        </div>
        <p class="subtitle">
          上传平时与期末成绩表 → 在线核对红框异常 → 一键生成达成度与试卷分析报告
        </p>
      </div>

      <div class="head-actions">
        <el-button
          v-if="task.status === 'completed'"
          plain
          size="large"
          @click="$emit('view-report')"
        >
          查看已有报告
        </el-button>
        <el-button
          :type="paperReady ? 'default' : 'warning'"
          :plain="paperReady"
          size="large"
          @click="openRuleDrawer(paperReady ? 'basic' : 'paper')"
        >
          {{ paperReady ? '查看 / 微调规则与试卷' : '去配置期末试卷 →' }}
        </el-button>
      </div>
    </div>

    <!-- 一行规则摘要条 -->
    <div class="rule-strip tabular-nums">
      <div class="rs-item" @click="openRuleDrawer('basic')">
        <span class="rs-k">成绩占比</span>
        <span v-if="task.ratios_confirmed" class="rs-v">
          平时 {{ Math.round((task.method['平时占比'] || 0) * 100) }}%（{{ dailyLinks.join(' / ') }}） ·
          期末 {{ Math.round((task.method['期末占比'] || 0) * 100) }}%
        </span>
        <span v-else class="status-pill warn"><span class="dot"></span>请先在下方配置占比</span>
      </div>
      <div class="rs-divider"></div>
      <div class="rs-item" @click="openRuleDrawer('matrix')">
        <span class="rs-k">课程目标</span>
        <span class="rs-v">{{ targetCount }} 个目标 · 合格线 {{ Math.round((task.threshold || 0.65) * 100) }}%</span>
      </div>
      <div class="rs-divider"></div>
      <div class="rs-item" @click="openRuleDrawer('paper')">
        <span class="rs-k">期末试卷</span>
        <span v-if="paperReady" class="status-pill ok">
          <span class="dot"></span>
          {{ task.paper_source === 'unified' ? '统考卷' : '自配卷' }}（{{ flatQuestions.length }} 题 · 100 分）
        </span>
        <span v-else class="status-pill warn">
          <span class="dot"></span>待配试卷（当前 {{ paperTotal }} 分）
        </span>
      </div>
    </div>

    <!-- 教师首次进入必做：按学校《成绩评定方法表》层级版式填写平时/期末占比 -->
    <div v-if="!task.ratios_confirmed" class="panel-card ratio-setup-card">
      <div class="panel-title">
        <span>第一步：填写本班《成绩评定方法》</span>
        <div class="actions">
          <span class="status-pill tabular-nums" :class="dailySumOk ? 'ok' : 'err'">
            平时内部合计 {{ dailySum.toFixed(2) }} / 1.00
          </span>
          <span class="status-pill tabular-nums" :class="totalRatioOk ? 'ok' : 'err'">
            平时 + 期末 {{ (Number(task.method['平时占比'] || 0) + Number(task.method['期末占比'] || 0)).toFixed(2) }} / 1.00
          </span>
        </div>
      </div>

      <div class="method-table-wrap">
        <table class="method-table tabular-nums">
          <thead>
            <tr>
              <th rowspan="2" class="mt-side">成绩评定方法</th>
              <th :colspan="dailyLinks.length" class="mt-group-daily">平时成绩</th>
              <th rowspan="2" class="mt-group-final">期末考试</th>
            </tr>
            <tr>
              <th v-for="link in dailyLinks" :key="'th-' + link" class="mt-sub">{{ link }}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="mt-row-lbl">占平时比例<br /><span>（相加 = 1）</span></td>
              <td v-for="link in dailyLinks" :key="'td-' + link" class="mt-cell">
                <el-input-number
                  v-model="task.method['平时环节'][link]"
                  :controls="false"
                  :min="0"
                  :max="1"
                  :precision="2"
                  placeholder="0.00"
                  style="width: 92px"
                />
              </td>
              <td class="mt-cell mt-dash">—</td>
            </tr>
            <tr>
              <td class="mt-row-lbl">占总评比例<br /><span>（相加 = 1）</span></td>
              <td :colspan="dailyLinks.length" class="mt-cell mt-daily-total">
                <el-input-number
                  v-model="task.method['平时占比']"
                  :controls="false"
                  :min="0"
                  :max="1"
                  :precision="2"
                  placeholder="如 0.40"
                  style="width: 120px"
                />
              </td>
              <td class="mt-cell mt-final-total">
                <el-input-number
                  v-model="task.method['期末占比']"
                  :controls="false"
                  :min="0"
                  :max="1"
                  :precision="2"
                  placeholder="如 0.60"
                  style="width: 110px"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="method-bottom tabular-nums">
        <div class="mb-left">
          <span class="mb-lbl">达标合格线</span>
          <el-input-number
            v-model="task.threshold"
            :controls="false"
            size="small"
            :min="0.1"
            :max="1"
            :precision="2"
            style="width: 80px"
          />
          <span v-if="totalRatioOk && dailySumOk" class="mb-preview">
            折合总评 100 分：
            <span v-for="l in dailyLinks" :key="'pv-' + l" class="mb-chip">
              {{ l }} <b>{{ ((task.method['平时占比'] || 0) * (task.method['平时环节'][l] || 0) * 100).toFixed(1) }}</b>分
            </span>
            <span class="mb-chip">
              期末考试 <b>{{ ((task.method['期末占比'] || 0) * 100).toFixed(1) }}</b>分
            </span>
          </span>
        </div>

        <el-button
          type="primary"
          size="large"
          :disabled="!totalRatioOk || !dailySumOk"
          :loading="savingRatios"
          @click="saveInitialRatios"
        >
          确认保存，开始上传成绩
        </el-button>
      </div>
    </div>

    <!-- 核心区 ①：双栏成绩上传 -->
    <div class="panel-card">
      <div class="panel-title">
        <span>导入成绩表</span>
        <el-button v-if="dailyMeta || finalMeta" link size="small" @click="mappingDrawer = true">调整列映射</el-button>
      </div>

      <div class="upload-grid">
        <label class="drop-card" :class="{ filled: !!dailyFile }">
          <input type="file" accept=".xlsx,.xls" class="hidden-input" @change="(e) => (dailyFile = e.target.files[0])" />
          <div class="drop-top">
            <span class="drop-badge">01</span>
            <span class="drop-title">平时成绩表（.xlsx / .xls）</span>
            <el-button link type="primary" size="small" @click.prevent.stop="downloadDailyTpl">下载模板</el-button>
          </div>
          <div class="drop-body">
            <template v-if="dailyFile">
              <div class="file-picked">{{ dailyFile.name }}</div>
              <div class="drop-sub">点击可重新选择文件</div>
            </template>
            <template v-else>
              <div class="drop-placeholder">点击选择平时成绩 Excel</div>
              <div class="drop-sub">需含列：学号、姓名、{{ dailyLinks.join('、') }}</div>
            </template>
          </div>
        </label>

        <label class="drop-card" :class="{ filled: !!finalFile }">
          <input type="file" accept=".xlsx,.xls" class="hidden-input" @change="(e) => (finalFile = e.target.files[0])" />
          <div class="drop-top">
            <span class="drop-badge">02</span>
            <span class="drop-title">期末小题成绩表（.xlsx / .xls）</span>
            <el-button link type="primary" size="small" :disabled="!paperReady" @click.prevent.stop="downloadFinalTpl">
              下载模板
            </el-button>
          </div>
          <div class="drop-body">
            <template v-if="finalFile">
              <div class="file-picked">{{ finalFile.name }}</div>
              <div class="drop-sub">点击可重新选择文件</div>
            </template>
            <template v-else>
              <div class="drop-placeholder">点击选择期末小题成绩 Excel</div>
              <div class="drop-sub">
                {{ paperReady ? `需含第 1 ~ 第 ${flatQuestions.length} 题得分列` : '请先点右上角配置期末试卷结构' }}
              </div>
            </template>
          </div>
        </label>
      </div>

      <div class="upload-footer">
        <span v-if="!task.ratios_confirmed" class="warn-tip">
          提示：请先在上方填写并保存本班「平时/期末占比」后，再解析成绩。
        </span>
        <span v-else-if="!paperReady" class="warn-tip">
          提示：请先点击右上角「去配置期末试卷」并保存（凑满 100 分），再解析成绩。
        </span>
        <el-button
          type="primary"
          size="large"
          style="margin-left: auto; min-width: 180px"
          :disabled="!task.ratios_confirmed || !paperReady || !dailyFile || !finalFile"
          :loading="parsing"
          @click="parseUploadedFiles()"
        >
          解析并校验成绩
        </el-button>
      </div>
    </div>

    <!-- 核心区 ②：在线预览与红框纠错表 -->
    <div v-if="students.length > 0" class="panel-card">
      <div class="panel-title">
        <div class="actions">
          <span>成绩校验与预览（{{ students.length }} 人）</span>
          <span v-if="liveErrorCount === 0" class="status-pill ok"><span class="dot"></span>校验全部通过</span>
          <span v-else class="status-pill err"><span class="dot"></span>发现 {{ liveErrorCount }} 处异常（点红框直接修改）</span>
        </div>

        <div class="actions">
          <el-input v-model="keyword" placeholder="搜学号 / 姓名" size="small" clearable style="width: 150px" />
          <el-switch v-model="onlyErrors" active-text="仅看异常" size="small" />
          <el-button size="small" plain @click="addStudent">+ 新增</el-button>
          <el-button
            type="success"
            :disabled="liveErrorCount > 0"
            :loading="calculating"
            @click="confirmAndCalculate"
          >
            生成达成度报告 →
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="extraFinalStudents.length > 0"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom: 12px"
        :title="`期末表中有 ${extraFinalStudents.length} 名学生不在平时成绩表中，已自动忽略。`"
      />

      <el-table :data="filteredStudents" stripe size="small" max-height="500" class="tabular-nums">
        <el-table-column type="index" label="#" width="46" fixed align="center" />
        <el-table-column label="学号" width="130" fixed>
          <template #default="{ row }"><el-input v-model="row['学号']" size="small" /></template>
        </el-table-column>
        <el-table-column label="姓名" width="90" fixed>
          <template #default="{ row }"><el-input v-model="row['姓名']" size="small" /></template>
        </el-table-column>

        <el-table-column v-for="link in dailyLinks" :key="'d-' + link" :label="link" width="96" align="center">
          <template #default="{ row }">
            <el-tooltip :disabled="!dailyCellError(row, link)" :content="dailyCellError(row, link)" placement="top">
              <input
                v-model.number="row['平时'][link]"
                type="number"
                step="0.5"
                class="cell-input"
                :class="{ 'error-cell': !!dailyCellError(row, link) }"
              />
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column
          v-for="q in flatQuestions"
          :key="'q-' + q['题号']"
          :label="`第${q['题号']}题(${q['满分']})`"
          width="96"
          align="center"
        >
          <template #default="{ row }">
            <el-tooltip :disabled="!finalCellError(row, q)" :content="finalCellError(row, q)" placement="top">
              <input
                v-model.number="row['期末'][q['题号']]"
                type="number"
                step="0.5"
                class="cell-input"
                :class="{ 'error-cell': !!finalCellError(row, q) }"
              />
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button v-if="hasMissingFinal(row)" link type="warning" size="small" @click="fillZeroFinal(row)">补0</el-button>
            <el-button link type="danger" size="small" @click="deleteStudent(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <RuleDrawer
      v-model="ruleDrawerOpen"
      :task="task"
      :initial-tab="ruleDrawerTab"
      @saved="(t) => $emit('task-updated', t)"
    />

    <el-drawer v-model="mappingDrawer" title="Excel 列映射确认" size="480px">
      <div v-if="dailyMeta">
        <div class="sec-title">平时成绩表（表头位于第 {{ dailyMeta.header_row }} 行）</div>
        <el-form label-width="100px" size="small">
          <el-form-item v-for="field in ['学号', '姓名', ...dailyLinks]" :key="field" :label="field">
            <el-select v-model="customDailyMap[field]" style="width: 100%">
              <el-option v-for="(h, idx) in dailyMeta.headers" :key="idx" :label="`第 ${idx + 1} 列：${h}`" :value="idx" />
            </el-select>
          </el-form-item>
        </el-form>
      </div>
      <el-button v-if="dailyFile && finalFile" type="primary" style="width: 100%; margin-top: 14px" @click="reparseWithMapping">
        应用映射并重新解析
      </el-button>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import RuleDrawer from './RuleDrawer.vue'

const props = defineProps({
  task: { type: Object, required: true },
})
const emit = defineEmits(['calculated', 'task-updated', 'view-report'])

const ruleDrawerOpen = ref(false)
const ruleDrawerTab = ref('basic')
const dailyFile = ref(null)
const finalFile = ref(null)
const parsing = ref(false)
const calculating = ref(false)
const savingRatios = ref(false)
const students = ref([])
const extraFinalStudents = ref([])
const dailyMeta = ref(null)
const finalMeta = ref(null)
const mappingDrawer = ref(false)
const customDailyMap = reactive({})
const keyword = ref('')
const onlyErrors = ref(false)

function openRuleDrawer(tab = 'basic') {
  ruleDrawerTab.value = tab
  ruleDrawerOpen.value = true
}

const dailyLinks = computed(() => Object.keys(props.task.method?.['平时环节'] || {}))
const targetCount = computed(() => Object.keys(props.task.matrix || {}).length)
const flatQuestions = computed(() => (props.task.paper || []).flatMap((g) => g['小题'] || []))
const paperTotal = computed(() => flatQuestions.value.reduce((a, q) => a + (Number(q['满分']) || 0), 0))
const paperReady = computed(() => flatQuestions.value.length > 0 && paperTotal.value === 100)
const totalRatioOk = computed(
  () => Math.abs(Number(props.task.method?.['平时占比'] || 0) + Number(props.task.method?.['期末占比'] || 0) - 1) < 1e-6
)
const dailySum = computed(() =>
  Object.values(props.task.method?.['平时环节'] || {}).reduce((a, b) => a + Number(b || 0), 0)
)
const dailySumOk = computed(() => Math.abs(dailySum.value - 1) < 1e-6)

async function saveInitialRatios() {
  savingRatios.value = true
  try {
    const res = await api.updateTaskRules(props.task.id, {
      meta: props.task.meta,
      threshold: props.task.threshold,
      method: props.task.method,
      matrix: props.task.matrix,
      paper: props.task.paper,
    })
    ElMessage.success('占比已保存，现在可以上传平时与期末成绩表')
    emit('task-updated', res.task)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    savingRatios.value = false
  }
}

watch(
  () => props.task?.id,
  () => {
    dailyFile.value = null
    finalFile.value = null
    const existing = props.task?.students || []
    students.value = existing.map((s) => {
      const f = {}
      for (const q of flatQuestions.value) f[q['题号']] = s['期末']?.[q['题号']] ?? s['期末']?.[String(q['题号'])] ?? null
      return { 学号: s['学号'], 姓名: s['姓名'], 平时: { ...s['平时'] }, 期末: f }
    })
  },
  { immediate: true }
)

function isValidNumber(v) { return v !== null && v !== undefined && v !== '' && !Number.isNaN(Number(v)) }
function dailyCellError(row, link) {
  const v = row['平时']?.[link]
  if (!isValidNumber(v)) return `「${link}」不能为空或非数值`
  const num = Number(v)
  if (num < 0 || num > 100) return `「${link}」得分 ${num} 超出 0~100 范围`
  return ''
}
function finalCellError(row, q) {
  const qn = q['题号']
  const v = row['期末']?.[qn] ?? row['期末']?.[String(qn)]
  if (!isValidNumber(v)) return `第${qn}题得分不能为空或非数值`
  const num = Number(v)
  if (num < 0 || num > q['满分']) return `第${qn}题得分 ${num} 超出合法范围 0~${q['满分']}`
  return ''
}
function hasMissingFinal(row) {
  return flatQuestions.value.some((q) => !isValidNumber(row['期末']?.[q['题号']] ?? row['期末']?.[String(q['题号'])]))
}
function rowErrorCount(row) {
  let cnt = 0
  if (!row['学号'] || !row['姓名']) cnt++
  for (const l of dailyLinks.value) if (dailyCellError(row, l)) cnt++
  for (const q of flatQuestions.value) if (finalCellError(row, q)) cnt++
  return cnt
}

const liveErrorCount = computed(() => students.value.reduce((acc, s) => acc + rowErrorCount(s), 0))
const filteredStudents = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return students.value.filter((s) => {
    if (onlyErrors.value && rowErrorCount(s) === 0) return false
    if (!kw) return true
    return String(s['学号'] || '').toLowerCase().includes(kw) || String(s['姓名'] || '').toLowerCase().includes(kw)
  })
})

function applyParsedResult(res) {
  dailyMeta.value = res.daily_meta
  finalMeta.value = res.final_meta
  extraFinalStudents.value = res.extra_final_students || []
  Object.assign(customDailyMap, res.daily_meta?.mapping || {})
  if (res.need_mapping) {
    mappingDrawer.value = true
    ElMessage.warning('部分列名未自动识别，请在右侧抽屉手动确认')
    return
  }
  students.value = (res.students || []).map((s) => {
    const f = {}
    for (const q of flatQuestions.value) f[q['题号']] = s['期末']?.[q['题号']] ?? s['期末']?.[String(q['题号'])] ?? null
    return { 学号: s['学号'], 姓名: s['姓名'], 平时: { ...s['平时'] }, 期末: f }
  })
  if (liveErrorCount.value === 0) ElMessage.success(`解析完成：共 ${students.value.length} 人，全部校验通过`)
  else ElMessage.warning(`解析完成：共 ${students.value.length} 人，发现 ${liveErrorCount.value} 处异常，请点红框修改`)
}

async function parseUploadedFiles(dMap = null) {
  if (!dailyFile.value || !finalFile.value) return
  parsing.value = true
  try {
    const res = await api.parseTaskScores(props.task.id, dailyFile.value, finalFile.value, dMap)
    applyParsedResult(res)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    parsing.value = false
  }
}

async function reparseWithMapping() { mappingDrawer.value = false; await parseUploadedFiles(customDailyMap) }
async function downloadDailyTpl() { try { await api.downloadTaskDailyTpl(props.task.id, props.task.class_name) } catch (e) { ElMessage.error(e.message) } }
async function downloadFinalTpl() { try { await api.downloadTaskFinalTpl(props.task.id, props.task.class_name) } catch (e) { ElMessage.error(e.message) } }

function addStudent() {
  const daily = {}
  for (const l of dailyLinks.value) daily[l] = 80
  const final = {}
  for (const q of flatQuestions.value) final[q['题号']] = 0
  students.value.unshift({ 学号: `NEW${String(students.value.length + 1).padStart(3, '0')}`, 姓名: '新增学生', 平时: daily, 期末: final })
}
function deleteStudent(row) { const i = students.value.indexOf(row); if (i >= 0) students.value.splice(i, 1) }
function fillZeroFinal(row) {
  for (const q of flatQuestions.value) if (!isValidNumber(row['期末'][q['题号']])) row['期末'][q['题号']] = 0
  ElMessage.success(`已为 ${row['姓名']} 补填期末缺考项为 0 分`)
}

async function confirmAndCalculate() {
  calculating.value = true
  try {
    const res = await api.calculateTask(props.task.id, {
      students: students.value,
      class_name: props.task.class_name,
    })
    ElMessage.success('达成度计算与试卷分析已完成')
    emit('calculated', res.task)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    calculating.value = false
  }
}
</script>

<style scoped>
.title-area { display: flex; flex-direction: column; gap: 4px; }
.title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.class-chip {
  font-size: 13px;
  font-weight: 600;
  color: #1d4ed8;
  background: #eff6ff;
  padding: 3px 10px;
  border-radius: 6px;
}
.meta-badge { font-size: 12px; color: #475569; background: #e2e8f0; padding: 3px 10px; border-radius: 999px; }
.head-actions { display: flex; align-items: center; gap: 10px; }

.rule-strip {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  background: #ffffff;
  border-radius: 12px;
  padding: 14px 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.rs-item { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.rs-item:hover .rs-v { color: #2563eb; }
.rs-k { font-size: 12.5px; color: #94a3b8; }
.rs-v { font-size: 13.5px; font-weight: 500; color: #1e293b; }
.rs-divider { width: 1px; height: 18px; background: #e2e8f0; }

.upload-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.drop-card {
  display: block;
  border: 1.5px dashed #cbd5e1;
  border-radius: 12px;
  padding: 18px 20px;
  background: #f8fafc;
  cursor: pointer;
  transition: all 0.15s;
}
.drop-card:hover { border-color: #2563eb; background: #f0f6ff; }
.drop-card.filled { border-style: solid; border-color: #93c5fd; background: #eff6ff; }
.hidden-input { display: none; }
.drop-top { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.drop-badge { font-size: 11px; font-weight: 700; color: #2563eb; background: #dbeafe; padding: 2px 7px; border-radius: 6px; }
.drop-title { font-size: 14px; font-weight: 600; color: #0f172a; margin-right: auto; }
.drop-body { text-align: center; padding: 10px 0 4px; }
.drop-placeholder { font-size: 14px; font-weight: 500; color: #334155; }
.file-picked { font-size: 14px; font-weight: 600; color: #1d4ed8; word-break: break-all; }
.drop-sub { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.upload-footer { display: flex; align-items: center; gap: 16px; margin-top: 18px; }
.warn-tip { font-size: 13px; color: #b45309; }
.ratio-setup-card { border: 1.5px solid #93c5fd; background: #ffffff; }
.method-table-wrap { overflow-x: auto; }
.method-table {
  width: 100%;
  border-collapse: collapse;
  text-align: center;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  overflow: hidden;
}
.method-table th,
.method-table td {
  border: 1px solid #dbe2ec;
  padding: 12px 10px;
  vertical-align: middle;
}
.mt-side {
  width: 148px;
  background: #f8fafc;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}
.mt-group-daily {
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 14px;
  font-weight: 700;
}
.mt-group-final {
  width: 160px;
  background: #f0fdf4;
  color: #047857;
  font-size: 14px;
  font-weight: 700;
}
.mt-sub {
  background: #f8fafc;
  color: #334155;
  font-size: 13.5px;
  font-weight: 600;
}
.mt-row-lbl {
  background: #f8fafc;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  line-height: 1.4;
}
.mt-row-lbl span {
  font-size: 11.5px;
  font-weight: 400;
  color: #94a3b8;
}
.mt-cell { background: #ffffff; }
.mt-daily-total { background: #f8fbff; }
.mt-final-total { background: #f6fef9; }
.mt-dash { color: #cbd5e1; font-size: 15px; }

.method-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 16px;
}
.mb-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.mb-lbl { font-size: 13px; font-weight: 600; color: #334155; }
.mb-preview {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12.5px;
  color: #64748b;
  margin-left: 8px;
}
.mb-chip {
  background: #f1f5f9;
  color: #334155;
  padding: 2px 9px;
  border-radius: 6px;
}
.actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sec-title { font-size: 14px; font-weight: 600; color: #0f172a; margin-bottom: 10px; }
</style>
