<template>
  <LoginView v-if="!user" @success="onLoginSuccess" />

  <div v-else class="app-shell">
    <!-- 极简左侧边栏 -->
    <aside class="sidebar">
      <div class="side-logo">
        <div class="logo-mark">OBE</div>
        <div>
          <div class="logo-title">达成度分析</div>
          <div class="logo-sub">教学评价工作台</div>
        </div>
      </div>

      <nav class="side-nav">
        <div
          v-if="user.role === 'admin'"
          class="nav-item"
          :class="{ active: activeView === 'admin' }"
          @click="activeView = 'admin'"
        >
          <el-icon><Setting /></el-icon>
          <span>教务管理后台</span>
        </div>

        <div
          class="nav-item"
          :class="{ active: activeView === 'workbench' }"
          @click="activeView = 'workbench'"
        >
          <el-icon><DataAnalysis /></el-icon>
          <span>达成度工作台</span>
        </div>

        <div
          class="nav-item"
          :class="{ active: activeView === 'history' }"
          @click="activeView = 'history'"
        >
          <el-icon><Document /></el-icon>
          <span>历史报告归档</span>
        </div>
      </nav>

      <div class="side-footer">
        <div class="user-info">
          <div class="avatar">{{ (user.name || '教')[0] }}</div>
          <div class="user-text">
            <div class="user-name">{{ user.name }}</div>
            <div class="user-role">{{ user.role === 'admin' ? '教务管理员' : '任课教师' }}</div>
          </div>
        </div>
        <el-button link type="info" size="small" @click="logout">退出</el-button>
      </div>
    </aside>

    <!-- 右侧主工作区 -->
    <div class="main-wrap">
      <!-- 极简顶栏（绝不把步骤条硬塞进顶栏！） -->
      <header class="topbar">
        <div v-if="activeView === 'workbench' && cfg" class="top-course-bar">
          <span class="top-label">当前课程</span>
          <el-select
            :model-value="cfg.course_id"
            style="width: 260px"
            @change="switchCourse"
          >
            <el-option
              v-for="c in courses"
              :key="c.id"
              :label="`${c.course_name} (${c.semester})${c.is_public ? ' · 公共' : ''}`"
              :value="c.id"
            />
          </el-select>
          <el-button plain @click="createNewCourse">+ 新建课程</el-button>
        </div>
        <div v-else-if="activeView === 'history'" class="top-title">历史报告归档</div>
        <div v-else class="top-title">教务管理后台</div>
      </header>

      <main class="content">
        <!-- 教师工作台：顶部独立干净的 6 步线性进度条 -->
        <template v-if="activeView === 'workbench' && cfg">
          <div class="step-track">
            <div
              v-for="(label, idx) in stepLabels"
              :key="idx"
              class="step-node"
              :class="{
                active: step === idx,
                done: idx < step,
                disabled: idx === 5 && !calcResult,
              }"
              @click="goStep(idx)"
            >
              <span class="step-num">{{ idx < step ? '✓' : idx + 1 }}</span>
              <span class="step-txt">{{ label }}</span>
            </div>
          </div>

          <ConfigStep
            v-if="step <= 3"
            :cfg="cfg"
            :current-step="step"
            @saved="refreshCourseList"
            @go-step="goStep"
            @reload-config="loadConfig"
          />
          <ScoreStep
            v-show="step === 4"
            :cfg="cfg"
            :initial-students="loadedStudents"
            @calculated="onCalculated"
            @roster-updated="(n) => (rosterCount = n)"
          />
          <ReportStep
            v-if="step === 5 && calcResult"
            :result="calcResult"
            @back="step = 4"
          />
        </template>

        <HistoryView
          v-else-if="activeView === 'history'"
          @view-report="onViewHistoryReport"
          @reload-students="onReloadHistoryStudents"
        />

        <AdminView v-else-if="activeView === 'admin'" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from './api/client'
import LoginView from './components/LoginView.vue'
import ConfigStep from './components/ConfigStep.vue'
import ScoreStep from './components/ScoreStep.vue'
import ReportStep from './components/ReportStep.vue'
import HistoryView from './components/HistoryView.vue'
import AdminView from './components/AdminView.vue'

