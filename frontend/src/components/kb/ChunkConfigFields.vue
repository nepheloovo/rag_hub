<template>
  <div class="chunk-config">
    <n-form label-placement="top" size="small" :show-feedback="false">
      <n-form-item label="切块方式">
        <n-select :value="modelValue.strategy" :options="strategyOptions" :render-label="renderLabel" @update:value="patch({ strategy: $event })" />
      </n-form-item>
      <div class="fit-hint">{{ current?.desc }}；适合：{{ current?.fit }}</div>

      <div v-if="showSize" class="param-grid">
        <n-form-item :label="modelValue.strategy === 'parent_child' ? '父块大小（字）' : '块大小（字）'">
          <n-input-number :value="modelValue.chunk_size" :min="100" :max="4000" :step="50" @update:value="patch({ chunk_size: $event ?? 600 })" />
        </n-form-item>
        <n-form-item v-if="showOverlap" label="重叠长度（字）">
          <n-input-number :value="modelValue.chunk_overlap" :min="0" :max="Math.floor(modelValue.chunk_size / 2)" :step="10" @update:value="patch({ chunk_overlap: $event ?? 0 })" />
        </n-form-item>
      </div>

      <n-form-item v-if="modelValue.strategy === 'separator'" label="分隔符" style="margin-top: 10px">
        <div class="separator-box">
          <n-input :value="modelValue.separator" placeholder="自定义，如 ### 或 ---，正则以 re: 开头" @update:value="patch({ separator: $event })" />
          <div class="preset-row">
            <n-tag
              v-for="p in SEPARATOR_PRESETS"
              :key="p.label"
              size="small"
              checkable
              :checked="modelValue.separator === p.value"
              @update:checked="patch({ separator: p.value })"
            >{{ p.label }}</n-tag>
          </div>
        </div>
      </n-form-item>

      <div class="enhance">
        <div class="enhance-title">分块增强</div>
        <label class="enhance-item">
          <n-switch size="small" :value="modelValue.enhance_keywords" @update:value="patch({ enhance_keywords: $event })" />
          <span><b>抽取关键词</b>　为每块生成检索关键词，未配置模型时按规则抽取</span>
        </label>
        <label class="enhance-item">
          <n-switch size="small" :value="modelValue.enhance_qa" @update:value="patch({ enhance_qa: $event })" />
          <span><b>生成问答对</b>　为每块生成它能回答的问题，提升口语化提问命中率（需配置对话模型）</span>
        </label>
      </div>
    </n-form>
  </div>
</template>

<script setup lang="ts">
import { computed, h } from 'vue'
import type { SelectOption } from 'naive-ui'
import type { ChunkConfig } from '@/api/types'
import { SEPARATOR_PRESETS, STRATEGIES } from './chunkConfig'

const props = defineProps<{ modelValue: ChunkConfig }>()
const emit = defineEmits<{ 'update:modelValue': [value: ChunkConfig] }>()

const current = computed(() => STRATEGIES.find(s => s.value === props.modelValue.strategy))
const strategyOptions = STRATEGIES.map(s => ({ label: s.label, value: s.value, fit: s.fit }))
const showSize = computed(() => !['page', 'table_row', 'qa_split'].includes(props.modelValue.strategy))
const showOverlap = computed(() => ['smart', 'heading', 'fixed', 'parent_child'].includes(props.modelValue.strategy))

function renderLabel(option: SelectOption) {
  return h('span', [option.label as string, h('span', { style: 'margin-left:8px;font-size:12px;color:#8f959e' }, String(option.fit || ''))])
}

function patch(change: Partial<ChunkConfig>) {
  const next = { ...props.modelValue, ...change }
  next.chunk_overlap = Math.min(next.chunk_overlap, Math.floor(next.chunk_size / 2))
  emit('update:modelValue', next)
}
</script>

<style scoped>
.fit-hint { margin: 6px 0 12px; font-size: 12px; line-height: 1.6; color: #8f959e; }
.param-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.separator-box { width: 100%; }
.preset-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.enhance { margin-top: 14px; padding-top: 12px; border-top: 1px dashed #e5e6eb; }
.enhance-title { font-size: 13px; font-weight: 600; color: #1f2329; margin-bottom: 8px; }
.enhance-item { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; font-size: 12px; line-height: 1.6; color: #4e5969; cursor: pointer; }
.enhance-item b { color: #1f2329; font-weight: 600; }
</style>
