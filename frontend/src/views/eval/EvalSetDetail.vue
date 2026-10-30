<template>
  <div class="page set-page">
    <div v-if="loading" class="loading-wrap"><n-spin size="small" /><span>加载评测集…</span></div>

    <template v-else-if="set">
      <div class="detail-top">
        <n-button text size="small" class="back-btn" @click="$router.push('/app/eval')">
          <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
          返回评测集
        </n-button>
        <div class="title-col">
          <div class="title-row">
            <h2 class="set-title">{{ set.name }}</h2>
            <n-tag size="tiny" :bordered="false">{{ set.case_count }} 条 Case</n-tag>
            <n-tag size="tiny" :bordered="false" type="success">{{ set.good_count }} Good</n-tag>
            <n-tag size="tiny" :bordered="false" type="error">{{ set.bad_count }} Bad</n-tag>
          </div>
          <div class="set-desc">{{ set.description || '暂无描述' }}</div>
          <div class="set-meta">
            <span>创建人 {{ set.created_by || '—' }}</span>
            <span class="dot"></span>
            <span>更新于 {{ formatDateTime(set.updated_at) }}</span>
            <span v-if="set.apps?.length" class="dot"></span>
            <span v-if="set.apps?.length">覆盖 {{ set.apps.join(' · ') }}</span>
          </div>
        </div>
        <div class="action-col">
          <n-button size="small" :disabled="running" @click="openEdit">编辑信息</n-button>
          <n-button size="small" @click="exportJsonl">
            <template #icon><n-icon><DownloadOutline /></n-icon></template>
            导出 JSONL
          </n-button>
          <n-button size="small" type="primary" :disabled="running" @click="openAddCases">
            <template #icon><n-icon><AddOutline /></n-icon></template>
            添加 Case
          </n-button>
          <n-button size="small" text type="error" :disabled="running" @click="confirmDelete">删除</n-button>
        </div>
      </div>

      <MetricStrip :items="metrics" />

      <div class="quality-panel">
        <div class="binding-row">
          <div class="binding-field">
            <label class="label">绑定应用</label>
            <n-select :value="set.app_id || null" :options="appOptions" filterable clearable placeholder="选择应用，评测其当前草稿" :disabled="bindingSaving || running" :loading="bindingSaving" @update:value="bindApp" />
          </div>
          <div class="gate-field">
            <label class="label">发布门禁</label>
            <n-switch :value="set.is_release_gate" :disabled="!set.app_id || bindingSaving || running" :loading="bindingSaving" aria-label="发布门禁" @update:value="toggleGate" />
          </div>
        </div>
        <div class="standard-hint">门禁评测必须基于当前草稿全部通过，才可发布。待补标准的 Case 不参与运行。</div>
        <EvalRunPanel :key="set.id" :set-id="set.id" :app-id="set.app_id" :latest-run="set.latest_run" :disabled="bindingSaving || saving" @completed="reload" @running-change="running = $event" />
      </div>

      <div class="list-panel">
        <div class="list-head">
          <div class="list-title">Case 列表</div>
          <div class="list-actions">
            <n-radio-group v-model:value="labelFilter" size="small">
              <n-radio-button value="">全部 {{ set.case_count }}</n-radio-button>
              <n-radio-button value="good">Good {{ set.good_count }}</n-radio-button>
              <n-radio-button value="bad">Bad {{ set.bad_count }}</n-radio-button>
            </n-radio-group>
            <n-button size="small" quaternary :disabled="running" @click="manualModal = true">回流新 Case</n-button>
          </div>
        </div>

        <div v-if="filteredCases.length" class="case-list">
          <div v-for="item in filteredCases" :key="item.id" class="case-row">
            <div class="case-label">
              <n-tag size="tiny" :bordered="false" :type="item.label === 'good' ? 'success' : 'error'">
                {{ item.label === 'good' ? 'Good' : 'Bad' }}
              </n-tag>
              <n-tag size="tiny" :bordered="false" :type="item.readiness === 'ready' ? 'success' : 'warning'">
                {{ item.readiness === 'ready' ? '可运行' : '待补标准' }}
              </n-tag>
            </div>
            <div class="case-main" @click="openCase(item)">
              <div class="case-question">{{ item.question }}</div>
              <div class="case-answer">{{ item.answer || '（无回答）' }}</div>
              <div v-if="item.reference_answer" class="case-reference">
                <span class="ref-label">期望</span>{{ item.reference_answer }}
              </div>
            </div>
            <div class="case-meta-col">
              <span class="meta-app">{{ item.app_name || '—' }}</span>
              <span class="meta-source">{{ sourceLabel(item.source) }}</span>
              <span v-if="item.tags?.length" class="meta-tags">{{ item.tags.slice(0, 3).join(' · ') }}</span>
            </div>
            <div class="case-actions">
              <n-button v-if="item.trace_id" text size="tiny" type="primary" @click="openTrace(item.trace_id)">链路</n-button>
              <n-button text size="tiny" :disabled="running" @click="openCase(item)">编辑</n-button>
              <n-button text size="tiny" type="error" :disabled="running" @click="removeCase(item)">移出</n-button>
            </div>
          </div>
        </div>
        <div v-else class="empty">
          <div class="empty-title">{{ set.case_count ? '没有符合筛选条件的 Case' : '这个评测集还没有 Case' }}</div>
          <div class="empty-desc">从 Case 池挑选，或直接回流一条线上对话，把 good / bad 样本汇总到这里。</div>
          <n-button size="small" type="primary" ghost :disabled="running" @click="openAddCases">从 Case 池添加</n-button>
        </div>
      </div>

      <!-- Case 标准编辑 -->
      <n-drawer v-model:show="caseDrawer" :width="580" style="max-width: 100vw" placement="right">
        <n-drawer-content v-if="activeCase" closable>
          <template #header>
            <div class="drawer-head">
              <n-tag size="small" :bordered="false" :type="activeCase.label === 'good' ? 'success' : 'error'">
                {{ activeCase.label === 'good' ? 'Good Case' : 'Bad Case' }}
              </n-tag>
              <n-tag size="tiny" :bordered="false" :type="activeCase.readiness === 'ready' ? 'success' : 'warning'">{{ activeCase.readiness === 'ready' ? '可运行' : '待补标准' }}</n-tag>
              <span class="drawer-sub">{{ sourceLabel(activeCase.source) }}</span>
            </div>
          </template>
          <div class="case-detail">
            <div class="detail-block">
              <div class="detail-label">问题</div>
              <n-input v-model:value="editCase.question" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
            </div>
            <div class="detail-block">
              <div class="detail-label">线上回答</div>
              <div class="detail-text">{{ activeCase.answer || '（无）' }}</div>
            </div>
            <div class="detail-block">
              <div class="detail-label">期望回答</div>
              <n-input v-model:value="editCase.reference_answer" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="填写期望回答，作为回归对照" />
            </div>
            <div class="detail-block">
              <div class="detail-label">必须包含关键词</div>
              <n-dynamic-tags v-model:value="editCase.expected_keywords" />
            </div>
            <div class="detail-block">
              <div class="detail-label">禁止出现关键词</div>
              <n-dynamic-tags v-model:value="editCase.forbidden_keywords" />
            </div>
            <div class="detail-block">
              <div class="detail-label">要求引用</div>
              <n-switch v-model:value="editCase.require_citations" aria-label="要求引用" style="align-self: flex-start" />
              <span class="standard-hint">填写期望回答、关键词或引用要求后，Case 才能参与评测。</span>
            </div>
            <div class="detail-block">
              <div class="detail-label">备注</div>
              <n-input v-model:value="editCase.note" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
            </div>
            <div class="detail-meta">
              <span>应用：{{ activeCase.app_name || '—' }}</span>
              <span>标签：{{ activeCase.tags?.join('、') || '—' }}</span>
              <span>Trace：{{ activeCase.trace_id || '—' }}</span>
            </div>
            <n-button v-if="activeCase.trace_id" size="small" type="primary" ghost @click="openTrace(activeCase.trace_id)">
              查看原始调用链路
            </n-button>
          </div>
          <template #footer>
            <div class="modal-footer">
              <div class="spacer"></div>
              <n-button size="small" @click="caseDrawer = false">取消</n-button>
              <n-button size="small" type="primary" :loading="saving" :disabled="running || !editCase.question.trim()" @click="saveCase">保存修改</n-button>
            </div>
          </template>
        </n-drawer-content>
      </n-drawer>

      <!-- 从 Case 池添加 -->
      <n-modal v-model:show="addModal" preset="card" title="从 Case 池添加" style="width: 760px; max-width: calc(100vw - 32px)" :bordered="false">
        <div class="add-toolbar">
          <n-input v-model:value="poolQuery" placeholder="搜索问题 / 回答 / 备注" clearable style="width: 260px" @keydown.enter="loadPool" />
          <n-button size="small" @click="loadPool">搜索</n-button>
          <span class="pool-count">{{ availableCases.length }} 条可选</span>
        </div>
        <div class="pool-list">
          <label v-for="item in availableCases" :key="item.id" class="pool-row">
            <n-checkbox v-model:checked="poolChecked[item.id]" />
            <n-tag size="tiny" :bordered="false" :type="item.label === 'good' ? 'success' : 'error'">
              {{ item.label === 'good' ? 'Good' : 'Bad' }}
            </n-tag>
            <div class="pool-main">
              <div class="pool-q">{{ item.question }}</div>
              <div class="pool-a">{{ item.answer }}</div>
            </div>
            <span class="pool-app">{{ item.app_name || '—' }}</span>
          </label>
          <div v-if="!availableCases.length" class="empty-line">没有可添加的 Case（已在本评测集或筛选无结果）</div>
        </div>
        <template #footer>
          <div class="modal-footer">
            <span class="selected-hint">已选 {{ checkedPoolIds.length }} 条</span>
            <div class="spacer"></div>
            <n-button size="small" @click="addModal = false">取消</n-button>
            <n-button size="small" type="primary" :disabled="!checkedPoolIds.length" :loading="saving" @click="addSelected">
              加入评测集
            </n-button>
          </div>
        </template>
      </n-modal>

      <!-- 编辑信息 -->
      <n-modal v-model:show="editModal" preset="card" title="编辑评测集" style="width: 520px; max-width: calc(100vw - 32px)" :bordered="false">
        <div class="edit-form">
          <div class="field">
            <label class="label">名称</label>
            <n-input v-model:value="editSet.name" />
          </div>
          <div class="field">
            <label class="label">描述</label>
            <n-input v-model:value="editSet.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
          </div>
        </div>
        <template #footer>
          <div class="modal-footer">
            <div class="spacer"></div>
            <n-button size="small" @click="editModal = false">取消</n-button>
            <n-button size="small" type="primary" :loading="saving" :disabled="!editSet.name.trim()" @click="saveEdit">保存</n-button>
          </div>
        </template>
      </n-modal>

      <CaseFlowModal
        v-model:show="manualModal"
        mode="manual"
        :default-set-id="set.id"
        :preset-app-id="set.app_id"
        :preset-app-name="set.app_name"
        @saved="reload"
      />
    </template>

    <div v-else class="empty-page">
      <div class="empty-title">评测集不存在</div>
      <n-button size="small" @click="$router.push('/app/eval')">返回</n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDialog, useMessage } from 'naive-ui'
