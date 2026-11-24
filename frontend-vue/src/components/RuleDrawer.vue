<template>
  <el-drawer
    :model-value="modelValue"
    size="760px"
    :title="`规则与试卷配置 · ${task?.course_name || ''}`"
    destroy-on-close
    @update:model-value="(v) => $emit('update:modelValue', v)"
  >
    <div v-if="task" class="drawer-body">
      <el-tabs v-model="activeTab">
        <!-- Tab 1: 基本信息与占比 -->
        <el-tab-pane label="1. 基本信息与占比" name="basic">
          <div class="sec-block">
            <div class="sec-title">课程与班级信息</div>
            <el-row :gutter="14">
              <el-col :span="12">
                <div class="f-label">课程名称</div>
                <el-input v-model="task.meta['课程名称']" />
              </el-col>
              <el-col :span="12">
                <div class="f-label">开课学期</div>
                <el-input v-model="task.meta['学期']" />
              </el-col>
              <el-col :span="12" style="margin-top: 12px">
                <div class="f-label">教学班级</div>
                <el-input v-model="task.meta['班级']" />
              </el-col>
              <el-col :span="12" style="margin-top: 12px">
                <div class="f-label">达标合格线（0.65 即 65%）</div>
                <el-input-number v-model="task.threshold" :controls="false" :min="0.1" :max="1" :precision="2" style="width: 100%" />
              </el-col>
            </el-row>
          </div>

          <div class="sec-block">
            <div class="sec-head">
              <span class="sec-title">平时与期末总占比</span>
              <span class="status-pill" :class="totalRatioOk ? 'ok' : 'err'">
                {{ totalRatioOk ? '合计 1.00' : '相加须为 1.00' }}
              </span>
            </div>
            <el-row :gutter="14">
              <el-col :span="12">
                <div class="f-label">平时成绩占比</div>
                <el-input-number v-model="task.method['平时占比']" :controls="false" :min="0" :max="1" :precision="2" style="width: 100%" />
              </el-col>
              <el-col :span="12">
                <div class="f-label">期末考试占比</div>
                <el-input-number v-model="task.method['期末占比']" :controls="false" :min="0" :max="1" :precision="2" style="width: 100%" />
              </el-col>
            </el-row>
          </div>

          <div class="sec-block">
            <div class="sec-head">
              <span class="sec-title">平时细项构成（相加须为 1.00）</span>
              <span class="status-pill" :class="dailySumOk ? 'ok' : 'err'">当前合计 {{ dailySum.toFixed(2) }}</span>
            </div>
            <div v-for="row in dailyRows" :key="row.name" class="link-row">
              <el-input :model-value="row.name" size="small" style="flex: 1" @change="(v) => renameDaily(row.name, v)" />
              <el-input-number
                :model-value="row.ratio"
                :controls="false"
                size="small"
                :min="0"
                :max="1"
                :precision="2"
                style="width: 96px"
                @change="(v) => (task.method['平时环节'][row.name] = v ?? 0)"
              />
              <el-button link type="danger" size="small" :disabled="dailyRows.length <= 1" @click="removeDaily(row.name)">
                删除
              </el-button>
            </div>
            <div class="inline-row" style="margin-top: 10px">
              <el-input v-model="newLinkName" size="small" placeholder="新平时环节，如：实验" style="width: 200px" @keyup.enter="addDaily" />
              <el-button size="small" plain @click="addDaily">+ 添加环节</el-button>
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 目标权重矩阵 -->
        <el-tab-pane label="2. 目标权重矩阵" name="matrix">
          <div class="sec-block">
            <div class="sec-head">
              <span class="sec-title">课程目标 × 考核环节对应比例</span>
              <div class="inline-row">
                <el-input v-model="newTargetName" size="small" placeholder="新目标，如 课程目标4" style="width: 150px" @keyup.enter="addTarget" />
                <el-button size="small" plain @click="addTarget">+ 添加目标</el-button>
              </div>
            </div>
            <el-table :data="targetList" size="small" class="tabular-nums">
              <el-table-column label="课程目标" width="110">
                <template #default="{ row }"><strong>{{ row }}</strong></template>
              </el-table-column>
              <el-table-column v-for="link in allLinks" :key="link" :label="link" align="center">
                <template #default="{ row }">
                  <el-input-number v-model="task.matrix[row][link]" :controls="false" size="small" :min="0" :precision="2" style="width: 72px" />
                </template>
              </el-table-column>
              <el-table-column label="" width="54" align="center">
                <template #default="{ row }">
                  <el-button link type="danger" size="small" :disabled="targetList.length <= 1" @click="removeTarget(row)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Tab 3: 期末试卷结构 -->
        <el-tab-pane name="paper">
          <template #label>
            <span>3. 期末试卷结构</span>
            <span v-if="paperTotal !== 100" class="tab-dot"></span>
          </template>

          <div class="sec-block">
            <div class="paper-top-bar tabular-nums">
              <div class="sec-title" style="margin: 0">
                共 {{ flatQuestions.length }} 道小题 · 当前总分
                <span :style="{ color: paperTotal === 100 ? '#059669' : '#dc2626' }">{{ paperTotal }}</span> / 100 分
              </div>
              <div class="inline-row">
                <el-button size="small" plain @click="downloadPaperTpl">下载4列模板</el-button>
                <input ref="paperFileRef" type="file" accept=".xlsx" style="display: none" @change="uploadPaperExcel" />
                <el-button size="small" type="primary" plain @click="paperFileRef?.click()">上传模板导入</el-button>
                <el-button size="small" plain @click="addGroup">+ 添加大题</el-button>
              </div>
            </div>

            <el-progress
              :percentage="Math.min(100, paperTotal)"
              :status="paperTotal === 100 ? 'success' : paperTotal > 100 ? 'exception' : ''"
              :show-text="false"
              :stroke-width="6"
              style="margin: 12px 0 16px"
            />

            <el-empty v-if="task.paper.length === 0" description="尚未配置期末试卷，可点击「上传模板导入」或「+ 添加大题」" :image-size="60" />

            <el-collapse v-else v-model="expandedGroups">
              <el-collapse-item v-for="(grp, gi) in task.paper" :key="gi" :name="gi">
                <template #title>
                  <div class="grp-head" @click.stop>
                    <el-input v-model="grp['大题']" size="small" style="width: 160px" />
                    <span class="grp-meta tabular-nums">{{ grp['小题'].length }} 题 · {{ groupTotal(grp) }} 分</span>
                    <div class="inline-row" style="margin-left: auto; margin-right: 10px">
                      <el-button size="small" plain @click="addSingleQ(gi)">+ 小题</el-button>
                      <el-button size="small" link type="danger" @click="removeGroup(gi)">删除</el-button>
                    </div>
                  </div>
                </template>
                <el-table :data="grp['小题']" size="small" class="tabular-nums">
                  <el-table-column label="题号" width="80" align="center">
                    <template #default="{ row }">第 {{ row['题号'] }} 题</template>
                  </el-table-column>
                  <el-table-column label="满分" width="110" align="center">
                    <template #default="{ row }">
                      <el-input-number v-model="row['满分']" :controls="false" size="small" :min="0.5" :max="100" style="width: 72px" />
                    </template>
                  </el-table-column>
                  <el-table-column label="所属课程目标">
                    <template #default="{ row }">
                      <el-select v-model="row['目标']" size="small" style="width: 150px">
                        <el-option v-for="t in targetList" :key="t" :label="t" :value="t" />
                      </el-select>
                    </template>
                  </el-table-column>
                  <el-table-column label="" width="60" align="center">
                    <template #default="{ $index }">
                      <el-button link type="danger" size="small" @click="removeQ(gi, $index)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-collapse-item>
            </el-collapse>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <span v-if="!canSave" class="err-hint">{{ saveBlockReason }}</span>
        <div class="inline-row" style="margin-left: auto">
          <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
          <el-button type="primary" :loading="saving" :disabled="!canSave" @click="saveAll">保存规则配置</el-button>
        </div>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  task: { type: Object, required: true },
  initialTab: { type: String, default: 'basic' },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const activeTab = ref(props.initialTab)
