<template>
  <div class="page eval-page">
    <div class="page-head">
      <div>
        <h2 class="page-title">评测集</h2>
        <p class="page-desc">把线上真实对话回流成 good / bad Case，按业务聚合为可复用的回归基线。</p>
      </div>
      <div class="head-actions">
        <n-button size="small" @click="manualModal = true">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          手动新建 Case
        </n-button>
        <n-button size="small" type="primary" @click="openCreateSet()">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          新建评测集
        </n-button>
      </div>
    </div>

    <MetricStrip :items="metrics" />

    <n-tabs v-model:value="tab" type="line" class="eval-tabs" display-directive="if">
      <n-tab-pane name="cases" tab="Case 池">
        <div class="pool">
          <div class="filter-bar">
            <n-select v-model:value="filters.label" :options="labelOptions" placeholder="标签" clearable style="width: 110px" @update:value="search" />
            <n-select v-model:value="filters.source" :options="sourceOptions" placeholder="来源" clearable style="width: 120px" @update:value="search" />
            <n-select v-model:value="filters.status" :options="statusOptions" placeholder="状态" clearable style="width: 110px" @update:value="search" />
            <n-input v-model:value="filters.q" placeholder="搜索问题 / 回答 / 备注" clearable style="width: 240px" @keydown.enter="search" />
            <n-button type="primary" ghost @click="search">
              <template #icon><n-icon><SearchOutline /></n-icon></template>
              筛选
            </n-button>
            <n-button text @click="reset">重置</n-button>
            <span class="count">共 {{ total }} 条 Case</span>
          </div>

          <div v-if="selectedIds.length" class="bulk-bar">
            <span class="bulk-count">已选 {{ selectedIds.length }} 条</span>
            <n-button size="small" type="primary" ghost @click="addToSetModal = true">加入评测集</n-button>
            <n-button size="small" @click="openCreateSet(selectedIds)">新建评测集并加入</n-button>
            <n-button size="small" text @click="selectedIds = []">清除选择</n-button>
          </div>

          <div class="table-panel">
            <n-data-table
              v-model:checked-row-keys="selectedIds"
              :columns="columns"
              :data="cases"
              :row-key="(row: EvalCase) => row.id"
              :loading="loading"
              :pagination="pagination"
              remote
              :scroll-x="1000"
              @update:page="onPage"
            />
            <div v-if="!loading && !cases.length" class="empty">
              <div class="empty-title">Case 池还是空的</div>
              <div class="empty-desc">
                去「可观测中心 → 调用链 / 对话日志」，把真实线上对话标记为 Good 或 Bad 后一键回流；也可以手动录入外部反馈。
              </div>
              <n-space :size="8">
                <n-button size="small" type="primary" ghost @click="$router.push('/app/observability?tab=traces')">去调用链回流</n-button>
                <n-button size="small" @click="manualModal = true">手动新建</n-button>
              </n-space>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="sets" tab="评测集">
        <div class="sets">
          <div v-if="sets.length" class="set-list">
            <button v-for="set in sets" :key="set.id" class="set-row" type="button" @click="openSet(set.id)">
              <div class="set-main">
                <div class="set-title-line">
                  <span class="set-name">{{ set.name }}</span>
                  <n-tag size="tiny" :bordered="false">{{ set.case_count }} 条 Case</n-tag>
                  <n-tag v-if="set.is_release_gate" size="tiny" :bordered="false" type="warning">发布门禁</n-tag>
                </div>
                <div class="set-desc">{{ set.description || '暂无描述' }}</div>
                <div class="set-meta">
                  <span>{{ set.app_name || '未绑定应用' }}</span>
                  <span v-if="set.latest_run">最近 {{ set.latest_run.passed_count }}/{{ set.latest_run.total_count }} 通过{{ set.latest_run.matches_draft ? '' : ' · 草稿已变更' }}</span>
                  <span class="dot"></span>
                  <span>更新于 {{ formatDate(set.updated_at) }}</span>
                  <span v-if="set.tags?.length" class="set-tags">
                    <span v-for="tag in set.tags.slice(0, 4)" :key="tag" class="tag">{{ tag }}</span>
                  </span>
                </div>
              </div>
              <div class="set-stats">
                <div class="ratio-bar">
                  <span class="good" :style="{ width: goodWidth(set) }"></span>
                  <span class="bad"></span>
                </div>
                <div class="ratio-label">
                  <span class="good-text">{{ set.good_count }} Good</span>
                  <span class="bad-text">{{ set.bad_count }} Bad</span>
                </div>
              </div>
              <n-icon size="16" class="set-arrow"><ChevronForwardOutline /></n-icon>
            </button>
          </div>
          <div v-else class="empty set-empty">
            <div class="empty-title">还没有评测集</div>
            <div class="empty-desc">评测集是 Case 的聚合容器。可以按业务线、版本或问题类型建立多个基线，例如「售后客服回归集」。</div>
            <n-button size="small" type="primary" ghost @click="openCreateSet()">新建评测集</n-button>
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>

    <!-- Case 详情 / 编辑抽屉 -->
    <n-drawer v-model:show="caseDrawer" :width="620" style="max-width: 100vw" placement="right">
      <n-drawer-content v-if="activeCase" closable>
        <template #header>
          <div class="drawer-head">
            <n-tag size="small" :bordered="false" :type="activeCase.label === 'good' ? 'success' : 'error'">
              {{ activeCase.label === 'good' ? 'Good Case' : 'Bad Case' }}
            </n-tag>
            <n-tag size="tiny" :bordered="false" :type="activeCase.readiness === 'ready' ? 'success' : 'warning'">
              {{ activeCase.readiness === 'ready' ? '可运行' : '待补标准' }}
            </n-tag>
            <span class="drawer-sub">{{ sourceLabel(activeCase.source) }} · {{ formatDate(activeCase.created_at) }}</span>
          </div>
        </template>

        <div class="drawer-form">
          <div class="field">
            <label class="label">问题</label>
            <n-input v-model:value="editForm.question" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
          </div>
          <div class="field">
            <label class="label">线上回答</label>
            <div class="readonly-block">{{ activeCase.answer || '（无）' }}</div>
          </div>
          <div class="field">
            <label class="label">期望回答（评测基线）</label>
            <n-input v-model:value="editForm.reference_answer" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="用于后续回归对比" />
          </div>
          <div class="field-row">
            <div class="field">
              <label class="label">必须包含关键词</label>
              <n-dynamic-tags v-model:value="editForm.expected_keywords" />
            </div>
            <div class="field">
              <label class="label">禁止出现关键词</label>
              <n-dynamic-tags v-model:value="editForm.forbidden_keywords" />
            </div>
          </div>
          <div class="field">
            <label class="label">要求引用</label>
            <n-switch v-model:value="editForm.require_citations" aria-label="要求引用" style="align-self: flex-start" />
            <span class="standard-hint">填写期望回答、关键词或引用要求后，Case 才能参与评测。</span>
          </div>
          <div class="field-row">
            <div class="field">
              <label class="label">标签</label>
              <n-select v-model:value="editForm.label" :options="labelOptions" />
            </div>
            <div class="field">
              <label class="label">状态</label>
              <n-select v-model:value="editForm.status" :options="statusOptions" />
            </div>
          </div>
          <div class="field">
            <label class="label">备注</label>
            <n-input v-model:value="editForm.note" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
          </div>
          <div class="field">
            <label class="label">标签词</label>
            <n-dynamic-tags v-model:value="editForm.tags" :max="6" />
          </div>

          <div class="meta-grid">
            <div class="meta-item"><span>应用</span>{{ activeCase.app_name || '—' }}</div>
            <div class="meta-item"><span>来源</span>{{ sourceLabel(activeCase.source) }}</div>
            <div class="meta-item"><span>所属评测集</span>{{ activeCase.sets?.map(s => s.name).join('、') || '未加入' }}</div>
            <div class="meta-item"><span>Trace</span>{{ activeCase.trace_id || '—' }}</div>
          </div>
          <n-button v-if="activeCase.trace_id" size="small" type="primary" ghost @click="openTrace(activeCase.trace_id)">
            查看原始调用链路
          </n-button>
        </div>

        <template #footer>
          <div class="drawer-footer">
            <n-button size="small" type="error" ghost @click="removeCase">删除 Case</n-button>
            <div class="spacer"></div>
            <n-button size="small" @click="caseDrawer = false">取消</n-button>
            <n-button size="small" type="primary" :loading="saving" @click="saveCase">保存修改</n-button>
          </div>
        </template>
      </n-drawer-content>
    </n-drawer>

    <CaseFlowModal v-model:show="manualModal" mode="manual" @saved="reload" />

    <!-- 新建评测集 -->
    <n-modal v-model:show="setModal" preset="card" title="新建评测集" style="width: 520px; max-width: calc(100vw - 32px)" :bordered="false">
      <div class="drawer-form">
        <div class="field">
          <label class="label">名称 <span class="req">*</span></label>
          <n-input v-model:value="newSet.name" placeholder="例如：售后客服回归集 v2" />
        </div>
        <div class="field">
          <label class="label">描述</label>
          <n-input v-model:value="newSet.description" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" placeholder="测试范围、业务背景、回归频率" />
        </div>
        <div v-if="pendingCaseIds.length" class="pending-hint">将同时把已选的 {{ pendingCaseIds.length }} 条 Case 加入该评测集。</div>
      </div>
      <template #footer>
        <div class="drawer-footer">
          <div class="spacer"></div>
          <n-button size="small" @click="setModal = false">取消</n-button>
          <n-button size="small" type="primary" :disabled="!newSet.name.trim()" :loading="saving" @click="createSet">创建</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 加入已有评测集 -->
    <n-modal v-model:show="addToSetModal" preset="card" title="加入评测集" style="width: 480px; max-width: calc(100vw - 32px)" :bordered="false">
      <div class="drawer-form">
        <div class="field">
          <label class="label">选择评测集</label>
          <n-select v-model:value="targetSetId" :options="setOptions" filterable placeholder="选择一个评测集" />
        </div>
        <div class="pending-hint">已选 {{ selectedIds.length }} 条 Case。</div>
      </div>
      <template #footer>
        <div class="drawer-footer">
          <div class="spacer"></div>
          <n-button size="small" @click="addToSetModal = false">取消</n-button>
          <n-button size="small" type="primary" :disabled="!targetSetId" :loading="saving" @click="addSelectedToSet">加入</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NTag, useMessage, type DataTableColumns } from 'naive-ui'
