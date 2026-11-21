<template>
  <el-tabs v-model="tab" type="border-card">
    <!-- 1. 公共课程规则模板库管理 -->
    <el-tab-pane label="公共课程模板库管理" name="templates">
      <div class="bar">
        <div>
          <strong>批量导入公共课程规则（一个 Excel，每个工作表 = 一门课）</strong>
          <p class="panel-sub" style="margin: 4px 0 0">
            下载模板后，每门课占一个工作表，一页从上到下填完；新增课程右键工作表标签“移动或复制 → 建立副本”即可。上传后逐门校验，失败的课程不影响其他课程发布。
          </p>
        </div>
        <div class="actions">
          <el-button plain @click="downloadConfigTpl">
            <el-icon><Download /></el-icon>&nbsp;下载《课程规则配置模板.xlsx》
          </el-button>
          <input
            ref="batchInputRef"
            type="file"
            accept=".xlsx"
            multiple
            style="display: none"
            @change="handleBatchFiles"
          />
          <el-button type="primary" :loading="batchUploading" @click="batchInputRef?.click()">
            <el-icon><Upload /></el-icon>&nbsp;批量上传 Excel 发布公共模板（可多选）
          </el-button>
        </div>
      </div>

      <!-- 批量导入结果明细 -->
      <el-alert
        v-if="batchReport"
        :type="batchReport.fail_count === 0 ? 'success' : 'warning'"
        show-icon
        style="margin-top: 12px"
        :title="`批量导入完成：共 ${batchReport.total} 个文件，成功发布 ${batchReport.success_count} 门课程，失败 ${batchReport.fail_count} 个`"
      />
      <el-table
        v-if="batchReport?.results?.length"
        :data="batchReport.results"
        border
        size="small"
        style="margin-top: 8px"
      >
        <el-table-column prop="filename" label="文件名" min-width="180" />
        <el-table-column prop="course_name" label="解析课程名" width="160" />
        <el-table-column prop="semester" label="学期" width="110" align="center" />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.ok ? 'success' : 'danger'" size="small">
              {{ row.ok ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="详情说明" min-width="200" />
      </el-table>

      <el-table :data="templates" border stripe size="small" style="margin-top: 14px">
        <el-table-column prop="course_name" label="课程名称" min-width="160" />
        <el-table-column prop="course_code" label="课程代码" width="120" align="center" />
        <el-table-column prop="semester" label="学期" width="120" align="center" />
        <el-table-column label="合格阈值" width="100" align="center">
          <template #default="{ row }">{{ (row.pass_threshold * 100).toFixed(0) }}%</template>
        </el-table-column>
        <el-table-column prop="updated_at" label="发布时间" width="160" align="center" />
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="deleteTpl(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-tab-pane>

    <!-- 2. 教师账号管理 -->
    <el-tab-pane label="教师账号管理" name="users">
      <div class="bar">
        <strong>系统用户列表</strong>
        <el-button type="primary" size="small" @click="addUserDialog = true">+ 新增教师账号</el-button>
      </div>

      <el-table :data="users" border stripe size="small" style="margin-top: 14px">
        <el-table-column prop="username" label="账号 / 工号" width="140" />
        <el-table-column prop="name" label="姓名" width="120" />
        <el-table-column prop="department" label="所属院系" min-width="150" />
        <el-table-column label="角色" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'warning' : 'primary'" size="small">
              {{ row.role === 'admin' ? '管理员' : '教师' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '正常' : '已禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160" align="center" />
        <el-table-column label="操作" width="180" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="resetPwd(row)">重置密码</el-button>
            <el-button
              link
              :type="row.is_active ? 'danger' : 'success'"
              size="small"
              :disabled="row.username === 'admin'"
              @click="toggleUser(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-tab-pane>

    <!-- 3. 全院达成度汇总监控 -->
    <el-tab-pane label="全院达成度汇总监控" name="overview">
      <div v-if="overview" class="kpi-grid tabular-nums">
        <div class="kpi-card">
          <div class="panel-sub">注册教师总数</div>
          <div class="kpi-value">{{ overview.teacher_count }}</div>
        </div>
        <div class="kpi-card">
          <div class="panel-sub">已发布公共课程模板</div>
          <div class="kpi-value">{{ overview.public_template_count }}</div>
        </div>
        <div class="kpi-card">
          <div class="panel-sub">已归档班级报告数</div>
          <div class="kpi-value">{{ overview.report_count }}</div>
        </div>
        <div class="kpi-card">
          <div class="panel-sub">全院课程目标总体达标率</div>
          <div class="kpi-value" style="color: #059669">
            {{ (overview.overall_pass_rate * 100).toFixed(1) }}%
          </div>
        </div>
      </div>

      <h4 style="margin: 14px 0 8px">未达标课程目标预警清单</h4>
      <el-table :data="overview?.unpassed_alerts || []" border size="small" class="tabular-nums">
        <el-table-column prop="course_name" label="课程名称" min-width="150" />
        <el-table-column prop="semester" label="学期" width="120" align="center" />
        <el-table-column prop="class_name" label="班级" width="140" align="center" />
        <el-table-column prop="target" label="未达标目标" width="120" align="center" />
        <el-table-column label="实际达成度" width="110" align="center">
          <template #default="{ row }">
            <span style="color: #dc2626; font-weight: 600">
              {{ (row.achievement * 100).toFixed(1) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="合格线" width="90" align="center">
          <template #default="{ row }">{{ (row.threshold * 100).toFixed(0) }}%</template>
        </el-table-column>
      </el-table>
    </el-tab-pane>
  </el-tabs>

  <!-- 新增用户弹窗 -->
  <el-dialog v-model="addUserDialog" title="新增系统账号" width="400px">
    <el-form :model="newUser" label-width="80px">
      <el-form-item label="账号">
        <el-input v-model="newUser.username" placeholder="工号/登录名" />
      </el-form-item>
      <el-form-item label="姓名">
        <el-input v-model="newUser.name" placeholder="教师姓名" />
      </el-form-item>
      <el-form-item label="所属院系">
        <el-input v-model="newUser.department" placeholder="如：智能制造学院" />
      </el-form-item>
      <el-form-item label="初始密码">
        <el-input v-model="newUser.password" />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="newUser.role" style="width: 100%">
          <el-option label="教师" value="teacher" />
          <el-option label="管理员" value="admin" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="addUserDialog = false">取消</el-button>
      <el-button type="primary" @click="createUser">确定创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, downloadBlob } from '../api/client'

const tab = ref('templates')
const templates = ref([])
const users = ref([])
const overview = ref(null)
const addUserDialog = ref(false)
const batchInputRef = ref(null)
const batchUploading = ref(false)
const batchReport = ref(null)
const newUser = reactive({
  username: '',
  name: '',
  department: '',
  password: '123456',
  role: 'teacher',
})

async function refreshAll() {
  try {
    const [tRes, uRes, oRes] = await Promise.all([
      api.listPublicTemplates(),
      api.adminListUsers(),
      api.adminOverview(),
    ])
    templates.value = tRes.templates || []
    users.value = uRes.users || []
    overview.value = oRes.overview
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function downloadConfigTpl() {
  try {
    await downloadBlob('/api/templates/course-config-excel', '课程规则配置模板.xlsx')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleBatchFiles(e) {
  const files = Array.from(e.target.files || [])
  if (!files.length) return
  batchUploading.value = true
  try {
    const res = await api.importCourseTemplateBatch(files)
    batchReport.value = res
    if (res.fail_count === 0) {
      ElMessage.success(`批量发布成功：共 ${res.success_count} 门公共课程模板`)
    } else {
      ElMessage.warning(`批量导入完成：成功 ${res.success_count} 门，失败 ${res.fail_count} 个`)
    }
    await refreshAll()
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    batchUploading.value = false
    if (batchInputRef.value) batchInputRef.value.value = ''
  }
}

async function deleteTpl(id) {
  try {
    await api.deleteCourse(id)
    ElMessage.success('已删除模板')
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function createUser() {
  try {
    await api.adminCreateUser(newUser)
    ElMessage.success('账号创建成功')
    addUserDialog.value = false
    Object.assign(newUser, { username: '', name: '', department: '', password: '123456', role: 'teacher' })
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function toggleUser(row) {
  try {
    await api.adminToggleUser(row.id)
    ElMessage.success('账号状态已更新')
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function resetPwd(row) {
  try {
    const res = await api.adminResetPassword(row.id, '123456')
    ElMessage.success(res.message)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(refreshAll)
</script>

<style scoped>
.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
