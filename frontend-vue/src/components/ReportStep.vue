<template>
  <div v-if="result">
    <!-- 顶部元信息与导出栏 -->
    <div class="panel-card">
      <div class="panel-title">
        <div>
          <span>{{ result.meta['课程名称'] }} · {{ result.meta['班级'] }}</span>
          <el-tag size="small" type="info" style="margin-left: 10px">
            学期 {{ result.meta['学期'] }}
          </el-tag>
          <el-tag size="small" type="info" style="margin-left: 6px">
            样本 {{ result.student_count }} 人 · 合格基准 {{ (result.threshold * 100).toFixed(0) }}%
          </el-tag>
        </div>
        <div class="actions">
          <el-button @click="$emit('back')">← 返回修改成绩</el-button>
          <el-button type="primary" :loading="exporting" @click="exportExcel">
            <el-icon><Download /></el-icon>&nbsp;一键导出 4-Sheet《达成度数据分析表.xlsx》
          </el-button>
        </div>
      </div>
    </div>

    <!-- 一、顶部核心 KPI 指标卡片 -->
    <div class="kpi-grid tabular-nums">
      <div v-for="(info, target) in result.report" :key="target" class="kpi-card">
        <div class="kpi-head">
          <strong>{{ target }}</strong>
          <el-tag :type="info['是否达标'] ? 'success' : 'danger'" effect="dark" size="small">
            {{ info['是否达标'] ? '达标' : '未达标预警' }}
          </el-tag>
        </div>
        <div class="kpi-value" :style="{ color: info['是否达标'] ? '#059669' : '#dc2626' }">
          {{ (info['达成度'] * 100).toFixed(1) }}%
        </div>
        <el-progress
          :percentage="Math.min(100, Number((info['达成度'] * 100).toFixed(1)))"
          :status="info['是否达标'] ? 'success' : 'exception'"
          :show-text="false"
          :stroke-width="8"
        />
        <div class="kpi-meta">
          实得 <b>{{ info['实得'].toFixed(2) }}</b> / 理论满分 <b>{{ info['理论满分'].toFixed(2) }}</b> 分
          （平时 {{ sumDaily(info).toFixed(2) }} · 期末 {{ info['期末'].toFixed(2) }}）
        </div>
      </div>
    </div>

    <!-- 二、ECharts 双图可视化 -->
    <el-row :gutter="18">
      <el-col :xs="24" :lg="12">
        <div class="panel-card">
          <div class="panel-title">
            <span>课程目标达成度对比图（含合格基准线）</span>
            <el-button size="small" plain @click="saveChartPng(barChart, '课程目标达成度对比图.png')">
              保存图片 (PPT 用)
            </el-button>
          </div>
          <div ref="barRef" style="height: 300px; width: 100%"></div>
        </div>
      </el-col>
      <el-col :xs="24" :lg="12">
        <div class="panel-card">
          <div class="panel-title">
            <span>各考核环节得分率对比（精准定位薄弱项）</span>
            <el-button size="small" plain @click="saveChartPng(linkChart, '考核环节得分率对比图.png')">
              保存图片
            </el-button>
          </div>
          <div ref="linkRef" style="height: 300px; width: 100%"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 三、印刷级《课程目标评价达成情况终表》 -->
    <div class="panel-card">
      <div class="panel-title">
        <span>《课程目标评价达成情况终表》所见即所得预览</span>
      </div>
      <el-table
        :data="summaryRows"
        border
        size="small"
        :span-method="summarySpanMethod"
        class="tabular-nums"
      >
        <el-table-column prop="target" label="课程目标" width="120" align="center">
          <template #default="{ row }"><strong>{{ row.target }}</strong></template>
        </el-table-column>
        <el-table-column prop="basis" label="评价依据" width="110" align="center" />
        <el-table-column
          v-for="link in allLinks"
          :key="link"
          :prop="link"
          :label="link"
          align="center"
        />
        <el-table-column prop="total" label="合计(分)" width="100" align="center">
          <template #default="{ row }"><strong>{{ row.total }}</strong></template>
        </el-table-column>
        <el-table-column prop="achievement" label="达成度" width="100" align="center">
          <template #default="{ row }"><strong>{{ row.achievement }}</strong></template>
        </el-table-column>
        <el-table-column prop="status" label="评价结果" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.status !== '—'"
              :type="row.passed ? 'success' : 'danger'"
              size="small"
            >
              {{ row.status }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 四、OBE 教学诊断 Agent 下钻分析与持续改进措施 -->
    <div class="panel-card">
      <div class="panel-title">
        <span>OBE 智能诊断下钻与持续改进措施（预留大模型 Agent 扩展）</span>
        <div class="actions">
          <el-button type="primary" plain :loading="diagLoading" @click="runDiagnostics">
            <el-icon><Cpu /></el-icon>&nbsp;一键运行 4 维诊断并生成改进草稿
          </el-button>
          <el-button v-if="result.report_id" type="success" plain @click="saveNotes">
            保存改进措施至报告
          </el-button>
        </div>
      </div>

      <div v-if="diagData" class="diag-grid">
        <div class="diag-box">
          <h4>期末得分率最低 Top 5 试题</h4>
          <el-table :data="diagData.hard_questions" size="small" border class="tabular-nums">
            <el-table-column label="题号" width="70" align="center">
              <template #default="{ row }">第{{ row['题号'] }}题</template>
            </el-table-column>
            <el-table-column prop="所属目标" label="归属目标" width="95" align="center" />
            <el-table-column label="均分/满分" align="center">
              <template #default="{ row }">{{ row['全班均分'] }} / {{ row['满分'] }}</template>
            </el-table-column>
            <el-table-column label="得分率" width="85" align="center">
              <template #default="{ row }">
                <span style="color: #dc2626; font-weight: 600">
                  {{ (row['得分率'] * 100).toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="diag-box">
          <h4>学情分布与反差预警</h4>
          <p class="panel-sub" style="margin-top: 4px">
            平时均分 ≥ 80 分但期末卷面 &lt; 60 分的反差学生：
            <strong style="color: #d97706">{{ diagData.distribution['平时高期末低反差人数'] }} 人</strong>
          </p>
          <div
            v-for="(dist, tg) in diagData.distribution['各目标分布']"
            :key="tg"
            class="dist-line tabular-nums"
          >
            <strong>{{ tg }}</strong>：个人达标 {{ dist['达标人数'] }}/{{ diagData.distribution['样本人数'] }} 人
            （达标率 {{ (dist['个人达标率'] * 100).toFixed(1) }}% · 最高 {{ (dist['最高达成度'] * 100).toFixed(1) }}% / 最低 {{ (dist['最低达成度'] * 100).toFixed(1) }}%）
          </div>
        </div>
      </div>

      <el-row :gutter="16" style="margin-top: 14px">
        <el-col :xs="24" :md="12">
          <div class="note-label">达成情况分析（导出时自动填入 Sheet1《目标达成评价表》）</div>
          <el-input
            v-model="analysisText"
            type="textarea"
            :rows="6"
            placeholder="点击上方「一键运行 4 维诊断并生成改进草稿」，或手写本班课程目标达成情况分析..."
          />
        </el-col>
        <el-col :xs="24" :md="12">
          <div class="note-label">拟改进的措施（导出时自动填入 Sheet1《目标达成评价表》）</div>
          <el-input
            v-model="improvementNotes"
            type="textarea"
            :rows="6"
            placeholder="填写下一轮教学持续改进措施..."
          />
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const props = defineProps({
  result: { type: Object, required: true },
})
defineEmits(['back'])

const barRef = ref(null)
const linkRef = ref(null)
let barChart = null
let linkChart = null
const exporting = ref(false)
const diagLoading = ref(false)
const diagData = ref(null)
const analysisText = ref(props.result?.analysis_text || '')
const improvementNotes = ref(props.result?.improvement_notes || '')

const allLinks = computed(() => Object.keys(props.result.link_weights || {}))

function sumDaily(info) {
  return Object.values(info['平时明细'] || {}).reduce((a, b) => a + b, 0)
}

const summaryRows = computed(() => {
  const rows = []
  const wRow = { target: '—', basis: '环节总分', total: '100.00', achievement: '—', status: '—', passed: true }
  for (const l of allLinks.value) {
    wRow[l] = ((props.result.link_weights[l] || 0) * 100).toFixed(2)
  }
  rows.push(wRow)

  for (const [t, info] of Object.entries(props.result.report || {})) {
    const fullRow = {
      target: t,
      basis: '理论满分',
      total: info['理论满分'].toFixed(2),
      achievement: `${(info['达成度'] * 100).toFixed(1)}%`,
      status: info['是否达标'] ? '达标' : '未达标',
      passed: info['是否达标'],
    }
    const actRow = {
      target: t,
      basis: '实际得分',
      total: info['实得'].toFixed(2),
      achievement: `${(info['达成度'] * 100).toFixed(1)}%`,
      status: info['是否达标'] ? '达标' : '未达标',
      passed: info['是否达标'],
    }
    for (const l of allLinks.value) {
      const ow = props.result.output_weights?.[t]?.[l] || 0
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
  if (!barRef.value || !linkRef.value) return
  if (!barChart) barChart = echarts.init(barRef.value)
  if (!linkChart) linkChart = echarts.init(linkRef.value)

  const targets = Object.keys(props.result.report || {})
  const thPct = Number(((props.result.threshold || 0.65) * 100).toFixed(1))

  // 图 1：各目标达成度柱状图 + 红色虚线合格基准线
  barChart.setOption({
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${v}%` },
    grid: { left: 48, right: 24, top: 36, bottom: 32 },
    xAxis: { type: 'category', data: targets },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        name: '达成度',
        type: 'bar',
        barWidth: 44,
        data: targets.map((t) => {
          const info = props.result.report[t]
          return {
            value: Number((info['达成度'] * 100).toFixed(1)),
            itemStyle: {
              color: info['是否达标'] ? '#10b981' : '#ef4444',
              borderRadius: [6, 6, 0, 0],
            },
          }
        }),
        label: { show: true, position: 'top', formatter: '{c}%', fontWeight: 600 },
        markLine: {
          silent: true,
          lineStyle: { color: '#ef4444', type: 'dashed', width: 2 },
          label: { formatter: `合格基准 ${thPct}%`, position: 'insideEndTop', color: '#dc2626' },
          data: [{ yAxis: thPct }],
        },
      },
    ],
  })

  // 图 2：各考核环节得分率分组柱状图
  const links = allLinks.value
  linkChart.setOption({
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${v}%` },
    legend: { top: 4 },
    grid: { left: 48, right: 20, top: 38, bottom: 32 },
    xAxis: { type: 'category', data: links },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: targets.map((t) => ({
      name: t,
      type: 'bar',
      barMaxWidth: 28,
      data: links.map((l) => {
        const fullS = (props.result.output_weights?.[t]?.[l] || 0) * 100
        if (fullS <= 0) return 0
        const act = l === '期末考试' ? props.result.report[t]['期末'] : props.result.report[t]['平时明细'][l] || 0
        return Number(((act / fullS) * 100).toFixed(1))
      }),
    })),
  })
}

function saveChartPng(chart, filename) {
  if (!chart) return
  const url = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#ffffff' })
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
}

async function exportExcel() {
  exporting.value = true
  try {
    const filename = `${props.result.meta['班级'] || ''}${props.result.meta['课程名称'] || ''}达成度数据分析表.xlsx`
    await api.exportRecords(
      {
        course_id: props.result.course_id,
        students: props.result.students,
        threshold: props.result.threshold,
        meta: props.result.meta,
        analysis_text: analysisText.value,
        improvement_notes: improvementNotes.value,
      },
      filename
    )
    ElMessage.success('已导出 4-Sheet《达成度数据分析表.xlsx》（含封面评价表与签字栏）')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    exporting.value = false
  }
}

async function runDiagnostics() {
  diagLoading.value = true
  try {
    const res = await api.analyzeDiagnostics({
      course_id: props.result.course_id,
      students: props.result.students,
      threshold: props.result.threshold,
      meta: props.result.meta,
    })
    diagData.value = res.diagnostics
    analysisText.value = res.diagnostics.analysis_text || ''
    improvementNotes.value = res.diagnostics.improvement_text || ''
    ElMessage.success('4 维数据下钻诊断完成，已自动填充「达成情况分析」与「拟改进的措施」')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    diagLoading.value = false
  }
}

async function saveNotes() {
  try {
    await api.updateReportNotes(props.result.report_id, analysisText.value, improvementNotes.value)
    ElMessage.success('达成情况分析与改进措施已保存到历史报告')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function handleResize() {
  barChart?.resize()
  linkChart?.resize()
}

onMounted(() => {
  nextTick(renderCharts)
  window.addEventListener('resize', handleResize)
})

watch(() => props.result, () => nextTick(renderCharts), { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  barChart?.dispose()
  linkChart?.dispose()
})
</script>

<style scoped>
.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.kpi-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.kpi-meta {
  font-size: 12px;
  color: #64748b;
  margin-top: 10px;
}

.diag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
  margin-top: 6px;
}

.diag-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
}

.diag-box h4 {
  margin: 0 0 10px;
  font-size: 14px;
  color: #1e293b;
}

.dist-line {
  font-size: 13px;
  padding: 6px 0;
  border-bottom: 1px dashed #e2e8f0;
  color: #334155;
}

.note-label {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 6px;
}
</style>
