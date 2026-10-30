<template>
  <div class="trace-table">
    <div class="filter-bar">
      <n-select v-model:value="filters.type" :options="typeOptions" placeholder="类型" clearable style="width: 128px" />
      <n-select v-model:value="filters.status" :options="statusOptions" placeholder="状态" clearable style="width: 110px" />
      <n-select v-model:value="filters.app" :options="appOptions" placeholder="应用" clearable filterable style="width: 170px" />
      <n-input v-model:value="filters.q" placeholder="搜索问题 / 回答" clearable style="width: 230px" @keydown.enter="search" />
      <n-button type="primary" ghost @click="search">
        <template #icon><n-icon><SearchOutline /></n-icon></template>
        筛选
      </n-button>
      <n-button text @click="reset">重置</n-button>
      <div class="filter-right">
        <span class="count">共 {{ total }} 条链路</span>
        <n-button quaternary size="small" :loading="loading" @click="load">
          <template #icon><n-icon><RefreshOutline /></n-icon></template>
        </n-button>
      </div>
    </div>

    <div class="table-panel">
      <n-data-table
        :columns="columns"
        :data="rows"
        :row-key="(row: TraceRun) => row.id"
        :loading="loading"
        :pagination="pagination"
        remote
        :scroll-x="1040"
        @update:page="onPage"
      />
      <div v-if="!loading && !rows.length" class="empty">
        <div class="empty-title">还没有调用链路</div>
        <div class="empty-desc">发起一次对话或构建知识库后，这里会出现完整的执行链路；也可以先载入演示数据体验。</div>
        <n-button v-if="canDemo" size="small" type="primary" ghost @click="loadDemo">载入演示数据</n-button>
      </div>
    </div>

    <CaseFlowModal
      v-model:show="caseModal"
      mode="trace"
      :trace-id="active?.id || ''"
      :preset-question="active?.query || ''"
      :preset-answer="active?.answer || ''"
      :preset-app-id="active?.app_id || ''"
      :preset-app-name="active?.app_name || ''"
      @saved="load"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NTag, type DataTableColumns } from 'naive-ui'
import { RefreshOutline, SearchOutline } from '@vicons/ionicons5'
import { listApps, listTraces, loadDemoObservability } from '@/api'
import type { Application, TraceRun } from '@/api/types'
import CaseFlowModal from './CaseFlowModal.vue'

const emit = defineEmits<{ changed: [] }>()
const props = withDefaults(defineProps<{ canDemo?: boolean }>(), { canDemo: false })
const router = useRouter()
const loading = ref(false)
const rows = ref<TraceRun[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const appOptions = ref<{ label: string; value: string }[]>([])
const filters = reactive({ type: null as string | null, status: null as string | null, app: null as string | null, q: '' })
const caseModal = ref(false)
const active = ref<TraceRun | null>(null)

const typeOptions = [
  { label: 'Agent', value: 'agent' },
  { label: 'Chat Flow', value: 'chatflow' },
  { label: '简易 RAG', value: 'chat' },
  { label: '知识库构建', value: 'kb_build' }
]
const statusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'error' },
  { label: '降级', value: 'degraded' }
]

const TYPE_LABEL: Record<string, string> = { agent: 'Agent', chatflow: 'Chat Flow', chat: '简易 RAG', kb_build: '知识库构建' }
const TYPE_COLOR: Record<string, string> = { agent: 'purple', chatflow: 'info', chat: 'success', kb_build: 'warning' }

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
    load()
  }
}))

