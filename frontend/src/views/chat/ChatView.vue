<template>
  <div class="chat-page">
    <!-- 左侧会话列表 -->
    <div class="conv-panel">
      <n-button type="primary" block style="margin-bottom: 12px" @click="newConversation">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        新建对话
      </n-button>
      <n-scrollbar style="height: calc(100% - 50px)">
        <div v-if="convLoading" class="conv-loading">
          <n-spin size="small" />
        </div>
        <div
          v-for="c in conversations"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === activeConvId }"
          @click="openConversation(c.id)"
        >
          <div class="conv-title">{{ c.title }}</div>
          <div class="conv-time">{{ formatTime(c.created_at) }}</div>
        </div>
        <div v-if="!convLoading && conversations.length === 0" class="conv-empty">
          暂无历史对话
        </div>
      </n-scrollbar>
    </div>

    <!-- 右侧聊天区 -->
    <div class="chat-main">
      <div class="chat-toolbar">
        <div class="toolbar-left">
          <span class="toolbar-label">知识库</span>
          <n-select
            v-model:value="selectedKb"
            :options="kbOptions"
            size="small"
            style="width: 220px"
            placeholder="选择知识库"
            @update:value="onKbChange"
          />
          <span class="toolbar-label" style="margin-left: 16px">模型</span>
          <n-select
            v-model:value="selectedModel"
            :options="modelOptions"
            size="small"
            style="width: 180px"
            :placeholder="modelOptions.length ? '默认模型' : '未配置 LLM'"
            clearable
          />
        </div>
        <div class="toolbar-right">
          <span class="conv-status">
            <span class="dot" :class="{ on: !!activeConvId }"></span>
            {{ statusText }}
          </span>
        </div>
      </div>

      <n-scrollbar ref="scrollRef" class="msg-scroll">
        <div v-if="messages.length === 0" class="welcome">
          <n-icon size="44" color="#3370ff"><ChatbubblesOutline /></n-icon>
          <div class="welcome-title">你好，我是企业知识助手</div>
          <div class="welcome-sub">选择上方知识库后开始提问，回答将标注引用来源</div>
          <div class="suggest-row">
            <div v-for="s in suggests" :key="s" class="suggest-chip" @click="send(s)">{{ s }}</div>
          </div>
        </div>

        <div v-for="m in messages" :key="m.id" class="msg-row" :class="m.role">
          <div v-if="m.role === 'assistant'" class="avatar ai">
            <n-icon size="18" color="#fff"><SparklesOutline /></n-icon>
          </div>
          <div class="msg-body">
            <div class="msg-name">{{ m.role === 'user' ? '我' : '知识助手' }}</div>
            <div class="bubble" :class="m.role">
              <div class="bubble-text">
                {{ m.content }}<span v-if="m.streaming" class="cursor">▍</span>
              </div>
              <!-- 引用来源 -->
              <div v-if="m.role === 'assistant' && m.refs && m.refs.length" class="ref-block">
                <div class="ref-title">
                  <n-icon size="14"><DocumentTextOutline /></n-icon>
                  引用来源（{{ m.refs.length }}）
                </div>
                <div v-for="(r, i) in m.refs" :key="i" class="ref-item">
                  <div class="ref-head">
                    <span class="ref-doc">{{ r.title }}</span>
                    <n-space :size="6" align="center">
                      <n-tag v-if="r.page" size="tiny" :bordered="false" type="info">第 {{ r.page }} 页</n-tag>
                      <n-tag v-if="r.score !== null" size="tiny" :bordered="false" type="success">score {{ r.score }}</n-tag>
                    </n-space>
                  </div>
                  <div class="ref-snippet">{{ r.snippet }}</div>
                </div>
              </div>
            </div>
            <div v-if="m.role === 'assistant' && m.meta && !m.streaming" class="msg-meta">
              耗时 {{ (m.meta.durationMs / 1000).toFixed(1) }}s · {{ m.meta.tokens.toLocaleString() }} tokens
              <span v-if="m.meta.fake"> · 模拟模型（未配置服务商）</span>
            </div>
          </div>
          <div v-if="m.role === 'user'" class="avatar me">我</div>
        </div>
      </n-scrollbar>

      <div class="chat-input">
        <n-input
          v-model:value="inputText"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="输入你的问题，Enter 发送，Shift + Enter 换行"
          :disabled="sending || !selectedKb"
          @keydown="onKeydown"
        />
        <div class="input-actions">
          <div class="input-tip">
            {{ selectedKb ? '' : '请先选择知识库' }}
            <span v-if="sending" style="color: #3370ff">生成中…</span>
          </div>
          <n-button
            type="primary"
            :loading="sending"
            :disabled="!inputText.trim() || !selectedKb"
            @click="send()"
          >
            <template #icon><n-icon><SendOutline /></n-icon></template>
            发送
          </n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import {
  AddOutline,
  ChatbubblesOutline,
  SparklesOutline,
  DocumentTextOutline,
  SendOutline
} from '@vicons/ionicons5'
import { listConversations, listKbs, getMessages, streamChat, listProviders, getDefaults } from '@/api'
import type { ChatMessage, Conversation, KnowledgeBase, Provider, RefItem } from '@/api/types'
import { useAppStore } from '@/stores/app'

interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  refs?: RefItem[]
  meta?: { durationMs: number; tokens: number; fake: boolean }
}

const message = useMessage()
const store = useAppStore()
const scrollRef = ref<any>(null)
const kbs = ref<KnowledgeBase[]>([])
const selectedKb = ref<string | null>(null)
const selectedModel = ref<string | null>(null)
const modelOptions = ref<{ label: string; value: string }[]>([])
const inputText = ref('')
const sending = ref(false)
const messages = ref<Msg[]>([])
const conversations = ref<Conversation[]>([])
const convLoading = ref(false)
const activeConvId = ref<string | null>(null)

const kbOptions = computed(() => kbs.value.map(kb => ({ label: kb.name, value: kb.id })))
const statusText = computed(() => {
  if (!activeConvId.value) return '未开始'
  return `对话中 · ${messages.value.filter(m => m.role === 'assistant' && !m.streaming).length} 次回答`
})

const suggests = ['系统的检索链路是怎么设计的？', '支持导入哪些文件类型？', '部署需要哪些服务？']

function formatTime(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function scrollToBottom() {
  nextTick(() => {
    scrollRef.value?.scrollTo({ top: 999999, behavior: 'smooth' })
  })
}

async function loadKbs() {
  try {
    kbs.value = await listKbs()
    if (kbs.value.length && !selectedKb.value) selectedKb.value = kbs.value[0].id
  } catch (e: any) {
    message.error(e.message)
  }
}

async function loadModelOptions() {
  try {
    const [providers, defaults] = await Promise.all([listProviders(), getDefaults()])
    const options: { label: string; value: string }[] = []
    for (const p of providers) {
      if (!p.enabled) continue
      for (const m of p.models.llm) options.push({ label: `${p.name} · ${m}`, value: `${p.id}:${m}` })
    }
    modelOptions.value = options
    // 仅当默认模型存在于可选列表时才回显，否则留空显示占位提示
    selectedModel.value = options.some(o => o.value === defaults.default_llm)
      ? defaults.default_llm
      : null
  } catch {
    /* 配置页可管理，此处静默 */
  }
}

async function loadConversations() {
  convLoading.value = true
  try {
    conversations.value = await listConversations(selectedKb.value ?? undefined)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    convLoading.value = false
  }
}

function onKbChange() {
  messages.value = []
  activeConvId.value = null
  loadConversations()
}

function newConversation() {
  messages.value = []
  activeConvId.value = null
  message.success('已新建对话，开始提问吧')
}

async function openConversation(convId: string) {
  if (activeConvId.value === convId) return
  try {
    const history = await getMessages(convId)
    messages.value = history.map(m => ({
      id: m.id,
      role: m.role,
      content: m.content,
      refs: m.role === 'assistant' ? m.refs : undefined
    }))
    activeConvId.value = convId
    scrollToBottom()
  } catch (e: any) {
    message.error(e.message)
  }
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
  if (!selectedKb.value) {
    message.warning('请先选择知识库')
    return
  }

  inputText.value = ''
  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content })
  messages.value.push({ id: `a-${Date.now()}`, role: 'assistant', content: '', streaming: true })
  // 通过响应式代理获取消息对象，保证流式修改能触发视图更新
  const aiMsg = messages.value[messages.value.length - 1]
  scrollToBottom()
  sending.value = true

  try {
    for await (const { event, data } of streamChat({
      kb_id: selectedKb.value,
      query: content,
      role: store.role ?? 'user',
      conversation_id: activeConvId.value
    })) {
      if (event === 'delta') {
        const d = data as { text: string }
        aiMsg.content += d.text
        scrollToBottom()
      } else if (event === 'done') {
        const d = data as any
        aiMsg.content = d.answer
        aiMsg.streaming = false
        aiMsg.refs = d.refs
        aiMsg.meta = {
          durationMs: d.duration_ms,
          tokens: d.tokens?.total ?? 0,
          fake: !!d.models?.fake
        }
        if (!activeConvId.value && d.conversation_id) {
          activeConvId.value = d.conversation_id
          loadConversations()
        }
      } else if (event === 'error') {
        const d = data as { message: string }
        aiMsg.streaming = false
        aiMsg.content = aiMsg.content || `⚠️ ${d.message}`
        message.error(d.message)
      }
    }
  } catch (e: any) {
    aiMsg.streaming = false
    if (!aiMsg.content) aiMsg.content = `⚠️ ${e.message}`
    message.error(e.message)
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

onMounted(async () => {
  await Promise.all([loadKbs(), loadModelOptions()])
  await loadConversations()
})
</script>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
}

