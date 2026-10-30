<template>
  <div class="timeline">
    <div class="timeline-toolbar">
      <span class="timeline-hint">按执行顺序还原 ReAct / Plan / 工具与 Skill 全量内容</span>
      <div class="toolbar-actions">
        <n-button text size="tiny" @click="setAll(true)">全部展开</n-button>
        <span class="divider"></span>
        <n-button text size="tiny" @click="setAll(false)">全部收起</n-button>
      </div>
    </div>

    <div class="timeline-list">
      <div
        v-for="(span, index) in spans"
        :id="`span-${span.id}`"
        :key="span.id"
        class="timeline-row"
        :class="[`status-${span.status}`, { expanded: expanded.has(span.id) }]"
      >
        <div class="rail">
          <span class="rail-dot"></span>
          <span v-if="index < spans.length - 1" class="rail-line"></span>
        </div>

        <div class="node">
          <button class="node-head" type="button" @click="toggle(span.id)">
            <span class="node-icon"><n-icon size="15"><component :is="iconFor(span)" /></n-icon></span>
            <span class="node-main">
              <span class="node-title-row">
                <span class="node-name">{{ span.name }}</span>
                <span class="type-pill" :class="typeClass(span.span_type)">{{ typeLabel(span.span_type) }}</span>
                <span class="status-pill" :class="span.status">{{ statusLabel(span.status) }}</span>
                <span class="node-facts">
                  <span v-if="span.duration_ms" class="fact">{{ formatDuration(span.duration_ms) }}</span>
                  <span v-if="span.tokens && span.tokens.total" class="fact">{{ formatNumber(span.tokens.total) }} tok</span>
                  <span v-if="span.cost_cny" class="fact">¥{{ span.cost_cny.toFixed(4) }}</span>
                </span>
              </span>
              <span class="node-summary">{{ summary(span) }}</span>
            </span>
            <n-icon class="chev" size="16">
              <ChevronUpOutline v-if="expanded.has(span.id)" />
              <ChevronDownOutline v-else />
            </n-icon>
          </button>

          <div v-if="expanded.has(span.id)" class="node-body">
            <div v-if="span.error" class="error-panel">
              <div class="error-title">
                <n-icon size="14"><AlertCircleOutline /></n-icon>
                执行异常
              </div>
              <p class="error-text">{{ span.error }}</p>
              <p v-if="span.error_hint" class="error-hint">{{ span.error_hint }}</p>
            </div>

            <!-- Thought：推理 / 输出 / 工具决策 -->
            <template v-if="span.span_type === 'react.thought'">
              <div v-if="span.output?.reasoning" class="section">
                <div class="section-label">推理过程（Reasoning）</div>
                <div class="prose reasoning">{{ span.output.reasoning }}</div>
              </div>
              <div v-if="span.output?.content" class="section">
                <div class="section-label">模型输出（Content）</div>
                <div class="prose">{{ span.output.content }}</div>
              </div>
              <div v-if="span.output?.tool_calls?.length" class="section">
                <div class="section-label">工具决策（tool_calls）</div>
                <div v-for="call in span.output.tool_calls" :key="call.id" class="call-chip">
                  <span class="call-name">{{ call.name }}</span>
                  <span class="call-id">{{ call.id }}</span>
                  <code class="call-args">{{ JSON.stringify(call.args) }}</code>
                </div>
              </div>
              <div class="io-stack">
                <JsonBlock :value="span.input" label="本轮输入上下文" max-height="180px" />
                <JsonBlock :value="span.context" label="调用上下文" max-height="180px" />
              </div>
            </template>

            <!-- Action -->
            <template v-else-if="span.span_type === 'react.action'">
              <div class="action-row">
                <span class="action-label">决策</span>
                <span class="action-value">{{ span.output?.decision === 'execute' ? '调用能力' : span.output?.decision || '-' }}</span>
                <span class="action-label">目标</span>
                <span class="action-value mono">{{ span.input?.tool }}</span>
              </div>
              <JsonBlock :value="span.input?.args ?? span.input" label="调用参数" />
              <JsonBlock :value="span.output" label="动作结果" max-height="140px" />
            </template>

            <!-- Tool / Skill -->
            <template v-else-if="span.span_type === 'tool.call' || span.span_type === 'skill.call'">
              <div class="kv-row">
                <span class="kv"><b>类型</b>{{ span.span_type === 'skill.call' ? '内置 Skill' : '注册工具' }}</span>
                <span class="kv"><b>耗时</b>{{ formatDuration(span.duration_ms) }}</span>
                <span class="kv"><b>状态</b>{{ statusLabel(span.status) }}</span>
                <span v-if="span.metadata?.tool_type" class="kv"><b>接入方式</b>{{ span.metadata.tool_type }}</span>
              </div>
              <div class="io-stack">
                <JsonBlock :value="span.input" label="入参" max-height="220px" />
                <JsonBlock :value="span.output" label="返回结果（完整）" max-height="320px" />
              </div>
            </template>

            <!-- Observation -->
            <template v-else-if="span.span_type === 'react.observation'">
              <div class="prose observation">{{ span.output?.content || '（空）' }}</div>
            </template>

            <!-- Retrieval search -->
            <template v-else-if="span.span_type === 'retrieval.search'">
              <div v-if="span.output?.candidates?.length" class="candidates">
                <div class="section-label">召回候选（{{ span.output.candidates.length }}）</div>
                <div v-for="(c, i) in span.output.candidates.slice(0, 8)" :key="i" class="candidate">
                  <span class="score">{{ Number(c.score).toFixed(3) }}</span>
                  <div class="cand-main">
                    <div class="cand-meta">{{ c.source || '未命名文档' }}<span v-if="c.page"> · 第 {{ c.page }} 页</span></div>
                    <div class="cand-text">{{ c.content }}</div>
                  </div>
                </div>
              </div>
              <JsonBlock :value="span.input" label="检索参数" max-height="140px" />
            </template>

            <!-- Final / generic -->
            <template v-else>
              <div v-if="span.output?.content" class="section">
                <div class="section-label">输出内容</div>
                <div class="prose">{{ span.output.content }}</div>
              </div>
              <div class="io-stack">
                <JsonBlock :value="span.input" label="输入" max-height="260px" />
                <JsonBlock :value="span.output" label="输出（完整）" max-height="360px" />
              </div>
            </template>

            <div v-if="span.context && Object.keys(span.context).length && !['react.thought'].includes(span.span_type)" class="section">
              <JsonBlock :value="span.context" label="节点上下文" max-height="200px" />
            </div>

            <div v-if="span.code" class="code-entry">
              <button class="code-toggle" type="button" @click="toggleCode(span.id)">
                <n-icon size="14"><CodeSlashOutline /></n-icon>
                {{ codeOpen.has(span.id) ? '收起运行代码' : '查看内部运行代码' }}
                <span class="code-count">{{ span.code_explain?.length || 0 }} 段解释</span>
              </button>
              <CodeExplain
                v-if="codeOpen.has(span.id)"
                :code="span.code"
                :explain="span.code_explain"
                :language="span.code_key?.startsWith('build') ? 'python' : 'python'"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, markRaw } from 'vue'