const saving = ref(false)
const newLinkName = ref('')
const newTargetName = ref('')
const paperFileRef = ref(null)
const expandedGroups = ref([0])

watch(() => props.modelValue, (open) => { if (open) activeTab.value = props.initialTab || 'basic' })
watch(() => props.initialTab, (t) => { if (t) activeTab.value = t })

const dailyRows = computed(() =>
  Object.entries(props.task.method['平时环节'] || {}).map(([name, ratio]) => ({ name, ratio }))
)
const allLinks = computed(() => [...Object.keys(props.task.method['平时环节'] || {}), '期末考试'])
const targetList = computed(() => Object.keys(props.task.matrix || {}))
const dailySum = computed(() =>
  Object.values(props.task.method['平时环节'] || {}).reduce((a, b) => a + (Number(b) || 0), 0)
)
const dailySumOk = computed(() => Math.abs(dailySum.value - 1) < 1e-6)
const totalRatioOk = computed(
  () => Math.abs((props.task.method['平时占比'] || 0) + (props.task.method['期末占比'] || 0) - 1) < 1e-6
)
const flatQuestions = computed(() => (props.task.paper || []).flatMap((g) => g['小题'] || []))
const paperTotal = computed(() => flatQuestions.value.reduce((a, q) => a + (Number(q['满分']) || 0), 0))

