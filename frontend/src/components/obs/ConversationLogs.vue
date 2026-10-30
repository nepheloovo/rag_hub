<template>
  <div class="logs-wrap">
    <div class="logs-top">
      <MetricStrip :items="metrics" />
      <n-button quaternary size="small" :loading="loading" @click="load">
        <template #icon><n-icon><RefreshOutline /></n-icon></template>
        刷新
      </n-button>
    </div>

    <div class="filter-bar">
      <n-select v-model:value="filters.role" :options="roleOptions" placeholder="角色" clearable style="width: 130px" />
      <n-select v-model:value="filters.kb" :options="kbOptions" placeholder="知识库" clearable filterable style="width: 180px" />
      <n-select v-model:value="filters.status" :options="statusOptions" placeholder="状态" clearable style="width: 110px" />
      <n-input v-model:value="filters.q" placeholder="搜索问题 / 回答内容" clearable style="width: 220px" @keydown.enter="search" />
      <n-button type="primary" ghost @click="search">
        <template #icon><n-icon><SearchOutline /></n-icon></template>
        查询
      </n-button>
      <n-button text @click="reset">重置</n-button>
    </div>

    <div class="table-panel">
      <n-data-table
        :columns="columns"
        :data="rows"
        :row-key="(row: LogItem) => row.id"
        :loading="loading"
        :pagination="pagination"
        remote
        :scroll-x="1080"
        @update:page="onPage"
      />
    </div>

    <CaseFlowModal
      v-model:show="caseModal"
      :mode="caseMode"
      :trace-id="activeLog?.trace_id || ''"
      :preset-question="activeLog?.query || ''"
      :preset-answer="activeLog?.answer || ''"
      :preset-app-id="activeLog?.app_id || ''"
      :preset-app-name="activeLog?.app_name || ''"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NCode,
  NDescriptions,
  NDescriptionsItem,
  NTag,
  type DataTableColumns
} from 'naive-ui'
import { RefreshOutline, SearchOutline } from '@vicons/ionicons5'
import { getLogStats, listKbs, listLogs } from '@/api'
import type { LogItem, LogStats } from '@/api/types'
import MetricStrip from './MetricStrip.vue'
import CaseFlowModal from './CaseFlowModal.vue'

const router = useRouter()
const loading = ref(false)
const rows = ref<LogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const kbOptions = ref<{ label: string; value: string }[]>([])
const stats = ref<LogStats>({ today_count: 0, today_tokens: 0, avg_duration_ms: 0, success_rate: 100, trend: [] })
const filters = reactive({ role: null as string | null, kb: null as string | null, status: null as string | null, q: '' })

const caseModal = ref(false)
const activeLog = ref<LogItem | null>(null)
const caseMode = computed<'trace' | 'log'>(() => (activeLog.value?.trace_id ? 'trace' : 'log'))

const roleOptions = [
  { label: '管理员', value: 'admin' },
  { label: '知识库管理员', value: 'manager' },
  { label: '使用者', value: 'user' },
  { label: '访客', value: '访客' }
]
const statusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'error' }
]

const metrics = computed(() => [
  { label: '今日对话', value: stats.value.today_count },
  { label: '今日 Token', value: stats.value.today_tokens.toLocaleString() },
  { label: '平均响应', value: `${(stats.value.avg_duration_ms / 1000).toFixed(2)}s` },
  { label: '成功率', value: `${stats.value.success_rate}%`, tone: stats.value.success_rate >= 95 ? ('good' as const) : ('warn' as const) }
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
    load()
  }
}))

const roleLabel: Record<string, string> = { admin: '管理员', manager: '知识库管理员', user: '使用者', 访客: '访客' }

