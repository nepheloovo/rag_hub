<template>
  <div class="billing">
    <div class="billing-top">
      <n-select v-model:value="days" :options="dayOptions" size="small" style="width: 110px" @update:value="load" />
      <div class="spacer"></div>
      <n-button size="small" quaternary @click="priceDrawer = true">
        <template #icon><n-icon><PricetagOutline /></n-icon></template>
        单价配置
      </n-button>
      <n-button size="small" quaternary :loading="loading" @click="load">
        <template #icon><n-icon><RefreshOutline /></n-icon></template>
      </n-button>
    </div>

    <MetricStrip :items="metrics" />

    <TrendChart
      :points="chartPoints"
      bar-label="每日成本（元）"
      :format-value="v => '¥' + Number(v).toFixed(3)"
    />

    <div class="billing-grid">
      <div class="panel">
        <div class="panel-head">
          <span class="panel-title">按模型</span>
          <span class="panel-sub">元 / 百万 Token 折算</span>
        </div>
        <div v-if="data?.by_model?.length" class="breakdown">
          <div v-for="row in data.by_model" :key="row.model" class="breakdown-row">
            <div class="row-main">
              <div class="row-name mono">{{ row.model }}</div>
              <div class="row-meta">{{ row.spans }} 次调用 · 输入 {{ formatNumber(row.input) }} / 输出 {{ formatNumber(row.output) }}</div>
            </div>
            <div class="row-value">¥{{ Number(row.cost_cny).toFixed(4) }}</div>
          </div>
        </div>
        <div v-else class="empty-line">暂无模型消耗</div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <span class="panel-title">按应用</span>
          <span class="panel-sub">含知识库构建</span>
        </div>
        <div v-if="data?.by_app?.length" class="breakdown">
          <div v-for="row in data.by_app" :key="row.app_name" class="breakdown-row">
            <div class="row-main">
              <div class="row-name">{{ row.app_name }}</div>
              <div class="row-meta">{{ row.calls }} 次调用 · {{ formatNumber(row.tokens) }} tokens</div>
            </div>
            <div class="row-value">¥{{ Number(row.cost_cny).toFixed(4) }}</div>
          </div>
        </div>
        <div v-else class="empty-line">暂无应用消耗</div>
      </div>

      <div class="panel wide">
        <div class="panel-head">
          <span class="panel-title">按用途</span>
          <span class="panel-sub">对话 / Agent / 流程 / 构建</span>
        </div>
        <div v-if="data?.by_purpose?.length" class="purpose-grid">
          <div v-for="row in data.by_purpose" :key="row.type" class="purpose-item">
            <div class="purpose-name">{{ purposeLabel(row.type) }}</div>
            <div class="purpose-value">¥{{ Number(row.cost_cny).toFixed(4) }}</div>
            <div class="purpose-meta">{{ row.calls }} 次 · {{ formatNumber(row.tokens) }} tok</div>
          </div>
        </div>
        <div v-else class="empty-line">暂无消耗</div>
      </div>
    </div>

    <n-drawer v-model:show="priceDrawer" :width="560" placement="right">
      <n-drawer-content title="模型计费单价" closable>
        <p class="drawer-hint">
          单位：元 / 百万 Token。未配置的模型使用兜底单价；修改后仅影响之后的调用成本核算。
        </p>
        <div class="price-list">
          <div v-for="price in prices" :key="price.model" class="price-row">
            <div class="price-name mono">{{ price.model === '__default__' ? '兜底单价（未匹配模型）' : price.model }}</div>
            <div class="price-inputs">
              <n-input-number v-model:value="price.input_price" size="small" :min="0" :step="0.1" :precision="2">
                <template #prefix>入</template>
              </n-input-number>
              <n-input-number v-model:value="price.output_price" size="small" :min="0" :step="0.1" :precision="2">
                <template #prefix>出</template>
              </n-input-number>
              <n-button size="small" text type="primary" :disabled="!canEdit" @click="savePrice(price)">保存</n-button>
            </div>
          </div>
        </div>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { PricetagOutline, RefreshOutline } from '@vicons/ionicons5'
