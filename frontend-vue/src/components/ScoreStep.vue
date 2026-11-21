<template>
  <div>
    <!-- 上传与一键示例加载 -->
    <div class="panel-card" style="max-width: 960px; margin: 0 auto 18px">
      <div class="panel-title">
        <div>
          <el-tag size="small" effect="plain" style="margin-right: 8px">第 5 步 / 共 6 步</el-tag>
          <span>下载模板并上传平时与期末成绩表</span>
        </div>
        <div class="actions">
          <el-button size="small" plain @click="downloadDailyTpl">下载平时模板</el-button>
          <el-button size="small" plain @click="downloadFinalTpl">下载期末模板</el-button>
          <el-button type="warning" plain size="small" :loading="parsing" @click="loadSample">
            <el-icon><MagicStick /></el-icon>&nbsp;一键加载 44 人真实示例数据
          </el-button>
          <el-button v-if="dailyMeta || finalMeta" size="small" plain @click="mappingDrawer = true">
            调整列映射
          </el-button>
        </div>
      </div>

      <el-row :gutter="16" align="middle">
        <el-col :xs="24" :sm="9">
          <div class="upload-box">
            <div class="upload-label">平时成绩表（.xlsx）</div>
            <input type="file" accept=".xlsx" @change="(e) => (dailyFile = e.target.files[0])" />
            <div class="upload-tip">支持合并标题行、别名列名、末尾统计行自动过滤</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="9">
          <div class="upload-box">
            <div class="upload-label">期末小题成绩表（.xlsx）</div>
            <input type="file" accept=".xlsx" @change="(e) => (finalFile = e.target.files[0])" />
            <div class="upload-tip">按“第 N 题”前缀自动定位每道小题得分列</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="6">
          <el-button
            type="primary"
            size="large"
            style="width: 100%"
            :loading="parsing"
            @click="parseUploadedFiles()"
          >
            解析并预览成绩
          </el-button>
        </el-col>
      </el-row>
    </div>

    <!-- 在线可视化成绩增删查改与标红纠错表格 -->
    <div v-if="students.length > 0" class="panel-card">
      <div class="panel-title">
        <div class="actions">
          <span>② 全班学生成绩在线预览与纠错（共 {{ students.length }} 人）</span>
          <el-tag v-if="liveErrorCount === 0" type="success" effect="dark">
            数据校验全部通过，可直接计算
          </el-tag>
          <el-tag v-else type="danger" effect="dark">
            发现 {{ liveErrorCount }} 处异常待修正（红框单元格可直接修改）
          </el-tag>
        </div>
        <div class="actions">
          <el-input
            v-model="keyword"
            placeholder="搜索学号或姓名"
            size="small"
            clearable
            style="width: 170px"
          />
          <el-switch
            v-model="onlyErrors"
            active-text="仅看异常行"
            size="small"
          />
          <el-button size="small" type="primary" plain @click="addStudent">
            + 新增学生
          </el-button>
          <el-button
            type="success"
            :disabled="liveErrorCount > 0"
            :loading="calculating"
            @click="confirmAndCalculate"
          >
            确认无误并计算达成度 →
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="extraFinalStudents.length > 0"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom: 12px"
        :title="`提示：期末成绩表中有 ${extraFinalStudents.length} 名学生不在平时成绩表中（如重修/插班生：${extraFinalStudents.slice(0, 3).map(x => x['姓名'] || x['学号']).join('、')}），已自动忽略。`"
      />

      <el-table
        :data="filteredStudents"
        border
        stripe
        size="small"
        max-height="520"
        class="tabular-nums"
      >
        <el-table-column type="index" label="#" width="48" fixed align="center" />
        <el-table-column label="学号" width="135" fixed>
          <template #default="{ row }">
            <el-input v-model="row['学号']" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="姓名" width="95" fixed>
          <template #default="{ row }">
            <el-input v-model="row['姓名']" size="small" />
          </template>
        </el-table-column>

        <!-- 平时环节列 -->
        <el-table-column
          v-for="link in dailyLinks"
          :key="'d-' + link"
          :label="`平时-${link}`"
          width="105"
          align="center"
        >
          <template #default="{ row }">
            <el-tooltip
              :disabled="!dailyCellError(row, link)"
              :content="dailyCellError(row, link)"
              placement="top"
            >
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

        <!-- 期末小题列 -->
        <el-table-column
          v-for="q in flatQuestions"
          :key="'q-' + q['题号']"
          :label="`第${q['题号']}题(${q['满分']}分)`"
          width="105"
          align="center"
        >
          <template #default="{ row }">
            <el-tooltip
              :disabled="!finalCellError(row, q)"
              :content="finalCellError(row, q)"
              placement="top"
            >
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

        <!-- 状态与操作 -->
        <el-table-column label="操作" width="145" fixed="right" align="center">
          <template #default="{ row }">
            <el-button
              v-if="hasMissingFinal(row)"
              link
              type="warning"
              size="small"
              @click="fillZeroFinal(row)"
            >
              期末补0
            </el-button>
            <el-button link type="danger" size="small" @click="deleteStudent(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else class="panel-card">
      <el-empty description="请上传平时与期末成绩 Excel，或点击右上角「一键加载 44 人真实示例数据」体验在线纠错表格" />
    </div>

    <!-- 列映射确认抽屉 -->
    <el-drawer v-model="mappingDrawer" title="Excel 列映射确认" size="520px">
      <div v-if="dailyMeta">
        <h4>平时成绩表（表头位于第 {{ dailyMeta.header_row }} 行）</h4>
        <el-form label-width="110px" size="small">
          <el-form-item
            v-for="field in ['学号', '姓名', ...dailyLinks]"
            :key="field"
            :label="field"
          >
            <el-select v-model="customDailyMap[field]" style="width: 100%" placeholder="请选择对应列">
              <el-option
                v-for="(h, idx) in dailyMeta.headers"
                :key="idx"
                :label="`第 ${idx + 1} 列：${h}`"
                :value="idx"
              />
            </el-select>
          </el-form-item>
        </el-form>
      </div>
      <el-divider />
      <div v-if="finalMeta">
        <h4>期末成绩表（表头位于第 {{ finalMeta.header_row }} 行）</h4>
        <p class="panel-sub">
          已识别 {{ Object.keys(finalMeta.question_mapping || {}).length }} / {{ flatQuestions.length }} 道小题列
        </p>
      </div>
      <el-button
        v-if="dailyFile && finalFile"
        type="primary"
        style="width: 100%; margin-top: 12px"
        @click="reparseWithMapping"
      >
        应用列映射并重新解析
      </el-button>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, downloadBlob } from '../api/client'

