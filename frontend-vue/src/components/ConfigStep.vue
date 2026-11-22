<template>
  <div v-if="cfg" class="wizard-center">
    <!-- ==================== 第 1 步：选课程与班级 ==================== -->
    <div v-if="currentStep === 0" class="wizard-card">
      <div class="w-head">
        <span class="w-badge">第 1 步 / 共 6 步</span>
        <h2>确定本次要分析的课程与班级</h2>
        <p>你可以直接选用学院发布的公共课程模板（免去重复配规则），或直接修改下方课程与班级信息。</p>
      </div>

      <!-- 公共模板快捷选用条 -->
      <div v-if="publicTemplates.length > 0" class="pub-box">
        <div class="pub-label">学院公共课程模板（点击一键套用规则）：</div>
        <div class="pub-chips">
          <div
            v-for="tpl in publicTemplates"
            :key="tpl.id"
            class="pub-chip"
            :class="{ active: tpl.id === cfg.course_id }"
            @click="applyPublicTpl(tpl.id)"
          >
            <strong>{{ tpl.course_name }}</strong>
            <span>{{ tpl.semester }}</span>
            <el-tag :type="tpl.has_paper ? 'success' : 'warning'" size="small" effect="plain">
              {{ tpl.has_paper ? '含试卷' : '仅大纲' }}
            </el-tag>
          </div>
        </div>
      </div>

      <el-row :gutter="20" style="margin-top: 18px">
        <el-col :xs="24" :sm="12">
          <div class="field-label">课程名称</div>
          <el-input v-model="cfg.meta['课程名称']" size="large" placeholder="如：高等数学A（II）" />
        </el-col>
        <el-col :xs="24" :sm="12">
          <div class="field-label">开课学期</div>
          <el-input v-model="cfg.meta['学期']" size="large" placeholder="如：2023-2024-2" />
        </el-col>
      </el-row>

      <el-row :gutter="20" style="margin-top: 16px">
        <el-col :xs="24" :sm="12">
          <div class="field-label">本次分析的教学班级</div>
          <el-input v-model="cfg.meta['班级']" size="large" placeholder="如：23智能制造1班" />
        </el-col>
        <el-col :xs="24" :sm="12">
          <div class="field-label">课程目标达标合格线（0.65 即 65%）</div>
          <el-input-number
            v-model="cfg.threshold"
            :controls="false"
            size="large"
            :min="0.1"
            :max="1"
            :precision="2"
            style="width: 100%"
          />
        </el-col>
      </el-row>

      <!-- 选填：学校《目标达成评价表》扩展信息（默认收起，保持页面清爽） -->
      <div style="margin-top: 14px">
        <el-button link type="primary" size="small" @click="showExtMeta = !showExtMeta">
          {{ showExtMeta ? '收起评价表扩展信息 ▲' : '展开填写任课教师 / 课程代码 / 类别 / 学分 / 学时（用于导出封面表） ▼' }}
        </el-button>
        <el-row v-if="showExtMeta" :gutter="14" style="margin-top: 10px">
          <el-col :xs="12" :sm="6">
            <div class="field-label">任课教师</div>
            <el-input v-model="cfg.meta['任课教师']" placeholder="如：张老师" />
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="field-label">课程代码</div>
            <el-input v-model="cfg.meta['课程代码']" placeholder="如：1230601002F" />
          </el-col>
          <el-col :xs="12" :sm="4">
            <div class="field-label">课程类别</div>
            <el-input v-model="cfg.meta['课程类别']" placeholder="基础课" />
          </el-col>
          <el-col :xs="12" :sm="4">
            <div class="field-label">学分</div>
            <el-input-number v-model="cfg.meta['学分']" :controls="false" :precision="1" style="width: 100%" />
          </el-col>
          <el-col :xs="12" :sm="4">
            <div class="field-label">授课学时</div>
            <el-input-number v-model="cfg.meta['授课学时']" :controls="false" style="width: 100%" />
          </el-col>
        </el-row>
      </div>

      <div class="w-footer">
        <el-button
          v-if="configReady"
          type="success"
          plain
          size="large"
          @click="saveAndJumpUpload"
        >
          规则已齐全，跳过配置直接去传成绩 →
        </el-button>
        <div style="margin-left: auto">
          <el-button type="primary" size="large" @click="$emit('go-step', 1)">
            下一步：设置平时与期末占比 →
          </el-button>
        </div>
      </div>
    </div>

    <!-- ==================== 第 2 步：定平时与期末占比 ==================== -->
    <div v-else-if="currentStep === 1" class="wizard-card">
      <div class="w-head">
        <span class="w-badge">第 2 步 / 共 6 步</span>
        <h2>设置平时成绩与期末考试的占比</h2>
        <p>按照教学大纲填写总成绩的构成比例。平时环节可自由增删（不考测验可直接删掉）。</p>
      </div>

      <div class="ratio-pair">
        <div class="ratio-box">
          <div class="field-label">平时成绩总占比</div>
          <el-input-number
            v-model="cfg.method['平时占比']"
            :controls="false"
            size="large"
            :min="0"
            :max="1"
            :precision="2"
            style="width: 100%"
          />
        </div>
        <div class="ratio-box">
          <div class="field-label">期末考试总占比</div>
          <el-input-number
            v-model="cfg.method['期末占比']"
            :controls="false"
            size="large"
            :min="0"
            :max="1"
            :precision="2"
            style="width: 100%"
          />
        </div>
      </div>

      <div class="sub-head" style="margin-top: 22px">
        <span>平时成绩细项构成（以下各项相加须等于 1.00）</span>
        <el-tag :type="dailySumOk ? 'success' : 'danger'" size="small">
          当前合计：{{ dailySum.toFixed(2) }}
        </el-tag>
      </div>

      <div v-for="row in dailyRows" :key="row.name" class="clean-row">
        <el-input
          :model-value="row.name"
          size="default"
          style="flex: 1"
          @change="(val) => renameDaily(row.name, val)"
        />
        <el-input-number
          :model-value="row.ratio"
          :controls="false"
          size="default"
          :min="0"
          :max="1"
          :precision="2"
          style="width: 110px"
          @change="(val) => (cfg.method['平时环节'][row.name] = val ?? 0)"
        />
        <el-button
          link
          type="danger"
          :disabled="dailyRows.length <= 1"
          @click="removeDaily(row.name)"
        >
          删除
        </el-button>
      </div>

      <div class="inline-add" style="margin-top: 12px">
        <el-input
          v-model="newLinkName"
          placeholder="输入新环节名称，如：实验"
          style="width: 220px"
          @keyup.enter="addDaily"
        />
        <el-button plain @click="addDaily">+ 添加平时环节</el-button>
      </div>

      <!-- 一句大白话实时换算结果 -->
      <div class="plain-summary tabular-nums">
        按当前设置，全课程 100 分折算为：
        <span v-for="l in allLinks" :key="l" class="sum-chip">
          {{ l }} <b>{{ ((linkWeights[l] || 0) * 100).toFixed(1) }}</b> 分
        </span>
      </div>

      <div class="w-footer">
        <el-button size="large" @click="$emit('go-step', 0)">← 上一步</el-button>
        <el-button
          type="primary"
          size="large"
          :disabled="!totalRatioOk || !dailySumOk"
          @click="$emit('go-step', 2)"
        >
          下一步：分配课程目标权重 →
        </el-button>
      </div>
    </div>

    <!-- ==================== 第 3 步：配课程目标权重 ==================== -->
    <div v-else-if="currentStep === 2" class="wizard-card">
      <div class="w-head">
        <span class="w-badge">第 3 步 / 共 6 步</span>
        <h2>填写各课程目标的支撑比例</h2>
        <p>照教学大纲填入各目标在每个环节的相对比例（同一列不必相加为 1，系统会自动按列换算为理论满分）。</p>
      </div>

      <div class="sub-head">
        <span>课程目标 × 考核环节矩阵</span>
        <div class="inline-add">
          <el-input
            v-model="newTargetName"
            placeholder="新目标名，如：课程目标3"
            size="small"
            style="width: 150px"
            @keyup.enter="addTarget"
          />
          <el-button size="small" plain @click="addTarget">+ 添加课程目标</el-button>
        </div>
      </div>

      <el-table :data="targetList" border class="tabular-nums">
        <el-table-column label="课程目标" width="120">
          <template #default="{ row }"><strong>{{ row }}</strong></template>
        </el-table-column>
        <el-table-column
          v-for="link in allLinks"
          :key="link"
          :label="link"
          align="center"
        >
          <template #default="{ row }">
            <el-input-number
              v-model="cfg.matrix[row][link]"
              :controls="false"
              size="small"
              :min="0"
              :precision="2"
              style="width: 78px"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ row }">
            <el-button
              link
              type="danger"
              size="small"
              :disabled="targetList.length <= 1"
              @click="removeTarget(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        v-if="hasZeroCol"
        type="error"
        show-icon
        :closable="false"
        title="存在整列全为 0 的有效考核环节，请至少为一个课程目标填写大于 0 的比例"
        style="margin-top: 14px"
      />

      <!-- 简洁大字结论卡片（默认不塞满细节表格） -->
      <div class="result-chips tabular-nums">
        <div v-for="t in targetList" :key="t" class="target-full-card">
          <div class="tf-name">{{ t }} · 理论满分</div>
          <div class="tf-val">{{ targetFullMap[t].toFixed(2) }} <span>分</span></div>
        </div>
      </div>

      <div style="margin-top: 10px">
        <el-button link type="primary" @click="showDetailWeights = !showDetailWeights">
          {{ showDetailWeights ? '收起各环节详细产出权重 ▲' : '展开查看各环节详细产出权重 ▼' }}
        </el-button>
        <el-table
          v-if="showDetailWeights"
          :data="outputPreviewRows"
          border
          size="small"
          class="tabular-nums"
          style="margin-top: 8px"
        >
          <el-table-column prop="label" label="项目" width="110" />
          <el-table-column v-for="link in allLinks" :key="link" :prop="link" :label="link" align="center" />
          <el-table-column prop="full" label="理论满分" width="100" align="center">
            <template #default="{ row }"><strong>{{ row.full }} 分</strong></template>
          </el-table-column>
        </el-table>
      </div>

      <div class="w-footer">
        <el-button size="large" @click="$emit('go-step', 1)">← 上一步</el-button>
        <el-button type="primary" size="large" :disabled="hasZeroCol" @click="$emit('go-step', 3)">
          下一步：配置期末试卷题目 →
        </el-button>
      </div>
    </div>

    <!-- ==================== 第 4 步：配期末试卷结构 ==================== -->
    <div v-else-if="currentStep === 3" class="wizard-card">
      <div class="w-head">
        <span class="w-badge">第 4 步 / 共 6 步</span>
        <h2>配置期末试卷的大题与小题</h2>
        <p>只需配置每道小题的满分与归属目标（凑满 100 分即可）。点击任意大题可展开编辑小题。</p>
      </div>

      <div class="paper-status-bar tabular-nums">
        <div class="ps-top">
          <span>
            共 <b>{{ flatQuestions.length }}</b> 道小题 · 当前总分
            <b :style="{ color: paperTotal === 100 ? '#059669' : '#dc2626' }">{{ paperTotal }}</b> / 100 分
          </span>
          <div class="actions">
            <el-tag v-for="t in targetList" :key="t" size="small" effect="plain">
              {{ t }} 卷面 {{ paperTargetFull[t] || 0 }} 分
            </el-tag>
            <el-button size="small" plain @click="downloadMyPaperTpl">下载4列试卷模板</el-button>
            <input
              ref="paperFileRef"
              type="file"
              accept=".xlsx"
              style="display: none"
              @change="uploadMyPaperExcel"
            />
            <el-button size="small" type="success" plain @click="paperFileRef?.click()">
              上传试卷模板导入
            </el-button>
            <el-button size="small" type="primary" plain @click="addGroup">+ 添加大题</el-button>
          </div>
        </div>
        <el-progress
          :percentage="Math.min(100, paperTotal)"
          :status="paperTotal === 100 ? 'success' : paperTotal > 100 ? 'exception' : ''"
          :show-text="false"
          :stroke-width="6"
          style="margin-top: 8px"
        />
      </div>

      <el-collapse v-model="expandedGroups" style="margin-top: 14px">
        <el-collapse-item v-for="(grp, gi) in cfg.paper" :key="gi" :name="gi">
          <template #title>
            <div class="collapse-head" @click.stop>
              <el-input v-model="grp['大题']" size="small" style="width: 170px" />
              <span class="group-stat tabular-nums">
                {{ grp['小题'].length }} 题 · 共 {{ groupTotal(grp) }} 分
              </span>
              <div class="actions" style="margin-left: auto; margin-right: 12px">
                <el-popover placement="bottom" :width="260" trigger="click">
                  <template #reference>
                    <el-button size="small" type="primary" plain>+ 批量加题</el-button>
                  </template>
                  <el-form label-width="68px" size="small">
                    <el-form-item label="题数">
                      <el-input-number v-model="batch.count" :min="1" :max="30" />
                    </el-form-item>
                    <el-form-item label="每题分">
                      <el-input-number v-model="batch.score" :min="0.5" :max="50" :step="0.5" />
                    </el-form-item>
                    <el-form-item label="目标">
                      <el-select v-model="batch.target" style="width: 100%">
                        <el-option v-for="t in targetList" :key="t" :label="t" :value="t" />
                      </el-select>
                    </el-form-item>
                    <el-button type="primary" size="small" style="width: 100%" @click="batchAddQ(gi)">
                      确认添加
                    </el-button>
                  </el-form>
                </el-popover>
                <el-button size="small" plain @click="addSingleQ(gi)">+ 单题</el-button>
                <el-button size="small" link type="danger" @click="removeGroup(gi)">删除</el-button>
              </div>
            </div>
          </template>

          <el-table :data="grp['小题']" size="small" class="tabular-nums">
            <el-table-column label="题号" width="90" align="center">
              <template #default="{ row }">第 {{ row['题号'] }} 题</template>
            </el-table-column>
            <el-table-column label="满分(分)" width="130" align="center">
              <template #default="{ row }">
                <el-input-number
                  v-model="row['满分']"
                  :controls="false"
                  size="small"
                  :min="0.5"
                  :max="100"
                  style="width: 80px"
                />
              </template>
            </el-table-column>
            <el-table-column label="归属课程目标">
              <template #default="{ row }">
                <el-select v-model="row['目标']" size="small" style="width: 160px">
                  <el-option v-for="t in targetList" :key="t" :label="t" :value="t" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="70" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="removeQ(gi, $index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>

      <div class="w-footer">
        <el-button size="large" @click="$emit('go-step', 2)">← 上一步</el-button>
        <el-button
          type="primary"
          size="large"
          :loading="saving"
          :disabled="paperTotal !== 100"
          @click="saveAndJumpUpload"
        >
          保存配置，下一步：上传成绩 →
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const props = defineProps({
  cfg: { type: Object, required: true },
  currentStep: { type: Number, default: 0 },
})
const emit = defineEmits(['saved', 'go-step', 'reload-config'])

