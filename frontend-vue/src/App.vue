<template>
  <LoginView v-if="!user" @success="onLoginSuccess" />

  <div v-else class="app-shell">
    <!-- 左侧导航栏 -->
    <aside class="sidebar">
      <div class="side-logo">
        <div class="logo-icon">OBE</div>
        <div>
          <div class="logo-title">达成度分析系统</div>
          <div class="logo-sub">Course Attainment</div>
        </div>
      </div>

      <nav class="side-nav">
        <div
          class="nav-item"
          :class="{ active: activeView === 'workbench' }"
          @click="activeView = 'workbench'"
        >
          <el-icon><DataAnalysis /></el-icon>
          <span>达成度分析工作台</span>
        </div>
        <div
          class="nav-item"
          :class="{ active: activeView === 'history' }"
          @click="activeView = 'history'"
        >
          <el-icon><Document /></el-icon>
          <span>历史报告归档</span>
        </div>
        <div
          v-if="user.role === 'admin'"
          class="nav-item"
          :class="{ active: activeView === 'admin' }"
          @click="activeView = 'admin'"
        >
          <el-icon><Setting /></el-icon>
          <span>教务管理后台</span>
        </div>
      </nav>

      <div class="side-footer">
        <div class="user-info">
          <div class="avatar">{{ (user.name || '教')[0] }}</div>
          <div>
            <div class="user-name">{{ user.name }}</div>
            <div class="user-role">{{ user.role === 'admin' ? '教务管理员' : '任课教师' }}</div>
          </div>
        </div>
        <el-button link type="info" size="small" @click="logout">退出</el-button>
      </div>
    </aside>

    <!-- 右侧主内容区 -->
    <div class="main-wrap">
      <header class="topbar">
        <div class="top-left">
          <template v-if="activeView === 'workbench' && cfg">
            <span class="top-label">当前课程：</span>
            <el-select
              :model-value="cfg.course_id"
              size="small"
              style="width: 240px"
              @change="switchCourse"
            >
              <el-option
                v-for="c in courses"
                :key="c.id"
                :label="`${c.course_name} (${c.semester})${c.is_public ? ' [公共]' : ''}`"
                :value="c.id"
              />
            </el-select>
            <el-button size="small" plain @click="createNewCourse">+ 新建课程</el-button>
          </template>
          <span v-else-if="activeView === 'history'" class="top-title">历史班级达成度报告</span>
          <span v-else class="top-title">教务管理后台（模板库 · 账号 · 全院监控）</span>
        </div>

        <div v-if="activeView === 'workbench'" class="stepper">
          <div
            v-for="(label, idx) in [
              '1 选课程',
              '2 定占比',
              '3 配目标',
              '4 配试卷',
              '5 传成绩',
              '6 看报告',
            ]"
            :key="idx"
            class="step-pill"
            :class="{ active: step === idx, done: idx < step, disabled: idx === 5 && !calcResult }"
            @click="goStep(idx)"
          >
            {{ label }}
          </div>
        </div>
      </header>

      <main class="content">
        <template v-if="activeView === 'workbench' && cfg">
          <ConfigStep
            v-if="step <= 3"
            :cfg="cfg"
            :current-step="step"
            @saved="refreshCourseList"
            @go-step="(s) => (step = s)"
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
      meta: { 课程名称: '新课程配置', 学期: '2024-2025-1', 班级: '1班' },
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
  // P0-4：从配置步骤(0~3)跳到上传步骤(4)时，自动同步保存最新配置，杜绝拿旧配置解析
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
  ElMessage.success(`已将 ${rec.class_name} 的成绩载入纠错表格，修改后可重新计算`)
}

function onLoginSuccess(res) {
  user.value = res.user
  localStorage.setItem('obe_user', JSON.stringify(res.user))
  localStorage.setItem('obe_token', res.token)
  // 管理员登录后默认直达教务管理后台，教师默认进入工作台
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
  width: 230px;
  background: #0f172a;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.side-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.logo-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: #fff;
  font-weight: 700;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-title {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
}

.logo-sub {
  font-size: 11px;
  color: #94a3b8;
}

.side-nav {
  flex: 1;
  padding: 14px 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #cbd5e1;
  margin-bottom: 4px;
  transition: all 0.15s;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
}

.nav-item.active {
  background: #2563eb;
  color: #fff;
  font-weight: 500;
}

.side-footer {
  padding: 14px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
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
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #334155;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 13px;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
}

.user-role {
  font-size: 11px;
  color: #94a3b8;
}

.main-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.top-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.top-label {
  font-size: 13px;
  color: #64748b;
}

.top-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.stepper {
  display: flex;
  gap: 8px;
}

.step-pill {
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  background: #f1f5f9;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
}

.step-pill.done {
  background: #eff6ff;
  color: #2563eb;
}

.step-pill.active {
  background: #2563eb;
  color: #fff;
  font-weight: 600;
}

.step-pill.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.content {
  padding: 20px 24px 48px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}
</style>
