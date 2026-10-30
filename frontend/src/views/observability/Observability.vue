<template>
  <div class="page obs-page">
    <div class="page-head">
      <div>
        <h2 class="page-title">可观测中心</h2>
        <p class="page-desc">知识库构建、Agent 调用、对话日志与计费消耗，统一回到同一条执行链路。</p>
      </div>
      <div class="head-actions">
        <n-select v-model:value="days" :options="dayOptions" size="small" style="width: 108px" @update:value="loadOverview" />
        <n-button quaternary size="small" :loading="loading" @click="loadAll">
          <template #icon><n-icon><RefreshOutline /></n-icon></template>
        </n-button>
        <n-button v-if="canDemo" size="small" ghost type="primary" @click="loadDemo">
          <template #icon><n-icon><SparklesOutline /></n-icon></template>
          载入演示数据
        </n-button>
      </div>
    </div>

    <n-tabs v-model:value="tab" type="line" display-directive="if" class="obs-tabs" @update:value="syncTab">
      <n-tab-pane name="overview" tab="总览">
        <div class="overview">
          <MetricStrip :items="metrics" />

          <div class="overview-grid">
            <TrendChart
              :points="trendPoints"
              bar-label="调用量"
              line-label="失败数"
              :format-value="v => String(Math.round(v))"
            />
            <div class="health-panel">
              <div class="panel-head">
                <span class="panel-title">运行健康</span>
                <span class="panel-sub">近 {{ days }} 天</span>
              </div>
              <div class="health-grid">
                <div class="health-item">
                  <span class="health-label">Agent 运行</span>
                  <span class="health-value">{{ overview?.agent_runs ?? 0 }}</span>
                </div>
                <div class="health-item">
                  <span class="health-label">工具 / Skill 调用</span>
                  <span class="health-value">{{ overview?.tool_calls ?? 0 }}</span>
                </div>
                <div class="health-item">
                  <span class="health-label">工具失败</span>
                  <span class="health-value" :class="{ bad: (overview?.tool_errors ?? 0) > 0 }">{{ overview?.tool_errors ?? 0 }}</span>
                </div>
                <div class="health-item">
                  <span class="health-label">平均耗时</span>
                  <span class="health-value">{{ ((overview?.avg_duration_ms ?? 0) / 1000).toFixed(2) }}s</span>
                </div>
              </div>
              <div class="health-section">
                <div class="section-label">类型分布</div>
                <div v-for="type in overview?.types || []" :key="type.type" class="type-row">
                  <span class="type-name">{{ typeLabel(type.type) }}</span>
                  <span class="type-bar"><i :style="{ width: typeWidth(type.count) }"></i></span>
                  <span class="type-count">{{ type.count }}</span>
                </div>
                <div v-if="!overview?.types?.length" class="empty-line">暂无数据</div>
              </div>
              <div v-if="overview?.skills?.length" class="health-section">
                <div class="section-label">Skill 调用</div>
                <div class="skill-row" v-for="skill in overview.skills.slice(0, 4)" :key="skill.name">
                  <span class="skill-name">{{ skill.name }}</span>
                  <span class="skill-count">{{ skill.count }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="recent-grid">
            <div class="panel recent-panel">
              <div class="panel-head">
                <span class="panel-title">最近链路</span>
                <n-button text size="tiny" type="primary" @click="tab = 'traces'">查看全部 →</n-button>
              </div>
              <div v-if="recent.length" class="recent-list">
                <button v-for="row in recent" :key="row.id" class="recent-row" type="button" @click="openTrace(row.id)">
                  <span class="status-dot" :class="row.status"></span>
                  <span class="recent-type">{{ typeLabel(row.trace_type) }}</span>
                  <span class="recent-query">{{ row.query || row.title }}</span>
                  <span class="recent-app">{{ row.app_name || row.kb_name || '—' }}</span>
                  <span class="recent-meta">{{ (row.tokens?.total || 0).toLocaleString() }} tok</span>
                  <span class="recent-meta">{{ formatDuration(row.duration_ms) }}</span>
                  <span class="recent-cost">¥{{ Number(row.cost_cny || 0).toFixed(4) }}</span>
                </button>
              </div>
              <div v-else class="empty-line">暂无链路，发起一次对话后即可看到完整 ReAct 过程</div>
            </div>

            <div class="panel error-panel">
              <div class="panel-head">
                <span class="panel-title">失败与异常</span>
                <span class="panel-sub">近 {{ days }} 天</span>
              </div>
              <div v-if="errorTraces.length" class="error-list">
                <button v-for="row in errorTraces" :key="row.id" class="error-row" type="button" @click="openTrace(row.id)">
                  <div class="error-main">
                    <div class="error-query">{{ row.query || row.title }}</div>
                    <div class="error-meta">{{ row.app_name || row.kb_name }} · {{ formatTime(row.started_at) }}</div>
                  </div>
                  <n-icon size="14" color="#c22d3d"><ChevronForwardOutline /></n-icon>
                </button>
              </div>
              <div v-else class="empty-line good-line">近 {{ days }} 天没有失败链路</div>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane name="traces" tab="调用链">
        <TraceTable :can-demo="canDemo" @changed="loadAll" />
      </n-tab-pane>

      <n-tab-pane name="logs" tab="对话日志">
        <ConversationLogs />
      </n-tab-pane>

      <n-tab-pane name="billing" tab="计费消耗">
        <BillingPanel />
      </n-tab-pane>

      <n-tab-pane name="builds" tab="知识库构建">
        <BuildPanel />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  ChevronForwardOutline,
  RefreshOutline,
  SparklesOutline
} from '@vicons/ionicons5'
import { getObsOverview, listTraces, loadDemoObservability } from '@/api'
import type { ObsOverview, TraceRun } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import MetricStrip from '@/components/obs/MetricStrip.vue'
import TrendChart from '@/components/obs/TrendChart.vue'
import TraceTable from '@/components/obs/TraceTable.vue'
import ConversationLogs from '@/components/obs/ConversationLogs.vue'
import BillingPanel from '@/components/obs/BillingPanel.vue'
import BuildPanel from '@/components/obs/BuildPanel.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
const canDemo = computed(() => ['platform_admin', 'app_developer'].includes(auth.role || ''))