const saving = ref(false)
const newLinkName = ref('')
const newTargetName = ref('')
const showDetailWeights = ref(false)
const showExtMeta = ref(false)
const paperFileRef = ref(null)
const expandedGroups = ref([]) // 默认全部收起大题，极致清爽！
const publicTemplates = ref([])
const batch = reactive({ count: 5, score: 3, target: '' })

const dailyRows = computed(() =>
  Object.entries(props.cfg.method['平时环节']).map(([name, ratio]) => ({ name, ratio }))
)
const allLinks = computed(() => [...Object.keys(props.cfg.method['平时环节']), '期末考试'])
const targetList = computed(() => Object.keys(props.cfg.matrix))
const dailySum = computed(() =>
  Object.values(props.cfg.method['平时环节']).reduce((a, b) => a + (Number(b) || 0), 0)
)
const dailySumOk = computed(() => Math.abs(dailySum.value - 1) < 1e-6)
const totalRatioOk = computed(
  () => Math.abs((props.cfg.method['平时占比'] || 0) + (props.cfg.method['期末占比'] || 0) - 1) < 1e-6
)

const linkWeights = computed(() => {
  const w = {}
  for (const [k, r] of Object.entries(props.cfg.method['平时环节'])) {
    w[k] = (props.cfg.method['平时占比'] || 0) * (r || 0)
  }
  w['期末考试'] = props.cfg.method['期末占比'] || 0
  return w
})

