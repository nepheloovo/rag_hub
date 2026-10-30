<template>
  <div class="page app-page">
    <!-- 头部 -->
    <div class="page-head">
      <div class="head-left">
        <n-button quaternary circle size="small" @click="$router.push('/app/apps')">
          <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
        </n-button>
        <div>
          <div class="title-row">
            <h2 class="page-title">{{ app?.name || '应用详情' }}</h2>
            <n-tag v-if="app" size="small" :bordered="false" :color="{ color: typeBg, textColor: typeColor }">
              {{ kindLabel }}
            </n-tag>
            <n-tag v-if="app" size="small" :bordered="false" :type="statusTagType">
              {{ releaseStatusLabel }}
            </n-tag>
            <n-tag v-if="canManage && app?.draft_dirty" size="small" type="warning" :bordered="false">草稿有未发布修改</n-tag>
          </div>
          <p class="page-desc">{{ app?.description || '暂无描述' }}</p>
        </div>
      </div>
      <n-space v-if="canManage && app" :size="8">
        <n-button type="primary" size="small" :disabled="saving || configDirty" @click="openRelease">发布</n-button>
        <n-button v-if="app.status === 'published'" size="small" :loading="unpublishing" @click="confirmUnpublish">下线</n-button>
        <n-button type="error" secondary size="small" @click="removeApp">
        删除应用
        </n-button>
      </n-space>
    </div>

    <n-alert v-if="canManage && configDirty" type="warning" :bordered="false" class="unsaved-hint">配置有未保存修改，调试与评测以已保存草稿为准。请先保存配置再发布。</n-alert>

    <n-tabs v-model:value="activeTab" type="line" animated style="margin-top: -6px">
      <n-tab-pane name="chat" :tab="canManage ? '调试对话' : '对话'">
        <div class="chat-wrap">
          <!-- 会话列表 -->
          <div class="conv-panel">
            <n-button type="primary" block style="margin-bottom: 12px" @click="newConversation">
              <template #icon><n-icon><AddOutline /></n-icon></template>
              新建对话
            </n-button>
            <n-scrollbar style="height: calc(100% - 50px)">
              <div v-if="convLoading" class="conv-loading"><n-spin size="small" /></div>
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
            </n-scrollbar>
          </div>

          <!-- 聊天区 -->
          <div class="chat-main">
            <div class="chat-toolbar">
              <div class="toolbar-left">
                <n-icon size="18" :color="typeColor">
                  <component :is="typeIcon" />
                </n-icon>
                <span class="toolbar-name">{{ app?.name }}</span>
                <n-tag v-if="canManage" size="tiny" :bordered="false" type="warning">当前草稿</n-tag>
                <n-tag size="tiny" :bordered="false" type="info">{{ currentModelLabel }}</n-tag>
              </div>
              <span class="conv-status">
                <span class="dot" :class="{ on: !!activeConvId }"></span>
                {{ app?.show_refs ? '引用溯源已开启' : '引用溯源已关闭' }}
              </span>
            </div>

            <n-scrollbar ref="scrollRef" class="msg-scroll">
              <div v-if="messages.length === 0" class="welcome">
                <div class="welcome-avatar" :style="{ background: typeBg }">
                  <n-icon size="26" :color="typeColor"><component :is="typeIcon" /></n-icon>
                </div>
                <div class="welcome-title">{{ app?.opening || '你好，有什么可以帮你？' }}</div>
                <div class="suggest-row">
                  <div
                    v-for="s in app?.suggested_questions || []"
                    :key="s"
                    class="suggest-chip"
                    @click="send(s)"
                  >{{ s }}</div>
                </div>
              </div>

              <div v-for="m in messages" :key="m.id" class="msg-row" :class="m.role">
                <div v-if="m.role === 'assistant'" class="avatar ai" :style="{ background: typeBg }">
                  <n-icon size="18" :color="typeColor"><component :is="typeIcon" /></n-icon>
                </div>
                <div class="msg-body">
                  <div class="msg-name">{{ m.role === 'user' ? '我' : app?.name }}</div>
                  <div class="bubble" :class="m.role">
                    <div class="bubble-text">{{ m.content }}<span v-if="m.streaming" class="cursor">▍</span></div>
                    <div
                      v-if="m.role === 'assistant' && m.refs && m.refs.length"
                      class="ref-block"
                    >
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
                    <n-button v-if="m.meta.traceId" text size="tiny" type="primary" class="trace-link" @click="router.push(`/app/observability/traces/${m.meta.traceId}`)">
                      查看调用链路 →
                    </n-button>
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
                :disabled="sending"
                @keydown="onKeydown"
              />
              <div class="input-actions">
                <span class="input-tip">{{ sending ? '生成中…' : '' }}</span>
                <n-button
                  type="primary"
                  :loading="sending"
                  :disabled="!inputText.trim()"
                  @click="send()"
                >
                  <template #icon><n-icon><SendOutline /></n-icon></template>
                  发送
                </n-button>
              </div>
            </div>
          </div>
        </div>
      </n-tab-pane>

      <n-tab-pane v-if="canManage" name="flow" tab="编排">
        <FlowEditor :app-id="route.params.id as string" @saved="onDraftSaved" @debug="activeTab = 'chat'" />
      </n-tab-pane>

      <n-tab-pane v-if="canManage" name="eval" tab="评测" display-directive="show:lazy">
        <AppEvalPanel :app-id="route.params.id as string" @changed="refreshApp" />
      </n-tab-pane>

      <n-tab-pane v-if="canManage" name="versions" tab="版本" display-directive="show:lazy">
        <VersionsPanel :app-id="route.params.id as string" :refresh-key="releaseRefresh" @changed="onReleaseChanged" />
      </n-tab-pane>

      <n-tab-pane v-if="canManage" name="config" tab="配置">
        <n-card size="small" title="基础配置" style="max-width: 760px; margin-bottom: 16px">
          <n-form label-placement="left" label-width="100">
            <n-form-item label="应用名称">
              <n-input v-model:value="form.name" />
            </n-form-item>
            <n-form-item label="描述">
              <n-input v-model:value="form.description" />
            </n-form-item>
            <n-form-item label="应用形态">
              <n-select
                v-model:value="form.app_kind"
                :options="[
                  { label: '简易（提示词 + 知识库 + 表单）', value: 'simple' },
                  { label: 'Chat Flow（可视化编排）', value: 'chatflow' },
                  { label: 'Agent（自主规划工具）', value: 'agent' }
                ]"
              />
            </n-form-item>
            <n-form-item label="业务分类">
              <n-select
                v-model:value="form.category"
                :options="['报告撰写', '智能客服', '制度与合同审校', '营销内容', '办公提效'].map(c => ({ label: c, value: c }))"
              />
            </n-form-item>
            <n-form-item label="线上版本">
              <span class="field-hint">{{ releaseStatusLabel }}，保存仅更新草稿</span>
            </n-form-item>
            <n-form-item label="绑定知识库">
              <n-select
                v-model:value="form.kb_ids"
                multiple
                :options="kbOptions"
                placeholder="可绑定多个知识库"
              />
            </n-form-item>
            <n-form-item v-if="form.kb_ids.length" label="检索参数">
              <div class="retrieval-box">
                <label class="retrieval-toggle">
                  <n-switch v-model:value="form.retrieval_custom" size="small" />
                  <span>{{ form.retrieval_custom ? '自定义' : '使用平台默认（语义检索 · 引用上限 5 · 结果重排）' }}</span>
                </label>
                <template v-if="form.retrieval_custom">
                  <n-radio-group v-model:value="form.retrieval.mode" size="small">
                    <n-radio-button value="semantic">语义</n-radio-button>
                    <n-radio-button value="fulltext">全文</n-radio-button>
                    <n-radio-button value="hybrid">混合（推荐）</n-radio-button>
                  </n-radio-group>
                  <div class="retrieval-grid">
                    <label>引用上限 <n-input-number v-model:value="form.retrieval.top_n" size="small" :min="1" :max="20" style="width: 90px" /></label>
                    <label>最低相关度 {{ form.retrieval.score_threshold.toFixed(2) }}
                      <n-slider v-model:value="form.retrieval.score_threshold" :min="0" :max="1" :step="0.05" style="width: 140px" />
                    </label>
                    <label>结果重排 <n-switch v-model:value="form.retrieval.rerank" size="small" /></label>
                  </div>
                  <div class="field-hint">可在知识库「测试检索」中调好参数后一键写入；修改后需重新评测再发布</div>
                </template>
              </div>
            </n-form-item>
            <n-form-item label="LLM 模型">
              <n-select
                v-model:value="form.llm_ref"
                :options="llmOptions"
                placeholder="跟随全局默认模型"
                clearable
              />
            </n-form-item>
          </n-form>
        </n-card>

        <n-card size="small" title="对话配置" style="max-width: 760px; margin-bottom: 16px">
          <n-form label-placement="left" label-width="100">
            <n-form-item label="系统提示词">
              <n-input
                v-model:value="form.system_prompt"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 10 }"
              />
            </n-form-item>
            <n-form-item label="温度">
              <n-slider v-model:value="form.temperature" :min="0" :max="2" :step="0.1" style="max-width: 400px" />
            </n-form-item>
            <n-form-item label="引用溯源">
              <n-switch v-model:value="form.show_refs" />
              <span class="field-hint">回答中展示来源文档/页码/分数</span>
            </n-form-item>
            <n-form-item label="开场白">
              <n-input v-model:value="form.opening" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
            </n-form-item>
            <n-form-item label="推荐问题">
              <n-dynamic-tags v-model:value="form.suggested_questions" />
            </n-form-item>
          </n-form>
        </n-card>

        <n-card v-if="app?.app_type === 'service'" size="small" title="客服专属配置" style="max-width: 760px; margin-bottom: 16px">
          <n-form label-placement="left" label-width="100">
            <n-form-item label="兜底话术">
              <n-input
                v-model:value="form.fallback_reply"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="未检索到相关内容时的回复"
              />
            </n-form-item>
            <n-form-item label="转人工提示">
              <n-input
                v-model:value="form.transfer_hint"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="附加在兜底话术后的提示"
              />
            </n-form-item>
          </n-form>
        </n-card>

        <n-card size="small" title="发布设置" style="max-width: 760px; margin-bottom: 16px">
          <n-form label-placement="left" label-width="100">
            <n-form-item label="对外发布">
              <n-switch v-model:value="form.publish_enabled" />
              <span class="field-hint">应用需为「已发布」状态且开启此开关后，公开链接才可访问</span>
            </n-form-item>
            <n-form-item v-if="form.publish_enabled" label="公开链接">
              <div style="width: 100%">
                <n-input-group>
                  <n-input :value="publicUrl" readonly />
                  <n-button type="primary" @click="copyPublicUrl">复制</n-button>
                </n-input-group>
                <div class="field-hint">iframe 嵌入代码：</div>
                <n-input :value="embedCode" readonly type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" />
              </div>
            </n-form-item>
            <n-form-item label="访客日限额">
              <n-input-number v-model:value="form.visitor_daily_limit" :min="0" :precision="0" style="width: 180px" />
            </n-form-item>
            <n-form-item label="企业微信">
              <span class="field-hint">接入配置规划中（需企业微信自建应用，后续版本开放）</span>
            </n-form-item>
          </n-form>
        </n-card>

        <div style="max-width: 760px; display: flex; justify-content: flex-end">
          <n-button type="primary" :loading="saving" @click="saveConfig">保存配置</n-button>
        </div>
      </n-tab-pane>
    </n-tabs>
    <ReleaseDialog v-if="app && canManage" v-model:show="releaseDialog" :app-id="app.id" @published="onReleaseChanged" @eval="activeTab = 'eval'" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, nextTick, onMounted, markRaw, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  AddOutline,
  ArrowBackOutline,
  ChatbubblesOutline,
  DocumentTextOutline,
  HeadsetOutline,
  SendOutline
} from '@vicons/ionicons5'
import {
  deleteApp,
  getApp,
  getMessages,
  listAppConversations,
  listKbs,
  listProviders,
  streamAppChat,
  updateApp,
  unpublishApp
} from '@/api'
import type { AppKind, Application, Conversation, KnowledgeBase, Provider, RefItem, RetrievalMode } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import FlowEditor from './FlowEditor.vue'
import ReleaseDialog from '@/components/release/ReleaseDialog.vue'
import AppEvalPanel from '@/components/release/AppEvalPanel.vue'
import VersionsPanel from '@/components/release/VersionsPanel.vue'

interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  refs?: RefItem[]
  meta?: { durationMs: number; tokens: number; fake: boolean; traceId?: string }
}

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()

const app = ref<Application | null>(null)
const kbs = ref<KnowledgeBase[]>([])
const providers = ref<Provider[]>([])
const activeTab = ref('chat')
const canManage = computed(() => ['platform_admin', 'app_developer', 'kb_admin'].includes(auth.role!))
const releaseDialog = ref(false)
const unpublishing = ref(false)
const releaseRefresh = ref(0)

// 类型元信息
const typeMap: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  qa: { label: '问答应用', color: '#3370ff', bg: '#eef3ff', icon: markRaw(ChatbubblesOutline) },
  service: { label: '智能客服', color: '#22c55e', bg: '#ecfdf3', icon: markRaw(HeadsetOutline) },
  report: { label: '报告分析', color: '#8b5cf6', bg: '#f3efff', icon: markRaw(DocumentTextOutline) }
}
const typeLabel = computed(() => (app.value ? typeMap[app.value.app_type]?.label || '应用' : '应用'))
const typeColor = computed(() => (app.value ? typeMap[app.value.app_type]?.color || '#3370ff' : '#3370ff'))
const typeBg = computed(() => (app.value ? typeMap[app.value.app_type]?.bg || '#eef3ff' : '#eef3ff'))
const typeIcon = computed(() => (app.value ? typeMap[app.value.app_type]?.icon || ChatbubblesOutline : ChatbubblesOutline))
const kindLabel = computed(() => {
  const m: Record<string, string> = { simple: '简易', chatflow: 'Chat Flow', agent: 'Agent' }
  return app.value ? m[app.value.app_kind] || '简易' : '简易'
})
const releaseStatusLabel = computed(() => {
  if (app.value?.status === 'offline') return '已下线'
  if (app.value?.status === 'published' && app.value.published_version != null) return `线上 v${app.value.published_version}`
  return '未发布'
})
const statusTagType = computed(() => {
  if (!app.value) return 'default'
  return app.value.status === 'published' ? 'success' : app.value.status === 'offline' ? 'warning' : 'default'
})