const loading = ref(false)
const days = ref(7)
const tab = ref((route.query.tab as string) || 'overview')
const overview = ref<ObsOverview | null>(null)
const recent = ref<TraceRun[]>([])
const errorTraces = ref<TraceRun[]>([])

const dayOptions = [
  { label: '今日', value: 1 },
  { label: '近 7 天', value: 7 },
  { label: '近 14 天', value: 14 },
  { label: '近 30 天', value: 30 }
]

const metrics = computed(() => {
  const o = overview.value
  return [
    { label: '调用量', value: (o?.total ?? 0).toLocaleString(), sub: `近 ${days.value} 天` },
    {
      label: '成功率',
      value: `${o?.success_rate ?? 100}%`,
      sub: `${o?.error ?? 0} 次失败 · ${o?.degraded ?? 0} 次降级`,
      tone: (o?.success_rate ?? 100) >= 95 ? ('good' as const) : ('bad' as const)
    },
    { label: 'P95 耗时', value: `${((o?.p95_duration_ms ?? 0) / 1000).toFixed(2)}s`, sub: `均值 ${((o?.avg_duration_ms ?? 0) / 1000).toFixed(2)}s` },
    { label: 'Token 消耗', value: (o?.tokens ?? 0).toLocaleString() },
    { label: '计费消耗', value: `¥${Number(o?.cost_cny || 0).toFixed(3)}`, sub: '按模型单价折算' }
  ]
})

const trendPoints = computed(
  () =>
    overview.value?.trend.map(item => ({
      label: item.date,
      bar: item.total,
      line: item.error
    })) || []
)

