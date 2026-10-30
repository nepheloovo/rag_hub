<template>
  <div class="page trace-page">
    <div v-if="loading" class="loading-wrap">
      <n-spin size="small" />
      <span>加载执行链路…</span>
    </div>

    <template v-else-if="trace">
      <div class="detail-top">
        <div class="back-col">
          <n-button text size="small" class="back-btn" @click="goBack">
            <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
            返回调用链
          </n-button>
        </div>
        <div class="title-col">
          <div class="title-row">
            <h2 class="detail-title">{{ trace.query || trace.title }}</h2>
            <n-tag size="tiny" :bordered="false" :type="statusType(trace.status)">{{ statusLabel(trace.status) }}</n-tag>
            <n-tag size="tiny" :bordered="false" type="info">{{ typeLabel(trace.trace_type) }}</n-tag>
            <n-tag v-if="trace.metadata?.demo" size="tiny" :bordered="false">演示数据</n-tag>
          </div>
          <div class="title-sub">
            <span>{{ trace.app_name || trace.kb_name || '—' }}</span>
            <span class="divider-dot"></span>
            <span class="mono">{{ trace.id }}</span>
            <span class="divider-dot"></span>
            <span>{{ formatDateTime(trace.started_at) }}</span>
            <span v-if="trace.source === 'public'" class="channel">公开渠道</span>
          </div>
        </div>
        <div class="action-col">
          <n-button size="small" @click="openCase('good')">
            <template #icon><n-icon><CheckmarkCircleOutline /></n-icon></template>
            标记 Good
          </n-button>
          <n-button size="small" @click="openCase('bad')">
            <template #icon><n-icon><CloseCircleOutline /></n-icon></template>
            标记 Bad
          </n-button>
        </div>
      </div>

      <MetricStrip :items="metrics" />

      <div class="detail-grid">
        <div class="main-col">
          <div class="chain-panel">
            <div class="chain-head">
              <div>
                <span class="chain-title">执行链路</span>
                <span class="chain-sub">{{ trace.span_count }} 个节点 · 点击定位 · 可横向滚动</span>
              </div>
              <span class="chain-legend">
                <i class="dot success"></i>成功
                <i class="dot error"></i>失败
                <i class="dot skipped"></i>跳过
              </span>
            </div>
            <div class="chain-scroll">
              <div class="chain">
                <template v-for="(span, idx) in trace.spans" :key="span.id">
                  <button
                    type="button"
                    class="chain-node"
                    :class="[span.status, { reactive: isReactive(span) }]"
                    @click="scrollToSpan(span.id)"
                  >
                    <span class="chain-type">{{ typeLabel(span.span_type) }}</span>
                    <span class="chain-name">{{ shorten(span.name, 18) }}</span>
                    <span class="chain-meta">
                      <span class="chain-dot"></span>
                      {{ span.duration_ms ? formatDuration(span.duration_ms) : '—' }}
                    </span>
                  </button>
                  <span v-if="idx < trace.spans.length - 1" class="chain-arrow"></span>
                </template>
              </div>
            </div>
          </div>

          <div class="timeline-panel">
            <TraceTimeline ref="timelineRef" :spans="trace.spans" />
          </div>
        </div>

        <aside class="side-col">
          <div class="side-panel">
            <n-tabs v-model:value="sideTab" type="line" size="small" display-directive="if">
              <n-tab-pane name="overview" tab="概览">
                <div class="kv-list">
                  <div class="kv-item"><span class="kv-key">应用</span><span class="kv-val">{{ trace.app_name || '—' }}</span></div>
                  <div class="kv-item"><span class="kv-key">知识库</span><span class="kv-val">{{ trace.kb_name || '—' }}</span></div>
                  <div class="kv-item"><span class="kv-key">角色</span><span class="kv-val">{{ trace.role || '—' }}</span></div>
                  <div class="kv-item"><span class="kv-key">主模型</span><span class="kv-val mono">{{ trace.models?.llm || trace.model || '—' }}</span></div>
                  <div class="kv-item"><span class="kv-key">Embedding</span><span class="kv-val mono">{{ trace.models?.embedding || '—' }}</span></div>
                  <div v-if="trace.models?.rerank" class="kv-item"><span class="kv-key">Rerank</span><span class="kv-val mono">{{ trace.models.rerank }}</span></div>
                  <div class="kv-item"><span class="kv-key">耗时</span><span class="kv-val">{{ formatDuration(trace.duration_ms) }}</span></div>
                  <div class="kv-item"><span class="kv-key">节点</span><span class="kv-val">{{ trace.span_count }}</span></div>
                  <div class="kv-item"><span class="kv-key">会话</span><span class="kv-val mono small">{{ trace.conversation_id || '—' }}</span></div>
                  <div class="kv-item"><span class="kv-key">消息</span><span class="kv-val mono small">{{ trace.message_id || '—' }}</span></div>
                </div>

                <div class="side-section">
                  <div class="side-label">输出回答</div>
                  <div class="answer-preview">{{ trace.answer || '（无输出）' }}</div>
                </div>

                <div v-if="trace.cases?.length" class="side-section">
                  <div class="side-label">已回流 Case</div>
                  <div v-for="c in trace.cases" :key="c.id" class="case-item">
                    <n-tag size="tiny" :bordered="false" :type="c.label === 'good' ? 'success' : 'error'">
                      {{ c.label === 'good' ? 'Good' : 'Bad' }}
                    </n-tag>
                    <span class="case-note">{{ c.note || '已加入评测集' }}</span>
                  </div>
                </div>
              </n-tab-pane>

              <n-tab-pane name="context" tab="上下文">
                <div class="side-section first">
                  <div class="side-label">系统提示词</div>
                  <div class="prompt-box">{{ trace.context?.system_prompt || '—' }}</div>
                </div>
                <div v-if="historyMessages.length" class="side-section">
                  <div class="side-label">历史消息（{{ historyMessages.length }}）</div>
                  <div v-for="(m, i) in historyMessages" :key="i" class="message-row">
                    <span class="message-role" :class="m.role">{{ m.role === 'user' ? '用户' : '助手' }}</span>
                    <span class="message-content">{{ m.content }}</span>
                  </div>
                </div>
                <div v-if="chunks.length" class="side-section">
                  <div class="side-label">检索分块（{{ chunks.length }}）</div>
                  <div v-for="(c, i) in chunks" :key="i" class="chunk-card">
                    <div class="chunk-head">
                      <span class="chunk-source">{{ c.source || '未命名' }}<template v-if="c.page"> · 第 {{ c.page }} 页</template></span>
                      <span v-if="c.score !== undefined" class="chunk-score">{{ Number(c.score).toFixed(3) }}</span>
                    </div>
                    <div class="chunk-text">{{ c.content }}</div>
                  </div>
                </div>
                <div class="side-section">
                  <div class="side-label">可用能力</div>
                  <div class="ability-row">
                    <span v-for="skill in availableSkills" :key="skill" class="ability-chip skill">{{ skill }}</span>
                    <span v-for="tool in availableTools" :key="tool" class="ability-chip tool">{{ tool }}</span>
                    <span v-if="!availableSkills.length && !availableTools.length" class="empty-line">未记录能力清单</span>
                  </div>
                </div>
              </n-tab-pane>

              <n-tab-pane name="errors" tab="异常">
                <div v-if="errorSpans.length" class="side-section first">
                  <div v-for="span in errorSpans" :key="span.id" class="exception-card" @click="scrollToSpan(span.id)">
                    <div class="exception-title">{{ span.name }}</div>
                    <div class="exception-error">{{ span.error }}</div>
                    <div v-if="span.error_hint" class="exception-hint">{{ span.error_hint }}</div>
                  </div>
                </div>
                <div v-else class="empty-side">
                  <n-icon size="26" color="#b8d8c4"><CheckmarkCircleOutline /></n-icon>
                  <div class="empty-title">本次执行没有异常</div>
                  <div class="empty-desc">工具、Skill、模型调用均正常完成。</div>
                </div>
              </n-tab-pane>

              <n-tab-pane name="cost" tab="计费">
                <div class="side-section first">
                  <div class="cost-total">
                    <span class="cost-label">本次总成本</span>
                    <span class="cost-value">¥{{ Number(trace.cost_cny || 0).toFixed(4) }}</span>
                  </div>
                  <div class="token-breakdown">
                    <div class="token-row">
                      <span>输入 Token</span>
                      <span class="mono">{{ (trace.tokens?.input || 0).toLocaleString() }}</span>
                    </div>
                    <div class="token-row">
                      <span>输出 Token</span>
                      <span class="mono">{{ (trace.tokens?.output || 0).toLocaleString() }}</span>
                    </div>
                    <div class="token-row sub">
                      <span>LLM</span>
                      <span class="mono">{{ (trace.tokens?.llm || 0).toLocaleString() }}</span>
                    </div>
                    <div class="token-row sub">
                      <span>Embedding</span>
                      <span class="mono">{{ (trace.tokens?.embedding || 0).toLocaleString() }}</span>
                    </div>
                    <div class="token-row sub">
                      <span>Rerank</span>
                      <span class="mono">{{ (trace.tokens?.rerank || 0).toLocaleString() }}</span>
                    </div>
                  </div>
                  <div class="cost-note">按「模型单价 × 输入/输出 Token」折算，单价可在计费页调整。</div>
                </div>
                <div class="side-section">
                  <div class="side-label">各步骤消耗</div>
                  <div v-for="span in costSpans" :key="span.id" class="cost-span-row">
                    <span class="cost-span-name">{{ shorten(span.name, 22) }}</span>
                    <span class="cost-span-token">{{ (span.tokens?.total || 0).toLocaleString() }}</span>
                    <span class="cost-span-cost">¥{{ Number(span.cost_cny || 0).toFixed(4) }}</span>
                  </div>
                  <div v-if="!costSpans.length" class="empty-line">本链路没有记录到 Token 消耗</div>
                </div>
              </n-tab-pane>
            </n-tabs>
          </div>
        </aside>
      </div>

      <CaseFlowModal
        v-model:show="caseModal"
        mode="trace"
        :trace-id="trace.id"
        :preset-question="trace.query"
        :preset-answer="trace.answer"
        :preset-app-id="trace.app_id"
        :preset-app-name="trace.app_name"
        :initial-label="caseLabel"
        @saved="reload"
      />
    </template>

    <div v-else class="empty-page">
      <div class="empty-title">链路不存在或已过期</div>
      <n-button size="small" @click="goBack">返回调用链</n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  ArrowBackOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline
} from '@vicons/ionicons5'
import { getTrace } from '@/api'
import type { TraceDetail, TraceSpan } from '@/api/types'
import MetricStrip from '@/components/obs/MetricStrip.vue'
import TraceTimeline from '@/components/obs/TraceTimeline.vue'
import CaseFlowModal from '@/components/obs/CaseFlowModal.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const loading = ref(false)
const trace = ref<TraceDetail | null>(null)
const sideTab = ref('overview')
const caseModal = ref(false)
const caseLabel = ref<'good' | 'bad'>('good')
const timelineRef = ref<any>(null)