// 对话
const conversations = ref<Conversation[]>([])
const convLoading = ref(false)
const messages = ref<Msg[]>([])
const activeConvId = ref<string | null>(null)
const inputText = ref('')
const sending = ref(false)
const scrollRef = ref<any>(null)

const currentModelLabel = computed(() => {
  if (!app.value) return ''
  if (app.value.llm_ref) return app.value.llm_ref.split(':')[1] || app.value.llm_ref
  return '默认 LLM'
})

// 配置表单
const form = reactive({
  name: '',
  description: '',
  app_kind: 'simple' as AppKind,
  category: '办公提效',
  kb_ids: [] as string[],
  llm_ref: '' as string | null,
  system_prompt: '',
  temperature: 0.2,
  show_refs: true,
  opening: '',
  suggested_questions: [] as string[],
  fallback_reply: '',
  transfer_hint: '',
  publish_enabled: false,
  visitor_daily_limit: 100 as number | null,
  retrieval_custom: false,
  retrieval: { mode: 'hybrid' as RetrievalMode, top_k: 20, top_n: 5, score_threshold: 0, rerank: true }
})
const saving = ref(false)
const savedConfig = ref('')
const configDirty = computed(() => !!savedConfig.value && JSON.stringify(form) !== savedConfig.value)

const publicUrl = computed(() => `${location.origin}/pub/${route.params.id}`)
const embedCode = computed(() => `<iframe src="${publicUrl.value}" style="width:100%;height:600px;border:0;border-radius:12px"></iframe>`)