import {
  AddOutline,
  ChevronForwardOutline,
  SearchOutline
} from '@vicons/ionicons5'
import {
  addCasesToSet,
  createEvalSet,
  deleteCase,
  getEvalOverview,
  listCases,
  listEvalSets,
  updateCase
} from '@/api'
import type { EvalCase, EvalOverview, EvalSetSummary } from '@/api/types'
import MetricStrip from '@/components/obs/MetricStrip.vue'
import CaseFlowModal from '@/components/obs/CaseFlowModal.vue'

const router = useRouter()
const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const tab = ref('cases')
const overview = ref<EvalOverview | null>(null)
const cases = ref<EvalCase[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const sets = ref<EvalSetSummary[]>([])
const selectedIds = ref<string[]>([])
const filters = reactive({
  label: null as string | null,
  source: null as string | null,
  status: null as string | null,
  q: ''
})

const labelOptions = [
  { label: 'Good', value: 'good' },
  { label: 'Bad', value: 'bad' }
]
const statusOptions = [
  { label: '待确认', value: 'candidate' },
  { label: '已确认', value: 'confirmed' }
]
const sourceOptions = [
  { label: '链路回流', value: 'trace' },
  { label: '日志回流', value: 'log' },
  { label: '手工录入', value: 'manual' },
  { label: 'AI 设计', value: 'ai' }
]
const setOptions = computed(() => sets.value.map(s => ({ label: `${s.name}（${s.case_count}）`, value: s.id })))

const metrics = computed(() => [
  { label: 'Case 总数', value: overview.value?.case_count ?? 0 },
  { label: 'Good', value: overview.value?.good_count ?? 0, tone: 'good' as const },
  { label: 'Bad', value: overview.value?.bad_count ?? 0, tone: 'bad' as const },
  { label: '评测集', value: overview.value?.set_count ?? 0 },
  { label: '本周新增', value: overview.value?.new_this_week ?? 0, sub: `${overview.value?.unassigned ?? 0} 条未归集` }
])

const pagination = computed(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: total.value,
  showSizePicker: true,
  pageSizes: [20, 50, 100],
  onChange: (p: number) => (page.value = p),
  onUpdatePageSize: (s: number) => {
    pageSize.value = s
    page.value = 1
    loadCases()
  }
}))