const metrics = computed(() => {
  const t = trace.value
  const rounds = t?.spans.filter(s => s.span_type === 'react.thought').length || 0
  return [
    { label: '总耗时', value: formatDuration(t?.duration_ms || 0) },
    { label: 'Token', value: (t?.tokens?.total || 0).toLocaleString() },
    { label: '成本', value: `¥${Number(t?.cost_cny || 0).toFixed(4)}` },
    { label: '执行节点', value: t?.span_count || 0 },
    { label: 'ReAct 轮次', value: rounds || '—', sub: rounds ? '模型思考次数' : '非 Agent 链路' }
  ]
})

const historyMessages = computed(() => {
  const history = trace.value?.context?.history
  return Array.isArray(history) ? history : []
})
const chunks = computed(() => {
  const value = trace.value?.context?.retrieved_chunks
  return Array.isArray(value) ? value : []
})
const availableSkills = computed(() => {
  const list = trace.value?.context?.available_skills
  return Array.isArray(list) ? list.map((x: any) => x.label || x.name || x) : []
})
const availableTools = computed(() => {
  const list = trace.value?.context?.available_tools
  return Array.isArray(list) ? list.map((x: any) => x.label || x.name || x) : []
})
const errorSpans = computed(() => trace.value?.spans.filter(s => s.status === 'error' || s.error) || [])
const costSpans = computed(() =>
  (trace.value?.spans || []).filter(s => (s.tokens?.total || 0) > 0 || (s.cost_cny || 0) > 0)
)