const props = defineProps({
  cfg: { type: Object, required: true },
  initialStudents: { type: Array, default: () => [] },
})
const emit = defineEmits(['calculated', 'roster-updated'])

const dailyFile = ref(null)
const finalFile = ref(null)
const parsing = ref(false)
const calculating = ref(false)
const students = ref([])
const extraFinalStudents = ref([])
const dailyMeta = ref(null)
const finalMeta = ref(null)
const mappingDrawer = ref(false)
const customDailyMap = reactive({})
const keyword = ref('')
const onlyErrors = ref(false)

watch(
  () => props.initialStudents,
  (val) => {
    if (val && val.length > 0) {
      students.value = JSON.parse(JSON.stringify(val))
    }
  },
  { immediate: true }
)

const dailyLinks = computed(() => Object.keys(props.cfg.method['平时环节']))
const flatQuestions = computed(() => props.cfg.paper.flatMap((g) => g['小题']))

function isValidNumber(v) {
  return v !== null && v !== undefined && v !== '' && !Number.isNaN(Number(v))
}

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

const liveErrorCount = computed(() =>
  students.value.reduce((acc, s) => acc + rowErrorCount(s), 0)
)

const filteredStudents = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return students.value.filter((s) => {
    if (onlyErrors.value && rowErrorCount(s) === 0) return false
    if (!kw) return true
    return (
      String(s['学号'] || '').toLowerCase().includes(kw) ||
      String(s['姓名'] || '').toLowerCase().includes(kw)
    )
  })
})