const hasZeroCol = computed(() =>
  allLinks.value.some((l) => {
    if ((linkWeights.value[l] || 0) <= 0) return false
    const s = targetList.value.reduce((acc, t) => acc + (props.cfg.matrix[t][l] || 0), 0)
    return s <= 0
  })
)

const targetFullMap = computed(() => {
  const m = {}
  for (const t of targetList.value) {
    let sum = 0
    for (const l of allLinks.value) {
      const colSum = targetList.value.reduce((acc, tg) => acc + (props.cfg.matrix[tg][l] || 0), 0)
      const val = colSum > 0 ? ((linkWeights.value[l] || 0) * (props.cfg.matrix[t][l] || 0)) / colSum : 0
      sum += val * 100
    }
    m[t] = sum
  }
  return m
})

const outputPreviewRows = computed(() => {
  const rows = []
  const wRow = { label: '环节总分', full: '100.00' }
  for (const l of allLinks.value) wRow[l] = `${((linkWeights.value[l] || 0) * 100).toFixed(2)}分`
  rows.push(wRow)
  for (const t of targetList.value) {
    const r = { label: t, full: targetFullMap.value[t].toFixed(2) }
    for (const l of allLinks.value) {
      const colSum = targetList.value.reduce((acc, tg) => acc + (props.cfg.matrix[tg][l] || 0), 0)
      const val = colSum > 0 ? ((linkWeights.value[l] || 0) * (props.cfg.matrix[t][l] || 0)) / colSum : 0
      r[l] = `${(val * 100).toFixed(2)}分`
    }
    rows.push(r)
  }
  return rows
})

