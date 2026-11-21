<template>
  <div class="panel-card">
    <div class="panel-title">
      <span>历史班级达成度报告归档</span>
      <el-button size="small" plain @click="loadReports">刷新列表</el-button>
    </div>

    <el-table :data="reports" border stripe size="small" v-loading="loading" class="tabular-nums">
      <el-table-column prop="course_name" label="课程名称" min-width="150" />
      <el-table-column prop="semester" label="学期" width="120" align="center" />
      <el-table-column prop="class_name" label="教学班级" width="140" align="center" />
      <el-table-column prop="student_count" label="人数" width="70" align="center" />
      <el-table-column label="各目标达成度" min-width="240">
        <template #default="{ row }">
          <el-tag
            v-for="(val, tg) in extractTargets(row)"
            :key="tg"
            :type="val['达成度'] >= row.pass_threshold ? 'success' : 'danger'"
            size="small"
            style="margin-right: 6px; margin-bottom: 4px"
          >
            {{ tg }}：{{ (val['达成度'] * 100).toFixed(1) }}%
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="生成时间" width="160" align="center" />
      <el-table-column label="操作" width="230" fixed="right" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openReport(row.id)">
            查看大屏
          </el-button>
          <el-button link type="success" size="small" @click="reExport(row)">
            导出 Excel
          </el-button>
          <el-button link type="warning" size="small" @click="reloadToEdit(row.id)">
            重载修改
          </el-button>
          <el-button link type="danger" size="small" @click="delReport(row.id)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, downloadBlob } from '../api/client'

const emit = defineEmits(['view-report', 'reload-students'])
const loading = ref(false)
const reports = ref([])

function extractTargets(row) {
  return row.report?.report || row.report || {}
}

async function loadReports() {
  loading.value = true
  try {
    const res = await api.listReports()
    reports.value = res.reports || []
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function openReport(id) {
  try {
    const res = await api.getReport(id)
    const d = res.data
    emit('view-report', {
      report_id: d.id,
      course_id: d.course_id,
      student_count: d.student_count,
      threshold: d.pass_threshold,
      meta: d.report.meta || {
        课程名称: d.course_name,
        学期: d.semester,
        班级: d.class_name,
      },
      link_weights: d.report.link_weights,
      output_weights: d.report.output_weights,
      full_scores: d.report.full_scores,
      paper_target_full: d.report.paper_target_full,
      report: d.report.report,
      students: d.students,
      analysis_text: d.analysis_text || '',
      improvement_notes: d.improvement_notes || '',
    })
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function reloadToEdit(id) {
  try {
    const res = await api.getReport(id)
    emit('reload-students', res.data)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function reExport(row) {
  try {
    const fname = `${row.course_name}_${row.class_name}_达成度计算表.xlsx`
    await downloadBlob(`/api/reports/${row.id}/export`, fname)
    ElMessage.success('已重新导出三 Sheet《达成度计算表.xlsx》')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function delReport(id) {
  try {
    await ElMessageBox.confirm('确定删除该条历史达成度报告吗？', '确认删除', { type: 'warning' })
    await api.deleteReport(id)
    ElMessage.success('已删除')
    await loadReports()
  } catch {
    // cancelled
  }
}

onMounted(loadReports)
</script>
