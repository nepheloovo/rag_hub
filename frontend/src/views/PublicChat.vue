<template>
  <div class="pub-page">
    <div class="pub-header">
      <div class="pub-logo">
        <n-icon size="18" color="#fff"><GridOutline /></n-icon>
        <span>知枢</span>
      </div>
      <div class="pub-app-name">{{ app?.name || '加载中…' }}</div>
    </div>

    <n-scrollbar ref="scrollRef" class="pub-scroll">
      <div v-if="messages.length === 0" class="pub-welcome">
        <div class="pub-avatar">AI</div>
        <div class="pub-opening">{{ app?.opening || '你好，有什么可以帮你？' }}</div>
        <div class="pub-suggests">
          <div v-for="s in app?.suggested_questions || []" :key="s" class="pub-suggest" @click="send(s)">
            {{ s }}
          </div>
        </div>
      </div>
      <div v-for="m in messages" :key="m.id" class="pub-msg-row" :class="m.role">
        <div class="pub-bubble" :class="m.role">
          <div class="pub-bubble-text">{{ m.content }}<span v-if="m.streaming" class="cursor">▍</span></div>
          <div v-if="m.role === 'assistant' && m.refs?.length" class="pub-refs">
            <div v-for="(r, i) in m.refs.slice(0, 3)" :key="i" class="pub-ref">
              {{ r.title }}<template v-if="r.page"> · 第 {{ r.page }} 页</template>
            </div>
          </div>
          <MessageFeedback
            v-if="m.role === 'assistant' && m.messageId && !m.streaming"
            v-model:rating="m.feedback"
            :message-id="m.messageId"
            :public-app-id="String(route.params.appId)"
          />
        </div>
      </div>
    </n-scrollbar>

    <div class="pub-input">
      <n-input
        v-model:value="inputText"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 3 }"
        placeholder="输入你的问题…"
        :disabled="sending"
        @keydown="onKeydown"
      />
      <n-button type="primary" :loading="sending" :disabled="!inputText.trim()" @click="send()">
        <template #icon><n-icon><SendOutline /></n-icon></template>
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { GridOutline, SendOutline } from '@vicons/ionicons5'
import { getPublicApp, streamPublicChat } from '@/api'
import type { AppDoneData, FeedbackRating, RefItem } from '@/api/types'
import MessageFeedback from '@/components/chat/MessageFeedback.vue'

interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  refs?: RefItem[]
  messageId?: string
  feedback?: FeedbackRating
}

const route = useRoute()
const app = ref<any>(null)
const messages = ref<Msg[]>([])
const inputText = ref('')
const sending = ref(false)
const scrollRef = ref<any>(null)

function scrollToBottom() {
  nextTick(() => scrollRef.value?.scrollTo({ top: 999999, behavior: 'smooth' }))
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

async function send(text?: string) {
  const content = (text ?? inputText.value).trim()
  if (!content || sending.value) return
  inputText.value = ''
  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content })
  messages.value.push({ id: `a-${Date.now()}`, role: 'assistant', content: '', streaming: true })
  const aiMsg = messages.value[messages.value.length - 1]
  scrollToBottom()
  sending.value = true
  try {
    for await (const { event, data } of streamPublicChat(route.params.appId as string, { query: content })) {
      if (event === 'delta') {
        aiMsg.content += (data as any).text
        scrollToBottom()
      } else if (event === 'done') {
        const d = data as AppDoneData
        aiMsg.content = d.answer
        aiMsg.streaming = false
        aiMsg.refs = d.refs
        aiMsg.messageId = d.message_id
        aiMsg.feedback = 0
      } else if (event === 'error') {
        aiMsg.streaming = false
        aiMsg.content = aiMsg.content || `⚠️ ${(data as any).message}`
      }
    }
  } catch (e: any) {
    aiMsg.streaming = false
    if (!aiMsg.content) aiMsg.content = `⚠️ ${e.message}`
  } finally {
    aiMsg.streaming = false
    sending.value = false
    scrollToBottom()
  }
}

onMounted(async () => {
  try {
    app.value = await getPublicApp(route.params.appId as string)
    document.title = `${app.value.name} · 知枢`
  } catch (e: any) {
    app.value = { name: '应用不可用', opening: '该应用未发布或不存在' }
    document.title = '知枢'
  }
})
</script>

<style scoped>
.pub-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}

.pub-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #f0f1f3;
  flex-shrink: 0;
}

.pub-logo {
  display: flex;
  align-items: center;
  gap: 6px;
  background: linear-gradient(135deg, #3370ff, #5c8aff);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  padding: 5px 12px;
  border-radius: 8px;
}

.pub-app-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2329;
}

.pub-scroll {
  flex: 1;
  min-height: 0;
}

.pub-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 24px;
  gap: 12px;
}

.pub-avatar {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: linear-gradient(135deg, #3370ff, #5c8aff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
}

.pub-opening {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
  text-align: center;
  white-space: pre-wrap;
}

.pub-suggests {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 6px;
}

.pub-suggest {
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  font-size: 13px;
  color: #4b5563;
  cursor: pointer;
  text-align: center;
}

.pub-suggest:hover {
  border-color: #3370ff;
  color: #3370ff;
}

.pub-msg-row {
  display: flex;
  padding: 12px 24px;
}

.pub-msg-row.user {
  justify-content: flex-end;
}

.pub-bubble {
  max-width: 78%;
  font-size: 14px;
  line-height: 1.7;
}

.pub-bubble.user {
  background: #3370ff;
  color: #fff;
  padding: 10px 14px;
  border-radius: 12px 12px 2px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.pub-bubble.assistant {
  white-space: pre-wrap;
  word-break: break-word;
}

.cursor {
  animation: blink 1s infinite;
  color: #3370ff;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.pub-refs {
  margin-top: 10px;
  border: 1px solid #e8ebf2;
  border-radius: 8px;
  background: #fff;
  padding: 8px 10px;
}

.pub-ref {
  font-size: 12px;
  color: #6b7280;
  padding: 2px 0;
}

.pub-input {
  display: flex;
  gap: 10px;
  padding: 12px 24px 16px;
  background: #fff;
  border-top: 1px solid #f0f1f3;
  flex-shrink: 0;
}
</style>