const flatQuestions = computed(() => props.cfg.paper.flatMap((g) => g['小题']))
const paperTotal = computed(() =>
  flatQuestions.value.reduce((a, q) => a + (Number(q['满分']) || 0), 0)
)
const paperTargetFull = computed(() => {
  const m = {}
  for (const q of flatQuestions.value) {
    m[q['目标']] = (m[q['目标']] || 0) + (Number(q['满分']) || 0)
  }
  return m
})
const configReady = computed(
  () => totalRatioOk.value && dailySumOk.value && !hasZeroCol.value && paperTotal.value === 100
)

function groupTotal(grp) {
  return grp['小题'].reduce((a, q) => a + (Number(q['满分']) || 0), 0)
}

function renumberQuestions() {
  let seq = 1
  for (const g of props.cfg.paper) {
    for (const q of g['小题']) q['题号'] = seq++
  }
}

function renameDaily(oldName, newName) {
  const name = (newName || '').trim()
  if (!name || name === oldName || name in props.cfg.method['平时环节']) return
  const entries = Object.entries(props.cfg.method['平时环节']).map(([k, v]) =>
    k === oldName ? [name, v] : [k, v]
  )
  props.cfg.method['平时环节'] = Object.fromEntries(entries)
  for (const t of targetList.value) {
    props.cfg.matrix[t][name] = props.cfg.matrix[t][oldName] ?? 0
    delete props.cfg.matrix[t][oldName]
  }
}