const columns: DataTableColumns<TraceRun> = [
  {
    title: '时间',
    key: 'started_at',
    width: 136,
    render: row => h('span', { class: 'time' }, formatTime(row.started_at))
  },
  {
    title: '类型',
    key: 'trace_type',
    width: 104,
    render: row =>
      h(
        NTag,
        { size: 'tiny', bordered: false, type: (TYPE_COLOR[row.trace_type] || 'default') as any },
        { default: () => TYPE_LABEL[row.trace_type] || row.trace_type }
      )
  },
  {
    title: '应用 / 来源',
    key: 'app_name',
    width: 136,
    render: row => h('span', { class: 'app-cell' }, row.app_name || row.kb_name || '—')
  },
  {
    title: '输入 / 标题',
    key: 'query',
    width: 288,
    render: row =>
      h('div', { class: 'title-cell' }, [
        h('div', { class: 'title-text', onClick: () => open(row) }, row.query || row.title || '—'),
        h(
          'div',
          { class: 'title-sub' },
          (row.title && row.title !== row.query ? row.title : `${row.span_count} 个执行节点`) +
            (row.cases?.length ? ` · 已回流 ${row.cases[0].label === 'good' ? 'Good' : 'Bad'}` : '')
        )
      ])
  },
  {
    title: '状态',
    key: 'status',
    width: 76,
    render: row =>
      h(
        NTag,
        {
          size: 'tiny',
          bordered: false,
          type: row.status === 'success' ? 'success' : row.status === 'error' ? 'error' : 'warning'
        },
        { default: () => ({ success: '成功', error: '失败', degraded: '降级', running: '运行中' }[row.status] || row.status) }
      )
  },
  {
    title: 'Token',
    key: 'tokens',
    width: 82,
    render: row => h('span', { class: 'num' }, (row.tokens?.total ?? 0).toLocaleString())
  },
  {
    title: '成本',
    key: 'cost_cny',
    width: 92,
    render: row => h('span', { class: 'num' }, `¥${Number(row.cost_cny || 0).toFixed(4)}`)
  },
  {
    title: '耗时',
    key: 'duration_ms',
    width: 78,
    render: row => h('span', { class: 'num' }, formatDuration(row.duration_ms))
  },
  {
    title: '操作',
    key: 'actions',
    width: 130,
    fixed: 'right',
    render: row =>
      h('div', { class: 'row-actions' }, [
        h(NButton, { text: true, size: 'tiny', type: 'primary', onClick: () => open(row) }, { default: () => '查看链路' }),
        h(
          NButton,
          {
            text: true,
            size: 'tiny',
            onClick: () => {
              active.value = row
              caseModal.value = true
            }
          },
          { default: () => '回流' }
        )
      ])
  }
]

function formatTime(iso: string) {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 60000).toFixed(1)}m`
}
function open(row: TraceRun) {
  router.push(`/app/observability/traces/${row.id}`)
}

async function load() {
  loading.value = true
  try {
    const data = await listTraces({
      trace_type: filters.type ?? undefined,
      status: filters.status ?? undefined,
      app_id: filters.app ?? undefined,
      q: filters.q || undefined,
      page: page.value,
      page_size: pageSize.value
    })
    rows.value = data.items
    total.value = data.total
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}
function search() {
  page.value = 1
  load()
}
function reset() {
  filters.type = null
  filters.status = null
  filters.app = null
  filters.q = ''
  search()
}
function onPage(p: number) {
  page.value = p
  load()
}
async function loadDemo() {
  try {
    await loadDemoObservability()
    await load()
    emit('changed')
  } catch (e: any) {
    console.error(e)
  }
}

onMounted(async () => {
  try {
    const apps = await listApps()
    appOptions.value = apps.map((a: Application) => ({ label: a.name, value: a.id }))
  } catch {
    appOptions.value = []
  }
  load()
})

defineExpose({ reload: load })
void props
</script>

<style scoped>
.trace-table {
  display: flex;
  flex-direction: column;
  gap: 14px;
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
.filter-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}
.count {
  font-size: 11.5px;
  color: #8a9099;
}
.table-panel {
  position: relative;
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 4px 4px 0;
  overflow: hidden;
}
:deep(.num) {
  font-variant-numeric: tabular-nums;
  color: #4e5969;
}
:deep(.time) {
  font-variant-numeric: tabular-nums;
  color: #5c6470;
}
:deep(.app-cell) {
  color: #3b4351;
}
:deep(.title-cell) {
  cursor: default;
}
:deep(.title-text) {
  color: #1f2329;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
:deep(.title-text:hover) {
  color: #3370ff;
}
:deep(.title-sub) {
  font-size: 10.5px;
  color: #9aa1ab;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.row-actions) {
  display: flex;
  gap: 10px;
}
:deep(.muted) {
  color: #b3b9c2;
}
.empty {
  padding: 38px 20px 44px;
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
  margin: 6px auto 14px;
  max-width: 420px;
  line-height: 1.7;
}

.table-panel :deep(table) {
  table-layout: fixed !important;
}
</style>