const stepLabels = ['选课程', '定占比', '配目标', '配试卷', '传成绩', '看报告']
const user = ref(JSON.parse(localStorage.getItem('obe_user') || 'null'))
const activeView = ref(user.value?.role === 'admin' ? 'admin' : 'workbench')
const step = ref(0)
const cfg = ref(null)
const courses = ref([])
const rosterCount = ref(0)
const calcResult = ref(null)
const loadedStudents = ref([])

async function loadConfig(courseId = null) {
  try {
    const [cRes, listRes] = await Promise.all([
      api.getConfig(courseId),
      api.listCourses(),
    ])
    cfg.value = cRes
    rosterCount.value = cRes.roster_count || 0
    courses.value = listRes.courses || []
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function refreshCourseList() {
  const res = await api.listCourses()
  courses.value = res.courses || []
}

function switchCourse(cid) {
  loadConfig(cid)
}

async function createNewCourse() {
  try {
    const res = await api.createCourse({
      meta: { 课程名称: '新课程配置', 学期: '2025-2026-1', 班级: '1班' },
      threshold: 0.65,
    })
    ElMessage.success('已新建私有课程配置')
    await loadConfig(res.course.course_id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function goStep(idx) {
  if (idx === 5 && !calcResult.value) return
  if (step.value <= 3 && idx === 4 && cfg.value) {
    try {
      const res = await api.saveConfig(cfg.value)
      if (res.config) cfg.value = res.config
      await refreshCourseList()
    } catch (e) {
      ElMessage.warning(`请先完善配置后再上传成绩：${e.message}`)
      return
    }
  }
  step.value = idx
}

function onCalculated(res) {
  calcResult.value = res
  step.value = 5
}

function onViewHistoryReport(res) {
  calcResult.value = res
  activeView.value = 'workbench'
  step.value = 5
}

async function onReloadHistoryStudents(rec) {
  await loadConfig(rec.course_id)
  if (cfg.value) cfg.value.meta['班级'] = rec.class_name
  loadedStudents.value = rec.students || []
  activeView.value = 'workbench'
  step.value = 4
  ElMessage.success(`已将 ${rec.class_name} 的成绩载入纠错表格`)
}

function onLoginSuccess(res) {
  user.value = res.user
  localStorage.setItem('obe_user', JSON.stringify(res.user))
  localStorage.setItem('obe_token', res.token)
  activeView.value = res.user.role === 'admin' ? 'admin' : 'workbench'
  step.value = 0
  loadConfig()
}

function logout() {
  user.value = null
  localStorage.removeItem('obe_user')
  localStorage.removeItem('obe_token')
}

onMounted(() => {
  if (user.value) loadConfig()
})
</script>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 224px;
  background: #ffffff;
  border-right: 1px solid #e5e9f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.side-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 22px 20px;
}

.logo-mark {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #2563eb;
  color: #ffffff;
  font-weight: 700;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.5px;
}

.logo-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.logo-sub {
  font-size: 11.5px;
  color: #94a3b8;
  margin-top: 1px;
}

.side-nav {
  flex: 1;
  padding: 8px 12px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #475569;
  margin-bottom: 4px;
  transition: all 0.15s;
}

.nav-item:hover {
  background: #f8fafc;
  color: #0f172a;
}

.nav-item.active {
  background: #eff6ff;
  color: #2563eb;
  font-weight: 600;
}

.side-footer {
  padding: 16px 18px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #eff6ff;
  color: #2563eb;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
}

.user-name {
  font-size: 13.5px;
  font-weight: 600;
  color: #0f172a;
}

.user-role {
  font-size: 11.5px;
  color: #94a3b8;
}

.main-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  height: 60px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid #e5e9f0;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 20;
}

.top-course-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.top-label {
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
}

.top-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.content {
  padding: 28px 36px 64px;
  max-width: 1240px;
  width: 100%;
  margin: 0 auto;
}

/* 干净独立的 6 步线性进度条 */
.step-track {
  max-width: 820px;
  margin: 0 auto 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  padding: 12px 20px;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  border: 1px solid rgba(226, 232, 240, 0.8);
}

.step-node {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #94a3b8;
  font-size: 13.5px;
  font-weight: 500;
  transition: all 0.15s;
}

.step-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #f1f5f9;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.step-node.done {
  color: #475569;
}

.step-node.done .step-num {
  background: #dbeafe;
  color: #2563eb;
}

.step-node.active {
  color: #0f172a;
  font-weight: 600;
}

.step-node.active .step-num {
  background: #2563eb;
  color: #ffffff;
}

.step-node.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