function applyParsedResult(res) {
  dailyMeta.value = res.daily_meta
  finalMeta.value = res.final_meta
  extraFinalStudents.value = res.extra_final_students || []
  Object.assign(customDailyMap, res.daily_meta?.mapping || {})

  if (res.need_mapping) {
    mappingDrawer.value = true
    ElMessage.warning('部分列名未自动识别，请在右侧抽屉手动确认列映射')
    return
  }

  // 统一把期末键标准化为数字键，方便 v-model 双向绑定
  students.value = (res.students || []).map((s) => {
    const f = {}
    for (const q of flatQuestions.value) {
      const qn = q['题号']
      f[qn] = s['期末']?.[qn] ?? s['期末']?.[String(qn)] ?? null
    }
    return {
      学号: s['学号'],
      姓名: s['姓名'],
      平时: { ...s['平时'] },
      期末: f,
    }
  })
  emit('roster-updated', students.value.length)
  if (liveErrorCount.value === 0) {
    ElMessage.success(`解析完成：共 ${students.value.length} 名学生，全部校验通过`)
  } else {
    ElMessage.warning(`解析完成：共 ${students.value.length} 人，发现 ${liveErrorCount.value} 处异常，请直接在红框单元格修正`)
  }
}

async function parseUploadedFiles(dMap = null) {
  if (!dailyFile.value || !finalFile.value) {
    ElMessage.warning('请先选择平时成绩表和期末小题成绩表')
    return
  }
  parsing.value = true
  try {
    const res = await api.parseFiles(dailyFile.value, finalFile.value, props.cfg.course_id, dMap)
    applyParsedResult(res)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    parsing.value = false
  }
}

async function reparseWithMapping() {
  mappingDrawer.value = false
  await parseUploadedFiles(customDailyMap)
}

async function downloadDailyTpl() {
  try {
    const q = props.cfg.course_id ? `?course_id=${props.cfg.course_id}` : ''
    await downloadBlob(`/api/template/daily${q}`, '平时成绩录入模板.xlsx')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function downloadFinalTpl() {
  try {
    const q = props.cfg.course_id ? `?course_id=${props.cfg.course_id}` : ''
    await downloadBlob(`/api/template/final${q}`, '期末小题成绩录入模板.xlsx')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadSample() {
  parsing.value = true
  try {
    const res = await api.parseSample(props.cfg.course_id)
    applyParsedResult(res)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    parsing.value = false
  }
}

function addStudent() {
  const daily = {}
  for (const l of dailyLinks.value) daily[l] = 80
  const final = {}
  for (const q of flatQuestions.value) final[q['题号']] = 0
  students.value.unshift({
    学号: `NEW${String(students.value.length + 1).padStart(3, '0')}`,
    姓名: '新增学生',
    平时: daily,
    期末: final,
  })
}

function deleteStudent(row) {
  const idx = students.value.indexOf(row)
  if (idx >= 0) students.value.splice(idx, 1)
}

function fillZeroFinal(row) {
  for (const q of flatQuestions.value) {
    if (!isValidNumber(row['期末'][q['题号']])) {
      row['期末'][q['题号']] = 0
    }
  }
  ElMessage.success(`已为 ${row['姓名']} 补填期末缺考项为 0 分`)
}

async function confirmAndCalculate() {
  calculating.value = true
  try {
    const res = await api.calculateRecords({
      course_id: props.cfg.course_id,
      students: students.value,
      threshold: props.cfg.threshold,
      meta: props.cfg.meta,
      save_report: true,
    })
    ElMessage.success('达成度计算完成，并已自动保存至历史报告')
    emit('calculated', res)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    calculating.value = false
  }
}
</script>

<style scoped>
.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.upload-box {
  border: 1.5px dashed #cbd5e1;
  border-radius: 10px;
  padding: 14px 16px;
  background: #f8fafc;
}

.upload-label {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #1e293b;
}

.upload-tip {
  font-size: 12px;
  color: #64748b;
  margin-top: 6px;
}

.cell-input {
  width: 72px;
  padding: 4px 6px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  text-align: center;
  font-size: 13px;
  outline: none;
  background: #fff;
}

.cell-input:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}
</style>