const columns: DataTableColumns<EvalCase> = [
  { type: 'selection' },
  {
    title: '标签',
    key: 'label',
    width: 76,
    render: row =>
      h(NTag, { size: 'tiny', bordered: false, type: row.label === 'good' ? 'success' : 'error' }, {
        default: () => (row.label === 'good' ? 'Good' : 'Bad')
      })
  },
  {
    title: '问题 / 回答',
    key: 'question',
    width: 330,
    render: row =>
      h('div', { class: 'case-cell', onClick: () => openCase(row) }, [
        h('div', { class: 'case-q' }, row.question || '（无问题）'),
        h('div', { class: 'case-a' }, row.answer || '（无回答）')
      ])
  },
  {
    title: '评测标准',
    key: 'readiness',
    width: 100,
    render: row => h(NTag, { size: 'tiny', bordered: false, type: row.readiness === 'ready' ? 'success' : 'warning' }, {
      default: () => row.readiness === 'ready' ? '可运行' : '待补标准'
    })
  },
  {
    title: '应用',
    key: 'app_name',
    width: 120,
    render: row => h('span', { class: 'muted' }, row.app_name || '—')
  },
  {
    title: '来源',
    key: 'source',
    width: 88,
    render: row => h('span', { class: 'source-pill ' + row.source }, sourceLabel(row.source))
  },
  {
    title: '评测集',
    key: 'sets',
    width: 132,
    render: row =>
      row.sets?.length
        ? h('div', { class: 'set-chips' }, row.sets.slice(0, 2).map(s => h('span', { class: 'set-chip' }, s.name)))
        : h('span', { class: 'muted' }, '未归集')
  },
  {
    title: '时间',
    key: 'created_at',
    width: 100,
    render: row => h('span', { class: 'muted num' }, formatDate(row.created_at))
  },
  {
    title: '操作',
    key: 'actions',
    width: 84,
    render: row =>
      h('div', { class: 'row-actions' }, [
        h(NButton, { text: true, size: 'tiny', type: 'primary', onClick: () => openCase(row) }, { default: () => '查看' })
      ])
  }
]