const saveBlockReason = computed(() => {
  if (!totalRatioOk.value) return '平时与期末总占比之和须为 1.00'
  if (!dailySumOk.value) return '平时细项比例之和须为 1.00'
  if (props.task.paper.length > 0 && paperTotal.value !== 100) return `期末试卷总分须为 100 分（当前 ${paperTotal.value} 分）`
  return ''
})
const canSave = computed(() => !saveBlockReason.value)

function groupTotal(grp) { return (grp['小题'] || []).reduce((a, q) => a + (Number(q['满分']) || 0), 0) }
function renumberQuestions() {
  let seq = 1
  for (const g of props.task.paper) for (const q of g['小题']) q['题号'] = seq++
}
function renameDaily(oldName, newName) {
  const name = (newName || '').trim()
  if (!name || name === oldName || name in props.task.method['平时环节']) return
  const entries = Object.entries(props.task.method['平时环节']).map(([k, v]) => (k === oldName ? [name, v] : [k, v]))
  props.task.method['平时环节'] = Object.fromEntries(entries)
  for (const t of targetList.value) {
    props.task.matrix[t][name] = props.task.matrix[t][oldName] ?? 0
    delete props.task.matrix[t][oldName]
  }
}
function addDaily() {
  const name = newLinkName.value.trim()
  if (!name || name in props.task.method['平时环节']) return
  props.task.method['平时环节'][name] = 0
  for (const t of targetList.value) props.task.matrix[t][name] = 0.1
  newLinkName.value = ''
}
function removeDaily(name) {
  delete props.task.method['平时环节'][name]
  for (const t of targetList.value) delete props.task.matrix[t][name]
}
function addTarget() {
  const name = newTargetName.value.trim() || `课程目标${targetList.value.length + 1}`
  if (name in props.task.matrix) return
  const row = {}
  for (const l of allLinks.value) row[l] = l === '期末考试' ? 0 : 0.1
  props.task.matrix[name] = row
  newTargetName.value = ''
}
function removeTarget(name) {
  delete props.task.matrix[name]
  const fallback = targetList.value[0]
  for (const g of props.task.paper) for (const q of g['小题']) if (q['目标'] === name) q['目标'] = fallback
}
function addGroup() {
  props.task.paper.push({ 大题: `第${props.task.paper.length + 1}大题`, 小题: [] })
  expandedGroups.value = [props.task.paper.length - 1]
}
function removeGroup(gi) { props.task.paper.splice(gi, 1); renumberQuestions() }
function addSingleQ(gi) {
  props.task.paper[gi]['小题'].push({ 题号: 0, 满分: 5, 目标: targetList.value[0] })
  renumberQuestions()
  if (!expandedGroups.value.includes(gi)) expandedGroups.value.push(gi)
}
function removeQ(gi, qi) { props.task.paper[gi]['小题'].splice(qi, 1); renumberQuestions() }

async function downloadPaperTpl() {
  try { await api.downloadTaskPaperTpl(props.task.id, props.task.course_name) } catch (e) { ElMessage.error(e.message) }
}
async function uploadPaperExcel(e) {
  const file = e.target.files?.[0]
  if (!file) return
  try {
    const res = await api.importTaskPaperExcel(props.task.id, file)
    ElMessage.success(res.message)
    emit('saved', res.task)
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    if (paperFileRef.value) paperFileRef.value.value = ''
  }
}
async function saveAll() {
  renumberQuestions()
  saving.value = true
  try {
    const res = await api.updateTaskRules(props.task.id, {
      meta: props.task.meta,
      threshold: props.task.threshold,
      method: props.task.method,
      matrix: props.task.matrix,
      paper: props.task.paper,
    })
    ElMessage.success('规则与试卷配置已保存')
    emit('saved', res.task)
    emit('update:modelValue', false)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.drawer-body { padding: 0 4px; }
.sec-block { margin-bottom: 24px; }
.sec-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sec-title { font-size: 14px; font-weight: 600; color: #0f172a; margin-bottom: 10px; }
.sec-head .sec-title { margin-bottom: 0; }
.f-label { font-size: 12.5px; color: #64748b; margin-bottom: 6px; }
.link-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.inline-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.paper-top-bar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.grp-head { display: flex; align-items: center; gap: 12px; width: 100%; }
.grp-meta { font-size: 12.5px; color: #64748b; }
.tab-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #f59e0b; margin-left: 6px; vertical-align: middle; }
.drawer-footer { display: flex; align-items: center; width: 100%; gap: 12px; }
.err-hint { font-size: 12.5px; color: #dc2626; }
</style>
