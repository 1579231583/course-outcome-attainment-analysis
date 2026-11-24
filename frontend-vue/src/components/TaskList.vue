<template>
  <div>
    <div class="page-header">
      <div>
        <h1>我的班级分析</h1>
        <p class="subtitle">每个班级一张卡片：选用公共大纲建班 → 传成绩 → 一键导出《达成度分析表》与《考试试卷分析表》</p>
      </div>
      <div class="head-actions">
        <el-select
          v-if="semesterOptions.length > 1"
          v-model="semesterFilter"
          clearable
          placeholder="全部学期"
          style="width: 145px"
        >
          <el-option v-for="s in semesterOptions" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button plain size="large" @click="openCustomModal">新建自定义班级</el-button>
        <el-button type="primary" size="large" @click="openPickModal">+ 选用公共大纲建班</el-button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && filteredTasks.length === 0" class="empty-panel">
      <div class="empty-title">还没有班级达成度分析任务</div>
      <p class="empty-sub">点击下方按钮，从教务处发布的公共大纲库中选一门课、填写你的教学班级即可开始。</p>
      <el-button type="primary" size="large" @click="openPickModal">+ 选用公共大纲建班</el-button>
    </div>

    <!-- 统一班级分析卡片网格（彻底合并原“我的课程”与“历史报告”） -->
    <div v-else class="task-grid" v-loading="loading">
      <div
        v-for="t in filteredTasks"
        :key="t.id"
        class="task-card"
        @click="$emit(t.status === 'completed' ? 'open-report' : 'open-score', t.id)"
      >
        <div class="tc-top">
          <div class="tc-title-wrap">
            <h3 class="tc-name">{{ t.course_name }}</h3>
            <div class="tc-badges">
              <span class="class-chip">{{ t.class_name }}</span>
              <span class="sem-chip tabular-nums">{{ t.semester }}</span>
            </div>
          </div>

          <span
            class="status-pill"
            :class="t.status === 'completed' ? 'ok' : t.status === 'pending_scores' ? 'info' : 'warn'"
          >
            <span class="dot"></span>
            {{
              t.status === 'completed'
                ? `已出报告 (${t.student_count}人)`
                : t.status === 'pending_ratios'
                  ? '待配置占比'
                  : t.status === 'pending_scores'
                    ? '待上传成绩'
                    : '待配期末试卷'
            }}
          </span>
        </div>

        <!-- 已完成任务：直接展示各目标达成度预览 -->
        <div v-if="t.status === 'completed' && t.target_summary" class="target-pills tabular-nums">
          <span
            v-for="(val, tg) in t.target_summary"
            :key="tg"
            class="status-pill"
            :class="val['达成度'] >= t.pass_threshold ? 'ok' : 'err'"
          >
            {{ tg }} {{ (val['达成度'] * 100).toFixed(1) }}%
          </span>
        </div>

        <!-- 未完成任务：展示规则与统考试卷关联情况 -->
        <div v-else class="tc-meta tabular-nums">
          <span v-if="t.ratios_confirmed">平时 {{ Math.round(t.daily_ratio * 100) }}% / 期末 {{ Math.round(t.final_ratio * 100) }}%</span>
          <span v-else style="color: #d97706; font-weight: 500">占比待配置</span>
          <span class="sep">·</span>
          <span>{{ t.target_count }} 个目标</span>
          <span class="sep">·</span>
          <span>
            {{
              t.paper_ready
                ? `${t.paper_source === 'unified' ? '统考卷' : '自配卷'} ${t.question_count}题`
                : '尚未配试卷'
            }}
          </span>
        </div>

        <div class="tc-footer" @click.stop>
          <span class="tc-time">{{ (t.updated_at || '').slice(0, 16) }}</span>
          <div class="tc-actions">
            <template v-if="t.status === 'completed'">
              <el-button link type="success" size="small" @click="exportZip(t)">导出归档包</el-button>
              <el-button link type="primary" size="small" @click="$emit('open-score', t.id)">改成绩</el-button>
              <el-button link type="danger" size="small" @click="delTask(t)">删除</el-button>
              <el-button type="primary" plain size="small" @click="$emit('open-report', t.id)">查看报告</el-button>
            </template>
            <template v-else>
              <el-button link type="danger" size="small" @click="delTask(t)">删除</el-button>
              <el-button type="primary" plain size="small" @click="$emit('open-score', t.id)">进入分析 →</el-button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 弹窗 1：选用公共大纲建班 -->
    <el-dialog v-model="pickOpen" title="选用公共教学大纲建班" width="640px" destroy-on-close>
      <div v-if="syllabuses.length === 0" class="dlg-empty">
        教务管理员尚未发布公共教学大纲。您可以联系教务处上传大纲 PDF，或先点「新建自定义班级」。
      </div>
      <template v-else>
        <div class="dlg-label">1. 选择课程教学大纲（由教务处统一维护）</div>
        <div class="pub-list">
          <div
            v-for="s in syllabuses"
            :key="s.id"
            class="pub-item"
            :class="{ selected: pickForm.syllabusId === s.id }"
            @click="pickForm.syllabusId = s.id"
          >
            <div>
              <div class="pub-name">{{ s.course_name }}</div>
              <div class="pub-sub tabular-nums">
                {{ s.course_code ? `代码 ${s.course_code} · ` : '' }}
                {{ s.target_count }} 个课程目标 · 考核环节：{{ [...(s.daily_links || []), '期末考试'].join('/') }}
              </div>
            </div>
            <span class="status-pill" :class="s.has_paper ? 'ok' : 'warn'">
              {{ s.has_paper ? `${s.paper_count} 份统考卷` : '仅大纲' }}
            </span>
          </div>
        </div>

        <el-row :gutter="16" style="margin-top: 20px">
          <el-col :span="10">
            <div class="dlg-label">2. 开课学期 *</div>
            <el-input v-model="pickForm.semester" size="large" placeholder="如：2025-2026-1" />
          </el-col>
          <el-col :span="14">
            <div class="dlg-label">3. 你的教学班级 *</div>
            <el-input
              v-model="pickForm.className"
              size="large"
              placeholder="如：24智能制造1班"
              @keyup.enter="confirmPick"
            />
          </el-col>
        </el-row>

        <div v-if="selectedSyllabus" class="paper-match-tip">
          <span v-if="matchedUnifiedPaper" class="match-ok">
            ✓ 检测到教务处已发布「{{ matchedUnifiedPaper.semester }}」统考试卷（{{ matchedUnifiedPaper.question_count }} 题），建班后将自动关联，直接上传成绩即可。
          </span>
          <span v-else class="match-info">
            该学期暂无教务处统考试卷，建班后可在右侧抽屉中上传或配置本班期末试卷结构。
          </span>
        </div>
      </template>

      <template #footer>
        <el-button @click="pickOpen = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!pickForm.syllabusId || !pickForm.semester.trim() || !pickForm.className.trim()"
          :loading="submitting"
          @click="confirmPick"
        >
          确认建班并进入 →
        </el-button>
      </template>
    </el-dialog>

    <!-- 弹窗 2：新建自定义班级 -->
    <el-dialog v-model="customOpen" title="新建自定义班级分析" width="460px" destroy-on-close>
      <div class="dlg-field">
        <div class="dlg-label">课程名称 *</div>
        <el-input v-model="customForm.courseName" placeholder="例如：大学物理B" />
      </div>
      <div class="dlg-field">
        <div class="dlg-label">开课学期 *</div>
        <el-input v-model="customForm.semester" placeholder="例如：2025-2026-1" />
      </div>
      <div class="dlg-field">
        <div class="dlg-label">教学班级 *</div>
        <el-input v-model="customForm.className" placeholder="例如：24机械工程2班" />
      </div>
      <template #footer>
        <el-button @click="customOpen = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!customForm.courseName.trim() || !customForm.semester.trim() || !customForm.className.trim()"
          :loading="submitting"
          @click="confirmCustom"
        >
          创建并进入配置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['open-score', 'open-report', 'refresh'])