function copyPublicUrl() {
  navigator.clipboard?.writeText(publicUrl.value).then(
    () => message.success('公开链接已复制'),
    () => message.info(`公开链接：${publicUrl.value}`)
  )
}

const kbOptions = computed(() => kbs.value.map(k => ({ label: k.name, value: k.id })))
const llmOptions = computed(() =>
  providers.value
    .filter(p => p.enabled)
    .flatMap(p => p.models.llm.map(m => ({ label: `${p.name} · ${m}`, value: `${p.id}:${m}` })))
)

function formatTime(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function scrollToBottom() {
  nextTick(() => scrollRef.value?.scrollTo({ top: 999999, behavior: 'smooth' }))
}

async function loadApp() {
  try {
    const [appData, kbList, pvList] = await Promise.all([
      getApp(route.params.id as string),
      canManage.value ? listKbs() : Promise.resolve([]),
      canManage.value ? listProviders() : Promise.resolve([])
    ])
    app.value = appData
    kbs.value = kbList
    providers.value = pvList
    fillForm(appData)
  } catch (e: any) {
    message.error(e.message)
  }
}

function fillForm(a: Application) {
  form.name = a.name
  form.description = a.description
  form.app_kind = a.app_kind
  form.category = a.category
  form.kb_ids = [...a.kb_ids]
  form.retrieval_custom = !!a.retrieval?.mode
  form.retrieval = { mode: 'hybrid', top_k: 20, top_n: 5, score_threshold: 0, rerank: true, ...(a.retrieval || {}) }
  form.llm_ref = a.llm_ref || null
  form.system_prompt = a.system_prompt
  form.temperature = a.temperature
  form.show_refs = a.show_refs
  form.opening = a.opening
  form.suggested_questions = [...a.suggested_questions]
  form.fallback_reply = a.fallback_reply
  form.transfer_hint = a.transfer_hint
  form.publish_enabled = !!a.publish_enabled
  form.visitor_daily_limit = a.visitor_daily_limit
  savedConfig.value = JSON.stringify(form)
}

function onDraftSaved(updated: Application) {
  const dirty = configDirty.value
  app.value = updated
  if (!dirty) fillForm(updated)
  releaseRefresh.value++
}
function onReleaseChanged(updated: Application) {
  onDraftSaved(updated)
  messages.value = []
  activeConvId.value = null
}
async function refreshApp() {
  try { onDraftSaved(await getApp(route.params.id as string)) }
  catch (e: any) { message.error(e.message || '应用状态刷新失败') }
}
function openRelease() {
  if (configDirty.value) { activeTab.value = 'config'; message.warning('请先保存配置'); return }
  releaseDialog.value = true
}
function confirmUnpublish() {
  if (!app.value || unpublishing.value) return
  dialog.warning({
    title: '下线应用',
    content: '下线后，工作台与公开链接将无法使用此应用。发布版本保留，可重新上线。',
    positiveText: '确认下线', negativeText: '取消',
    onPositiveClick: async () => {
      unpublishing.value = true
      try {
        onReleaseChanged(await unpublishApp(app.value!.id))
        message.success('应用已下线')
      } catch (e: any) { message.error(e.message || '下线失败'); return false }
      finally { unpublishing.value = false }
    }
  })
}

async function loadConversations() {
  convLoading.value = true
  try {
    conversations.value = await listAppConversations(route.params.id as string)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    convLoading.value = false
  }
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
  inputText.value = ''
  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content })
  messages.value.push({ id: `a-${Date.now()}`, role: 'assistant', content: '', streaming: true })
  const aiMsg = messages.value[messages.value.length - 1]
  scrollToBottom()
  sending.value = true

  try {
    for await (const { event, data } of streamAppChat(route.params.id as string, {
      query: content,
      role: auth.role ?? 'business_user',
      conversation_id: activeConvId.value,
      draft: canManage.value
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
        aiMsg.meta = { durationMs: d.duration_ms, tokens: d.tokens?.total ?? 0, fake: !!d.models?.fake, traceId: d.trace_id }
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

async function saveConfig() {
  saving.value = true
  try {
    const updated = await updateApp(route.params.id as string, {
      name: form.name,
      description: form.description,
      app_kind: form.app_kind,
      category: form.category,
      kb_ids: form.kb_ids,
      llm_ref: form.llm_ref || '',
      system_prompt: form.system_prompt,
      temperature: form.temperature,
      show_refs: form.show_refs,
      opening: form.opening,
      suggested_questions: form.suggested_questions,
      fallback_reply: form.fallback_reply,
      transfer_hint: form.transfer_hint,
      publish_enabled: form.publish_enabled,
      visitor_daily_limit: form.visitor_daily_limit ?? 0,
      retrieval: form.retrieval_custom ? { ...form.retrieval, top_k: Math.max(form.retrieval.top_k, form.retrieval.top_n) } : {}
    })
    app.value = updated
    fillForm(updated)
    releaseRefresh.value++
    message.success('草稿配置已保存')
  } catch (e: any) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}

function removeApp() {
  if (!app.value) return
  dialog.warning({
    title: '删除应用',
    content: `确定删除「${app.value.name}」吗？其下的会话记录将一并删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteApp(app.value!.id)
        message.success('已删除')
        window.location.href = '/app/apps'
      } catch (e: any) {
        message.error(e.message)
      }
    }
  })
}

onMounted(async () => {
  await loadApp()
  await loadConversations()
})
watch(() => route.query.tab, tab => {
  if (typeof tab === 'string' && ['chat', 'flow', 'config', 'eval', 'versions'].includes(tab) && (canManage.value || tab === 'chat')) activeTab.value = tab
}, { immediate: true })
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}
.unsaved-hint { margin-bottom: 14px; }

.head-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #1f2329;
}

.page-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: #8f959e;
}

.field-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #a8adb5;
}

.chat-wrap {
  display: flex;
  border: 1px solid #e8ebf2;
  border-radius: 10px;
  background: #fff;
  height: calc(100vh - 240px);
  min-height: 420px;
  overflow: hidden;
}

.conv-panel {
  width: 216px;
  border-right: 1px solid #f0f1f3;
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
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
  height: 48px;
  padding: 0 18px;
  border-bottom: 1px solid #f0f1f3;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2329;
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
  gap: 10px;
  padding: 20px;
}

.welcome-avatar {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.welcome-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2329;
  text-align: center;
  white-space: pre-wrap;
}

.suggest-row {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggest-chip {
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  font-size: 13px;
  color: #4b5563;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.suggest-chip:hover {
  border-color: #3370ff;
  color: #3370ff;
  background: #f0f5ff;
}

.msg-row {
  display: flex;
  gap: 10px;
  padding: 16px 40px;
  max-width: 860px;
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

.avatar.me {
  background: #eef0f4;
  color: #6b7280;
}

.msg-body {
  max-width: 76%;
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


.trace-link {
  margin-left: 8px;
  font-size: 11px;
}
.msg-meta {
  margin-top: 6px;
  font-size: 11px;
  color: #b3b8bf;
}

.chat-input {
  flex-shrink: 0;
  padding: 12px 40px 14px;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.input-tip {
  font-size: 12px;
  color: #3370ff;
}
.retrieval-box { width: 100%; display: flex; flex-direction: column; gap: 10px; }
.retrieval-toggle { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: #4e5969; cursor: pointer; }
.retrieval-grid { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; font-size: 13px; color: #4e5969; }
.retrieval-grid label { display: inline-flex; align-items: center; gap: 8px; }
</style>