import {
  AlertCircleOutline,
  AnalyticsOutline,
  BuildOutline,
  ChatbubbleEllipsesOutline,
  ChevronDownOutline,
  ChevronUpOutline,
  CodeSlashOutline,
  ConstructOutline,
  CubeOutline,
  DocumentTextOutline,
  FlashOutline,
  GitNetworkOutline,
  LayersOutline,
  SearchOutline,
  SparklesOutline,
  TerminalOutline
} from '@vicons/ionicons5'
import type { TraceSpan } from '@/api/types'
import JsonBlock from './JsonBlock.vue'
import CodeExplain from './CodeExplain.vue'

const props = defineProps<{ spans: TraceSpan[] }>()

const expanded = ref<Set<string>>(new Set())
const codeOpen = ref<Set<string>>(new Set())

const DEFAULT_OPEN = new Set([
  'react.plan',
  'react.thought',
  'react.action',
  'final.answer',
  'exception',
  'llm.call',
  'retrieval.embed',
  'retrieval.search',
  'retrieval.rerank'
])

watch(
  () => props.spans,
  spans => {
    const next = new Set<string>()
    for (const span of spans) {
      if (DEFAULT_OPEN.has(span.span_type)) next.add(span.id)
    }
    expanded.value = next
  },
  { immediate: true, deep: false }
)