import {
  AddOutline,
  ArrowBackOutline,
  DownloadOutline
} from '@vicons/ionicons5'
import {
  addCasesToSet,
  deleteEvalSet,
  getEvalSet,
  listApps,
  listCases,
  removeCaseFromSet,
  updateEvalSet,
  updateCase
} from '@/api'
import type { Application, EvalCase, EvalSetDetail } from '@/api/types'
import MetricStrip from '@/components/obs/MetricStrip.vue'
import CaseFlowModal from '@/components/obs/CaseFlowModal.vue'
import EvalRunPanel from '@/components/release/EvalRunPanel.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const loading = ref(false)
const saving = ref(false)
const bindingSaving = ref(false)
const running = ref(false)
const apps = ref<Application[]>([])
const appOptions = computed(() => apps.value.map(app => ({ label: app.name, value: app.id })))
const set = ref<EvalSetDetail | null>(null)
const labelFilter = ref('')
const caseDrawer = ref(false)
const activeCase = ref<EvalCase | null>(null)
const editCase = reactive({
  question: '',
  reference_answer: '',
  expected_keywords: [] as string[],
  forbidden_keywords: [] as string[],
  require_citations: false,
  note: ''
})
const addModal = ref(false)
const poolQuery = ref('')
const availableCases = ref<EvalCase[]>([])
const poolChecked = ref<Record<string, boolean>>({})
const editModal = ref(false)
const editSet = reactive({ name: '', description: '' })
const manualModal = ref(false)

