<template>
  <div v-if="task && rep">
    <div class="page-header">
      <div>
        <h1>{{ task.course_name }} · {{ task.class_name }}</h1>
        <p class="subtitle tabular-nums">
          学期 {{ task.semester }} · 有效样本 {{ task.student_count }} 人 · 合格基准 {{ (task.pass_threshold * 100).toFixed(0) }}%
        </p>
      </div>
      <div class="actions">
        <el-button size="large" @click="$emit('back')">← 修改成绩</el-button>
        <el-button type="primary" size="large" :loading="exporting" @click="exportBundle">
          <el-icon><Download /></el-icon>&nbsp;一键导出归档包（含 2 份表）
        </el-button>
      </div>
    </div>

    <!-- 一、核心 KPI 指标卡片 -->
    <div class="kpi-grid tabular-nums">
      <div v-for="(info, target) in rep.report" :key="target" class="kpi-card">
        <div class="kpi-head">
          <span class="kpi-label">{{ target }}</span>
          <span class="status-pill" :class="info['是否达标'] ? 'ok' : 'err'">
            <span class="dot"></span>{{ info['是否达标'] ? '已达标' : '未达标' }}
          </span>
        </div>
        <div class="kpi-value" :style="{ color: info['是否达标'] ? '#059669' : '#dc2626' }">
          {{ (info['达成度'] * 100).toFixed(1) }}%
        </div>
        <el-progress
          :percentage="Math.min(100, Number((info['达成度'] * 100).toFixed(1)))"
          :status="info['是否达标'] ? 'success' : 'exception'"
          :show-text="false"
          :stroke-width="6"
        />
        <div class="kpi-meta">
          实得 <b>{{ info['实得'].toFixed(2) }}</b> / {{ info['理论满分'].toFixed(2) }} 分
          （平时 {{ sumDaily(info).toFixed(2) }} · 期末 {{ info['期末'].toFixed(2) }}）
        </div>
      </div>
    </div>

    <!-- 二、双图可视化 -->
    <el-row :gutter="20">
      <el-col :xs="24" :lg="12">
        <div class="panel-card">
          <div class="panel-title">
            <span>课程目标达成度对比</span>
            <el-button link type="primary" size="small" @click="saveChartPng(barChart, '课程目标达成度对比图.png')">
              保存图片
            </el-button>
          </div>
          <div ref="barRef" style="height: 290px; width: 100%"></div>
        </div>
      </el-col>
      <el-col :xs="24" :lg="12">
        <div class="panel-card">
          <div class="panel-title">
            <span>各考核环节得分率</span>
            <el-button link type="primary" size="small" @click="saveChartPng(linkChart, '考核环节得分率对比图.png')">
              保存图片
            </el-button>
          </div>
          <div ref="linkRef" style="height: 290px; width: 100%"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 三、OBE 智能诊断与持续改进 -->
    <div class="panel-card">
      <div class="panel-title">
        <span>OBE 教学诊断与持续改进</span>
        <el-button type="primary" plain size="small" :loading="savingNotes" @click="saveNotes">
          保存全部三段分析文本
        </el-button>
      </div>

      <div v-if="diagData" class="diag-grid">
        <div class="diag-box">
          <h4>期末得分率最低 Top 5 试题</h4>
          <el-table :data="diagData.hard_questions" size="small" class="tabular-nums">
            <el-table-column label="题号" width="76" align="center">
              <template #default="{ row }">第{{ row['题号'] }}题</template>
            </el-table-column>
            <el-table-column prop="所属目标" label="归属目标" width="96" align="center" />
            <el-table-column label="均分 / 满分" align="center">
              <template #default="{ row }">{{ row['全班均分'] }} / {{ row['满分'] }}</template>
            </el-table-column>
            <el-table-column label="得分率" width="84" align="center">
              <template #default="{ row }">
                <span style="color: #dc2626; font-weight: 600">{{ (row['得分率'] * 100).toFixed(1) }}%</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="diag-box">
          <h4>学情分布与反差预警</h4>
          <div class="contrast-alert">
            平时 ≥ 80 分但期末 &lt; 60 分的反差学生：
            <strong>{{ diagData.distribution['平时高期末低反差人数'] }} 人</strong>
          </div>
          <div v-for="(dist, tg) in diagData.distribution['各目标分布']" :key="tg" class="dist-line tabular-nums">
            <strong>{{ tg }}</strong>：个人达标 {{ dist['达标人数'] }}/{{ diagData.distribution['样本人数'] }} 人
            （{{ (dist['个人达标率'] * 100).toFixed(1) }}% · 最高 {{ (dist['最高达成度'] * 100).toFixed(1) }}% / 最低 {{ (dist['最低达成度'] * 100).toFixed(1) }}%）
          </div>
        </div>
      </div>

      <el-row :gutter="18" style="margin-top: 16px">
        <el-col :xs="24" :md="12">
          <div class="note-label">达成情况分析（导出填入《达成度数据分析表》Sheet1）</div>
          <el-input v-model="analysisText" type="textarea" :rows="5" />
        </el-col>
        <el-col :xs="24" :md="12">
          <div class="note-label">拟改进的措施（导出填入《达成度数据分析表》Sheet1）</div>
          <el-input v-model="improvementNotes" type="textarea" :rows="5" />
        </el-col>
      </el-row>
    </div>

    <!-- 四、期末试卷分析（对应《考试试卷分析表》） -->
    <div v-if="examStats" class="panel-card">
      <div class="panel-title">
        <span>期末试卷分析（导出归档包自动生成《考试试卷分析表.xlsx》）</span>
        <span class="sub-hint tabular-nums">实考 {{ examStats.total_count }} 人 · 及格 {{ examStats.pass_count }} 人</span>
      </div>

      <div class="exam-kpi-row tabular-nums">
        <div class="ek-box"><span class="ek-k">卷面平均分</span><strong class="ek-v">{{ examStats.avg.toFixed(1) }}</strong></div>
        <div class="ek-box"><span class="ek-k">最高分</span><strong class="ek-v" style="color: #059669">{{ examStats.max }}</strong></div>
        <div class="ek-box"><span class="ek-k">最低分</span><strong class="ek-v" style="color: #dc2626">{{ examStats.min }}</strong></div>
        <div class="ek-box">
          <span class="ek-k">卷面及格率</span>
          <strong class="ek-v" :style="{ color: examStats.pass_rate >= 0.6 ? '#059669' : '#d97706' }">
            {{ (examStats.pass_rate * 100).toFixed(1) }}%
          </strong>
        </div>
      </div>

      <el-row :gutter="18" style="margin-top: 16px">
        <el-col :xs="24" :md="11">
          <div class="note-label">期末 5 档分数段分布</div>
          <div class="bucket-list tabular-nums">
            <div v-for="b in examStats.buckets" :key="b.label" class="bucket-row">
              <span class="b-lbl">{{ b.label }}</span>
              <div class="b-bar-wrap">
                <div class="b-bar" :class="{ fail: b.label.includes('59') }" :style="{ width: `${Math.max(2, b.ratio * 100)}%` }"></div>
              </div>
              <span class="b-num">{{ b.count }} 人（{{ (b.ratio * 100).toFixed(1) }}%）</span>
            </div>
          </div>
        </el-col>
        <el-col :xs="24" :md="13">
          <div class="note-label">各大题得分率统计</div>
          <el-table :data="examStats.sections" size="small" class="tabular-nums">
            <el-table-column prop="name" label="大题" min-width="120" />
            <el-table-column prop="full" label="应得分" width="80" align="center" />
            <el-table-column prop="avg" label="平均分" width="80" align="center" />
            <el-table-column label="得分率" width="90" align="center">
              <template #default="{ row }">
                <span :style="{ color: row.rate < 0.6 ? '#dc2626' : '#059669', fontWeight: 600 }">
                  {{ (row.rate * 100).toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-col>
      </el-row>

      <div style="margin-top: 16px">
        <div class="note-label">试卷质量分析与教学改进意见（导出填入《考试试卷分析表》Sheet2）</div>
        <el-input v-model="examAnalysisText" type="textarea" :rows="4" />
      </div>
    </div>

    <!-- 五、评价达成情况终表 -->
    <div class="panel-card">
      <div class="panel-title"><span>《课程目标评价达成情况终表》预览</span></div>
      <el-table :data="summaryRows" size="small" :span-method="summarySpanMethod" class="tabular-nums">
        <el-table-column prop="target" label="课程目标" width="115" align="center">
          <template #default="{ row }"><strong>{{ row.target }}</strong></template>
        </el-table-column>
        <el-table-column prop="basis" label="评价依据" width="100" align="center" />
        <el-table-column v-for="link in allLinks" :key="link" :prop="link" :label="link" align="center" />
        <el-table-column prop="total" label="合计" width="90" align="center">
          <template #default="{ row }"><strong>{{ row.total }}</strong></template>
        </el-table-column>
        <el-table-column prop="achievement" label="达成度" width="95" align="center">
          <template #default="{ row }"><strong>{{ row.achievement }}</strong></template>
        </el-table-column>
        <el-table-column prop="status" label="结果" width="95" align="center">
          <template #default="{ row }">
            <span v-if="row.status !== '—'" class="status-pill" :class="row.passed ? 'ok' : 'err'">{{ row.status }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const props = defineProps({
  task: { type: Object, required: true },
})
defineEmits(['back'])

const barRef = ref(null)
const linkRef = ref(null)
let barChart = null
let linkChart = null
const exporting = ref(false)
const savingNotes = ref(false)

const rep = computed(() => props.task?.report || null)
const diagData = computed(() => rep.value?.diagnostics || null)
const examStats = computed(() => rep.value?.exam_analysis || null)
const allLinks = computed(() => Object.keys(rep.value?.link_weights || {}))

const analysisText = ref('')
const improvementNotes = ref('')
const examAnalysisText = ref('')

function syncTexts() {
  analysisText.value = props.task?.analysis_text || diagData.value?.analysis_text || ''
  improvementNotes.value = props.task?.improvement_notes || diagData.value?.improvement_text || ''
  examAnalysisText.value = props.task?.exam_analysis_text || examStats.value?.default_analysis_text || ''
}

function sumDaily(info) { return Object.values(info['平时明细'] || {}).reduce((a, b) => a + b, 0) }

const summaryRows = computed(() => {
  if (!rep.value) return []
  const rows = []
  const wRow = { target: '—', basis: '环节总分', total: '100.00', achievement: '—', status: '—', passed: true }
  for (const l of allLinks.value) wRow[l] = ((rep.value.link_weights[l] || 0) * 100).toFixed(2)
  rows.push(wRow)
  for (const [t, info] of Object.entries(rep.value.report || {})) {
    const fullRow = {
      target: t, basis: '理论满分', total: info['理论满分'].toFixed(2),
      achievement: `${(info['达成度'] * 100).toFixed(1)}%`, status: info['是否达标'] ? '达标' : '未达标', passed: info['是否达标'],
    }
    const actRow = {
      target: t, basis: '实际得分', total: info['实得'].toFixed(2),
      achievement: `${(info['达成度'] * 100).toFixed(1)}%`, status: info['是否达标'] ? '达标' : '未达标', passed: info['是否达标'],
    }
    for (const l of allLinks.value) {
      const ow = rep.value.output_weights?.[t]?.[l] || 0
      fullRow[l] = (ow * 100).toFixed(2)
      actRow[l] = (l === '期末考试' ? info['期末'] : info['平时明细'][l] || 0).toFixed(2)
    }
    rows.push(fullRow, actRow)
  }
  return rows
})

function summarySpanMethod({ rowIndex, columnIndex }) {
  if (rowIndex === 0) return [1, 1]
  const totalCols = allLinks.value.length + 5
  if (columnIndex === 0 || columnIndex === totalCols - 2 || columnIndex === totalCols - 1) {
    return (rowIndex - 1) % 2 === 0 ? [2, 1] : [0, 0]
  }
  return [1, 1]
}

function renderCharts() {
  if (!barRef.value || !linkRef.value || !rep.value) return
  if (!barChart) barChart = echarts.init(barRef.value)
  if (!linkChart) linkChart = echarts.init(linkRef.value)

  const targets = Object.keys(rep.value.report || {})
  const thPct = Number(((props.task.pass_threshold || 0.65) * 100).toFixed(1))

  barChart.setOption({
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${v}%` },
    grid: { left: 46, right: 20, top: 32, bottom: 28 },
    xAxis: { type: 'category', data: targets, axisLine: { lineStyle: { color: '#e2e8f0' } } },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
    series: [{
      name: '达成度', type: 'bar', barWidth: 40,
      data: targets.map((t) => {
        const info = rep.value.report[t]
        return { value: Number((info['达成度'] * 100).toFixed(1)), itemStyle: { color: info['是否达标'] ? '#10b981' : '#ef4444', borderRadius: [8, 8, 0, 0] } }
      }),
      label: { show: true, position: 'top', formatter: '{c}%', fontWeight: 600 },
      markLine: {
        silent: true,
        lineStyle: { color: '#ef4444', type: 'dashed', width: 1.5 },
        label: { formatter: `合格基准 ${thPct}%`, position: 'insideEndTop', color: '#dc2626' },
        data: [{ yAxis: thPct }],
      },
    }],
  })

  const links = allLinks.value
  linkChart.setOption({
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${v}%` },
    legend: { top: 2 },
    grid: { left: 46, right: 16, top: 34, bottom: 28 },
    xAxis: { type: 'category', data: links, axisLine: { lineStyle: { color: '#e2e8f0' } } },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
    series: targets.map((t) => ({
      name: t, type: 'bar', barMaxWidth: 26, itemStyle: { borderRadius: [5, 5, 0, 0] },
      data: links.map((l) => {
        const fullS = (rep.value.output_weights?.[t]?.[l] || 0) * 100
        if (fullS <= 0) return 0
        const act = l === '期末考试' ? rep.value.report[t]['期末'] : rep.value.report[t]['平时明细'][l] || 0
        return Number(((act / fullS) * 100).toFixed(1))
      }),
    })),
  })
}

function saveChartPng(chart, filename) {
  if (!chart) return
  const a = document.createElement('a')
  a.href = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#ffffff' })
  a.download = filename
  a.click()
}

async function saveNotes(silent = false) {
  savingNotes.value = true
  try {
    await api.updateTaskNotes(props.task.id, {
      analysis_text: analysisText.value,
      improvement_notes: improvementNotes.value,
      exam_analysis_text: examAnalysisText.value,
    })
    if (!silent) ElMessage.success('三段分析与改进意见已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    savingNotes.value = false
  }
}

async function exportBundle() {
  exporting.value = true
  try {
    await saveNotes(true)
    const fname = `${props.task.class_name}${props.task.course_name}_归档材料.zip`
    await api.exportTaskBundle(props.task.id, fname)
    ElMessage.success('已导出归档包（解压即见《达成度数据分析表》+《考试试卷分析表》）')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    exporting.value = false
  }
}

function handleResize() { barChart?.resize(); linkChart?.resize() }
onMounted(() => { syncTexts(); nextTick(renderCharts); window.addEventListener('resize', handleResize) })
watch(() => props.task, () => { syncTexts(); nextTick(renderCharts) }, { deep: true })
onBeforeUnmount(() => { window.removeEventListener('resize', handleResize); barChart?.dispose(); linkChart?.dispose() })
</script>

<style scoped>
.actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.kpi-head { display: flex; justify-content: space-between; align-items: center; }
.kpi-meta { font-size: 12.5px; color: #64748b; margin-top: 10px; }
.diag-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
.diag-box { background: #f8fafc; border-radius: 12px; padding: 16px 18px; }
.diag-box h4 { margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #0f172a; }
.contrast-alert { font-size: 13px; color: #92400e; background: #fef3c7; padding: 8px 12px; border-radius: 8px; margin-bottom: 10px; }
.dist-line { font-size: 13px; color: #334155; padding: 7px 0; border-bottom: 1px dashed #e2e8f0; }
.dist-line:last-child { border-bottom: none; }
.note-label { font-size: 13px; font-weight: 600; color: #334155; margin-bottom: 8px; }
.sub-hint { font-size: 13px; font-weight: 400; color: #64748b; }
.exam-kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; }
.ek-box { background: #f8fafc; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }
.ek-k { font-size: 12.5px; color: #64748b; }
.ek-v { font-size: 24px; font-weight: 700; color: #0f172a; }
.bucket-list { display: flex; flex-direction: column; gap: 10px; padding-top: 4px; }
.bucket-row { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.b-lbl { width: 72px; color: #475569; flex-shrink: 0; }
.b-bar-wrap { flex: 1; height: 10px; background: #f1f5f9; border-radius: 999px; overflow: hidden; }
.b-bar { height: 100%; background: #3b82f6; border-radius: 999px; }
.b-bar.fail { background: #ef4444; }
.b-num { width: 108px; text-align: right; color: #334155; font-weight: 500; flex-shrink: 0; }
</style>
