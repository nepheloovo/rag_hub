<template>
  <div class="builds">
    <div class="filter-bar">
      <n-select v-model:value="filters.status" :options="statusOptions" placeholder="状态" clearable style="width: 110px" @update:value="search" />
      <n-select v-model:value="filters.kb" :options="kbOptions" placeholder="知识库" clearable filterable style="width: 190px" @update:value="search" />
      <div class="spacer"></div>
      <span class="count">共 {{ total }} 次构建</span>
      <n-button quaternary size="small" :loading="loading" @click="load">
        <template #icon><n-icon><RefreshOutline /></n-icon></template>
      </n-button>
    </div>

    <div class="build-list">
      <div v-if="!loading && !rows.length" class="empty">
        <div class="empty-title">还没有构建记录</div>
        <div class="empty-desc">上传并解析文档后，解析 → 分块 → Embedding → 入库的每个阶段耗时与 Token 都会记录在这里。</div>
      </div>
      <button
        v-for="row in rows"
        :key="row.id"
        class="build-row"
        type="button"
        @click="open(row)"
      >
        <div class="build-main">
          <div class="build-title-line">
            <span class="build-title">{{ row.title || row.query }}</span>
            <n-tag size="tiny" :bordered="false" :type="row.status === 'success' ? 'success' : 'error'">
              {{ row.status === 'success' ? '构建成功' : '构建失败' }}
            </n-tag>
            <span class="build-kb">{{ row.kb_name }}</span>
            <span class="build-time">{{ formatTime(row.started_at) }}</span>
          </div>
          <div v-if="row.error" class="build-error">{{ row.error }}</div>
          <div class="stages">
            <template v-for="(stage, idx) in stageList(row)" :key="stage.span_type">
              <div class="stage" :class="stage.status">
                <span class="stage-name">{{ stageShort(stage) }}</span>
                <span class="stage-time">{{ formatDuration(stage.duration_ms) }}</span>
                <span v-if="stage.tokens?.total" class="stage-token">{{ stage.tokens.total }} tok</span>
              </div>
              <span v-if="idx < stageList(row).length - 1" class="stage-link"></span>
            </template>
          </div>
        </div>
        <div class="build-side">
          <div class="side-metric">
            <span class="side-value">{{ row.span_count }}</span>
            <span class="side-label">阶段</span>
          </div>
          <div class="side-metric">
            <span class="side-value">{{ (row.tokens?.total || 0).toLocaleString() }}</span>
            <span class="side-label">Token</span>
          </div>
          <div class="side-metric">
            <span class="side-value">¥{{ Number(row.cost_cny || 0).toFixed(3) }}</span>
            <span class="side-label">成本</span>
          </div>
          <div class="side-metric">
            <span class="side-value">{{ formatDuration(row.duration_ms) }}</span>
            <span class="side-label">总耗时</span>
          </div>
        </div>
      </button>
    </div>

    <n-drawer v-model:show="drawer" :width="760" placement="right">
      <n-drawer-content v-if="active" closable>
        <template #header>
          <div class="drawer-title">
            {{ active.title || active.query }}
            <n-tag size="small" :bordered="false" :type="active.status === 'success' ? 'success' : 'error'">
              {{ active.status === 'success' ? '构建成功' : '构建失败' }}
            </n-tag>
          </div>
        </template>
        <div class="drawer-summary">
          <span>知识库：{{ active.kb_name || '—' }}</span>
          <span>阶段：{{ active.span_count }}</span>
          <span>Token：{{ (active.tokens?.total || 0).toLocaleString() }}</span>
          <span>成本：¥{{ Number(active.cost_cny || 0).toFixed(4) }}</span>
          <span>耗时：{{ formatDuration(active.duration_ms) }}</span>
        </div>
        <TraceTimeline :spans="active.stages || []" />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { NTag } from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import { listBuilds, listKbs } from '@/api'