const syllabuses = ref([])
const semesterFilter = ref('')
const pickOpen = ref(false)
const customOpen = ref(false)
const submitting = ref(false)

const pickForm = reactive({ syllabusId: null, semester: '2025-2026-1', className: '' })
const customForm = reactive({ courseName: '', semester: '2025-2026-1', className: '' })

const semesterOptions = computed(() => [...new Set(props.tasks.map((t) => t.semester).filter(Boolean))])
const filteredTasks = computed(() =>
  semesterFilter.value ? props.tasks.filter((t) => t.semester === semesterFilter.value) : props.tasks
)

const selectedSyllabus = computed(() => syllabuses.value.find((s) => s.id === pickForm.syllabusId) || null)
const matchedUnifiedPaper = computed(() => {
  if (!selectedSyllabus.value) return null
  const sem = pickForm.semester.trim()
  return (selectedSyllabus.value.exam_papers || []).find((ep) => ep.semester === sem) || null
})

async function loadSyllabuses() {
  try {
    const res = await api.listSyllabuses()
    syllabuses.value = res.syllabuses || []
  } catch {
    // ignore
  }
}

async function openPickModal() {
  await loadSyllabuses()
  pickForm.className = ''
  pickForm.syllabusId = syllabuses.value[0]?.id || null
  pickOpen.value = true
}

