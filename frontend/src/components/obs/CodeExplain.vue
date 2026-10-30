<template>
  <div v-if="code" class="code-wrap">
    <div class="code-head">
      <div class="code-title">
        <n-icon size="14"><CodeSlashOutline /></n-icon>
        内部运行代码
        <span class="code-lang">{{ language }}</span>
      </div>
      <n-tag size="tiny" :bordered="false" type="info">只读快照</n-tag>
    </div>
    <div class="code-body" :class="{ 'single': !explain.length }">
      <div class="code-pane">
        <div
          v-for="(line, i) in lines"
          :key="i"
          class="code-line"
          :class="{ active: activeLines.includes(i + 1), annotated: lineBlockMap[i + 1] !== undefined }"
          @mouseenter="hoverLine = i + 1"
          @mouseleave="hoverLine = 0"
        >
          <span class="ln">{{ i + 1 }}</span>
          <span class="code-text">{{ line || ' ' }}</span>
        </div>
      </div>
      <div v-if="explain.length" class="explain-pane">
        <div class="explain-title">逐段解释</div>
        <button
          v-for="(block, idx) in explain"
          :key="idx"
          class="explain-block"
          :class="{ active: activeBlock === idx, hovered: hoverLine >= block.lines[0] && hoverLine <= block.lines[1] }"
          type="button"
          @mouseenter="activeBlock = idx"
          @mouseleave="activeBlock = -1"
          @click="focusBlock(block)"
        >
          <div class="explain-meta">
            <span class="explain-no">{{ String(idx + 1).padStart(2, '0') }}</span>
            <span class="explain-title-text">{{ block.title }}</span>
            <span class="explain-lines">L{{ block.lines[0] }}–{{ block.lines[1] }}</span>
          </div>
          <p class="explain-text">{{ block.text }}</p>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { CodeSlashOutline } from '@vicons/ionicons5'
import type { CodeExplainBlock } from '@/api/types'

const props = withDefaults(
  defineProps<{ code: string; explain?: CodeExplainBlock[]; language?: string }>(),
  { explain: () => [], language: 'python' }
)

const lines = computed(() => (props.code || '').replace(/\n$/, '').split('\n'))
const activeBlock = ref(-1)
const hoverLine = ref(0)

const lineBlockMap = computed(() => {
  const map: Record<number, number> = {}
  props.explain.forEach((block, idx) => {
    for (let l = block.lines[0]; l <= block.lines[1]; l++) map[l] = idx
  })
  return map
})

const activeLines = computed(() => {
  if (activeBlock.value >= 0) {
    const block = props.explain[activeBlock.value]
    const out: number[] = []
    for (let l = block.lines[0]; l <= block.lines[1]; l++) out.push(l)
    return out
  }
  if (hoverLine.value) {
    const idx = lineBlockMap.value[hoverLine.value]
    if (idx === undefined) return [hoverLine.value]
    const block = props.explain[idx]
    const out: number[] = []
    for (let l = block.lines[0]; l <= block.lines[1]; l++) out.push(l)
    return out
  }
  return []
})

function focusBlock(block: CodeExplainBlock) {
  const el = document.querySelector(`.code-line:nth-child(${block.lines[0]})`)
  el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}
</script>

<style scoped>
.code-wrap {
  border: 1px solid #e3e6ea;
  border-radius: 9px;
  overflow: hidden;
  background: #fbfcfd;
}
.code-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #e9ecf0;
  background: #f4f6f8;
}
.code-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #3b4351;
}
.code-lang {
  font-size: 10px;
  text-transform: uppercase;
  color: #8a9099;
  letter-spacing: 0.06em;
  padding-left: 2px;
}
.code-body {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(220px, 1fr);
}
.code-body.single {
  grid-template-columns: 1fr;
}
.code-pane {
  max-height: 380px;
  overflow: auto;
  background: #1e232b;
  padding: 8px 0;
}
.code-line {
  display: flex;
  gap: 12px;
  padding: 0 12px 0 0;
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.72;
  color: #c8d0da;
  white-space: pre;
  border-left: 2px solid transparent;
}
.code-line.annotated {
  background: rgba(51, 112, 255, 0.06);
}
.code-line.active {
  background: rgba(51, 112, 255, 0.16);
  border-left-color: #5c8aff;
  color: #fff;
}
.ln {
  width: 34px;
  flex: 0 0 34px;
  text-align: right;
  color: #5d6a7c;
  user-select: none;
}
.code-text {
  min-width: 0;
}
.explain-pane {
  padding: 10px;
  border-left: 1px solid #e9ecf0;
  background: #fbfcfd;
  max-height: 380px;
  overflow: auto;
}
.explain-title {
  font-size: 11px;
  color: #8a9099;
  letter-spacing: 0.06em;
  margin: 2px 2px 8px;
}
.explain-block {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid #eceff3;
  background: #fff;
  border-radius: 7px;
  padding: 8px 10px;
  margin-bottom: 7px;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease;
}
.explain-block:hover,
.explain-block.active {
  border-color: #a9c2ff;
  background: #f4f7ff;
}
.explain-block.hovered {
  border-color: #c6d5f7;
}
.explain-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}
.explain-no {
  color: #3370ff;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.explain-title-text {
  color: #2b3442;
  font-weight: 600;
}
.explain-lines {
  margin-left: auto;
  color: #9aa1ab;
  font-size: 10px;
}
.explain-text {
  margin: 5px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: #596273;
}
@media (max-width: 860px) {
  .code-body {
    grid-template-columns: 1fr;
  }
  .explain-pane {
    border-left: none;
    border-top: 1px solid #e9ecf0;
  }
}
</style>