const maxType = computed(() => Math.max(1, ...(overview.value?.types || []).map(t => t.count)))
function typeWidth(count: number) {
  return `${Math.max(6, (count / maxType.value) * 100)}%`
}
const TYPE_LABEL: Record<string, string> = {
  agent: 'Agent',
  chatflow: 'Chat Flow',
  chat: '简易 RAG',
  kb_build: '知识库构建'
}
function typeLabel(type: string) {
  return TYPE_LABEL[type] || type
}
function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 60000).toFixed(1)}min`
}
function formatTime(iso: string) {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function openTrace(id: string) {
  router.push(`/app/observability/traces/${id}`)
}
function syncTab(value: string) {
  router.replace({ query: { ...route.query, tab: value } })
}

async function loadOverview() {
  loading.value = true
  try {
    const [o, traces] = await Promise.all([
      getObsOverview(days.value),
      listTraces({ page: 1, page_size: 8 })
    ])
    overview.value = o
    recent.value = traces.items
    errorTraces.value = traces.items.filter(t => t.status === 'error' || t.status === 'degraded').slice(0, 5)
  } catch (e: any) {
    message.error(e.message || '观测数据加载失败')
  } finally {
    loading.value = false
  }
}
async function loadAll() {
  await loadOverview()
}
async function loadDemo() {
  try {
    const result = await loadDemoObservability()
    message.success(result.message || '演示数据已载入')
    await loadOverview()
  } catch (e: any) {
    message.error(e.message || '载入失败')
  }
}

onMounted(loadOverview)
</script>

<style scoped>
.obs-page {
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
  align-items: center;
  gap: 8px;
}
.obs-tabs :deep(.n-tabs-nav) {
  margin-bottom: 16px;
}
.obs-tabs :deep(.n-tabs-tab) {
  font-size: 13px;
}

@media (max-width: 820px) {
  .obs-tabs :deep(.n-tabs-nav-scroll-content) {
    max-width: 100%;
    overflow-x: auto !important;
    scrollbar-width: none;
  }
  .obs-tabs :deep(.n-tabs-nav-scroll-content::-webkit-scrollbar) {
    display: none;
  }
  .obs-tabs :deep(.n-tabs-tab) {
    font-size: 12px;
    padding: 0 10px;
  }
}
.overview {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.9fr) minmax(280px, 1fr);
  gap: 14px;
  align-items: stretch;
}
.health-panel {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 0;
}
.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
}
.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #2b3442;
}
.panel-sub {
  font-size: 10.5px;
  color: #9aa1ab;
}
.health-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
  margin-bottom: 14px;
}
.health-item {
  background: #fafbfc;
  border: 1px solid #f0f2f5;
  border-radius: 7px;
  padding: 8px 10px;
}
.health-label {
  display: block;
  font-size: 10.5px;
  color: #8a9099;
}
.health-value {
  display: block;
  margin-top: 3px;
  font-size: 18px;
  font-weight: 650;
  color: #1f2329;
  font-variant-numeric: tabular-nums;
}
.health-value.bad {
  color: #c22d3d;
}
.health-section {
  margin-top: 10px;
}
.section-label {
  font-size: 10.5px;
  color: #9aa1ab;
  letter-spacing: 0.04em;
  margin-bottom: 7px;
}
.type-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.type-name {
  flex: 0 0 76px;
  font-size: 11px;
  color: #5c6470;
}
.type-bar {
  flex: 1;
  height: 5px;
  background: #f0f2f5;
  border-radius: 3px;
  overflow: hidden;
}
.type-bar i {
  display: block;
  height: 100%;
  background: #a9c2ff;
  border-radius: 3px;
}
.type-count {
  flex: 0 0 28px;
  text-align: right;
  font-size: 10.5px;
  color: #8a9099;
  font-variant-numeric: tabular-nums;
}
.skill-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 11px;
  color: #5c6470;
}
.skill-count {
  font-variant-numeric: tabular-nums;
  color: #3b4351;
}
.recent-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.9fr) minmax(280px, 1fr);
  gap: 14px;
}
.panel {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 0;
}
.recent-list {
  display: flex;
  flex-direction: column;
}
.recent-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border: 0;
  border-bottom: 1px dashed #f0f1f3;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-size: 11.5px;
}
.recent-row:last-child {
  border-bottom: 0;
}
.recent-row:hover {
  background: #fafbfc;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: 0 0 7px;
  background: #1fa35b;
}
.status-dot.error {
  background: #e5484d;
}
.status-dot.degraded {
  background: #e39a19;
}
.recent-type {
  flex: 0 0 78px;
  color: #7a828e;
  font-size: 10.5px;
}
.recent-query {
  flex: 1;
  min-width: 0;
  color: #333b48;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-app {
  flex: 0 0 108px;
  color: #8a9099;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10.5px;
}
.recent-meta {
  flex: 0 0 64px;
  text-align: right;
  color: #98a0ac;
  font-variant-numeric: tabular-nums;
  font-size: 10.5px;
}
.recent-cost {
  flex: 0 0 62px;
  text-align: right;
  color: #3b4351;
  font-variant-numeric: tabular-nums;
  font-size: 11px;
}
.error-list {
  display: flex;
  flex-direction: column;
}
.error-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  border: 0;
  border-bottom: 1px dashed #f0f1f3;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.error-row:last-child {
  border-bottom: 0;
}
.error-row:hover {
  background: #fffafa;
}
.error-main {
  flex: 1;
  min-width: 0;
}
.error-query {
  font-size: 11.5px;
  color: #333b48;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.error-meta {
  font-size: 10px;
  color: #a3a9b3;
  margin-top: 2px;
}
.empty-line {
  padding: 18px 0;
  text-align: center;
  font-size: 11.5px;
  color: #a3a9b3;
}
.good-line {
  color: #3d9a67;
}
@media (max-width: 1080px) {
  .overview-grid,
  .recent-grid {
    grid-template-columns: 1fr;
  }
  .recent-app,
  .recent-meta {
    display: none;
  }
}
@media (max-width: 720px) {
  .page-head {
    flex-direction: column;
  }
  .head-actions {
    flex-wrap: wrap;
  }
}
</style>
