<template>
  <div class="admin-page">
    <!-- 干净的无边框下划线导航（彻底砍掉丑陋的 border-card 外壳！） -->
    <el-tabs v-model="tab" class="admin-tabs">
      <!-- ==================== Tab 1：公共课程大纲库 ==================== -->
      <el-tab-pane label="公共课程大纲库" name="templates">
        <div class="page-header" style="margin-top: 8px">
          <div>
            <h1>公共课程大纲库</h1>
            <p>上传《教学大纲 PDF》自动提取课程底座，统考大课可补充 4 列试卷模板</p>
          </div>
          <div>
            <input
              ref="pdfInputRef"
              type="file"
              accept=".pdf"
              multiple
              style="display: none"
              @change="handlePreviewPdfFiles"
            />
            <el-button type="primary" size="large" :loading="previewLoading" @click="pdfInputRef?.click()">
              <el-icon><Upload /></el-icon>&nbsp;上传《教学大纲 PDF》
            </el-button>
          </div>
        </div>

        <!-- 大纲 PDF 提取预览区（仅在刚上传 PDF 时出现） -->
        <div v-if="drafts.length > 0" class="panel-card preview-highlight">
          <div class="panel-title">
            <span>大纲提取结果确认（共 {{ drafts.length }} 门课）</span>
            <div class="actions">
              <el-button plain @click="drafts = []">取消</el-button>
              <el-button
                type="primary"
                :disabled="validDraftCourses.length === 0 || invalidDraftCount > 0"
                :loading="publishing"
                @click="confirmPublishBatch"
              >
                确认发布 {{ validDraftCourses.length }} 门到公共大纲库
              </el-button>
            </div>
          </div>

          <div v-if="drafts.length > 1" class="course-tabs">
            <div
              v-for="(d, idx) in drafts"
              :key="idx"
              class="c-pill"
              :class="{ active: activeDraftIdx === idx, err: draftErrors(d).length > 0 }"
              @click="activeDraftIdx = idx"
            >
              <span>{{ d.course?.meta?.['课程名称'] || d.sheet }}</span>
              <span class="remove-x" @click.stop="removeDraft(idx)">×</span>
            </div>
          </div>

          <div v-if="currentDraft && currentCourse">
            <el-alert
              v-if="draftErrors(currentDraft).length > 0"
              type="error"
              show-icon
              :closable="false"
              style="margin-bottom: 16px"
              :title="draftErrors(currentDraft).join(' ； ')"
            />

            <div
              v-if="Object.keys(currentCourse.target_descriptions || {}).length"
              class="pdf-summary-strip"
            >
              <div class="strip-title">已提取课程目标与毕业要求指标点</div>
              <div
                v-for="(desc, tg) in currentCourse.target_descriptions"
                :key="tg"
                class="strip-line"
              >
                <b>{{ tg }}</b>：{{ desc }}
              </div>
            </div>

            <div class="sub-block-title">课程基本信息</div>
            <el-row :gutter="14">
              <el-col :xs="12" :sm="6">
                <div class="fl">课程名称</div>
                <el-input v-model="currentCourse.meta['课程名称']" />
              </el-col>
              <el-col :xs="12" :sm="4">
                <div class="fl">课程代码</div>
                <el-input v-model="currentCourse.meta['课程代码']" />
              </el-col>
              <el-col :xs="12" :sm="4">
                <div class="fl">开课学期</div>
                <el-input v-model="currentCourse.meta['学期']" />
              </el-col>
              <el-col :xs="12" :sm="4">
                <div class="fl">课程类别</div>
                <el-input v-model="currentCourse.meta['课程类别']" />
              </el-col>
              <el-col :xs="12" :sm="3">
                <div class="fl">合格线</div>
                <el-input-number v-model="currentCourse.threshold" :controls="false" :precision="2" style="width: 100%" />
              </el-col>
              <el-col :xs="12" :sm="3">
                <div class="fl">学分 / 学时</div>
                <div style="display: flex; gap: 6px">
                  <el-input-number v-model="currentCourse.meta['学分']" :controls="false" style="width: 50%" />
                  <el-input-number v-model="currentCourse.meta['授课学时']" :controls="false" style="width: 50%" />
                </div>
              </el-col>
            </el-row>

            <div class="sub-block-title" style="margin-top: 20px">大纲考核环节对应矩阵</div>
            <el-table :data="curTargets" class="tabular-nums">
              <el-table-column label="课程目标" width="120">
                <template #default="{ row }"><strong>{{ row }}</strong></template>
              </el-table-column>
              <el-table-column v-for="link in curAllLinks" :key="link" :label="link" align="center">
                <template #default="{ row }">
                  <el-input-number
                    v-model="currentCourse.matrix[row][link]"
                    :controls="false"
                    size="small"
                    :min="0"
                    :precision="2"
                    style="width: 76px"
                  />
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <!-- 3 张极简状态筛选统计卡（一眼分清：全部 / 仅大纲 / 大纲+试卷齐全） -->
        <div class="kpi-filter-row tabular-nums">
          <div class="kf-item" :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'">
            <div class="kf-top">
              <span class="kf-dot blue"></span>
              <span>全部公共课程</span>
            </div>
            <div class="kf-val">{{ templates.length }}</div>
          </div>

          <div class="kf-item amber" :class="{ active: statusFilter === 'only_syllabus' }" @click="statusFilter = 'only_syllabus'">
            <div class="kf-top">
              <span class="kf-dot amber"></span>
              <span>仅大纲 · 待配试卷</span>
            </div>
            <div class="kf-val">{{ onlySyllabusCount }}</div>
          </div>

          <div class="kf-item green" :class="{ active: statusFilter === 'ready' }" @click="statusFilter = 'ready'">
            <div class="kf-top">
              <span class="kf-dot green"></span>
              <span>大纲 + 试卷齐全</span>
            </div>
            <div class="kf-val">{{ fullReadyCount }}</div>
          </div>
        </div>

        <input
          ref="paperImportRef"
          type="file"
          accept=".xlsx"
          style="display: none"
          @change="handleAdminPaperImport"
        />

        <!-- 清晰舒朗的课程卡片网格 -->
        <div v-if="filteredTemplates.length > 0" class="course-grid">
          <div v-for="row in filteredTemplates" :key="row.id" class="c-card">
            <div class="c-card-head">
              <div>
                <div class="c-name">{{ row.course_name }}</div>
                <div class="c-sub tabular-nums">{{ row.course_code || '无代码' }} · {{ row.semester }}</div>
              </div>
              <span class="status-pill" :class="row.has_paper ? 'ready' : 'pending'">
                {{ row.has_paper ? '大纲 + 试卷齐全' : '仅大纲' }}
              </span>
            </div>

            <div class="c-checklist">
              <div class="chk-row ok">
                <span class="chk-icon">✓</span>
                <span>教学大纲底座已入库</span>
              </div>
              <div class="chk-row" :class="row.has_paper ? 'ok' : 'wait'">
                <span class="chk-icon">{{ row.has_paper ? '✓' : '·' }}</span>
                <span v-if="row.has_paper">统考试卷已配置（{{ row.question_count }} 题 · 100 分）</span>
                <span v-else>暂未配置统考试卷（可留给教师自配）</span>
              </div>
            </div>

            <div class="c-card-foot">
              <el-button type="primary" link @click="triggerRowPaperImport(row)">
                {{ row.has_paper ? '重传试卷' : '上传试卷模板' }}
              </el-button>
              <el-button link @click="downloadRowPaperTpl(row)">下载试卷模板</el-button>
              <el-button v-if="row.has_paper" link @click="openExistingPaper(row)">调整小题</el-button>
              <el-button link type="danger" style="margin-left: auto" @click="deleteTpl(row.id)">删除</el-button>
            </div>
          </div>
        </div>
        <div v-else class="panel-card">
          <el-empty description="当前分类下暂无课程，点击右上角上传《教学大纲 PDF》" />
        </div>
      </el-tab-pane>

      <!-- ==================== Tab 2：教师账号管理 ==================== -->
      <el-tab-pane label="教师账号管理" name="users">
        <div class="page-header" style="margin-top: 8px">
          <div>
            <h1>教师账号管理</h1>
            <p>统一管理任课教师登录账号、状态与密码重置</p>
          </div>
          <el-button type="primary" size="large" @click="addUserDialog = true">+ 新增教师账号</el-button>
        </div>

        <div class="panel-card">
          <el-table :data="users">
            <el-table-column prop="username" label="账号 / 工号" width="150" />
            <el-table-column prop="name" label="姓名" width="130">
              <template #default="{ row }"><strong>{{ row.name }}</strong></template>
            </el-table-column>
            <el-table-column prop="department" label="所属院系" min-width="160" />
            <el-table-column label="角色" width="110" align="center">
              <template #default="{ row }">
                <span class="status-pill" :class="row.role === 'admin' ? 'pending' : 'blue'">
                  {{ row.role === 'admin' ? '管理员' : '教师' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <span class="status-pill" :class="row.is_active ? 'ready' : 'gray'">
                  {{ row.is_active ? '正常' : '已禁用' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="180" align="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="resetPwd(row)">重置密码</el-button>
                <el-button
                  link
                  :type="row.is_active ? 'danger' : 'success'"
                  :disabled="row.username === 'admin'"
                  @click="toggleUser(row)"
                >
                  {{ row.is_active ? '禁用' : '启用' }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- ==================== Tab 3：全院达成度汇总监控 ==================== -->
      <el-tab-pane label="全院达成度监控" name="overview">
        <div class="page-header" style="margin-top: 8px">
          <div>
            <h1>全院达成度汇总监控</h1>
            <p>实时掌握各教学班达成度上报进度与未达标预警</p>
          </div>
        </div>

        <div v-if="overview" class="kpi-grid tabular-nums">
          <div class="kpi-card">
            <div class="kf-top">注册教师</div>
            <div class="kpi-value">{{ overview.teacher_count }}</div>
          </div>
          <div class="kpi-card">
            <div class="kf-top">公共课程大纲</div>
            <div class="kpi-value">{{ overview.public_template_count }}</div>
          </div>
          <div class="kpi-card">
            <div class="kf-top">已归档班级报告</div>
            <div class="kpi-value">{{ overview.report_count }}</div>
          </div>
          <div class="kpi-card">
            <div class="kf-top">全院目标总体达标率</div>
            <div class="kpi-value" style="color: #059669">
              {{ (overview.overall_pass_rate * 100).toFixed(1) }}%
            </div>
          </div>
        </div>

        <div class="panel-card">
          <div class="panel-title"><span>未达标课程目标预警清单</span></div>
          <el-table :data="overview?.unpassed_alerts || []" class="tabular-nums">
            <el-table-column prop="course_name" label="课程名称" min-width="160" />
            <el-table-column prop="semester" label="学期" width="120" align="center" />
            <el-table-column prop="class_name" label="班级" width="150" align="center" />
            <el-table-column prop="target" label="未达标目标" width="120" align="center" />
            <el-table-column label="实际达成度" width="120" align="center">
              <template #default="{ row }">
                <strong style="color: #dc2626">{{ (row.achievement * 100).toFixed(1) }}%</strong>
              </template>
            </el-table-column>
            <el-table-column label="合格线" width="100" align="center">
              <template #default="{ row }">{{ (row.threshold * 100).toFixed(0) }}%</template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 统考课：期末试卷结构在线预览与实时调整弹窗 -->
    <el-dialog
      v-model="paperDialog.visible"
      :title="`《${paperDialog.courseName}》期末试卷结构调整`"
      width="740px"
    >
      <div class="bar" style="margin-bottom: 14px">
        <div class="actions tabular-nums">
          <span class="status-pill" :class="paperModalTotal === 100 ? 'ready' : 'danger'">
            试卷总分 {{ paperModalTotal }} / 100 分（共 {{ paperModalFlat.length }} 题）
          </span>
          <span v-for="t in paperDialog.targets" :key="t" class="status-pill gray">
            {{ t }} {{ paperModalTargetFull[t] || 0 }}分
          </span>
        </div>
        <el-button size="small" plain @click="addPaperModalQuestion">+ 新增小题</el-button>
      </div>

      <el-alert
        v-if="paperModalErrors.length > 0"
        type="error"
        show-icon
        :closable="false"
        style="margin-bottom: 12px"
        :title="paperModalErrors.join(' ； ')"
      />

      <el-table :data="paperModalFlat" max-height="360" class="tabular-nums">
        <el-table-column label="大题名称" min-width="150">
          <template #default="{ row }">
            <el-input v-model="row.groupRef['大题']" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="题号" width="75" align="center">
          <template #default="{ $index }">第 {{ $index + 1 }} 题</template>
        </el-table-column>
        <el-table-column label="满分" width="120" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.q['满分']" :controls="false" size="small" :min="0.5" :max="100" style="width: 80px" />
          </template>
        </el-table-column>
        <el-table-column label="归属课程目标" width="160">
          <template #default="{ row }">
            <el-select v-model="row.q['目标']" size="small" style="width: 100%">
              <el-option v-for="t in paperDialog.targets" :key="t" :label="t" :value="t" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="" width="65" align="center">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removePaperModalQuestion(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="paperDialog.visible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="paperModalErrors.length > 0"
          :loading="paperDialog.saving"
          @click="confirmSavePaperModal"
        >
          确认保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 新增用户弹窗 -->
    <el-dialog v-model="addUserDialog" title="新增教师账号" width="400px">
      <el-form :model="newUser" label-position="top">
        <el-form-item label="账号 / 工号"><el-input v-model="newUser.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="newUser.name" /></el-form-item>
        <el-form-item label="所属院系"><el-input v-model="newUser.department" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="newUser.password" /></el-form-item>
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
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const tab = ref('templates')
const statusFilter = ref('all')
const templates = ref([])
const users = ref([])
const overview = ref(null)
const addUserDialog = ref(false)
const pdfInputRef = ref(null)
const paperImportRef = ref(null)
const paperImportCourseId = ref(null)
const previewLoading = ref(false)
const publishing = ref(false)
const drafts = ref([])
const activeDraftIdx = ref(0)

const paperDialog = reactive({
  visible: false,
  saving: false,
  courseId: null,
  courseName: '',
  targets: [],
  matrix: {},
  method: {},
  paper: [],
})

const newUser = reactive({
  username: '',
  name: '',
  department: '',
  password: '123456',
  role: 'teacher',
})

const onlySyllabusCount = computed(() => templates.value.filter((t) => !t.has_paper).length)
const fullReadyCount = computed(() => templates.value.filter((t) => t.has_paper).length)
const filteredTemplates = computed(() => {
  if (statusFilter.value === 'only_syllabus') return templates.value.filter((t) => !t.has_paper)
  if (statusFilter.value === 'ready') return templates.value.filter((t) => t.has_paper)
  return templates.value
})

const currentDraft = computed(() => drafts.value[activeDraftIdx.value] || null)
const currentCourse = computed(() => currentDraft.value?.course || null)
const curAllLinks = computed(() =>
  currentCourse.value ? [...Object.keys(currentCourse.value.method['平时环节'] || {}), '期末考试'] : []
)
const curTargets = computed(() => Object.keys(currentCourse.value?.matrix || {}))

function draftErrors(d) {
  if (!d) return []
  if (!d.course) return d.errors || ['PDF 解析失败']
  const c = d.course
  const errs = []
  if (!(c.meta?.['课程名称'] || '').trim()) errs.push('课程名称不能为空')
  const targets = Object.keys(c.matrix || {})
  const links = [...Object.keys(c.method?.['平时环节'] || {}), '期末考试']
  for (const l of links) {
    const colSum = targets.reduce((a, t) => a + (Number(c.matrix[t]?.[l]) || 0), 0)
    if (colSum <= 0) errs.push(`矩阵中「${l}」整列比例之和为 0`)
  }
  return errs
}

const invalidDraftCount = computed(() => drafts.value.filter((d) => draftErrors(d).length > 0).length)
const validDraftCourses = computed(() =>
  drafts.value.filter((d) => d.course && draftErrors(d).length === 0).map((d) => d.course)
)

const paperModalFlat = computed(() => {
  const out = []
  for (const g of paperDialog.paper || []) {
    for (let i = 0; i < (g['小题'] || []).length; i++) out.push({ groupRef: g, qIdx: i, q: g['小题'][i] })
  }
  return out
})
const paperModalTotal = computed(() =>
  paperModalFlat.value.reduce((a, it) => a + (Number(it.q['满分']) || 0), 0)
)
const paperModalTargetFull = computed(() => {
  const m = {}
  for (const it of paperModalFlat.value) m[it.q['目标']] = (m[it.q['目标']] || 0) + (Number(it.q['满分']) || 0)
  return m
})
const paperModalErrors = computed(() => {
  const errs = []
  if (paperModalFlat.value.length === 0) errs.push('请至少配置一道小题')
  if (Math.abs(paperModalTotal.value - 100) > 1e-6) errs.push(`试卷总分为 ${paperModalTotal.value} 分，须等于 100 分`)
  if ((Number(paperDialog.method?.['期末占比']) || 0) > 0) {
    for (const t of paperDialog.targets) {
      if ((Number(paperDialog.matrix?.[t]?.['期末考试']) || 0) > 0 && (paperModalTargetFull.value[t] || 0) <= 0) {
        errs.push(`「${t}」设有期末权重，请至少分配一道属该目标的小题`)
      }
    }
  }
  return errs
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

async function handlePreviewPdfFiles(e) {
  const files = Array.from(e.target.files || [])
  if (!files.length) return
  previewLoading.value = true
  try {
    const res = await api.previewSyllabusPdfBatch(files)
    drafts.value = res.drafts || []
    activeDraftIdx.value = 0
    ElMessage.success(`已提取 ${drafts.value.length} 份《教学大纲 PDF》，请核对后发布`)
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    previewLoading.value = false
    if (pdfInputRef.value) pdfInputRef.value.value = ''
  }
}

function removeDraft(idx) {
  drafts.value.splice(idx, 1)
  if (activeDraftIdx.value >= drafts.value.length) activeDraftIdx.value = Math.max(0, drafts.value.length - 1)
}

async function confirmPublishBatch() {
  publishing.value = true
  try {
    const res = await api.publishCourseTemplateBatch(validDraftCourses.value)
    ElMessage.success(`已发布 ${res.success_count} 门课程到全院公共大纲库`)
    drafts.value = []
    await refreshAll()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    publishing.value = false
  }
}

async function downloadRowPaperTpl(row) {
  try {
    await api.downloadPaperTemplate(row.id, row.course_name)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function triggerRowPaperImport(row) {
  paperImportCourseId.value = row.id
  paperImportRef.value?.click()
}

async function handleAdminPaperImport(e) {
  const file = e.target.files?.[0]
  if (!file || !paperImportCourseId.value) return
  try {
    const res = await api.previewPaperExcel(paperImportCourseId.value, file)
    Object.assign(paperDialog, {
      courseId: res.course_id,
      courseName: res.course_name,
      targets: res.targets || [],
      matrix: res.matrix || {},
      method: res.method || {},
      paper: res.paper || [],
      visible: true,
    })
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    if (paperImportRef.value) paperImportRef.value.value = ''
  }
}

async function openExistingPaper(row) {
  try {
    const cfg = await api.getConfig(row.id)
    Object.assign(paperDialog, {
      courseId: cfg.course_id,
      courseName: cfg.meta['课程名称'],
      targets: Object.keys(cfg.matrix || {}),
      matrix: cfg.matrix || {},
      method: cfg.method || {},
      paper: JSON.parse(JSON.stringify(cfg.paper || [])),
      visible: true,
    })
  } catch (err) {
    ElMessage.error(err.message)
  }
}

function addPaperModalQuestion() {
  if (!paperDialog.paper.length) paperDialog.paper.push({ 大题: '一、新增大题', 小题: [] })
  paperDialog.paper[paperDialog.paper.length - 1]['小题'].push({
    题号: paperModalFlat.value.length + 1,
    满分: 5,
    目标: paperDialog.targets[0] || '课程目标1',
  })
}

function removePaperModalQuestion(item) {
  item.groupRef['小题'].splice(item.qIdx, 1)
}

async function confirmSavePaperModal() {
  paperDialog.saving = true
  try {
    const res = await api.savePaperJson(paperDialog.courseId, paperDialog.paper)
    ElMessage.success(res.message)
    paperDialog.visible = false
    await refreshAll()
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    paperDialog.saving = false
  }
}

async function deleteTpl(id) {
  try {
    await api.deleteCourse(id)
    ElMessage.success('已删除')
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
.actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

/* 3 张极简状态筛选卡 */
.kpi-filter-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-bottom: 24px;
}
.kf-item {
  background: #ffffff;
  border: 1.5px solid transparent;
  border-radius: 14px;
  padding: 20px 24px;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: all 0.15s;
}
.kf-item:hover {
  transform: translateY(-2px);
}
.kf-item.active {
  border-color: #2563eb;
  background: #f8fbff;
}
.kf-item.amber.active {
  border-color: #f59e0b;
  background: #fffdf5;
}
.kf-item.green.active {
  border-color: #10b981;
  background: #f4fdf9;
}
.kf-top {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
}
.kf-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.kf-dot.blue { background: #2563eb; }
.kf-dot.amber { background: #f59e0b; }
.kf-dot.green { background: #10b981; }
.kf-val {
  font-size: 34px;
  font-weight: 700;
  color: #0f172a;
  margin-top: 8px;
  line-height: 1.1;
}
.kf-item.amber .kf-val { color: #d97706; }
.kf-item.green .kf-val { color: #059669; }

/* 舒朗课程卡片网格 */
.course-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 20px;
}
.c-card {
  background: #ffffff;
  border-radius: 16px;
  padding: 22px 24px;
  box-shadow: var(--shadow-card);
  border: 1px solid rgba(226, 232, 240, 0.8);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.c-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.c-name {
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
}
.c-sub {
  font-size: 12.5px;
  color: #94a3b8;
  margin-top: 4px;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.status-pill.ready { background: #ecfdf5; color: #059669; }
.status-pill.pending { background: #fffbeb; color: #d97706; }
.status-pill.blue { background: #eff6ff; color: #2563eb; }
.status-pill.danger { background: #fef2f2; color: #dc2626; }
.status-pill.gray { background: #f1f5f9; color: #64748b; }

.c-checklist {
  margin: 18px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.chk-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
}
.chk-row.ok { color: #334155; }
.chk-row.wait { color: #b45309; }
.chk-icon {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}
.chk-row.ok .chk-icon { background: #dcfce7; color: #059669; }
.chk-row.wait .chk-icon { background: #fef3c7; color: #d97706; }

.c-card-foot {
  padding-top: 14px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  gap: 14px;
}

/* 预览区 */
.preview-highlight {
  border: 1.5px solid #93c5fd;
}
.pdf-summary-strip {
  background: #f8fbff;
  border-left: 3px solid #2563eb;
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  margin-bottom: 18px;
}
.strip-title {
  font-size: 12.5px;
  font-weight: 600;
  color: #2563eb;
  margin-bottom: 6px;
}
.strip-line {
  font-size: 13px;
  color: #334155;
  line-height: 1.6;
}
.sub-block-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 10px;
}
.fl {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
}
.course-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.c-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.c-pill.active {
  background: #eff6ff;
  border-color: #2563eb;
  color: #2563eb;
}
.remove-x { color: #94a3b8; }
.remove-x:hover { color: #dc2626; }
</style>
