<template>
  <div class="metric-strip">
    <div v-for="item in items" :key="item.label" class="metric">
      <div class="metric-label">{{ item.label }}</div>
      <div class="metric-value" :class="item.tone">{{ item.value }}</div>
      <div v-if="item.sub" class="metric-sub">{{ item.sub }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface MetricItem {
  label: string
  value: string | number
  sub?: string
  tone?: 'good' | 'bad' | 'warn' | 'muted'
}

defineProps<{ items: MetricItem[] }>()
</script>

<style scoped>
.metric-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.metric {
  padding: 14px 18px;
  border-right: 1px solid #f0f1f3;
  min-width: 0;
}
.metric:last-child {
  border-right: none;
}
.metric-label {
  font-size: 12px;
  color: #6b7280;
  letter-spacing: 0.02em;
}
.metric-value {
  margin-top: 5px;
  font-size: 22px;
  line-height: 1.2;
  font-weight: 650;
  color: #1f2329;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.metric-value.good {
  color: #12904f;
}
.metric-value.bad {
  color: #d22d3d;
}
.metric-value.warn {
  color: #b25e00;
}
.metric-value.muted {
  color: #4e5969;
}
.metric-sub {
  margin-top: 3px;
  font-size: 11px;
  color: #8a9099;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
@media (max-width: 720px) {
  .metric {
    border-right: none;
    border-bottom: 1px solid #f0f1f3;
  }
}
</style>