const checkedPoolIds = computed(() => Object.keys(poolChecked.value).filter(id => poolChecked.value[id]))
const filteredCases = computed(() => {
  if (!set.value) return []
  return labelFilter.value ? set.value.cases.filter(c => c.label === labelFilter.value) : set.value.cases
})
const metrics = computed(() => {
  const s = set.value
  return [
    { label: 'Case 总数', value: s?.case_count ?? 0 },
    { label: 'Good', value: s?.good_count ?? 0, tone: 'good' as const },
    { label: 'Bad', value: s?.bad_count ?? 0, tone: 'bad' as const },
    { label: '可运行', value: s?.cases.filter(c => c.readiness === 'ready').length ?? 0, tone: 'good' as const },
    { label: '待补标准', value: s?.cases.filter(c => c.readiness !== 'ready').length ?? 0 }
  ]
})

function sourceLabel(source: string) {
  return ({ trace: '链路回流', log: '日志回流', manual: '手工录入', ai: 'AI 设计' } as Record<string, string>)[source] || source
}
function formatDateTime(iso: string) {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function openCase(item: EvalCase) {
  if (running.value) return
  activeCase.value = item
  editCase.question = item.question
  editCase.reference_answer = item.reference_answer
  editCase.expected_keywords = [...(item.expected_keywords || [])]
  editCase.forbidden_keywords = [...(item.forbidden_keywords || [])]
  editCase.require_citations = item.require_citations || false
  editCase.note = item.note
  caseDrawer.value = true
}
async function saveCase() {
  if (!activeCase.value || running.value || !editCase.question.trim()) return
  saving.value = true
  try {
    const updated = await updateCase(activeCase.value.id, {
      ...editCase,
      expected_keywords: editCase.expected_keywords.map(k => k.trim()).filter(Boolean),
      forbidden_keywords: editCase.forbidden_keywords.map(k => k.trim()).filter(Boolean)
    })
    activeCase.value = updated
    message.success('Case 已保存')
    caseDrawer.value = false
    await reload()
  } catch (e: any) {
    message.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
function openTrace(id: string) {
  router.push(`/app/observability/traces/${id}`)
}

async function load(showLoading = true) {
  const id = String(route.params.id)
  if (showLoading) loading.value = true
  try {
    const data = await getEvalSet(id)
    if (String(route.params.id) === id) set.value = data
  } catch (e: any) {
    if (String(route.params.id) === id) {
      if (showLoading) set.value = null
      message.error(e.message || '评测集加载失败')
    }
  } finally {
    if (String(route.params.id) === id) loading.value = false
  }
}
async function reload() {
  await load(false)
}
async function saveBinding(data: { app_id?: string; is_release_gate?: boolean }) {
  if (!set.value || running.value || bindingSaving.value) return
  bindingSaving.value = true
  try {
    await updateEvalSet(set.value.id, data)
    await reload()
    message.success('评测集设置已保存')
  } catch (e: any) {
    message.error(e.message || '设置保存失败')
  } finally {
    bindingSaving.value = false
  }
}
function bindApp(id: string | null) {
  return saveBinding({ app_id: id || '', ...(!id ? { is_release_gate: false } : {}) })
}
function toggleGate(value: boolean) {
  return saveBinding({ is_release_gate: value })
}
function openEdit() {
  if (!set.value) return
  editSet.name = set.value.name
  editSet.description = set.value.description
  editModal.value = true
}
async function saveEdit() {
  if (!set.value || !editSet.name.trim()) return
  saving.value = true
  try {
    await updateEvalSet(set.value.id, { name: editSet.name.trim(), description: editSet.description })
    message.success('已保存')
    editModal.value = false
    await reload()
  } catch (e: any) {
    message.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
function confirmDelete() {
  if (!set.value) return
  dialog.warning({
    title: '删除评测集',
    content: `确认删除「${set.value.name}」？Case 本身会保留在 Case 池中。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteEvalSet(set.value!.id)
        message.success('评测集已删除')
        router.push('/app/eval')
      } catch (e: any) {
        message.error(e.message || '删除失败')
      }
    }
  })
}
async function removeCase(item: EvalCase) {
  if (!set.value) return
  try {
    await removeCaseFromSet(set.value.id, item.id)
    message.success('已移出评测集')
    await load()
  } catch (e: any) {
    message.error(e.message || '移出失败')
  }
}
async function openAddCases() {
  addModal.value = true
  poolQuery.value = ''
  poolChecked.value = {}
  await loadPool()
}
async function loadPool() {
  try {
    const data = await listCases({ q: poolQuery.value || undefined, page: 1, page_size: 100 })
    const existing = new Set((set.value?.cases || []).map(c => c.id))
    availableCases.value = data.items.filter(c => !existing.has(c.id))
  } catch (e: any) {
    message.error(e.message || 'Case 池加载失败')
  }
}
async function addSelected() {
  if (!set.value) return
  saving.value = true
  try {
    const result = await addCasesToSet(set.value.id, checkedPoolIds.value)
    message.success(`已加入 ${result.added} 条 Case`)
    addModal.value = false
    await load()
  } catch (e: any) {
    message.error(e.message || '加入失败')
  } finally {
    saving.value = false
  }
}
async function exportJsonl() {
  if (!set.value) return
  try {
    const token = localStorage.getItem('zhishu-token') || ''
    const resp = await fetch(`/api/eval/sets/${set.value.id}/export`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!resp.ok) throw new Error('导出失败')
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${set.value.name}-评测集.jsonl`
    link.click()
    URL.revokeObjectURL(url)
    message.success('已导出 JSONL')
  } catch (e: any) {
    message.error(e.message || '导出失败')
  }
}

watch(() => route.params.id, () => {
  labelFilter.value = ''
  caseDrawer.value = false
  running.value = false
  void load()
}, { immediate: true })
onMounted(async () => {
  try {
    apps.value = await listApps()
  } catch (e: any) {
    message.error(e.message || '应用列表加载失败')
  }
})
</script>

<style scoped>
.set-page {
  max-width: 1440px;
}
.loading-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 60px 0;
  justify-content: center;
  color: #8a9099;
  font-size: 12px;
}
.detail-top {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 14px;
}
.back-btn {
  color: #6b7280;
  white-space: nowrap;
  padding-top: 3px;
}
.title-col {
  flex: 1;
  min-width: 0;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.set-title {
  margin: 0;
  font-size: 19px;
  font-weight: 650;
  color: #1f2329;
  letter-spacing: -0.01em;
}
.set-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #7a828e;
  line-height: 1.6;
}
.set-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  margin-top: 5px;
  font-size: 10.5px;
  color: #9aa1ab;
}
.dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #cfd4dc;
}
.action-col {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.list-panel {
  margin-top: 14px;
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 14px 16px;
}
.quality-panel {
  margin-top: 14px;
  padding: 14px 16px;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  background: #fff;
}
.binding-row {
  display: flex;
  align-items: flex-end;
  gap: 24px;
  flex-wrap: wrap;
}
.binding-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 340px;
  max-width: 100%;
}
.gate-field {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 34px;
}
.standard-hint {
  margin: 8px 0 12px;
  font-size: 12px;
  color: #5c6470;
  line-height: 1.6;
}
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.list-title {
  font-size: 13px;
  font-weight: 600;
  color: #2b3442;
}
.list-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.case-list {
  display: flex;
  flex-direction: column;
}
.case-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 4px;
  border-bottom: 1px dashed #eef0f3;
}
.case-row:last-child {
  border-bottom: 0;
}
.case-label {
  flex: 0 0 72px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding-top: 2px;
}
.case-main {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.case-question {
  font-size: 12.5px;
  color: #1f2329;
  font-weight: 500;
  line-height: 1.5;
}
.case-main:hover .case-question {
  color: #3370ff;
}
.case-answer {
  font-size: 11px;
  color: #8a9099;
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.case-reference {
  margin-top: 5px;
  font-size: 10.5px;
  color: #4d6a9c;
  background: #f4f7ff;
  border-radius: 5px;
  padding: 4px 7px;
  line-height: 1.55;
}
.ref-label {
  color: #8aa0c8;
  margin-right: 5px;
}
.case-meta-col {
  flex: 0 0 150px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  align-items: flex-end;
  font-size: 10.5px;
  color: #8a9099;
  padding-top: 2px;
}
.meta-app {
  color: #5c6470;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta-tags {
  color: #9b8bc4;
}
.case-actions {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
  padding-top: 2px;
}
.empty {
  padding: 46px 16px;
  text-align: center;
}
.empty-title {
  font-size: 14px;
  font-weight: 600;
  color: #3b4351;
}
.empty-desc {
  font-size: 12px;
  color: #8a9099;
  max-width: 460px;
  margin: 6px auto 14px;
  line-height: 1.7;
}
.drawer-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.drawer-sub {
  font-size: 11px;
  color: #8a9099;
}
.case-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.detail-block {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.detail-label {
  font-size: 10.5px;
  color: #9aa1ab;
}
.detail-text {
  font-size: 12.5px;
  line-height: 1.75;
  color: #333b48;
  white-space: pre-wrap;
  word-break: break-word;
  background: #fafbfc;
  border: 1px solid #eef0f3;
  border-radius: 7px;
  padding: 9px 11px;
}
.detail-text.reference {
  background: #f7faff;
  border-color: #e3ebff;
  color: #33518c;
}
.detail-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: #8a9099;
  padding: 9px 11px;
  border: 1px dashed #e6e9ee;
  border-radius: 7px;
}
.add-toolbar {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 10px;
}
.pool-count {
  margin-left: auto;
  font-size: 11px;
  color: #8a9099;
}
.pool-list {
  max-height: 440px;
  overflow: auto;
  border: 1px solid #eef0f3;
  border-radius: 8px;
}
.pool-row {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 10px 12px;
  border-bottom: 1px dashed #f0f1f3;
  cursor: pointer;
}
.pool-row:hover {
  background: #fafbfc;
}
.pool-row:last-child {
  border-bottom: 0;
}
.pool-main {
  flex: 1;
  min-width: 0;
}
.pool-q {
  font-size: 12px;
  color: #333b48;
  line-height: 1.5;
}
.pool-a {
  font-size: 10.5px;
  color: #9aa1ab;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}
.pool-app {
  flex: 0 0 110px;
  font-size: 10.5px;
  color: #8a9099;
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty-line {
  padding: 26px 12px;
  text-align: center;
  font-size: 11.5px;
  color: #a3a9b3;
}
.modal-footer {
  display: flex;
  align-items: center;
  gap: 10px;
}
.selected-hint {
  font-size: 11.5px;
  color: #5c6470;
}
.spacer {
  flex: 1;
}
.edit-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.label {
  font-size: 12px;
  color: #4e5969;
}
.empty-page {
  padding: 80px 0;
  text-align: center;
}
.empty-page .empty-title {
  font-size: 14px;
  margin-bottom: 12px;
}
@media (max-width: 760px) {
  .detail-top {
    flex-wrap: wrap;
  }
  .case-meta-col {
    display: none;
  }
  .action-col {
    justify-content: flex-start;
  }
  .list-actions {
    flex-wrap: wrap;
  }
}
</style>