const columns: DataTableColumns<LogItem> = [
  { type: 'expand', renderExpand: row => detailView(row) },
  { title: '时间', key: 'time', width: 156, render: row => formatTime(row.time) },
  {
    title: '来源',
    key: 'source',
    width: 170,
    render: row => row.app_name || row.kb_name || '—'
  },
  { title: '问题', key: 'query', minWidth: 240, ellipsis: { tooltip: true } },
  {
    title: '模型',
    key: 'llm_model',
    width: 130,
    render: row => h(NTag, { size: 'tiny', bordered: false, type: 'info' }, { default: () => row.llm_model || '—' })
  },
  {
    title: 'Token',
    key: 'tokens',
    width: 90,
    render: row => h('span', { class: 'num' }, (row.tokens?.total ?? 0).toLocaleString())
  },
  {
    title: '耗时',
    key: 'duration_ms',
    width: 82,
    render: row => h('span', { class: 'num' }, (row.duration_ms / 1000).toFixed(2) + 's')
  },
  {
    title: '状态',
    key: 'status',
    width: 76,
    render: row =>
      h(
        NTag,
        { size: 'tiny', type: row.status === 'success' ? 'success' : 'error', bordered: false },
        { default: () => (row.status === 'success' ? '成功' : '失败') }
      )
  },
  {
    title: '操作',
    key: 'actions',
    width: 130,
    render: row =>
      h('div', { class: 'row-actions' }, [
        row.trace_id
          ? h(NButton, { text: true, size: 'tiny', type: 'primary', onClick: () => openTrace(row.trace_id || '') }, { default: () => '链路' })
          : null,
        h(NButton, { text: true, size: 'tiny', onClick: () => openCase(row) }, { default: () => '回流' })
      ])
  }
]

function formatTime(iso: string) {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function detailView(row: LogItem) {
  return h(
    NDescriptions,
    { labelPlacement: 'left', column: 2, bordered: true, size: 'small', class: 'log-detail' },
    {
      default: () => [
        h(NDescriptionsItem, { label: '完整问题', span: 2 }, { default: () => row.query }),
        h(NDescriptionsItem, { label: '应用 / 知识库' }, { default: () => row.app_name || row.kb_name || '—' }),
        h(NDescriptionsItem, { label: '角色' }, { default: () => roleLabel[row.role] || row.role }),
        h(NDescriptionsItem, { label: 'LLM' }, { default: () => row.llm_model || '—' }),
        h(NDescriptionsItem, { label: 'Embedding / Rerank' }, {
          default: () => `${row.embedding_model || '—'} / ${row.rerank_model || '未配置'}`
        }),
        h(NDescriptionsItem, { label: 'Token 明细' }, {
          default: () =>
            row.tokens
              ? `E ${row.tokens.embedding ?? 0} + R ${row.tokens.rerank ?? 0} + LLM ${row.tokens.llm ?? 0} = ${row.tokens.total ?? 0}`
              : '—'
        }),
        h(NDescriptionsItem, { label: 'Trace' }, { default: () => row.trace_id || '未记录（历史日志）' }),
        h(NDescriptionsItem, { label: '回答内容', span: 2 }, {
          default: () =>
            row.answer
              ? h(NCode, { language: 'text', style: 'white-space: pre-wrap; word-break: break-word; max-height: 260px; overflow: auto' }, { default: () => row.answer })
              : h('span', { style: 'color:#d22d3d' }, '生成失败（无返回内容）')
        })
      ]
    }
  )
}

function openTrace(id: string) {
  router.push(`/app/observability/traces/${id}`)
}
function openCase(row: LogItem) {
  activeLog.value = row
  caseModal.value = true
}

async function load() {
  loading.value = true
  try {
    const [data, statsData] = await Promise.all([
      listLogs({
        role: filters.role ?? undefined,
        kb_id: filters.kb ?? undefined,
        status: filters.status ?? undefined,
        q: filters.q || undefined,
        page: page.value,
        page_size: pageSize.value
      }),
      getLogStats()
    ])
    rows.value = data.items
    total.value = data.total
    stats.value = statsData
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
  filters.role = null
  filters.kb = null
  filters.status = null
  filters.q = ''
  search()
}
function onPage(p: number) {
  page.value = p
  load()
}

onMounted(async () => {
  try {
    const kbs = await listKbs()
    kbOptions.value = kbs.map(kb => ({ label: kb.name, value: kb.id }))
  } catch {
    kbOptions.value = []
  }
  load()
})
</script>

<style scoped>
.logs-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.logs-top {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.logs-top > :first-child {
  flex: 1;
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
.table-panel {
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
:deep(.row-actions) {
  display: flex;
  gap: 10px;
}
</style>