const caseDrawer = ref(false)
const activeCase = ref<EvalCase | null>(null)
const editForm = reactive({
  question: '',
  reference_answer: '',
  expected_keywords: [] as string[],
  forbidden_keywords: [] as string[],
  require_citations: false,
  label: 'good',
  status: 'confirmed',
  note: '',
  tags: [] as string[]
})

const manualModal = ref(false)
const setModal = ref(false)
const addToSetModal = ref(false)
const pendingCaseIds = ref<string[]>([])
const targetSetId = ref<string | null>(null)
const newSet = reactive({ name: '', description: '' })

function openCase(row: EvalCase) {
  activeCase.value = row
  editForm.question = row.question
  editForm.reference_answer = row.reference_answer
  editForm.expected_keywords = [...(row.expected_keywords || [])]
  editForm.forbidden_keywords = [...(row.forbidden_keywords || [])]
  editForm.require_citations = row.require_citations || false
  editForm.label = row.label
  editForm.status = row.status || 'confirmed'
  editForm.note = row.note
  editForm.tags = [...(row.tags || [])]
  caseDrawer.value = true
}
async function saveCase() {
  if (!activeCase.value) return
  saving.value = true
  try {
    const updated = await updateCase(activeCase.value.id, {
      question: editForm.question,
      reference_answer: editForm.reference_answer,
      expected_keywords: editForm.expected_keywords.map(k => k.trim()).filter(Boolean),
      forbidden_keywords: editForm.forbidden_keywords.map(k => k.trim()).filter(Boolean),
      require_citations: editForm.require_citations,
      label: editForm.label,
      status: editForm.status,
      note: editForm.note,
      tags: editForm.tags
    })
    message.success('Case 已保存')
    Object.assign(activeCase.value, updated)
    await reload()
  } catch (e: any) {
    message.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}
async function removeCase() {
  if (!activeCase.value) return
  try {
    await deleteCase(activeCase.value.id)
    message.success('Case 已删除')
    caseDrawer.value = false
    await reload()
  } catch (e: any) {
    message.error(e.message || '删除失败')
  }
}
function openTrace(id: string) {
  router.push(`/app/observability/traces/${id}`)
}
function sourceLabel(source: string) {
  return ({ trace: '链路回流', log: '日志回流', manual: '手工录入', ai: 'AI 设计' } as Record<string, string>)[source] || source
}
function formatDate(iso: string) {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function goodWidth(set: EvalSetSummary) {
  const total = set.case_count || 1
  return `${Math.max(4, (set.good_count / total) * 100)}%`
}

function openCreateSet(caseIds: string[] = []) {
  pendingCaseIds.value = caseIds
  newSet.name = ''
  newSet.description = ''
  setModal.value = true
}
function openSet(id: string) {
  router.push(`/app/eval/${id}`)
}
async function createSet() {
  if (!newSet.name.trim()) return
  saving.value = true
  try {
    const set = await createEvalSet({
      name: newSet.name.trim(),
      description: newSet.description,
      case_ids: pendingCaseIds.value
    })
    message.success('评测集已创建')
    setModal.value = false
    selectedIds.value = []
    await reload()
    tab.value = 'sets'
    router.push(`/app/eval/${set.id}`)
  } catch (e: any) {
    message.error(e.message || '创建失败')
  } finally {
    saving.value = false
  }
}
async function addSelectedToSet() {
  if (!targetSetId.value) return
  saving.value = true
  try {
    const result = await addCasesToSet(targetSetId.value, selectedIds.value)
    message.success(`已加入 ${result.added} 条 Case`)
    addToSetModal.value = false
    selectedIds.value = []
    await reload()
  } catch (e: any) {
    message.error(e.message || '加入失败')
  } finally {
    saving.value = false
  }
}

async function loadCases() {
  loading.value = true
  try {
    const data = await listCases({
      label: filters.label ?? undefined,
      source: filters.source ?? undefined,
      status: filters.status ?? undefined,
      q: filters.q || undefined,
      page: page.value,
      page_size: pageSize.value
    })
    cases.value = data.items
    total.value = data.total
  } catch (e: any) {
    message.error(e.message || 'Case 加载失败')
  } finally {
    loading.value = false
  }
}
async function loadMeta() {
  try {
    const [o, s] = await Promise.all([getEvalOverview(), listEvalSets()])
    overview.value = o
    sets.value = s
  } catch (e: any) {
    message.error(e.message || '评测数据加载失败')
  }
}
async function reload() {
  await Promise.all([loadCases(), loadMeta()])
}
function search() {
  page.value = 1
  loadCases()
}
function reset() {
  filters.label = null
  filters.source = null
  filters.status = null
  filters.q = ''
  search()
}
function onPage(p: number) {
  page.value = p
  loadCases()
}

onMounted(reload)
</script>

<style scoped>
.eval-page {
  max-width: 1440px;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: #1f2329;
}
.page-desc {
  margin: 5px 0 0;
  font-size: 12.5px;
  color: #7a828e;
  line-height: 1.6;
}
.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.eval-tabs :deep(.n-tabs-nav) {
  margin-bottom: 16px;
}
.pool {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 11px 12px;
}
.count {
  margin-left: auto;
  font-size: 11.5px;
  color: #8a9099;
}
.bulk-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #f4f7ff;
  border: 1px solid #dfe8ff;
  border-radius: 9px;
  padding: 9px 12px;
}
.bulk-count {
  font-size: 12px;
  color: #33518c;
  font-weight: 550;
}
.table-panel {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 4px 4px 0;
  overflow: hidden;
}
:deep(.case-cell) {
  cursor: pointer;
}
:deep(.case-q) {
  font-size: 12.5px;
  color: #1f2329;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.case-cell:hover .case-q) {
  color: #3370ff;
}
:deep(.case-a) {
  font-size: 10.5px;
  color: #9aa1ab;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}
:deep(.muted) {
  color: #8a9099;
}
:deep(.num) {
  font-variant-numeric: tabular-nums;
}
:deep(.source-pill) {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f2f4f7;
  color: #5c6470;
}
:deep(.source-pill.trace) {
  background: #eef3ff;
  color: #33518c;
}
:deep(.source-pill.log) {
  background: #eef8f8;
  color: #1d7474;
}
:deep(.set-chips) {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
:deep(.set-chip) {
  font-size: 9.5px;
  padding: 2px 5px;
  border-radius: 3px;
  background: #f4f2ff;
  color: #5f4b9e;
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.row-actions) {
  display: flex;
  gap: 8px;
}
.empty {
  padding: 46px 20px 52px;
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
  max-width: 480px;
  margin: 6px auto 14px;
  line-height: 1.7;
}
.sets {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.set-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.set-row {
  display: flex;
  align-items: center;
  gap: 18px;
  width: 100%;
  text-align: left;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  background: #fff;
  padding: 15px 16px;
  cursor: pointer;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}
.set-row:hover {
  border-color: #c7d5f3;
  box-shadow: 0 2px 12px rgba(35, 53, 92, 0.05);
}
.set-main {
  flex: 1;
  min-width: 0;
}
.set-title-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.set-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2329;
}
.set-desc {
  margin-top: 4px;
  font-size: 11.5px;
  color: #7a828e;
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.set-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 10.5px;
  color: #9aa1ab;
}
.dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #cfd4dc;
}
.set-tags {
  display: flex;
  gap: 4px;
}
.tag {
  background: #f5f6f8;
  border-radius: 3px;
  padding: 1px 5px;
  color: #7a828e;
}
.set-stats {
  flex: 0 0 170px;
}
.ratio-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: #f0f2f5;
}
.ratio-bar .good {
  background: #58c08a;
}
.ratio-bar .bad {
  flex: 1;
  background: #f0a6ad;
}
.ratio-label {
  display: flex;
  justify-content: space-between;
  margin-top: 5px;
  font-size: 10px;
}
.good-text {
  color: #1c7d4d;
}
.bad-text {
  color: #bf2c3b;
}
.set-arrow {
  color: #b3b9c2;
}
.set-empty {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
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
.drawer-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.label {
  font-size: 12px;
  color: #4e5969;
}
.req {
  color: #d22d3d;
}
.readonly-block {
  background: #fafbfc;
  border: 1px solid #eef0f3;
  border-radius: 7px;
  padding: 9px 11px;
  font-size: 12px;
  line-height: 1.7;
  color: #4b5563;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
  overflow: auto;
}
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 10px 12px;
  background: #fcfcfd;
  border: 1px solid #eef0f3;
  border-radius: 8px;
  font-size: 11px;
  color: #3b4351;
}
.meta-item span {
  display: block;
  font-size: 10px;
  color: #9aa1ab;
  margin-bottom: 2px;
}
.drawer-footer {
  display: flex;
  align-items: center;
  gap: 10px;
}
.spacer {
  flex: 1;
}
.pending-hint {
  font-size: 11.5px;
  color: #33518c;
  background: #f4f7ff;
  border: 1px solid #e2eaff;
  border-radius: 7px;
  padding: 8px 10px;
}
.standard-hint {
  color: #5c6470;
  font-size: 12px;
  line-height: 1.6;
}
@media (max-width: 760px) {
  .page-head {
    flex-direction: column;
  }
  .set-stats {
    display: none;
  }
  .field-row {
    grid-template-columns: 1fr;
  }
}

.table-panel :deep(table) {
  table-layout: fixed !important;
}
</style>
