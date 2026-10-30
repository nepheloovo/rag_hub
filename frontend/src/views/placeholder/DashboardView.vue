<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">看板</h2>
        <p class="page-desc">业务运营数据总览（数据来自系统真实统计）</p>
      </div>
    </div>

    <div class="stat-grid">
      <n-card size="small">
        <n-statistic label="本月应用调用" :value="stats.month_app_calls" />
      </n-card>
      <n-card size="small">
        <n-statistic label="本月新增知识" :value="stats.month_new_docs + ' 条'" />
      </n-card>
      <n-card size="small">
        <n-statistic label="本月新建应用" :value="stats.month_new_apps" />
      </n-card>
      <n-card size="small">
        <n-statistic label="已发布应用" :value="`${stats.published_count} / ${stats.app_count}`" />
      </n-card>
    </div>

    <n-card size="small" title="应用调用排行（近 7 天）" style="margin-top: 16px">
      <n-data-table
        :columns="columns"
        :data="rows"
        :bordered="false"
        :pagination="false"
        :loading="loading"
      />
    </n-card>

    <n-card size="small" title="近 14 日趋势" style="margin-top: 16px">
      <n-spin :show="trendLoading">
        <div class="chart-wrap">
          <svg :viewBox="`0 0 ${chartW} ${chartH}`" class="trend-chart" preserveAspectRatio="none">
            <!-- 网格线 -->
            <line v-for="i in 4" :key="i" :x1="40" :x2="chartW" :y1="chartH - i * (chartH - 40) / 4" :y2="chartH - i * (chartH - 40) / 4" stroke="#eef0f4" stroke-width="1" />
            <!-- 调用量折线 -->
            <polyline :points="callsLine" fill="none" stroke="#3370ff" stroke-width="2.5" />
            <circle v-for="(p, i) in callPoints" :key="i" :cx="p.x" :cy="p.y" r="3" fill="#3370ff" />
            <!-- 新增知识柱状 -->
            <rect
              v-for="(p, i) in docPoints"
              :key="'d' + i"
              :x="p.x - 6"
              :y="p.y"
              :width="10"
              :height="chartH - 24 - p.y"
              fill="#b7c8ff"
              rx="2"
            />
          </svg>
          <div class="chart-legend">
            <span class="legend-item"><i style="background:#3370ff"></i>应用调用（成功）</span>
            <span class="legend-item"><i style="background:#b7c8ff"></i>新增知识</span>
          </div>
          <div class="chart-dates">
            <span v-for="(d, i) in trendDates" :key="i" :style="{ left: 40 + (chartW - 50) * i / Math.max(trendDates.length - 1, 1) + 'px' }">{{ d.slice(5) }}</span>
          </div>
        </div>
      </n-spin>
    </n-card>

    <n-card size="small" style="margin-top: 16px">
      <n-empty description="更多图表规划中" style="padding: 24px 0" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted } from 'vue'
import { NTag } from 'naive-ui'
import { getStatsOverview, listApps } from '@/api'
import type { Application, StatsOverview } from '@/api/types'

const stats = ref<StatsOverview>({
  month_app_calls: 0, month_new_docs: 0, month_new_apps: 0,
  kb_count: 0, app_count: 0, published_count: 0
})
const rows = ref<Application[]>([])
const loading = ref(false)

const columns = [
  { title: '应用', key: 'name' },
  {
    title: '状态',
    key: 'status',
    width: 110,
    render: (row: Application) =>
      h(
        NTag,
        { size: 'small', bordered: false, type: row.status === 'published' ? 'success' : row.status === 'offline' ? 'warning' : 'default' },
        { default: () => ({ published: '已发布', offline: '已下线', draft: '草稿' } as const)[row.status] }
      )
  },
  {
    title: '近 7 天调用',
    key: 'call_count_7d',
    width: 140,
    render: (row: Application) => h('span', { style: 'font-variant-numeric: tabular-nums' }, row.call_count_7d.toLocaleString())
  },
  { title: '分类', key: 'category', width: 140 }
]

async function load() {
  loading.value = true
  try {
    const [s, apps] = await Promise.all([getStatsOverview(), listApps()])
    stats.value = s
    rows.value = [...apps].sort((a, b) => b.call_count_7d - a.call_count_7d)
  } finally {
    loading.value = false
  }
  loadTrend()
}

// ---------- 趋势图 ----------
const trendLoading = ref(false)
const trendDates = ref<string[]>([])
const calls = ref<number[]>([])
const docs = ref<number[]>([])
const chartW = 900
const chartH = 240

const callPoints = computed(() => {
  const max = Math.max(...calls.value, 1)
  return calls.value.map((v, i) => ({
    x: 40 + (chartW - 50) * i / Math.max(calls.value.length - 1, 1),
    y: chartH - 24 - (chartH - 56) * v / max
  }))
})
const docPoints = computed(() => {
  const max = Math.max(...docs.value, 1)
  return docs.value.map((v, i) => ({
    x: 40 + (chartW - 50) * i / Math.max(docs.value.length - 1, 1),
    y: chartH - 24 - (chartH - 56) * v / max
  }))
})
const callsLine = computed(() => callPoints.value.map(p => `${p.x},${p.y}`).join(' '))

async function loadTrend() {
  trendLoading.value = true
  try {
    const { getStatsTrend } = await import('@/api')
    const t = await getStatsTrend(14)
    trendDates.value = t.dates
    calls.value = t.calls
    docs.value = t.docs
  } finally {
    trendLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
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

.page-head {
  margin-bottom: 20px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
</style>

<style scoped>
.chart-wrap {
  position: relative;
  height: 300px;
  overflow-x: auto;
}

.trend-chart {
  width: 100%;
  min-width: 640px;
  height: 240px;
}

.chart-legend {
  display: flex;
  gap: 20px;
  padding: 6px 40px;
  font-size: 12px;
  color: #6b7280;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-item i {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
}

.chart-dates {
  position: relative;
  height: 22px;
  margin: 0 20px;
  font-size: 10px;
  color: #a8adb5;
}

.chart-dates span {
  position: absolute;
  transform: translateX(-20px);
  white-space: nowrap;
}
</style>