function addDaily() {
  const name = newLinkName.value.trim()
  if (!name || name in props.cfg.method['平时环节']) return
  props.cfg.method['平时环节'][name] = 0
  for (const t of targetList.value) props.cfg.matrix[t][name] = 0.1
  newLinkName.value = ''
}

function removeDaily(name) {
  delete props.cfg.method['平时环节'][name]
  for (const t of targetList.value) delete props.cfg.matrix[t][name]
}

function addTarget() {
  const name = newTargetName.value.trim() || `课程目标${targetList.value.length + 1}`
  if (name in props.cfg.matrix) return
  const row = {}
  for (const l of allLinks.value) row[l] = l === '期末考试' ? 0 : 0.1
  props.cfg.matrix[name] = row
  newTargetName.value = ''
}

function removeTarget(name) {
  delete props.cfg.matrix[name]
  const fallback = targetList.value[0]
  for (const g of props.cfg.paper) {
    for (const q of g['小题']) {
      if (q['目标'] === name) q['目标'] = fallback
    }
  }
}

function addGroup() {
  props.cfg.paper.push({ 大题: `第${props.cfg.paper.length + 1}大题`, 小题: [] })
  expandedGroups.value = [props.cfg.paper.length - 1]
}

function removeGroup(gi) {
  props.cfg.paper.splice(gi, 1)
  renumberQuestions()
}

