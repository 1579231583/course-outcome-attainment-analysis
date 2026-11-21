<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="brand">
        <div class="brand-badge">OBE</div>
        <div>
          <h1>课程目标达成度分析系统</h1>
          <p>高校教学质量评价与工程教育认证工作台</p>
        </div>
      </div>

      <el-tabs v-model="mode" stretch>
        <el-tab-pane label="账号登录" name="login">
          <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
            <el-form-item label="工号 / 账号">
              <el-input v-model="form.username" placeholder="请输入账号" size="large" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="form.password"
                type="password"
                show-password
                placeholder="请输入密码"
                size="large"
                @keyup.enter="handleLogin"
              />
            </el-form-item>
            <el-button
              type="primary"
              size="large"
              style="width: 100%; margin-top: 6px"
              :loading="loading"
              @click="handleLogin"
            >
              登录工作台
            </el-button>
          </el-form>

          <div class="demo-bar">
            <span>快速体验：</span>
            <el-button link type="primary" @click="quickLogin('teacher', '123456')">
              教师端 (teacher)
            </el-button>
            <el-divider direction="vertical" />
            <el-button link type="warning" @click="quickLogin('admin', 'admin123')">
              管理员端 (admin)
            </el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="教师注册" name="register">
          <el-form :model="reg" label-position="top">
            <el-form-item label="账号 / 工号">
              <el-input v-model="reg.username" placeholder="如：t202601" />
            </el-form-item>
            <el-form-item label="姓名">
              <el-input v-model="reg.name" placeholder="如：李老师" />
            </el-form-item>
            <el-form-item label="所属学院">
              <el-input v-model="reg.department" placeholder="如：智能制造学院" />
            </el-form-item>
            <el-form-item label="密码（至少 4 位）">
              <el-input v-model="reg.password" type="password" show-password />
            </el-form-item>
            <el-button
              type="primary"
              size="large"
              style="width: 100%"
              :loading="loading"
              @click="handleRegister"
            >
              注册并登录
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const emit = defineEmits(['success'])
const mode = ref('login')
const loading = ref(false)
const form = reactive({ username: 'teacher', password: '' })
const reg = reactive({ username: '', name: '', department: '', password: '' })

async function handleLogin() {
  loading.value = true
  try {
    const res = await api.login(form)
    ElMessage.success(`欢迎回来，${res.user.name}`)
    emit('success', res)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function quickLogin(username, password) {
  form.username = username
  form.password = password
  await handleLogin()
}

async function handleRegister() {
  loading.value = true
  try {
    const res = await api.register(reg)
    ElMessage.success('注册成功，已自动登录')
    emit('success', { ...res, user: { ...res.user, role: 'teacher' } })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #2563eb 100%);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 430px;
  background: #ffffff;
  border-radius: 16px;
  padding: 32px 34px 28px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.35);
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 22px;
}

.brand-badge {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  background: linear-gradient(135deg, #1e3a8a, #3b82f6);
  color: #fff;
  font-weight: 700;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.5px;
}

.brand h1 {
  margin: 0;
  font-size: 19px;
  color: #0f172a;
}

.brand p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #64748b;
}

.demo-bar {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid #f1f5f9;
  font-size: 13px;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