.conv-panel {
  width: 224px;
  background: #fff;
  border-right: 1px solid #f0f1f3;
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
}

.conv-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
}

.conv-item:hover {
  background: #f5f7fa;
}

.conv-item.active {
  background: #eef3ff;
}

.conv-title {
  font-size: 13px;
  color: #1f2329;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-item.active .conv-title {
  color: #3370ff;
  font-weight: 600;
}

.conv-time {
  font-size: 11px;
  color: #a8adb5;
  margin-top: 2px;
}

.conv-empty {
  font-size: 12px;
  color: #a8adb5;
  text-align: center;
  padding: 20px 0;
}

.conv-loading {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-toolbar {
  height: 52px;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #f0f1f3;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
}

.toolbar-label {
  font-size: 13px;
  color: #6b7280;
  margin-right: 8px;
  white-space: nowrap;
}

.conv-status {
  font-size: 12px;
  color: #8f959e;
  display: flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c9cdd4;
}

.dot.on {
  background: #22c55e;
}

.msg-scroll {
  flex: 1;
  min-height: 0;
}

.welcome {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.welcome-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2329;
}

.welcome-sub {
  font-size: 13px;
  color: #8f959e;
}

.suggest-row {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.suggest-chip {
  padding: 10px 18px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 20px;
  font-size: 13px;
  color: #4b5563;
  cursor: pointer;
  transition: all 0.2s;
}

.suggest-chip:hover {
  border-color: #3370ff;
  color: #3370ff;
  background: #f0f5ff;
}

.msg-row {
  display: flex;
  gap: 10px;
  padding: 18px 60px;
  max-width: 900px;
  margin: 0 auto;
}

.msg-row.user {
  justify-content: flex-end;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
}

.avatar.ai {
  background: linear-gradient(135deg, #3370ff, #5c8aff);
  color: #fff;
}

.avatar.me {
  background: #eef0f4;
  color: #6b7280;
}

.msg-body {
  max-width: 72%;
  display: flex;
  flex-direction: column;
}

.msg-row.user .msg-body {
  align-items: flex-end;
}

.msg-name {
  font-size: 12px;
  color: #8f959e;
  margin-bottom: 6px;
}

.bubble {
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.75;
}

.bubble.user {
  background: #3370ff;
  color: #fff;
  padding: 10px 16px;
  border-radius: 12px 12px 2px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble.assistant {
  padding: 2px 0;
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

.ref-block {
  margin-top: 14px;
  border: 1px solid #e8ebf2;
  border-radius: 10px;
  background: #fafbfd;
  padding: 12px 14px;
}

.ref-title {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}

.ref-item {
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #eef0f4;
  margin-bottom: 8px;
}

.ref-item:last-child {
  margin-bottom: 0;
}

.ref-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.ref-doc {
  font-size: 13px;
  font-weight: 600;
  color: #1f2329;
}

.ref-snippet {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.msg-meta {
  margin-top: 6px;
  font-size: 11px;
  color: #b3b8bf;
}

.chat-input {
  flex-shrink: 0;
  padding: 14px 60px 18px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.input-tip {
  font-size: 12px;
  color: #fa8c16;
}
</style>
