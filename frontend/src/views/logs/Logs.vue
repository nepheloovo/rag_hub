<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">日志监测</h2>
        <p class="page-desc">对话查询内容、Token 消耗与使用时长统计</p>
      </div>
    </div>

    <div class="stat-grid">
      <n-card size="small">
        <n-statistic label="今日对话数" :value="stats.today_count" />
      </n-card>
      <n-card size="small">
        <n-statistic label="今日消耗 Tokens" :value="stats.today_tokens" />
      </n-card>
      <n-card size="small">
        <n-statistic label="平均响应时长" :value="avgSeconds + ' s'" />
      </n-card>
      <n-card size="small">
        <n-statistic label="成功率" :value="stats.success_rate + '%'" />
      </n-card>
    </div>

    <n-card size="small" style="margin-top: 16px">
      <div class="filter-row">
        <n-select
          v-model:value="filterRole"
          :options="roleOptions"
          placeholder="角色"
          clearable
          style="width: 140px"
        />
        <n-select
          v-model:value="filterKb"
          :options="kbFilterOptions"
          placeholder="知识库"
          clearable
          style="width: 180px"
        />
        <n-select
          v-model:value="filterStatus"
          :options="statusOptions"
          placeholder="状态"
          clearable
          style="width: 120px"
        />
        <n-input
          v-model:value="filterQuery"
          placeholder="搜索查询内容"
          clearable
          style="width: 220px"
          @keydown.enter="load"
        />
        <n-button type="primary" ghost @click="load">
          <template #icon><n-icon><SearchOutline /></n-icon></template>
          查询
        </n-button>
        <n-button quaternary @click="resetFilters">重置</n-button>
      </div>
    </n-card>

    <n-card size="small" style="margin-top: 16px" :bordered="false">
      <n-data-table
        :columns="columns"
        :data="logs"
        :row-key="(row: LogItem) => row.id"
        :loading="loading"
        :pagination="pagination"
        remote
        @update:page="onPageChange"
      />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted } from 'vue'
import { NTag, NDescriptions, NDescriptionsItem, NCode, type DataTableColumns } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'
import { getLogStats, listKbs, listLogs } from '@/api'
import type { LogItem, LogStats } from '@/api/types'

const loading = ref(false)
const logs = ref<LogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const filterRole = ref<string | null>(null)
const filterKb = ref<string | null>(null)
const filterStatus = ref<string | null>(null)
const filterQuery = ref('')

const stats = ref<LogStats>({
  today_count: 0,
  today_tokens: 0,
  avg_duration_ms: 0,
  success_rate: 100,
  trend: []
})

const avgSeconds = computed(() => (stats.value.avg_duration_ms / 1000).toFixed(1))

const roleOptions = [
  { label: '管理员', value: 'admin' },
  { label: '知识库管理人员', value: 'manager' },
  { label: '使用者', value: 'user' }
]

const kbFilterOptions = ref<{ label: string; value: string }[]>([])
const statusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'error' }
]

const pagination = computed(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: total.value,
  showSizePicker: true,
  pageSizes: [10, 20, 50],
  onChange: (p: number) => (page.value = p),
  onUpdatePageSize: (s: number) => {
    pageSize.value = s
    page.value = 1
    load()
  }
}))

const roleLabel: Record<string, string> = { admin: '管理员', manager: '知识库管理人员', user: '使用者' }

const columns: DataTableColumns<LogItem> = [
  { type: 'expand', renderExpand: (row: LogItem) => detailView(row) },
  { title: '时间', key: 'time', width: 165, render: (row: LogItem) => formatTime(row.time) },
  { title: '角色', key: 'role', width: 120, render: (row: LogItem) => roleLabel[row.role] || row.role },
  { title: '知识库', key: 'kb_name', width: 140 },
  { title: '查询内容', key: 'query', width: 220, ellipsis: { tooltip: true } },
  {
    title: '模型',
    key: 'llm_model',
    width: 150,
    render: (row: LogItem) =>
      h(NTag, { size: 'small', bordered: false, type: 'info' }, { default: () => row.llm_model })
  },
  {
    title: 'Tokens',
    key: 'tokens',
    width: 110,
    render: (row: LogItem) =>
      h('span', { style: 'font-variant-numeric: tabular-nums' }, (row.tokens?.total ?? 0).toLocaleString())
  },
  {
    title: '时长',
    key: 'duration_ms',
    width: 100,
    render: (row: LogItem) =>
      h('span', { style: 'font-variant-numeric: tabular-nums' }, (row.duration_ms / 1000).toFixed(1) + 's')
  },
  {
    title: '状态',
    key: 'status',
    width: 90,
    render: (row: LogItem) =>
      row.status === 'success'
        ? h(NTag, { size: 'small', type: 'success', bordered: false }, { default: () => '成功' })
        : h(NTag, { size: 'small', type: 'error', bordered: false }, { default: () => '失败' })
  }
]

function formatTime(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function detailView(row: LogItem) {
  return h(
    NDescriptions,
    { labelPlacement: 'left', column: 2, bordered: true, size: 'small' },
    {
      default: () => [
        h(NDescriptionsItem, { label: '查询内容' }, { default: () => row.query }),
        h(NDescriptionsItem, { label: 'LLM 模型' }, { default: () => row.llm_model }),
        h(NDescriptionsItem, { label: 'Embedding 模型' }, { default: () => row.embedding_model }),
        h(NDescriptionsItem, { label: 'Rerank 模型' }, { default: () => row.rerank_model || '未配置（已降级）' }),
        h(NDescriptionsItem, { label: 'Token 明细' }, {
          default: () =>
            row.tokens
              ? `Embedding ${row.tokens.embedding ?? 0} + Rerank ${row.tokens.rerank ?? 0} + LLM ${row.tokens.llm ?? 0} = ${row.tokens.total ?? 0}`
              : '-'
        }),
        h(NDescriptionsItem, { label: '使用时长' }, { default: () => (row.duration_ms / 1000).toFixed(2) + ' 秒' }),
        h(NDescriptionsItem, { label: '回答内容', span: 2 }, {
          default: () =>
            row.answer
              ? h(NCode, { language: 'text', style: 'white-space: pre-wrap; word-break: break-word' }, { default: () => row.answer })
              : h('span', { style: 'color:#e5484d' }, '生成失败（无返回内容）')
        })
      ]
    }
  )
}

async function load() {
  loading.value = true
  try {
    const data = await listLogs({
      role: filterRole.value ?? undefined,
      kb_id: filterKb.value ?? undefined,
      status: filterStatus.value ?? undefined,
      q: filterQuery.value || undefined,
      page: page.value,
      page_size: pageSize.value
    })
    logs.value = data.items
    total.value = data.total
  } catch (e: any) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await getLogStats()
  } catch {
    /* 静默 */
  }
}

async function loadKbOptions() {
  try {
    const kbs = await listKbs()
    kbFilterOptions.value = kbs.map(k => ({ label: k.name, value: k.id }))
  } catch {
    /* 静默 */
  }
}

function onPageChange(p: number) {
  page.value = p
  load()
}

function resetFilters() {
  filterRole.value = null
  filterKb.value = null
  filterStatus.value = null
  filterQuery.value = ''
  page.value = 1
  load()
}

onMounted(() => {
  load()
  loadStats()
  loadKbOptions()
})
</script>

<style scoped>
.page-head {
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #1f2329;
}

.page-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: #8f959e;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.filter-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
