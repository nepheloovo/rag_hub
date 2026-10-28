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

    <n-card size="small" style="margin-top: 16px">
      <n-empty description="趋势图表规划中（路线图 Phase 3）" style="padding: 32px 0" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
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
        { size: 'small', bordered: false, type: row.status === 'published' ? 'success' : row.status === 'reviewing' ? 'warning' : 'default' },
        { default: () => ({ published: '已发布', reviewing: '评测中', draft: '草稿' } as any)[row.status] }
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
