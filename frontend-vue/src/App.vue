<template>
  <LoginView v-if="!user" @success="onLoginSuccess" />

  <div v-else class="app-shell">
    <!-- 极简左侧边栏：管理员 2 项，教师仅 1 项核心导航 -->
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
          :class="{ active: activeView === 'tasks' }"
          @click="goTaskList"
        >
          <el-icon><DataAnalysis /></el-icon>
          <span>我的班级分析</span>
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
      <header class="topbar">
        <div v-if="activeView === 'tasks'" class="breadcrumb">
          <template v-if="mode === 'list'">
            <span class="bc-current">我的班级分析</span>
          </template>
          <template v-else-if="mode === 'score' && currentTask">
            <span class="bc-link" @click="goTaskList">← 返回班级列表</span>
            <span class="bc-sep">/</span>
            <span class="bc-current">{{ currentTask.course_name }} · {{ currentTask.class_name }}</span>
          </template>
          <template v-else-if="mode === 'report' && currentTask">
            <span class="bc-link" @click="goTaskList">我的班级分析</span>
            <span class="bc-sep">/</span>
            <span class="bc-link" @click="mode = 'score'">{{ currentTask.course_name }} · {{ currentTask.class_name }}</span>
            <span class="bc-sep">/</span>
            <span class="bc-current">达成度诊断报告</span>
          </template>
        </div>
        <div v-else class="bc-current">教务管理后台</div>
      </header>

      <main class="content">
        <template v-if="activeView === 'tasks'">
          <TaskList
            v-if="mode === 'list'"
            :tasks="tasks"
            :loading="tasksLoading"
            @open-score="openTaskScore"
            @open-report="openTaskReport"
            @refresh="refreshTasks"
          />
          <ScoreStep
            v-else-if="mode === 'score' && currentTask"
            :task="currentTask"
            @task-updated="onTaskUpdated"
            @calculated="onCalculated"
            @view-report="mode = 'report'"
          />
          <ReportStep
            v-else-if="mode === 'report' && currentTask"
            :task="currentTask"
            @back="mode = 'score'"
          />
        </template>

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
import TaskList from './components/TaskList.vue'
import ScoreStep from './components/ScoreStep.vue'
import ReportStep from './components/ReportStep.vue'
import AdminView from './components/AdminView.vue'

const user = ref(JSON.parse(localStorage.getItem('obe_user') || 'null'))
const activeView = ref(user.value?.role === 'admin' ? 'admin' : 'tasks')
const mode = ref('list') // 'list' | 'score' | 'report'
const tasks = ref([])
const tasksLoading = ref(false)
const currentTask = ref(null)

async function refreshTasks() {
  tasksLoading.value = true
  try {
    const res = await api.listTasks()
    tasks.value = res.tasks || []
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    tasksLoading.value = false
  }
}

function goTaskList() {
  activeView.value = 'tasks'
  mode.value = 'list'
  currentTask.value = null
  refreshTasks()
}

async function openTaskScore(taskId) {
  try {
    const res = await api.getTask(taskId)
    currentTask.value = res.task
    activeView.value = 'tasks'
    mode.value = 'score'
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function openTaskReport(taskId) {
  try {
    const res = await api.getTask(taskId)
    currentTask.value = res.task
    activeView.value = 'tasks'
    mode.value = res.task.status === 'completed' ? 'report' : 'score'
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function onTaskUpdated(updatedTask) {
  currentTask.value = updatedTask
  refreshTasks()
}

function onCalculated(updatedTask) {
  currentTask.value = updatedTask
  mode.value = 'report'
  refreshTasks()
}

function onLoginSuccess(res) {
  user.value = res.user
  localStorage.setItem('obe_user', JSON.stringify(res.user))
  localStorage.setItem('obe_token', res.token)
  activeView.value = res.user.role === 'admin' ? 'admin' : 'tasks'
  mode.value = 'list'
  refreshTasks()
}

function logout() {
  user.value = null
  currentTask.value = null
  localStorage.removeItem('obe_user')
  localStorage.removeItem('obe_token')
}

onMounted(() => {
  if (user.value) refreshTasks()
})
</script>

<style scoped>
.app-shell { display: flex; min-height: 100vh; }
.sidebar {
  width: 224px;
  background: #ffffff;
  border-right: 1px solid #e5e9f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.side-logo { display: flex; align-items: center; gap: 12px; padding: 22px 20px; }
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
}
.logo-title { font-size: 15px; font-weight: 700; color: #0f172a; }
.logo-sub { font-size: 11.5px; color: #94a3b8; margin-top: 1px; }
.side-nav { flex: 1; padding: 8px 12px; }
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
.nav-item:hover { background: #f8fafc; color: #0f172a; }
.nav-item.active { background: #eff6ff; color: #2563eb; font-weight: 600; }
.side-footer {
  padding: 16px 18px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.user-info { display: flex; align-items: center; gap: 10px; }
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
.user-name { font-size: 13.5px; font-weight: 600; color: #0f172a; }
.user-role { font-size: 11.5px; color: #94a3b8; }
.main-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.topbar {
  height: 58px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid #e5e9f0;
  padding: 0 36px;
  display: flex;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 20;
}
.breadcrumb { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.bc-link { color: #475569; cursor: pointer; font-weight: 500; transition: color 0.15s; }
.bc-link:hover { color: #2563eb; }
.bc-sep { color: #cbd5e1; }
.bc-current { font-size: 15px; font-weight: 600; color: #0f172a; }
.content {
  padding: 28px 36px 48px;
  max-width: 1280px;
  width: 100%;
  margin: 0 auto;
}
</style>
