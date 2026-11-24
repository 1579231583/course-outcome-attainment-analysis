<template>
  <div class="admin-page">
    <el-tabs v-model="tab" class="admin-tabs">
      <!-- ==================== Tab 1：公共教学大纲库 ==================== -->
      <el-tab-pane label="公共教学大纲库" name="syllabuses">
        <div class="page-header" style="margin-top: 8px">
          <div>
            <h1>公共教学大纲库</h1>
            <p class="subtitle">上传《教学大纲 PDF》建立长期课程标准（不绑定学期）；统考大课可按学期挂接期末统考试卷</p>
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

        <!-- 大纲 PDF 提取预览与占比核对区（仅在刚上传 PDF 时出现） -->
        <div v-if="drafts.length > 0" class="panel-card preview-highlight">
          <div class="panel-title">
            <span>大纲提取结果核对（共 {{ drafts.length }} 门）</span>
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
              <span>{{ d.course?.meta?.['课程名称'] || d.source_file }}</span>
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
              <div v-for="(desc, tg) in currentCourse.target_descriptions" :key="tg" class="strip-line">
                <b>{{ tg }}</b>：{{ desc }}
              </div>
            </div>

            <div class="sub-block-title">一、课程基本信息（从大纲提取）</div>
            <el-row :gutter="14">
              <el-col :xs="12" :sm="8">
                <div class="fl">课程名称</div>
                <el-input v-model="currentCourse.meta['课程名称']" />
              </el-col>
              <el-col :xs="12" :sm="6">
                <div class="fl">课程代码</div>
                <el-input v-model="currentCourse.meta['课程代码']" />
              </el-col>
              <el-col :xs="12" :sm="5">
                <div class="fl">课程类别</div>
                <el-input v-model="currentCourse.meta['课程类别']" />
              </el-col>
              <el-col :xs="12" :sm="5">
                <div class="fl">学分 / 学时</div>
                <div style="display: flex; gap: 6px">
                  <el-input-number v-model="currentCourse.meta['学分']" :controls="false" :precision="1" style="width: 50%" />
                  <el-input-number v-model="currentCourse.meta['授课学时']" :controls="false" style="width: 50%" />
                </div>
              </el-col>
            </el-row>

            <div class="sub-block-title" style="margin-top: 20px">二、大纲考核环节对应矩阵（从大纲提取）</div>
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

        <!-- 3 张极简状态筛选统计卡 -->
        <div class="kpi-filter-row tabular-nums">
          <div class="kf-item" :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'">
            <div class="kf-top"><span class="kf-dot blue"></span><span>全部公共大纲</span></div>
            <div class="kf-val">{{ syllabuses.length }}</div>
          </div>
          <div class="kf-item amber" :class="{ active: statusFilter === 'only_syllabus' }" @click="statusFilter = 'only_syllabus'">
            <div class="kf-top"><span class="kf-dot amber"></span><span>仅大纲（未配统考卷）</span></div>
            <div class="kf-val">{{ onlySyllabusCount }}</div>
          </div>
          <div class="kf-item green" :class="{ active: statusFilter === 'ready' }" @click="statusFilter = 'ready'">
            <div class="kf-top"><span class="kf-dot green"></span><span>已挂接统考试卷</span></div>
            <div class="kf-val">{{ withPaperCount }}</div>
          </div>
        </div>

        <!-- 大纲卡片网格 -->
        <div v-if="filteredSyllabuses.length > 0" class="course-grid">
          <div v-for="s in filteredSyllabuses" :key="s.id" class="c-card">
            <div class="c-card-head">
              <div>
                <div class="c-name">{{ s.course_name }}</div>
                <div class="c-sub tabular-nums">
                  {{ s.course_code || '无代码' }} · {{ s.course_category }} · {{ s.credits }}学分 / {{ s.hours }}学时
                </div>
              </div>
              <span class="status-pill" :class="s.has_paper ? 'ok' : 'warn'">
                <span class="dot"></span>
                {{ s.has_paper ? `${s.paper_count} 份统考卷` : '仅大纲' }}
              </span>
            </div>

            <div class="c-rule-line tabular-nums">
              {{ s.target_count }} 个课程目标 · 考核环节：{{ [...s.daily_links, '期末考试'].join(' / ') }}
            </div>

            <div class="paper-tags">
              <template v-if="s.exam_papers.length > 0">
                <span v-for="ep in s.exam_papers" :key="ep.id" class="ep-chip tabular-nums">
                  {{ ep.semester }}（{{ ep.question_count }}题）
                </span>
              </template>
              <span v-else class="ep-empty">暂无统考期末试卷（专业课可由任课教师自配）</span>
            </div>

            <div class="c-card-footer">
              <el-button type="primary" plain size="small" @click="openPaperManager(s)">
                管理统考试卷
              </el-button>
              <el-button link type="danger" size="small" @click="delSyllabus(s)">删除大纲</el-button>
            </div>
          </div>
        </div>

        <div v-else class="panel-card" style="text-align: center; padding: 48px 20px">
          <el-empty description="暂无公共教学大纲，点击右上角「上传《教学大纲 PDF》」即可自动提取建库" />
        </div>
      </el-tab-pane>

      <!-- ==================== Tab 2：教师账号管理 ==================== -->
      <el-tab-pane label="教师账号管理" name="users">
        <div class="page-header" style="margin-top: 8px">
          <div>
            <h1>教师与管理员账号</h1>
            <p class="subtitle">创建任课教师账号、启用或禁用登录权限、重置默认密码</p>
          </div>
          <el-button type="primary" size="large" @click="userDlg = true">+ 新增账号</el-button>
        </div>

        <div class="panel-card">
          <el-table :data="users" stripe>
            <el-table-column prop="username" label="工号 / 账号" width="150" />
            <el-table-column prop="name" label="姓名" width="130" />
            <el-table-column prop="department" label="所属学院" min-width="160" />
            <el-table-column label="角色" width="110" align="center">
              <template #default="{ row }">
                <span class="status-pill" :class="row.role === 'admin' ? 'warn' : 'ok'">
                  {{ row.role === 'admin' ? '管理员' : '教师' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <span class="status-pill" :class="row.is_active ? 'ok' : 'err'">
                  {{ row.is_active ? '正常' : '已禁用' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="190" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="resetPwd(row)">重置密码</el-button>
                <el-button
                  v-if="row.username !== 'admin'"
                  link
                  :type="row.is_active ? 'danger' : 'success'"
                  size="small"
                  @click="toggleUser(row)"
                >
                  {{ row.is_active ? '禁用' : '启用' }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- ==================== Tab 3：全院达成度监控 ==================== -->
      <el-tab-pane label="全院达成度监控" name="overview">
        <div class="page-header" style="margin-top: 8px">
          <div>
            <h1>全院达成度汇总监控</h1>
            <p class="subtitle">实时查看全院已完成达成度分析的教学班级与达标率</p>
          </div>
          <el-button plain @click="loadOverview">刷新数据</el-button>
        </div>

        <div v-if="overview" class="kpi-grid tabular-nums">
          <div class="kpi-card">
            <div class="kpi-label">公共教学大纲</div>
            <div class="kpi-value">{{ overview.syllabus_count }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">统考期末试卷</div>
            <div class="kpi-value">{{ overview.exam_paper_count }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">已完成班级分析</div>
            <div class="kpi-value">{{ overview.report_count }}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">全院班级达标率</div>
            <div class="kpi-value" style="color: #059669">{{ overview.pass_rate }}%</div>
          </div>
        </div>

        <div class="panel-card">
          <el-empty v-if="!overview?.reports?.length" description="暂无教师提交的班级达成度分析报告" />
          <el-table v-else :data="overview.reports" stripe class="tabular-nums">
            <el-table-column prop="course_name" label="课程名称" min-width="150">
              <template #default="{ row }"><strong>{{ row.course_name }}</strong></template>
            </el-table-column>
            <el-table-column prop="semester" label="学期" width="120" align="center" />
            <el-table-column prop="class_name" label="教学班级" width="140" align="center" />
            <el-table-column prop="teacher_name" label="任课教师" width="100" align="center" />
            <el-table-column prop="student_count" label="人数" width="70" align="center" />
            <el-table-column label="各目标达成度" min-width="220">
              <template #default="{ row }">
                <div style="display: flex; flex-wrap: wrap; gap: 6px">
                  <span
                    v-for="(pct, tg) in row.targets"
                    :key="tg"
                    class="status-pill"
                    :class="pct >= row.pass_threshold * 100 ? 'ok' : 'err'"
                  >
                    {{ tg }} {{ pct }}%
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="结论" width="90" align="center">
              <template #default="{ row }">
                <span class="status-pill" :class="row.all_passed ? 'ok' : 'err'">
                  {{ row.all_passed ? '全部达标' : '有预警' }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 弹窗：按学期管理某门大纲的统考期末试卷 -->
    <el-dialog
      v-model="paperMgr.open"
      :title="`统考期末试卷管理 · ${paperMgr.syllabus?.course_name || ''}`"
      width="820px"
      destroy-on-close
    >
      <div v-if="paperMgr.syllabus">
        <!-- 已有学期试卷列表 -->
        <div class="sub-block-title">已挂接的学期统考试卷</div>
        <div v-if="paperMgr.syllabus.exam_papers.length === 0" class="ep-empty" style="margin-bottom: 16px">
          尚未上传统考试卷。下方选择学期并上传 4 列《期末试卷结构模板.xlsx》后，该学期所有任课教师将自动共用此试卷。
        </div>
        <div v-else class="ep-list">
          <div v-for="ep in paperMgr.syllabus.exam_papers" :key="ep.id" class="ep-row">
            <div>
              <strong>{{ ep.semester }}</strong>
              <span class="ep-meta tabular-nums"> · {{ ep.title }} · {{ ep.question_count }} 题（100分）</span>
            </div>
            <div class="actions">
              <el-button link type="primary" size="small" @click="loadPaperIntoEditor(ep)">编辑微调</el-button>
              <el-button link type="danger" size="small" @click="delExamPaper(ep)">删除</el-button>
            </div>
          </div>
        </div>

        <el-divider />

        <!-- 上传/编辑某学期试卷 -->
        <div class="paper-upload-bar">
          <div class="actions">
            <span class="fl" style="margin: 0">所属学期</span>
            <el-input v-model="paperMgr.semester" placeholder="如 2025-2026-1" style="width: 150px" />
            <el-button plain @click="downloadPaperTpl">下载 4 列试卷模板</el-button>
            <input ref="paperUploadRef" type="file" accept=".xlsx" style="display: none" @change="handlePaperFilePreview" />
            <el-button type="primary" plain @click="paperUploadRef?.click()">上传 4 列模板预览</el-button>
            <el-button plain @click="addPaperGroup">+ 手动加一大题</el-button>
          </div>
          <span class="status-pill tabular-nums" :class="paperMgrTotal === 100 ? 'ok' : 'err'">
            当前总分 {{ paperMgrTotal }} / 100 分
          </span>
        </div>

        <el-alert
          v-if="paperMgr.errors.length > 0"
          type="warning"
          show-icon
          :closable="false"
          style="margin: 12px 0"
          :title="paperMgr.errors.join(' ； ')"
        />

        <div v-if="paperMgr.paper.length > 0" style="margin-top: 14px; max-height: 360px; overflow-y: auto">
          <div v-for="(grp, gi) in paperMgr.paper" :key="gi" class="grp-box">
            <div class="grp-box-head">
              <el-input v-model="grp['大题']" size="small" style="width: 180px" />
              <div class="actions">
                <el-button size="small" plain @click="addPaperQ(gi)">+ 小题</el-button>
                <el-button size="small" link type="danger" @click="paperMgr.paper.splice(gi, 1)">删大题</el-button>
              </div>
            </div>
            <el-table :data="grp['小题']" size="small" class="tabular-nums">
              <el-table-column label="题号" width="76" align="center">
                <template #default="{ $index }">{{ $index + 1 }}</template>
              </el-table-column>
              <el-table-column label="满分" width="110" align="center">
                <template #default="{ row }">
                  <el-input-number v-model="row['满分']" :controls="false" size="small" :min="0.5" :max="100" style="width: 72px" />
                </template>
              </el-table-column>
              <el-table-column label="所属课程目标">
                <template #default="{ row }">
                  <el-select v-model="row['目标']" size="small" style="width: 160px">
                    <el-option v-for="t in paperMgrTargets" :key="t" :label="t" :value="t" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="" width="60" align="center">
                <template #default="{ $index }">
                  <el-button link type="danger" size="small" @click="grp['小题'].splice($index, 1)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="paperMgr.open = false">关闭</el-button>
        <el-button
          type="primary"
          :disabled="!paperMgr.semester.trim() || paperMgrTotal !== 100"
          :loading="paperMgr.saving"
          @click="confirmSaveExamPaper"
        >
          保存为 {{ paperMgr.semester || '本学期' }} 统考试卷
        </el-button>
      </template>
    </el-dialog>

    <!-- 弹窗：新增账号 -->
    <el-dialog v-model="userDlg" title="新增账号" width="420px">
      <el-form :model="newUser" label-position="top">
        <el-form-item label="工号 / 登录账号 *"><el-input v-model="newUser.username" /></el-form-item>
        <el-form-item label="姓名 *"><el-input v-model="newUser.name" /></el-form-item>
        <el-form-item label="所属学院"><el-input v-model="newUser.department" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="newUser.password" /></el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="newUser.role">
            <el-radio value="teacher">任课教师</el-radio>
            <el-radio value="admin">教务管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDlg = false">取消</el-button>
        <el-button type="primary" @click="createUser">确认创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'

const tab = ref('syllabuses')
const syllabuses = ref([])
const users = ref([])
const overview = ref(null)
const statusFilter = ref('all')

const pdfInputRef = ref(null)
const paperUploadRef = ref(null)
const previewLoading = ref(false)
const publishing = ref(false)
const drafts = ref([])
const activeDraftIdx = ref(0)

const userDlg = ref(false)
const newUser = reactive({ username: '', name: '', department: '', password: '123456', role: 'teacher' })

const paperMgr = reactive({
  open: false,
  syllabus: null,
  semester: '2025-2026-1',
  paper: [],
  errors: [],
  saving: false,
})

const onlySyllabusCount = computed(() => syllabuses.value.filter((s) => !s.has_paper).length)
const withPaperCount = computed(() => syllabuses.value.filter((s) => s.has_paper).length)
const filteredSyllabuses = computed(() => {
  if (statusFilter.value === 'only_syllabus') return syllabuses.value.filter((s) => !s.has_paper)
  if (statusFilter.value === 'ready') return syllabuses.value.filter((s) => s.has_paper)
  return syllabuses.value
})

const currentDraft = computed(() => drafts.value[activeDraftIdx.value] || null)
const currentCourse = computed(() => currentDraft.value?.course || null)
const curDailyLinks = computed(() => Object.keys(currentCourse.value?.method?.['平时环节'] || {}))
const curAllLinks = computed(() => [...curDailyLinks.value, '期末考试'])
const curTargets = computed(() => Object.keys(currentCourse.value?.matrix || {}))

function draftErrors(d) {
  if (!d?.course) return d?.errors || ['PDF 解析失败']
  const errs = []
  const c = d.course
  if (!(c.meta?.['课程名称'] || '').trim()) errs.push('课程名称不能为空')
  const dr = Number(c.method?.['平时占比'] || 0)
  const fr = Number(c.method?.['期末占比'] || 0)
  if (Math.abs(dr + fr - 1) > 1e-6) errs.push(`平时占比(${dr}) + 期末占比(${fr}) 须为 1.00`)
  const dsum = Object.values(c.method?.['平时环节'] || {}).reduce((a, b) => a + Number(b || 0), 0)
  if (Math.abs(dsum - 1) > 1e-6) errs.push(`平时细项比例之和须为 1.00（当前 ${dsum.toFixed(2)}）`)
  const tgs = Object.keys(c.matrix || {})
  const links = [...Object.keys(c.method?.['平时环节'] || {}), '期末考试']
  for (const l of links) {
    const w = l === '期末考试' ? fr : dr * Number(c.method?.['平时环节']?.[l] || 0)
    if (w > 0 && tgs.reduce((acc, t) => acc + Number(c.matrix?.[t]?.[l] || 0), 0) <= 0) {
      errs.push(`考核环节「${l}」整列比例全为 0`)
    }
  }
  return errs
}
const validDraftCourses = computed(() => drafts.value.filter((d) => d.course && draftErrors(d).length === 0).map((d) => d.course))
const invalidDraftCount = computed(() => drafts.value.filter((d) => !d.course || draftErrors(d).length > 0).length)

const paperMgrTargets = computed(() => Object.keys(paperMgr.syllabus?.matrix || {}))
const paperMgrTotal = computed(() =>
  paperMgr.paper.flatMap((g) => g['小题'] || []).reduce((a, q) => a + Number(q['满分'] || 0), 0)
)

async function loadSyllabuses() {
  try {
    const res = await api.listSyllabuses()
    syllabuses.value = res.syllabuses || []
    if (paperMgr.open && paperMgr.syllabus) {
      paperMgr.syllabus = syllabuses.value.find((x) => x.id === paperMgr.syllabus.id) || null
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadUsers() {
  try {
    const res = await api.adminListUsers()
    users.value = res.users || []
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function loadOverview() {
  try {
    const res = await api.adminOverview()
    overview.value = res.overview
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handlePreviewPdfFiles(e) {
  const files = Array.from(e.target.files || [])
  if (!files.length) return
  previewLoading.value = true
  try {
    const res = await api.previewSyllabusPdf(files)
    drafts.value = res.drafts || []
    activeDraftIdx.value = 0
    ElMessage.success(`已提取 ${drafts.value.length} 份大纲，请核对占比与矩阵后发布`)
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
    const res = await api.publishSyllabuses(validDraftCourses.value)
    ElMessage.success(`已发布 ${res.count} 门公共教学大纲`)
    drafts.value = []
    await loadSyllabuses()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    publishing.value = false
  }
}

async function delSyllabus(s) {
  try {
    await ElMessageBox.confirm(`确定删除公共大纲「${s.course_name}」及其挂接的统考试卷吗？`, '删除大纲', { type: 'warning' })
    await api.deleteSyllabus(s.id)
    ElMessage.success('已删除')
    await loadSyllabuses()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

function openPaperManager(s) {
  paperMgr.syllabus = s
  paperMgr.semester = '2025-2026-1'
  paperMgr.paper = []
  paperMgr.errors = []
  paperMgr.open = true
}

function loadPaperIntoEditor(ep) {
  paperMgr.semester = ep.semester
  paperMgr.paper = JSON.parse(JSON.stringify(ep.paper || []))
  paperMgr.errors = []
}

async function downloadPaperTpl() {
  if (!paperMgr.syllabus) return
  try {
    await api.downloadSyllabusPaperTpl(paperMgr.syllabus.id, paperMgr.syllabus.course_name, paperMgr.semester)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handlePaperFilePreview(e) {
  const file = e.target.files?.[0]
  if (!file || !paperMgr.syllabus) return
  try {
    const res = await api.previewSyllabusPaper(paperMgr.syllabus.id, file)
    paperMgr.paper = res.paper || []
    paperMgr.errors = res.errors || []
    ElMessage.success('试卷结构已载入预览，可微调后保存')
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    if (paperUploadRef.value) paperUploadRef.value.value = ''
  }
}

function addPaperGroup() {
  const tg = paperMgrTargets.value[0] || '课程目标1'
  paperMgr.paper.push({ 大题: `第${paperMgr.paper.length + 1}大题`, 小题: [{ 题号: 1, 满分: 10, 目标: tg }] })
}

function addPaperQ(gi) {
  const tg = paperMgrTargets.value[0] || '课程目标1'
  paperMgr.paper[gi]['小题'].push({ 题号: 1, 满分: 5, 目标: tg })
}

async function confirmSaveExamPaper() {
  if (!paperMgr.syllabus) return
  paperMgr.saving = true
  try {
    const res = await api.saveSyllabusPaper(paperMgr.syllabus.id, {
      semester: paperMgr.semester.trim(),
      title: `${paperMgr.semester.trim()} 统考试卷`,
      paper: paperMgr.paper,
    })
    ElMessage.success(res.message)
    paperMgr.paper = []
    await loadSyllabuses()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    paperMgr.saving = false
  }
}

async function delExamPaper(ep) {
  try {
    await ElMessageBox.confirm(`确定删除 ${ep.semester} 统考试卷吗？`, '删除试卷', { type: 'warning' })
    await api.deleteExamPaper(ep.id)
    ElMessage.success('已删除')
    await loadSyllabuses()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

async function createUser() {
  try {
    await api.adminCreateUser(newUser)
    ElMessage.success('账号已创建')
    userDlg.value = false
    newUser.username = ''
    newUser.name = ''
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function toggleUser(row) {
  try {
    await api.adminToggleUser(row.id)
    ElMessage.success('状态已更新')
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function resetPwd(row) {
  try {
    await ElMessageBox.confirm(`将「${row.name}」的密码重置为 123456 吗？`, '重置密码', { type: 'warning' })
    await api.adminResetPassword(row.id, '123456')
    ElMessage.success('已重置为 123456')
  } catch {
    // cancelled
  }
}

onMounted(() => {
  loadSyllabuses()
  loadUsers()
  loadOverview()
})
</script>

<style scoped>
.admin-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
.actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.preview-highlight { border: 1.5px solid #93c5fd; }
.course-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.c-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: #f1f5f9;
  font-size: 13px;
  cursor: pointer;
}
.c-pill.active { background: #2563eb; color: #fff; }
.c-pill.err { border: 1px solid #ef4444; }
.remove-x { font-weight: 700; opacity: 0.7; }
.pdf-summary-strip {
  background: #f8fafc;
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 18px;
  font-size: 13px;
  color: #334155;
}
.strip-title { font-weight: 600; color: #0f172a; margin-bottom: 6px; }
.strip-line { line-height: 1.6; }
.sub-block-title { font-size: 14px; font-weight: 600; color: #0f172a; margin-bottom: 10px; }
.fl { font-size: 12.5px; color: #64748b; margin-bottom: 6px; }

.kpi-filter-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.kf-item {
  background: #ffffff;
  border-radius: 14px;
  padding: 18px 22px;
  cursor: pointer;
  border: 1.5px solid transparent;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  transition: all 0.15s;
}
.kf-item:hover { transform: translateY(-1px); }
.kf-item.active { border-color: #2563eb; background: #f8fbff; }
.kf-item.amber.active { border-color: #f59e0b; background: #fffbeb; }
.kf-item.green.active { border-color: #10b981; background: #f0fdf4; }
.kf-top { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #64748b; }
.kf-dot { width: 8px; height: 8px; border-radius: 50%; }
.kf-dot.blue { background: #2563eb; }
.kf-dot.amber { background: #f59e0b; }
.kf-dot.green { background: #10b981; }
.kf-val { font-size: 32px; font-weight: 700; color: #0f172a; margin-top: 8px; }

.course-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 18px;
}
.c-card {
  background: #ffffff;
  border-radius: 14px;
  padding: 20px 22px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.c-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.c-name { font-size: 17px; font-weight: 700; color: #0f172a; }
.c-sub { font-size: 12.5px; color: #64748b; margin-top: 4px; }
.c-rule-line { font-size: 13px; color: #334155; background: #f8fafc; padding: 8px 12px; border-radius: 8px; }
.paper-tags { display: flex; flex-wrap: wrap; gap: 6px; min-height: 24px; align-items: center; }
.ep-chip {
  font-size: 12px;
  font-weight: 600;
  color: #065f46;
  background: #ecfdf5;
  padding: 3px 10px;
  border-radius: 999px;
}
.ep-empty { font-size: 12.5px; color: #94a3b8; }
.c-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
}
.ep-list { display: flex; flex-direction: column; gap: 8px; }
.ep-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8fafc;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13.5px;
}
.ep-meta { color: #64748b; font-size: 12.5px; }
.paper-upload-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.grp-box {
  background: #f8fafc;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.grp-box-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
</style>