const TYPE_LABEL: Record<string, string> = {
  agent: 'Agent',
  chatflow: 'Chat Flow',
  chat: '简易 RAG',
  kb_build: '知识库构建',
  'react.plan': '规划',
  'react.thought': '思考',
  'react.action': '行动',
  'tool.call': '工具',
  'skill.call': 'Skill',
  'react.observation': '观察',
  'retrieval.embed': '向量化',
  'retrieval.search': '召回',
  'retrieval.rerank': '重排',
  'context.assemble': '上下文',
  'llm.call': 'LLM',
  'flow.node': '流程节点',
  'build.parse': '解析',
  'build.chunk': '分块',
  'build.embed': '向量化',
  'build.index': '入库',
  'final.answer': '输出',
  exception: '异常'
}
function typeLabel(type: string) {
  return TYPE_LABEL[type] || type
}
function statusType(status: string) {
  return status === 'success' ? 'success' : status === 'error' ? 'error' : status === 'degraded' ? 'warning' : 'info'
}
function statusLabel(status: string) {
  return ({ success: '执行成功', error: '执行失败', degraded: '降级完成', running: '运行中' } as any)[status] || status
}
function isReactive(span: TraceSpan) {
  return span.span_type.startsWith('react') || span.span_type === 'final.answer'
}
function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 60000).toFixed(1)}min`
}
function formatDateTime(iso: string) {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
function shorten(value: string, max: number) {
  return value && value.length > max ? value.slice(0, max) + '…' : value || '—'
}
function scrollToSpan(id: string) {
  timelineRef.value?.scrollTo(id)
}
function openCase(label: 'good' | 'bad') {
  caseLabel.value = label
  caseModal.value = true
}
function goBack() {
  router.push('/app/observability?tab=traces')
}
async function load() {
  loading.value = true
  try {
    trace.value = await getTrace(String(route.params.id))
  } catch (e: any) {
    trace.value = null
    message.error(e.message || '链路加载失败')
  } finally {
    loading.value = false
  }
}
function reload() {
  load()
}

watch(() => route.params.id, load)
onMounted(load)
</script>

<style scoped>
.trace-page {
  max-width: 1480px;
}
.loading-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 60px 0;
  justify-content: center;
  font-size: 12px;
  color: #8a9099;
}
.detail-top {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 14px;
}
.back-col {
  padding-top: 3px;
}
.back-btn {
  color: #6b7280;
  white-space: nowrap;
}
.title-col {
  flex: 1;
  min-width: 0;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.detail-title {
  margin: 0;
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: #1f2329;
  line-height: 1.4;
}
.title-sub {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  font-size: 11px;
  color: #8a9099;
}
.divider-dot {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #cfd4dc;
}
.mono {
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
}
.channel {
  color: #3b6fd4;
  background: #eef3ff;
  padding: 1px 6px;
  border-radius: 4px;
}
.action-col {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}
.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 14px;
  margin-top: 14px;
  align-items: start;
}
.main-col {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.chain-panel {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 13px 15px 12px;
}
.chain-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.chain-title {
  font-size: 13px;
  font-weight: 600;
  color: #2b3442;
}
.chain-sub {
  margin-left: 8px;
  font-size: 10.5px;
  color: #9aa1ab;
}
.chain-legend {
  font-size: 10px;
  color: #8a9099;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.chain-legend .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
  margin-left: 4px;
}
.dot.success {
  background: #1fa35b;
}
.dot.error {
  background: #e5484d;
}
.dot.skipped {
  background: #b8bec8;
}
.chain-scroll {
  overflow-x: auto;
  padding: 11px 2px 5px;
}
.chain {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: max-content;
}
.chain-node {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 112px;
  max-width: 148px;
  border: 1px solid #e8ebef;
  border-radius: 7px;
  background: #fbfcfd;
  padding: 7px 9px;
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease;
}
.chain-node:hover {
  border-color: #a9c2ff;
  background: #f7faff;
}
.chain-node.error {
  border-color: #f3c4c6;
  background: #fffafa;
}
.chain-node.skipped {
  opacity: 0.62;
}
.chain-node.reactive {
  border-left: 2px solid #b7ccff;
}
.chain-type {
  font-size: 9.5px;
  color: #8a9099;
}
.chain-name {
  width: 100%;
  font-size: 11px;
  color: #333b48;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chain-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 9.5px;
  color: #a3a9b3;
  font-variant-numeric: tabular-nums;
}
.chain-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #1fa35b;
}
.chain-node.error .chain-dot {
  background: #e5484d;
}
.chain-node.skipped .chain-dot {
  background: #b8bec8;
}
.chain-arrow {
  width: 12px;
  height: 1px;
  background: #d9dee6;
  position: relative;
  flex: 0 0 12px;
}
.chain-arrow::after {
  content: '';
  position: absolute;
  right: 0;
  top: -2px;
  border-left: 4px solid #d9dee6;
  border-top: 3px solid transparent;
  border-bottom: 3px solid transparent;
}
.timeline-panel {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 14px 15px;
}
.side-col {
  position: sticky;
  top: 14px;
}
.side-panel {
  background: #fff;
  border: 1px solid #e5e6eb;
  border-radius: 10px;
  padding: 8px 15px 15px;
}
.side-panel :deep(.n-tabs-pane-wrapper) {
  max-height: calc(100vh - 260px);
  overflow-y: auto;
  padding-right: 2px;
}
.kv-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0 4px;
}
.kv-item {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 11.5px;
}
.kv-key {
  flex: 0 0 60px;
  color: #9aa1ab;
}
.kv-val {
  flex: 1;
  min-width: 0;
  color: #333b48;
  word-break: break-all;
}
.kv-val.small {
  font-size: 10.5px;
  color: #5c6470;
}
.side-section {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f0f2f5;
}
.side-section.first {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 0;
}
.side-label {
  font-size: 10.5px;
  color: #9aa1ab;
  letter-spacing: 0.04em;
  margin-bottom: 7px;
}
.answer-preview {
  font-size: 11.5px;
  line-height: 1.7;
  color: #4b5563;
  background: #fafbfc;
  border: 1px solid #eef0f3;
  border-radius: 7px;
  padding: 9px 10px;
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.case-item {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-bottom: 6px;
}
.case-note {
  font-size: 11px;
  color: #5c6470;
  line-height: 1.5;
}
.prompt-box {
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  font-size: 10.5px;
  line-height: 1.7;
  color: #4b5563;
  background: #fafbfc;
  border: 1px solid #eef0f3;
  border-radius: 7px;
  padding: 9px 10px;
  max-height: 170px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.message-row {
  display: flex;
  gap: 7px;
  margin-bottom: 7px;
  align-items: flex-start;
}
.message-role {
  flex: 0 0 auto;
  font-size: 9.5px;
  color: #8a9099;
  background: #f2f4f7;
  border-radius: 3px;
  padding: 1px 4px;
  margin-top: 1px;
}
.message-role.user {
  color: #3f5f9e;
  background: #eef3ff;
}
.message-content {
  font-size: 11px;
  line-height: 1.6;
  color: #5c6470;
  max-height: 80px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.chunk-card {
  border: 1px solid #eef0f3;
  border-radius: 7px;
  padding: 8px 9px;
  margin-bottom: 7px;
  background: #fcfcfd;
}
.chunk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.chunk-source {
  font-size: 10px;
  color: #7a828e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chunk-score {
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  font-size: 9.5px;
  color: #1d7474;
  background: #edf8f8;
  border-radius: 3px;
  padding: 1px 4px;
}
.chunk-text {
  font-size: 10.5px;
  line-height: 1.6;
  color: #5c6470;
  max-height: 80px;
  overflow: auto;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.ability-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.ability-chip {
  font-size: 10px;
  padding: 3px 7px;
  border-radius: 4px;
  background: #f2f4f7;
  color: #5c6470;
}
.ability-chip.skill {
  background: #f7f1ff;
  color: #6b3fb8;
}
.ability-chip.tool {
  background: #f0f7f2;
  color: #22794a;
}
.exception-card {
  border: 1px solid #f4c9cc;
  background: #fffafa;
  border-radius: 7px;
  padding: 9px 10px;
  margin-bottom: 8px;
  cursor: pointer;
}
.exception-title {
  font-size: 11.5px;
  font-weight: 600;
  color: #a62a37;
  margin-bottom: 4px;
}
.exception-error {
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  font-size: 10.5px;
  line-height: 1.6;
  color: #7d2b33;
  word-break: break-word;
}
.exception-hint {
  margin-top: 5px;
  font-size: 10.5px;
  line-height: 1.6;
  color: #9a5a60;
}
.empty-side {
  text-align: center;
  padding: 24px 8px;
}
.empty-title {
  margin-top: 6px;
  font-size: 12px;
  color: #3b4351;
}
.empty-desc {
  margin-top: 3px;
  font-size: 10.5px;
  color: #9aa1ab;
}
.cost-total {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 10px 12px;
  background: #fafbfc;
  border: 1px solid #eef0f3;
  border-radius: 8px;
}
.cost-label {
  font-size: 11px;
  color: #7a828e;
}
.cost-value {
  font-size: 20px;
  font-weight: 650;
  color: #1f2329;
  font-variant-numeric: tabular-nums;
}
.token-breakdown {
  margin-top: 9px;
}
.token-row {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #5c6470;
  padding: 4px 0;
  border-bottom: 1px dashed #f4f5f7;
}
.token-row.sub {
  padding-left: 10px;
  color: #8a9099;
  font-size: 10.5px;
}
.cost-note {
  margin-top: 8px;
  font-size: 10px;
  line-height: 1.6;
  color: #a3a9b3;
}
.cost-span-row {
  display: flex;
  gap: 7px;
  align-items: center;
  padding: 4px 0;
  font-size: 10.5px;
  border-bottom: 1px dashed #f4f5f7;
}
.cost-span-name {
  flex: 1;
  min-width: 0;
  color: #5c6470;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cost-span-token {
  color: #8a9099;
  font-variant-numeric: tabular-nums;
}
.cost-span-cost {
  color: #3b4351;
  font-variant-numeric: tabular-nums;
}
.empty-line {
  padding: 14px 0;
  text-align: center;
  font-size: 10.5px;
  color: #a3a9b3;
}
.empty-page {
  padding: 80px 0;
  text-align: center;
}
.empty-page .empty-title {
  font-size: 14px;
  margin-bottom: 12px;
}
@media (max-width: 1180px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
  .side-col {
    position: static;
  }
  .side-panel :deep(.n-tabs-pane-wrapper) {
    max-height: none;
  }
}
@media (max-width: 720px) {
  .detail-top {
    flex-wrap: wrap;
  }
  .action-col {
    width: 100%;
  }
}
</style>
