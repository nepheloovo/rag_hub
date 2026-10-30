<template>
  <div class="json-block">
    <div class="json-head">
      <span class="json-label">{{ label || '内容' }}</span>
      <n-button text size="tiny" class="copy-btn" @click="copy">
        <template #icon><n-icon><CopyOutline /></n-icon></template>
        {{ copied ? '已复制' : '复制' }}
      </n-button>
    </div>
    <pre v-if="isText" class="json-text" :style="{ maxHeight: maxHeight }">{{ text }}</pre>
    <pre v-else class="json-text json-code" :style="{ maxHeight: maxHeight }">{{ pretty }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { CopyOutline } from '@vicons/ionicons5'

const props = withDefaults(
  defineProps<{ value: any; label?: string; maxHeight?: string }>(),
  { label: '', maxHeight: '320px' }
)
const copied = ref(false)

const isText = computed(() => typeof props.value === 'string' || typeof props.value === 'number')
const text = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') return '（空）'
  return typeof props.value === 'string' ? props.value : String(props.value)
})
const pretty = computed(() => {
  if (props.value === null || props.value === undefined) return '（空）'
  try {
    return JSON.stringify(props.value, null, 2)
  } catch {
    return String(props.value)
  }
})

async function copy() {
  try {
    await navigator.clipboard.writeText(isText.value ? text.value : pretty.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 1400)
  } catch {
    /* ignore */
  }
}
</script>

<style scoped>
.json-block {
  border: 1px solid #eef0f3;
  border-radius: 8px;
  background: #fafbfc;
  overflow: hidden;
}
.json-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 10px 6px;
  border-bottom: 1px solid #eef0f3;
  background: #f7f8fa;
}
.json-label {
  font-size: 11px;
  color: #6b7280;
  letter-spacing: 0.04em;
}
.copy-btn {
  font-size: 11px;
  color: #8a9099;
}
.copy-btn:hover {
  color: #3370ff;
}
.json-text {
  margin: 0;
  padding: 10px 12px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SFMono-Regular', ui-monospace, 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.65;
  color: #2f3542;
  tab-size: 2;
}
.json-code {
  color: #1f2937;
}
</style>