function toggle(id: string) {
  const next = new Set(expanded.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expanded.value = next
}
function toggleCode(id: string) {
  const next = new Set(codeOpen.value)
  next.has(id) ? next.delete(id) : next.add(id)
  codeOpen.value = next
}
function setAll(open: boolean) {
  expanded.value = open ? new Set(props.spans.map(s => s.id)) : new Set()
}

const TYPE_LABELS: Record<string, string> = {
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

const ICONS: Record<string, any> = {
  'react.plan': markRaw(AnalyticsOutline),
  'react.thought': markRaw(SparklesOutline),
  'react.action': markRaw(FlashOutline),
  'tool.call': markRaw(ConstructOutline),
  'skill.call': markRaw(CubeOutline),
  'react.observation': markRaw(DocumentTextOutline),
  'retrieval.embed': markRaw(LayersOutline),
  'retrieval.search': markRaw(SearchOutline),
  'retrieval.rerank': markRaw(AnalyticsOutline),
  'context.assemble': markRaw(LayersOutline),
  'llm.call': markRaw(ChatbubbleEllipsesOutline),
  'flow.node': markRaw(GitNetworkOutline),
  'build.parse': markRaw(DocumentTextOutline),
  'build.chunk': markRaw(LayersOutline),
  'build.embed': markRaw(LayersOutline),
  'build.index': markRaw(BuildOutline),
  'final.answer': markRaw(TerminalOutline),
  exception: markRaw(AlertCircleOutline)
}

function iconFor(span: TraceSpan) {
  return ICONS[span.span_type] || markRaw(FlashOutline)
}
function typeLabel(type: string) {
  return TYPE_LABELS[type] || type
}
function typeClass(type: string) {
  if (type.startsWith('react')) return 'react'
  if (type === 'tool.call') return 'tool'
  if (type === 'skill.call') return 'skill'
  if (type.startsWith('retrieval') || type === 'context.assemble') return 'retrieval'
  if (type.startsWith('build')) return 'build'
  if (type === 'exception') return 'exception'
  return 'neutral'
}
function statusLabel(status: string) {
  return (
    { success: '成功', error: '失败', running: '运行中', skipped: '已跳过', degraded: '降级' }[status] ||
    status
  )
}
function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  return `${(ms / 60000).toFixed(1)}min`
}
function formatNumber(value: number) {
  return value >= 1000 ? value.toLocaleString() : String(value)
}
function summary(span: TraceSpan) {
  const out: any = span.output || {}
  if (span.error) return span.error.slice(0, 140)
  if (span.span_type === 'react.thought') {
    if (out.reasoning) return String(out.reasoning).slice(0, 160)
    if (out.content) return String(out.content).slice(0, 160)
    if (out.tool_calls?.length) return `决定调用 ${out.tool_calls.map((c: any) => c.name).join('、')}`
    return '模型推理完成'
  }
  if (span.span_type === 'react.action') return `→ ${span.input?.tool || ''}`
  if (span.span_type === 'tool.call' || span.span_type === 'skill.call') {
    const result = out.result ?? ''
    return String(result).replace(/\s+/g, ' ').slice(0, 160)
  }
  if (span.span_type === 'react.observation') return String(out.content || '').replace(/\s+/g, ' ').slice(0, 160)
  if (span.span_type === 'final.answer') return String(out.content || '').replace(/\s+/g, ' ').slice(0, 180)
  if (span.span_type === 'retrieval.search') return `召回 ${out.count ?? out.candidates?.length ?? 0} 条候选`
  if (span.span_type === 'retrieval.embed') return `${out.model || 'embedding'} · ${out.dim || 0} 维`
  if (span.span_type === 'retrieval.rerank') {
    if (span.status === 'skipped') return out.reason || '已跳过'
    return `保留 top-${out.kept ?? '-'}`
  }
  if (span.span_type === 'llm.call') return `${span.context?.model || span.context?.model_hint || 'LLM'} · ${String(out.content || '').slice(0, 120)}`
  if (span.span_type === 'flow.node') {
    const vars = out.variables || {}
    return `节点执行完成${out.result !== undefined ? ` · 分支 ${out.result}` : ''} · 变量 ${Object.keys(vars).length} 个`
  }
  if (span.span_type.startsWith('build.')) {
    if (out.count) return `${out.count} 个分块`
    if (out.chars) return `${out.chars} 字符`
    if (out.stored) return `${out.stored} 条向量入库`
    if (out.vectors) return `${out.vectors} 条向量 · ${out.dim} 维`
    if (out.model) return `${out.model} · ${out.batches || '-'} 批 · ${out.dim} 维`
  }
  return JSON.stringify(out).slice(0, 140)
}

function scrollTo(id: string) {
  const el = document.getElementById(`span-${id}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    expanded.value = new Set([...expanded.value, id])
  }
}

defineExpose({ scrollTo })
</script>

<style scoped>
.timeline-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2px 10px;
}
.timeline-hint {
  font-size: 11.5px;
  color: #8a9099;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #3370ff;
}
.divider {
  width: 1px;
  height: 10px;
  background: #e0e3e8;
}
.timeline-list {
  position: relative;
}
.timeline-row {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 10px;
  padding-bottom: 10px;
}
.rail {
  position: relative;
  display: flex;
  justify-content: center;
  padding-top: 17px;
}
.rail-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #c9ced6;
  box-shadow: 0 0 0 3px #fff;
  z-index: 1;
}
.status-success .rail-dot {
  background: #1fa35b;
}
.status-error .rail-dot {
  background: #e5484d;
  box-shadow: 0 0 0 3px #fff, 0 0 0 5px #ffe9ea;
}
.status-skipped .rail-dot {
  background: #b8bec8;
}
.status-degraded .rail-dot {
  background: #e39a19;
}
.rail-line {
  position: absolute;
  top: 24px;
  bottom: -10px;
  width: 1px;
  background: #e6e9ee;
}
.node {
  border: 1px solid #e7e9ee;
  border-radius: 9px;
  background: #fff;
  overflow: hidden;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}
.timeline-row.expanded .node {
  border-color: #d9e2f6;
  box-shadow: 0 2px 10px rgba(31, 42, 68, 0.04);
}
.status-error .node {
  border-color: #f3c4c6;
}
.node-head {
  display: flex;
  gap: 10px;
  width: 100%;
  padding: 11px 13px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  align-items: flex-start;
}
.node-head:hover {
  background: #fafbfc;
}
.node-icon {
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f2f5fb;
  color: #4b6db3;
  margin-top: 1px;
}
.status-error .node-icon {
  background: #fff0f0;
  color: #d22d3d;
}
.node-main {
  min-width: 0;
  flex: 1;
}
.node-title-row {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.node-name {
  font-size: 13px;
  font-weight: 600;
  color: #222a36;
}
.type-pill {
  font-size: 10px;
  line-height: 1;
  padding: 3px 6px;
  border-radius: 4px;
  background: #f1f3f6;
  color: #5f6b7c;
}
.type-pill.react {
  background: #eef3ff;
  color: #2f5fd0;
}
.type-pill.tool {
  background: #f0f7f2;
  color: #22794a;
}
.type-pill.skill {
  background: #f7f1ff;
  color: #6b3fb8;
}
.type-pill.retrieval {
  background: #eef8f8;
  color: #1d7474;
}
.type-pill.build {
  background: #fff6e9;
  color: #9a5b00;
}
.type-pill.exception {
  background: #fff0f0;
  color: #c22d3d;
}
.status-pill {
  font-size: 10px;
  padding: 2px 5px;
  border-radius: 4px;
  line-height: 1.4;
}
.status-pill.success {
  color: #1c7d4d;
  background: #eaf7ef;
}
.status-pill.error {
  color: #c22d3d;
  background: #ffeff1;
}
.status-pill.skipped {
  color: #7a828e;
  background: #f2f3f5;
}
.status-pill.degraded {
  color: #96600a;
  background: #fff6e6;
}
.node-facts {
  display: flex;
  gap: 9px;
  margin-left: auto;
  padding-left: 8px;
  flex-wrap: wrap;
}
.fact {
  font-size: 10.5px;
  color: #8a9099;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.node-summary {
  display: block;
  margin-top: 3px;
  font-size: 11.5px;
  color: #7a828e;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chev {
  color: #a7adb6;
  margin-top: 4px;
}
.node-body {
  border-top: 1px solid #f0f2f5;
  padding: 13px;
  background: #fcfcfd;
}
.section {
  margin-bottom: 11px;
}
.section-label {
  font-size: 10.5px;
  color: #8a9099;
  letter-spacing: 0.04em;
  margin-bottom: 5px;
}
.prose {
  font-size: 12.5px;
  line-height: 1.75;
  color: #333b48;
  background: #fff;
  border: 1px solid #eceef2;
  border-radius: 7px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.prose.reasoning {
  background: #f7f9ff;
  border-color: #e3ebff;
  color: #35456a;
}
.prose.observation {
  background: #f7f9f8;
  border-color: #e6efea;
}
.error-panel {
  border: 1px solid #f4c9cc;
  background: #fff7f7;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.error-title {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #c22d3d;
  font-size: 12px;
  font-weight: 600;
}
.error-text {
  margin: 6px 0 4px;
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.65;
  color: #7d2b33;
  white-space: pre-wrap;
  word-break: break-word;
}
.error-hint {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: #9a5a60;
}
.io-stack {
  display: grid;
  gap: 9px;
}
.io-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}
.call-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  border: 1px solid #ececfb;
  background: #faf9ff;
  border-radius: 7px;
  padding: 7px 9px;
  margin-bottom: 6px;
}
.call-name {
  font-size: 11.5px;
  font-weight: 600;
  color: #5b3bb5;
}
.call-id {
  font-size: 9.5px;
  color: #9a92b5;
}
.call-args {
  font-size: 10.5px;
  color: #5f5a70;
  background: transparent;
  word-break: break-all;
}
.action-row {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.action-label {
  font-size: 10.5px;
  color: #8a9099;
}
.action-value {
  font-size: 12px;
  color: #2b3442;
}
.action-value.mono {
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  background: #f3f5f8;
  padding: 2px 6px;
  border-radius: 4px;
}
.kv-row {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 9px;
}
.kv {
  font-size: 11px;
  color: #667085;
}
.kv b {
  color: #98a0ac;
  font-weight: 400;
  margin-right: 4px;
}
.candidates {
  margin-bottom: 10px;
}
.candidate {
  display: flex;
  gap: 9px;
  padding: 8px 0;
  border-bottom: 1px dashed #eceef2;
}
.candidate:last-child {
  border-bottom: 0;
}
.score {
  flex: 0 0 42px;
  font-family: 'SFMono-Regular', ui-monospace, Menlo, Consolas, monospace;
  font-size: 11px;
  color: #1d7474;
  background: #edf8f8;
  border-radius: 4px;
  height: 20px;
  line-height: 20px;
  text-align: center;
}
.cand-main {
  min-width: 0;
}
.cand-meta {
  font-size: 10.5px;
  color: #8a9099;
  margin-bottom: 2px;
}
.cand-text {
  font-size: 11.5px;
  line-height: 1.6;
  color: #4b5563;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.code-entry {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e6e9ee;
}
.code-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid #dfe5ef;
  background: #fff;
  color: #3f5f9e;
  border-radius: 6px;
  padding: 6px 9px;
  font-size: 11.5px;
  cursor: pointer;
}
.code-toggle:hover {
  border-color: #adc3f0;
  background: #f8faff;
}
.code-count {
  color: #98a0ac;
  font-size: 10.5px;
}
@media (max-width: 760px) {
  .node-facts {
    display: none;
  }
  .io-grid {
    grid-template-columns: 1fr;
  }
}
</style>
