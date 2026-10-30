<template>
  <div class="trend">
    <div class="trend-head">
      <div class="legend">
        <span class="legend-item"><i class="dot bar"></i>{{ barLabel }}</span>
        <span v-if="lineLabel" class="legend-item"><i class="dot line"></i>{{ lineLabel }}</span>
      </div>
      <span class="range">{{ points[0]?.label }} — {{ points[points.length - 1]?.label }}</span>
    </div>
    <div class="plot">
      <svg :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" role="img" :aria-label="barLabel">
        <g class="grid">
          <line v-for="i in 4" :key="i" :x1="PAD_L" :x2="W - PAD_R" :y1="yFor(axisMax * (i / 4))" :y2="yFor(axisMax * (i / 4))" />
          <text v-for="i in 4" :key="'t' + i" :x="PAD_L - 8" :y="yFor(axisMax * (i / 4)) + 3" text-anchor="end">
            {{ short(axisMax * (i / 4)) }}
          </text>
        </g>
        <g v-for="(p, i) in points" :key="p.label">
          <rect
            :x="barX(i)"
            :y="yFor(p.bar)"
            :width="barW"
            :height="Math.max(2, baseY - yFor(p.bar))"
            rx="2.5"
            class="bar"
          >
            <title>{{ p.label }} · {{ barLabel }} {{ format(p.bar) }}</title>
          </rect>
        </g>
        <path v-if="lineLabel" :d="linePath" class="line" />
        <g v-if="lineLabel">
          <circle v-for="(p, i) in points" :key="'c' + p.label" :cx="centerX(i)" :cy="yFor(p.line ?? 0)" r="2.8" class="point">
            <title>{{ p.label }} · {{ lineLabel }} {{ format(p.line ?? 0) }}</title>
          </circle>
        </g>
        <g class="x-labels">
          <text
            v-for="(p, i) in points"
            :key="'x' + p.label"
            :x="centerX(i)"
            :y="H - 6"
            text-anchor="middle"
            :class="{ dim: points.length > 14 && i % 2 !== 0 }"
          >
            {{ shortDate(p.label) }}
          </text>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Point {
  label: string
  bar: number
  line?: number
}

const props = withDefaults(
  defineProps<{
    points: Point[]
    barLabel: string
    lineLabel?: string
    formatValue?: (v: number) => string
  }>(),
  { lineLabel: '' }
)

const W = 820
const H = 220
const PAD_L = 44
const PAD_R = 12
const PAD_T = 12
const PAD_B = 26
const baseY = H - PAD_B

const max = computed(() => {
  const values = props.points.flatMap(p => [p.bar || 0, p.line || 0])
  return Math.max(0, ...values) || 1
})
const axisMax = computed(() => {
  const value = max.value * 1.05
  if (value <= 0) return 1
  if (value < 1) return Math.max(0.04, Math.ceil(value / 0.04) * 0.04)
  return Math.ceil(value / 4) * 4
})

const usable = computed(() => W - PAD_L - PAD_R)
const barW = computed(() => Math.max(3, Math.min(18, (usable.value / Math.max(1, props.points.length)) * 0.46)))

function centerX(i: number) {
  const step = usable.value / Math.max(1, props.points.length)
  return PAD_L + step * i + step / 2
}
function barX(i: number) {
  return centerX(i) - barW.value / 2
}
function yFor(v: number) {
  return PAD_T + (1 - Math.min(1, (v || 0) / axisMax.value)) * (baseY - PAD_T)
}
const linePath = computed(() =>
  props.points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${centerX(i).toFixed(1)},${yFor(p.line ?? 0).toFixed(1)}`)
    .join(' ')
)
function format(v: number) {
  if (props.formatValue) return props.formatValue(v)
  return v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(Math.round(v))
}
function short(v: number) {
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  if (v >= 1) return Number.isInteger(v) ? String(v) : v.toFixed(1)
  if (v > 0) return v.toFixed(2)
  return '0'
}
function shortDate(label: string) {
  const parts = String(label).split('-')
  return parts.length === 3 ? `${parts[1]}-${parts[2]}` : label
}
</script>

<style scoped>
.trend {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 14px 16px 8px;
}
.trend-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}
.legend {
  display: flex;
  gap: 14px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: #5c6470;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 2px;
}
.dot.bar {
  background: #b7ccff;
}
.dot.line {
  background: #3370ff;
  border-radius: 50%;
}
.range {
  font-size: 11px;
  color: #9aa1ab;
  font-variant-numeric: tabular-nums;
}
.plot svg {
  display: block;
  width: 100%;
  height: 220px;
}
.grid line {
  stroke: #eef1f4;
  stroke-width: 1;
}
.grid text {
  fill: #a3a9b3;
  font-size: 9px;
}
.bar {
  fill: #b7ccff;
  transition: fill 160ms ease;
}
.bar:hover {
  fill: #7ea2ff;
}
.line {
  fill: none;
  stroke: #3370ff;
  stroke-width: 1.8;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.point {
  fill: #fff;
  stroke: #3370ff;
  stroke-width: 1.6;
}
.x-labels text {
  fill: #8a9099;
  font-size: 9px;
}
.x-labels text.dim {
  opacity: 0;
}

@media (max-width: 820px) {
  .plot {
    overflow-x: auto;
  }
  .plot svg {
    min-width: 620px;
  }
}
</style>