import type { TraceRun, TraceSpan } from '@/api/types'
import TraceTimeline from './TraceTimeline.vue'

const loading = ref(false)
const rows = ref<TraceRun[]>([])
const total = ref(0)
const kbOptions = ref<{ label: string; value: string }[]>([])
const filters = reactive({ status: null as string | null, kb: null as string | null })
const drawer = ref(false)
const active = ref<TraceRun | null>(null)

const statusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'error' }
]

const STAGE_SHORT: Record<string, string> = {
  'build.parse': '解析',
  'build.chunk': '分块',
  'build.embed': '向量化',
  'build.index': '入库',
  exception: '异常'
}

function stageShort(stage: TraceSpan) {
  return STAGE_SHORT[stage.span_type] || stage.name
}
function stageList(row: TraceRun): TraceSpan[] {
  return (row.stages || []).filter(s => s.span_type.startsWith('build.') || s.span_type === 'exception')
}
function formatTime(iso: string) {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}
function open(row: TraceRun) {
  active.value = row
  drawer.value = true
}
async function load() {
  loading.value = true
  try {
    const data = await listBuilds({
      kb_id: filters.kb ?? undefined,
      status: filters.status ?? undefined,
      page: 1,
      page_size: 50
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
  load()
}

onMounted(async () => {
  try {
    const kbs = await listKbs()
    kbOptions.value = kbs.map(k => ({ label: k.name, value: k.id }))
  } catch {
    kbOptions.value = []
  }
  load()
})
</script>

<style scoped>
.builds {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 9px;
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 11px 12px;
}
.spacer {
  flex: 1;
}
.count {
  font-size: 11.5px;
  color: #8a9099;
}
.build-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.build-row {
  display: flex;
  align-items: stretch;
  gap: 18px;
  width: 100%;
  text-align: left;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  background: #fff;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}
.build-row:hover {
  border-color: #c7d5f3;
  box-shadow: 0 2px 12px rgba(35, 53, 92, 0.05);
}
.build-main {
  flex: 1;
  min-width: 0;
}
.build-title-line {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}
.build-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #1f2329;
}
.build-kb {
  font-size: 11px;
  color: #6b7280;
}
.build-time {
  margin-left: auto;
  font-size: 10.5px;
  color: #a3a9b3;
  font-variant-numeric: tabular-nums;
}
.build-error {
  margin-top: 5px;
  font-size: 11.5px;
  color: #c22d3d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.stages {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 11px;
  flex-wrap: wrap;
}
.stage {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #edf0f4;
  background: #fafbfc;
  border-radius: 5px;
  padding: 3px 7px;
}
.stage.error {
  border-color: #f3c4c6;
  background: #fff7f7;
}
.stage-name {
  font-size: 10.5px;
  color: #5c6470;
}
.stage.error .stage-name {
  color: #c22d3d;
}
.stage-time {
  font-size: 10px;
  color: #98a0ac;
  font-variant-numeric: tabular-nums;
}
.stage-token {
  font-size: 10px;
  color: #8b7bb8;
}
.stage-link {
  width: 10px;
  height: 1px;
  background: #dde2ea;
}
.build-side {
  display: flex;
  align-items: center;
  gap: 18px;
  flex: 0 0 auto;
  padding-left: 16px;
  border-left: 1px solid #f0f1f3;
}
.side-metric {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  min-width: 52px;
}
.side-value {
  font-size: 12.5px;
  color: #2b3442;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.side-label {
  font-size: 10px;
  color: #a3a9b3;
}
.empty {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 40px 20px;
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
  margin: 6px auto 0;
  line-height: 1.7;
}
.drawer-title {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2329;
}
.drawer-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  padding: 9px 12px;
  background: #fafbfc;
  border: 1px solid #eef0f3;
  border-radius: 8px;
  font-size: 11.5px;
  color: #5c6470;
  margin-bottom: 14px;
}
@media (max-width: 900px) {
  .build-side {
    display: none;
  }
}
</style>