function addSingleQ(gi) {
  props.cfg.paper[gi]['小题'].push({ 题号: 0, 满分: 5, 目标: targetList.value[0] })
  renumberQuestions()
  if (!expandedGroups.value.includes(gi)) expandedGroups.value.push(gi)
}

function batchAddQ(gi) {
  const tg = batch.target || targetList.value[0]
  for (let i = 0; i < batch.count; i++) {
    props.cfg.paper[gi]['小题'].push({ 题号: 0, 满分: batch.score, 目标: tg })
  }
  renumberQuestions()
  if (!expandedGroups.value.includes(gi)) expandedGroups.value.push(gi)
  ElMessage.success(`已批量添加 ${batch.count} 道小题`)
}

function removeQ(gi, qi) {
  props.cfg.paper[gi]['小题'].splice(qi, 1)
  renumberQuestions()
}

async function saveAndJumpUpload() {
  renumberQuestions()
  saving.value = true
  try {
    const res = await api.saveConfig(props.cfg)
    ElMessage.success('配置已保存')
    emit('saved', res)
    emit('go-step', 4)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function downloadMyPaperTpl() {
  try {
    await api.downloadPaperTemplate(props.cfg.course_id, props.cfg.meta['课程名称'] || '课程')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function uploadMyPaperExcel(e) {
  const file = e.target.files?.[0]
  if (!file) return
  try {
    const res = await api.importPaperExcel(props.cfg.course_id, file)
    props.cfg.paper = res.paper
    ElMessage.success(res.message)
    if (res.cloned && res.course_id) emit('reload-config', res.course_id)
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    if (paperFileRef.value) paperFileRef.value.value = ''
  }
}

async function applyPublicTpl(id) {
  try {
    const res = await api.applyTemplate(id)
    ElMessage.success(res.message)
    const newId = res.config?.course_id || id
    emit('reload-config', newId)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  try {
    const res = await api.listPublicTemplates()
    publicTemplates.value = res.templates || []
  } catch {
    // ignore
  }
})
</script>

<style scoped>
.wizard-center {
  max-width: 820px;
  margin: 12px auto 0;
}

.wizard-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 30px 34px;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
}

.w-head {
  margin-bottom: 24px;
}

.w-badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  color: #2563eb;
  background: #eff6ff;
  padding: 3px 10px;
  border-radius: 999px;
  margin-bottom: 10px;
}

.w-head h2 {
  margin: 0 0 6px;
  font-size: 21px;
  font-weight: 700;
  color: #0f172a;
}

.w-head p {
  margin: 0;
  font-size: 14px;
  color: #64748b;
  line-height: 1.6;
}

.pub-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px 16px;
}

.pub-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 10px;
}

.pub-chips {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.pub-chip {
  padding: 8px 14px;
  border-radius: 10px;
  background: #ffffff;
  border: 1.5px solid #e2e8f0;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  transition: all 0.15s;
}

.pub-chip:hover {
  border-color: #93c5fd;
}

.pub-chip.active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.pub-chip span {
  font-size: 12px;
  color: #64748b;
}

.field-label {
  font-size: 13px;
  font-weight: 500;
  color: #334155;
  margin-bottom: 8px;
}

.ratio-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.ratio-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px 16px;
}

.sub-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 12px;
}

.clean-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.inline-add {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plain-summary {
  margin-top: 22px;
  padding: 14px 16px;
  border-radius: 10px;
  background: #eff6ff;
  color: #1e3a8a;
  font-size: 13px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.sum-chip {
  background: #ffffff;
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid #bfdbfe;
}

.result-chips {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.target-full-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px 18px;
}

.tf-name {
  font-size: 13px;
  color: #64748b;
}

.tf-val {
  font-size: 26px;
  font-weight: 700;
  color: #1d4ed8;
  margin-top: 4px;
}

.tf-val span {
  font-size: 13px;
  font-weight: 400;
  color: #64748b;
}

.paper-status-bar {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px 16px;
}

.ps-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 14px;
}

.collapse-head {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.group-stat {
  font-size: 13px;
  color: #64748b;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.w-footer {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
</style>