function openCustomModal() {
  customForm.courseName = ''
  customForm.className = ''
  customForm.semester = '2025-2026-1'
  customOpen.value = true
}

async function confirmPick() {
  submitting.value = true
  try {
    const res = await api.createTask({
      syllabus_id: pickForm.syllabusId,
      semester: pickForm.semester.trim(),
      class_name: pickForm.className.trim(),
    })
    pickOpen.value = false
    ElMessage.success(
      res.task.paper_source === 'unified'
        ? '建班成功，已自动关联统考试卷，可直接传成绩'
        : '建班成功，请先配置期末试卷结构'
    )
    emit('refresh')
    emit('open-score', res.task.id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function confirmCustom() {
  submitting.value = true
  try {
    const res = await api.createTask({
      course_name: customForm.courseName.trim(),
      semester: customForm.semester.trim(),
      class_name: customForm.className.trim(),
    })
    customOpen.value = false
    ElMessage.success('已创建自定义班级，请先配置规则与试卷')
    emit('refresh')
    emit('open-score', res.task.id)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function exportZip(t) {
  try {
    const fname = `${t.class_name}${t.course_name}_归档材料.zip`
    await api.exportTaskBundle(t.id, fname)
    ElMessage.success('已导出归档包（含《达成度数据分析表》+《考试试卷分析表》）')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function delTask(t) {
  try {
    await ElMessageBox.confirm(`确定删除「${t.course_name} · ${t.class_name}」吗？`, '删除班级分析', { type: 'warning' })
    await api.deleteTask(t.id)
    ElMessage.success('已删除')
    emit('refresh')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

onMounted(loadSyllabuses)
</script>

<style scoped>
.head-actions { display: flex; gap: 10px; align-items: center; }
.empty-panel {
  background: #ffffff;
  border-radius: 16px;
  padding: 64px 32px;
  text-align: center;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.empty-title { font-size: 18px; font-weight: 600; color: #0f172a; margin-bottom: 8px; }
.empty-sub { font-size: 14px; color: #64748b; margin: 0 auto 24px; max-width: 480px; }

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(370px, 1fr));
  gap: 18px;
}
.task-card {
  background: #ffffff;
  border-radius: 14px;
  padding: 20px 22px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.16s ease;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.task-card:hover {
  border-color: #93c5fd;
  box-shadow: 0 6px 18px rgba(37, 99, 235, 0.08);
  transform: translateY(-1px);
}
.tc-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.tc-title-wrap { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.tc-name { margin: 0; font-size: 17px; font-weight: 700; color: #0f172a; }
.tc-badges { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.class-chip {
  font-size: 12.5px;
  font-weight: 600;
  color: #1d4ed8;
  background: #eff6ff;
  padding: 2px 10px;
  border-radius: 6px;
}
.sem-chip { font-size: 12px; color: #64748b; }
.target-pills { display: flex; flex-wrap: wrap; gap: 6px; }
.tc-meta { font-size: 13px; color: #64748b; display: flex; flex-wrap: wrap; gap: 6px; }
.sep { color: #cbd5e1; }
.tc-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
}
.tc-time { font-size: 12px; color: #94a3b8; }
.tc-actions { display: flex; align-items: center; gap: 8px; }

.status-pill.info { background: #eff6ff; color: #1d4ed8; }
.status-pill.info .dot { background: #2563eb; }

.dlg-label { font-size: 13px; font-weight: 600; color: #334155; margin-bottom: 8px; }
.dlg-field { margin-bottom: 16px; }
.dlg-empty { padding: 24px 0; text-align: center; color: #64748b; font-size: 14px; }
.pub-list { display: flex; flex-direction: column; gap: 10px; max-height: 260px; overflow-y: auto; }
.pub-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  border: 1.5px solid #e2e8f0;
  cursor: pointer;
  transition: all 0.15s;
}
.pub-item:hover { border-color: #93c5fd; background: #f8fafc; }
.pub-item.selected { border-color: #2563eb; background: #eff6ff; }
.pub-name { font-size: 15px; font-weight: 600; color: #0f172a; }
.pub-sub { font-size: 12.5px; color: #64748b; margin-top: 3px; }
.paper-match-tip { margin-top: 14px; font-size: 13px; line-height: 1.5; }
.match-ok { color: #059669; font-weight: 500; }
.match-info { color: #64748b; }
</style>
