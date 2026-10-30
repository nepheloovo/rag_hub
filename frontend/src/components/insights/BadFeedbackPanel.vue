<template>
  <n-card size="small">
    <template #header>
      <div class="card-title">
        最新差评
        <span class="card-hint">用户点踩的回答，点击查看完整调用链路</span>
      </div>
    </template>
    <template #header-extra>
      <n-button size="small" quaternary :loading="loading" @click="load">刷新</n-button>
    </template>
    <n-spin :show="loading">
      <n-empty v-if="!items.length" description="暂无差评" style="padding: 24px 0" />
      <div v-else class="bad-list">
        <div
          v-for="item in items"
          :key="item.message_id"
          class="bad-item"
          :class="{ clickable: !!item.trace_id }"
          role="button"
          :tabindex="item.trace_id ? 0 : -1"
          @click="open(item)"
          @keydown.enter="open(item)"
        >
          <div class="bad-head">
            <span class="bad-question">{{ item.question || '（未找到对应问题）' }}</span>
            <span class="bad-meta">{{ item.app_name || '—' }} · {{ formatTime(item.time) }}</span>
          </div>
          <div class="bad-answer">{{ item.answer }}</div>
          <div v-if="item.comment" class="bad-comment">原因：{{ item.comment }}</div>
        </div>
      </div>
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { getBadFeedback } from '@/api'
import type { BadFeedbackItem } from '@/api/types'

const router = useRouter()
const message = useMessage()
const items = ref<BadFeedbackItem[]>([])
const loading = ref(false)

function formatTime(value: string) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}

function open(item: BadFeedbackItem) {
  if (item.trace_id) router.push(`/app/observability/traces/${item.trace_id}`)
}

async function load() {
  loading.value = true
  try {
    items.value = await getBadFeedback(10)
  } catch (e: any) {
    message.error(e.message || '差评加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.card-title { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.card-hint { font-size: 12px; font-weight: 400; color: #8f959e; }
.bad-list { display: flex; flex-direction: column; }
.bad-item { padding: 12px 4px; border-bottom: 1px solid #eef0f4; border-radius: 6px; }
.bad-item:last-child { border-bottom: 0; }
.bad-item.clickable { cursor: pointer; }
.bad-item.clickable:hover, .bad-item.clickable:focus-visible { background: #f7f8fa; outline: none; }
.bad-head { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.bad-question { font-weight: 600; color: #1f2329; overflow-wrap: anywhere; }
.bad-meta { font-size: 12px; color: #8f959e; white-space: nowrap; }
.bad-answer {
  margin-top: 4px; font-size: 13px; color: #4e5969; line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.bad-comment { margin-top: 4px; font-size: 12px; color: #d4380d; }
</style>