import { getBilling, listPrices, updatePrice } from '@/api'
import type { BillingData, ModelPrice } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import MetricStrip from './MetricStrip.vue'
import TrendChart from './TrendChart.vue'

const message = useMessage()
const auth = useAuthStore()
const canEdit = computed(() => auth.role === 'platform_admin')
const loading = ref(false)
const data = ref<BillingData | null>(null)
const days = ref(14)
const priceDrawer = ref(false)
const prices = ref<ModelPrice[]>([])

const dayOptions = [
  { label: '近 7 天', value: 7 },
  { label: '近 14 天', value: 14 },
  { label: '近 30 天', value: 30 }
]

const metrics = computed(() => {
  const d = data.value
  const calls = d?.calls || 0
  return [
    { label: '总成本', value: `¥${Number(d?.total_cost_cny || 0).toFixed(3)}`, sub: `近 ${days.value} 天` },
    { label: '总 Token', value: formatNumber(d?.total_tokens || 0) },
    { label: '调用次数', value: calls.toLocaleString() },
    { label: '单次均价', value: `¥${(calls ? Number(d!.total_cost_cny) / calls : 0).toFixed(4)}` }
  ]
})

const chartPoints = computed(
  () => data.value?.by_day.map(row => ({ label: row.date, bar: Number(row.cost_cny) })) || []
)

const PURPOSE: Record<string, string> = {
  chat: '简易 RAG 对话',
  agent: 'Agent 调用',
  chatflow: 'Chat Flow',
  kb_build: '知识库构建'
}
function purposeLabel(type: string) {
  return PURPOSE[type] || type
}
function formatNumber(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  return String(v ?? 0)
}

async function load() {
  loading.value = true
  try {
    data.value = await getBilling(days.value)
  } catch (e: any) {
    message.error(e.message || '计费数据加载失败')
  } finally {
    loading.value = false
  }
}
async function loadPrices() {
  try {
    prices.value = await listPrices()
  } catch {
    prices.value = []
  }
}
async function savePrice(price: ModelPrice) {
  try {
    await updatePrice(price.model, {
      input_price: Number(price.input_price || 0),
      output_price: Number(price.output_price || 0)
    })
    message.success('单价已更新')
  } catch (e: any) {
    message.error(e.message || '保存失败')
  }
}

onMounted(() => {
  load()
  loadPrices()
})
</script>

<style scoped>
.billing {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.billing-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.spacer {
  flex: 1;
}
.billing-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.panel {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 0;
}
.panel.wide {
  grid-column: 1 / -1;
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
.breakdown-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px dashed #f0f1f3;
}
.breakdown-row:last-child {
  border-bottom: 0;
}
.row-main {
  min-width: 0;
  flex: 1;
}
.row-name {
  font-size: 12px;
  color: #333b48;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.row-name.mono {
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  font-size: 11.5px;
}
.row-meta {
  font-size: 10.5px;
  color: #9aa1ab;
  margin-top: 2px;
}
.row-value {
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  color: #1f2329;
  font-weight: 550;
}
.purpose-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.purpose-item {
  border: 1px solid #f0f2f5;
  border-radius: 8px;
  padding: 11px 12px;
  background: #fcfcfd;
}
.purpose-name {
  font-size: 11.5px;
  color: #5c6470;
}
.purpose-value {
  font-size: 18px;
  font-weight: 650;
  color: #1f2329;
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}
.purpose-meta {
  font-size: 10.5px;
  color: #9aa1ab;
  margin-top: 2px;
}
.empty-line {
  padding: 20px 0;
  font-size: 12px;
  color: #9aa1ab;
  text-align: center;
}
.drawer-hint {
  font-size: 11.5px;
  line-height: 1.7;
  color: #7a828e;
  margin: 0 0 12px;
}
.price-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.price-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px dashed #f0f1f3;
}
.price-name {
  flex: 1;
  min-width: 0;
  font-size: 11.5px;
  color: #3b4351;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.price-inputs {
  display: flex;
  align-items: center;
  gap: 6px;
}
.price-inputs :deep(.n-input-number) {
  width: 120px;
}
@media (max-width: 900px) {
  .billing-grid {
    grid-template-columns: 1fr;
  }
  .purpose-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
