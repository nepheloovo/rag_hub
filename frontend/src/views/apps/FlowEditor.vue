<template>
  <div class="flow-editor">
    <!-- 左侧节点面板 -->
    <div class="palette">
      <div class="palette-title">节点</div>
      <div
        v-for="t in nodeTypes"
        :key="t.type"
        class="palette-item"
        @click="addNode(t.type)"
      >
        <n-icon :color="t.color" size="16"><component :is="t.icon" /></n-icon>
        <span>{{ t.label }}</span>
      </div>
      <n-divider />
      <div class="palette-tip">
        使用说明：点击节点添加到画布；拖动节点调整位置；点击节点右侧圆点后再点击另一节点左侧圆点建立连线；点击连线可删除；条件节点有「是/否」两个出口。
      </div>
    </div>

    <!-- 画布 -->
    <div class="canvas-wrap" ref="canvasWrapRef">
      <div class="canvas-toolbar">
        <n-space :size="10">
          <n-button size="small" type="primary" :loading="saving" @click="saveFlow">
            保存编排
          </n-button>
          <n-dropdown trigger="click" :options="versionOptions" @select="onVersionSelect">
            <n-button size="small" quaternary>版本历史 (v{{ appVersion }})</n-button>
          </n-dropdown>
          <n-button size="small" quaternary type="error" @click="clearFlow">清空</n-button>
        </n-space>
        <span class="canvas-hint">{{ problems.length ? '⚠ ' + problems.join('；') : '编排校验通过' }}</span>
      </div>

      <div class="canvas" @mousedown.self="deselectNode">
        <!-- 连线层 -->
        <svg class="edge-layer" width="100%" height="100%">
          <path
            v-for="e in flow.edges"
            :key="e.id"
            :d="edgePath(e)"
            :stroke="selectedEdgeId === e.id ? '#3370ff' : '#b9c3d8'"
            stroke-width="2"
            fill="none"
            class="edge"
            @mousedown.stop="selectEdge(e)"
          />
          <path v-if="draftEdge" :d="draftEdge" stroke="#3370ff" stroke-width="2" stroke-dasharray="6 4" fill="none" />
        </svg>

        <!-- 节点层 -->
        <div
          v-for="n in flow.nodes"
          :key="n.id"
          class="flow-node"
          :class="{ selected: selectedNodeId === n.id, [n.type]: true }"
          :style="{ left: n.position.x + 'px', top: n.position.y + 'px' }"
          @mousedown.stop="startDrag($event, n)"
          @mouseup="endDrag"
          @click="onNodeClick(n)"
        >
          <div class="node-title">
            <n-icon size="14" :color="typeMeta[n.type]?.color"><component :is="typeMeta[n.type]?.icon" /></n-icon>
            <span>{{ typeMeta[n.type]?.label }}</span>
          </div>
          <div class="node-summary">{{ nodeSummary(n) }}</div>
          <!-- 输入端口 -->
          <div v-if="n.type !== 'start'" class="port port-in" title="输入" @mousedown.stop="onPortClick(n.id, 'in')" />
          <!-- 输出端口 -->
          <template v-if="n.type === 'condition'">
            <div class="port port-out port-true" title="是" @mousedown.stop="onPortClick(n.id, 'true')">是</div>
            <div class="port port-out port-false" title="否" @mousedown.stop="onPortClick(n.id, 'false')">否</div>
          </template>
          <div v-else-if="n.type !== 'answer'" class="port port-out" title="输出" @mousedown.stop="onPortClick(n.id, 'out')" />
        </div>
      </div>
    </div>

    <!-- 节点配置抽屉 -->
    <n-drawer
      v-model:show="showConfig"
      :width="380"
      placement="right"
      :title="`节点配置 · ${selectedNode ? typeMeta[selectedNode.type]?.label : ''}`"
    >
      <div v-if="selectedNode">
        <template v-if="selectedNode.type === 'start'">
          <n-alert type="info" :bordered="false">
            <span>用户输入通过变量 </span><code v-text="'{{input}}'"></code><span> 传入流程。</span>
          </n-alert>
        </template>

        <n-form v-if="selectedNode.type === 'retrieval'" label-placement="top">
          <n-form-item label="绑定知识库">
            <n-select v-model:value="cfg.kb_ids" multiple :options="kbOptions" placeholder="可多选" />
          </n-form-item>
          <n-form-item label="检索数量 top_k">
            <n-input-number v-model:value="cfg.top_k" :min="1" :max="20" style="width: 100%" />
          </n-form-item>
          <n-form-item label="输出变量名">
            <n-input v-model:value="cfg.output_var" placeholder="默认：{{selectedNode.id}}_output" />
          </n-form-item>
        </n-form>

        <n-form v-if="selectedNode.type === 'llm'" label-placement="top">
          <n-form-item label="模型">
            <n-select v-model:value="cfg.llm_ref" :options="llmOptions" placeholder="跟随全局默认" clearable />
          </n-form-item>
          <n-form-item label="系统提示词">
            <n-input v-model:value="cfg.system_prompt" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="支持 {{变量}} 插值" />
          </n-form-item>
          <n-form-item label="用户提示词">
            <n-input v-model:value="cfg.user_prompt" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="默认 {{input}}；可引用上游变量如 {{检索节点}}_output" />
          </n-form-item>
          <n-form-item label="温度">
            <n-slider v-model:value="cfg.temperature" :min="0" :max="2" :step="0.1" />
          </n-form-item>
          <n-form-item label="输出变量名">
            <n-input v-model:value="cfg.output_var" placeholder="默认：{{selectedNode.id}}_output" />
          </n-form-item>
        </n-form>

        <n-form v-if="selectedNode.type === 'tool'" label-placement="top">
          <n-form-item label="引用注册工具">
            <n-select
              v-model:value="cfg.tool_ref"
              :options="toolOptions"
              placeholder="不选则使用下方内联 HTTP 配置"
              clearable
            />
            <div class="field-hint">在「工具」页注册的工具可被复用并统计调用量</div>
          </n-form-item>
          <template v-if="!cfg.tool_ref">
            <n-form-item label="URL（支持 {{变量}}）">
              <n-input v-model:value="cfg.url" placeholder="https://api.example.com/order?q={{input}}" />
            </n-form-item>
            <n-form-item label="方法">
              <n-select v-model:value="cfg.method" :options="['GET', 'POST', 'PUT'].map(m => ({ label: m, value: m }))" />
            </n-form-item>
            <n-form-item label="Headers（JSON 对象）">
              <n-input v-model:value="cfg.headers_json" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder='{"Authorization": "Bearer xxx"}' />
            </n-form-item>
            <n-form-item label="Body（支持 {{变量}}）">
              <n-input v-model:value="cfg.body" type="textarea" :autosize="{ minRows: 3, maxRows: 5 }" placeholder='{"order_id": "{{input}}"}' />
            </n-form-item>
          </template>
          <n-form-item label="输出变量名">
            <n-input v-model:value="cfg.output_var" placeholder="默认：{{selectedNode.id}}_output" />
          </n-form-item>
        </n-form>

        <n-form v-if="selectedNode.type === 'condition'" label-placement="top">
          <n-form-item label="判断内容（支持 {{变量}}）">
            <n-input v-model:value="cfg.left" placeholder="如 {{output}}" />
          </n-form-item>
          <n-form-item label="条件">
            <n-select v-model:value="cfg.op" :options="opOptions" />
          </n-form-item>
          <n-form-item v-if="['contains', 'not_contains', 'equals'].includes(cfg.op)" label="关键字">
            <n-input v-model:value="cfg.value" placeholder="匹配关键字" />
          </n-form-item>
        </n-form>

        <n-form v-if="selectedNode.type === 'answer'" label-placement="top">
          <n-form-item label="输出内容（支持 {{变量}}）">
            <n-input v-model:value="cfg.content" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }" placeholder="最终回复内容，如：{{output}}" />
          </n-form-item>
        </n-form>

        <div style="margin-top: 16px; display: flex; justify-content: space-between">
          <n-button size="small" type="error" quaternary @click="deleteNode">删除节点</n-button>
          <n-button size="small" type="primary" @click="applyConfig">应用配置</n-button>
        </div>
      </div>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, markRaw, reactive } from 'vue'
import { useMessage } from 'naive-ui'
import {
  PlayOutline,
  FolderOpenOutline,
  SparklesOutline,
  ConstructOutline,
  GitBranchOutline,
  CheckmarkCircleOutline
} from '@vicons/ionicons5'
import { api, getApp, listKbs, listProviders, listTools, updateApp } from '@/api'
import type { Application, KnowledgeBase, Provider } from '@/api/types'

const props = defineProps<{ appId: string }>()
const message = useMessage()

const nodeTypes = [
  { type: 'start', label: '开始', color: '#22c55e', icon: markRaw(PlayOutline) },
  { type: 'retrieval', label: '知识库检索', color: '#3370ff', icon: markRaw(FolderOpenOutline) },
  { type: 'llm', label: 'LLM 生成', color: '#8b5cf6', icon: markRaw(SparklesOutline) },
  { type: 'tool', label: 'HTTP 工具', color: '#0ea5e9', icon: markRaw(ConstructOutline) },
  { type: 'condition', label: '条件分支', color: '#f59e0b', icon: markRaw(GitBranchOutline) },
  { type: 'answer', label: '结束输出', color: '#ef4444', icon: markRaw(CheckmarkCircleOutline) }
]
const typeMeta = Object.fromEntries(nodeTypes.map(t => [t.type, t]))

interface FlowNode { id: string; type: string; data: Record<string, any>; position: { x: number; y: number } }
interface FlowEdge { id: string; source: string; target: string; source_handle?: string }

const flow = reactive<{ nodes: FlowNode[]; edges: FlowEdge[] }>({ nodes: [], edges: [] })
const appVersion = ref(1)
const versions = ref<number[]>([])
const selectedNodeId = ref<string | null>(null)
const selectedEdgeId = ref<string | null>(null)
const showConfig = ref(false)
const saving = ref(false)
const connectingFrom = ref<{ nodeId: string; handle: string } | null>(null)
const draftEdge = ref('')
const canvasWrapRef = ref<HTMLElement | null>(null)

const kbs = ref<KnowledgeBase[]>([])
const providers = ref<Provider[]>([])
const tools = ref<any[]>([])
const kbOptions = computed(() => kbs.value.map(k => ({ label: k.name, value: k.id })))
const toolOptions = computed(() => tools.value.map(t => ({ label: `${t.name}（${t.tool_type === 'system' ? '系统内置' : 'HTTP'}）`, value: t.id })))
const llmOptions = computed(() =>
  providers.value
    .filter(p => p.enabled)
    .flatMap(p => p.models.llm.map(m => ({ label: `${p.name} · ${m}`, value: `${p.id}:${m}` })))
)
const opOptions = [
  { label: '包含关键字', value: 'contains' },
  { label: '不包含关键字', value: 'not_contains' },
  { label: '等于', value: 'equals' },
  { label: '内容为空', value: 'is_empty' },
  { label: '内容不为空', value: 'not_empty' }
]

const selectedNode = computed(() => flow.nodes.find(n => n.id === selectedNodeId.value) || null)
const problems = computed(() => {
  const p: string[] = []
  if (!flow.nodes.length) p.push('流程为空')
  else {
    if (!flow.nodes.some(n => n.type === 'start')) p.push('缺少开始节点')
    if (!flow.nodes.some(n => ['answer', 'llm', 'tool'].includes(n.type))) p.push('缺少输出节点')
    flow.edges.forEach(e => {
      const ok = flow.nodes.some(n => n.id === e.source) && flow.nodes.some(n => n.id === e.target)
      if (!ok) p.push('存在无效连线')
    })
  }
  return p
})

const cfg = reactive<Record<string, any>>({})

const versionOptions = computed(() => {
  const opts = versions.value.map(v => ({ label: `版本 v${v}${v === appVersion.value ? '（当前）' : ''}`, key: String(v) }))
  return opts.length ? opts : [{ label: '暂无历史版本', key: '__none', disabled: true }]
})

function nodeSummary(n: FlowNode): string {
  const d = n.data || {}
  switch (n.type) {
    case 'start': return '用户输入 → {{input}}'
    case 'retrieval': return `知识库 ${(d.kb_ids || []).length} 个 · top${d.top_k || 5}`
    case 'llm': return (d.system_prompt || '').slice(0, 24) || '系统提示词未配置'
    case 'tool': {
      const refName = tools.value.find(t => t.id === d.tool_ref)?.name
      return refName ? `调用工具：${refName}` : `${d.method || 'GET'} ${(d.url || '').slice(0, 28) || 'URL 未配置'}`
    }
    case 'condition': return `${d.left || '{{output}}'} ${d.op || 'not_empty'} ${d.value || ''}`
    case 'answer': return (d.content || '').slice(0, 28) || '输出内容未配置'
    default: return ''
  }
}

function newNode(type: string, x?: number, y?: number): FlowNode {
  const count = flow.nodes.length
  const pos = { x: x ?? 60 + (count % 4) * 240, y: y ?? 40 + Math.floor(count / 4) * 160 }
  const data: Record<string, any> = {}
  if (type === 'retrieval') data.kb_ids = []
  if (type === 'retrieval') data.top_k = 5
  if (type === 'llm') { data.system_prompt = ''; data.user_prompt = '{{input}}'; data.temperature = 0.2 }
  if (type === 'tool') { data.tool_ref = null; data.method = 'GET'; data.url = ''; data.headers_json = ''; data.body = '' }
  if (type === 'condition') { data.left = '{{output}}'; data.op = 'contains'; data.value = '' }
  if (type === 'answer') data.content = '{{output}}'
  return { id: 'n' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), type, data, position: pos }
}

function addNode(type: string) {
  flow.nodes.push(newNode(type))
  message.success(`已添加「${typeMeta[type].label}」节点`)
}

function selectNode(n: FlowNode) {
  selectedNodeId.value = n.id
  showConfig.value = true
  Object.keys(cfg).forEach(k => delete cfg[k])
  Object.assign(cfg, JSON.parse(JSON.stringify(n.data || {})))
  if (n.type === 'tool' && cfg.headers_json === undefined) cfg.headers_json = ''
}

function deselectNode() {
  selectedNodeId.value = null
  selectedEdgeId.value = null
}

function applyConfig() {
  if (!selectedNode.value) return
  const n = selectedNode.value
  n.data = { ...JSON.parse(JSON.stringify(cfg)) }
  showConfig.value = false
  message.success('节点配置已更新')
}

function deleteNode() {
  if (!selectedNodeId.value) return
  flow.nodes = flow.nodes.filter(n => n.id !== selectedNodeId.value)
  flow.edges = flow.edges.filter(e => e.source !== selectedNodeId.value && e.target !== selectedNodeId.value)
  showConfig.value = false
  selectedNodeId.value = null
}

// ---------- 拖拽 ----------
let dragState: { nodeId: string; offsetX: number; offsetY: number } | null = null
let dragMoved = false

function startDrag(e: MouseEvent, n: FlowNode) {
  if ((e.target as HTMLElement).closest('.port')) return
  dragState = { nodeId: n.id, offsetX: e.offsetX, offsetY: e.offsetY }
  dragMoved = false
  window.addEventListener('mousemove', onDragMove)
}

function onDragMove(e: MouseEvent) {
  if (!dragState || !canvasWrapRef.value) return
  const n = flow.nodes.find(x => x.id === dragState!.nodeId)
  if (!n) return
  const rect = canvasWrapRef.value.querySelector('.canvas')!.getBoundingClientRect()
  const nx = Math.max(0, e.clientX - rect.left - dragState.offsetX)
  const ny = Math.max(0, e.clientY - rect.top - dragState.offsetY)
  if (Math.abs(nx - n.position.x) > 2 || Math.abs(ny - n.position.y) > 2) dragMoved = true
  n.position.x = nx
  n.position.y = ny
}

function endDrag() {
  dragState = null
  window.removeEventListener('mousemove', onDragMove)
}

function onNodeClick(n: FlowNode) {
  if (dragMoved) return // 拖拽结束不打开配置
  selectNode(n)
}

// ---------- 连线 ----------
const PORT_SIZE = 12
const NODE_W = 190

function portPos(nodeId: string, handle: string): { x: number; y: number } {
  const n = flow.nodes.find(x => x.id === nodeId)
  if (!n) return { x: 0, y: 0 }
  const y = n.position.y + 44
  if (handle === 'in') return { x: n.position.x, y }
  if (handle === 'true') return { x: n.position.x + NODE_W, y: n.position.y + 34 }
  if (handle === 'false') return { x: n.position.x + NODE_W, y: n.position.y + 58 }
  return { x: n.position.x + NODE_W, y }
}

function edgePath(e: FlowEdge): string {
  const from = portPos(e.source, e.source_handle === 'true' ? 'true' : e.source_handle === 'false' ? 'false' : 'out')
  const to = portPos(e.target, 'in')
  const dx = Math.max(50, Math.abs(to.x - from.x) / 2)
  return `M ${from.x} ${from.y} C ${from.x + dx} ${from.y}, ${to.x - dx} ${to.y}, ${to.x} ${to.y}`
}

function onPortClick(nodeId: string, handle: string) {
  if (!connectingFrom.value) {
    if (handle === 'in') {
      message.warning('请先点击上游节点的输出端口')
      return
    }
    connectingFrom.value = { nodeId, handle }
    message.info('已选择输出端口，请点击另一节点的输入端口')
    const wrap = canvasWrapRef.value
    if (wrap) {
      const onMove = (ev: MouseEvent) => {
        const from = portPos(connectingFrom.value!.nodeId, connectingFrom.value!.handle)
        const rect = wrap.querySelector('.canvas')!.getBoundingClientRect()
        draftEdge.value = `M ${from.x} ${from.y} L ${ev.clientX - rect.left} ${ev.clientY - rect.top}`
      }
      const onUp = () => {
        wrap.removeEventListener('mousemove', onMove)
        window.removeEventListener('mouseup', onUp)
        draftEdge.value = ''
        connectingFrom.value = null
      }
      wrap.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
    }
    return
  }
  if (handle !== 'in') return
  const src = connectingFrom.value
  connectingFrom.value = null
  draftEdge.value = ''
  // 替换同一出口的旧连线
  flow.edges = flow.edges.filter(e => !(e.source === src.nodeId && (e.source_handle || 'out') === (src.handle === 'out' ? undefined : src.handle)))
  flow.edges.push({
    id: 'e' + Date.now().toString(36),
    source: src.nodeId,
    target: nodeId,
    source_handle: src.handle === 'out' ? undefined : src.handle
  })
  message.success('连线已建立')
}

function selectEdge(e: FlowEdge) {
  selectedEdgeId.value = e.id
  selectedNodeId.value = null
  // 点击连线即删除（第二次点击确认更稳，但保持简单：直接删除）
  flow.edges = flow.edges.filter(x => x.id !== e.id)
  message.success('连线已删除')
  selectedEdgeId.value = null
}

// ---------- 保存与版本 ----------
async function load() {
  try {
    const [app, kbList, pvList] = await Promise.all([getApp(props.appId), listKbs(), listProviders()])
    kbs.value = kbList
    tools.value = await listTools().catch(() => [])
    providers.value = pvList
    appVersion.value = app.version
    if (app.flow?.nodes) {
      flow.nodes = JSON.parse(JSON.stringify(app.flow.nodes))
      flow.edges = JSON.parse(JSON.stringify(app.flow.edges || []))
    } else if (!flow.nodes.length) {
      flow.nodes.push(newNode('start', 60, 60))
    }
    const vs = await api(`/apps/${props.appId}/versions`)
    versions.value = vs.versions || []
  } catch (e: any) {
    message.error(e.message)
  }
}

async function saveFlow() {
  if (problems.value.length) {
    message.warning('编排未通过校验：' + problems.value.join('；'))
  }
  saving.value = true
  try {
    const updated = await updateApp(props.appId, { flow: { nodes: flow.nodes, edges: flow.edges } })
    appVersion.value = updated.version
    const vs = await api(`/apps/${props.appId}/versions`)
    versions.value = vs.versions || []
    message.success('编排已保存（版本 +1）')
  } catch (e: any) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}

async function onVersionSelect(key: string) {
  if (key === '__none') return
  try {
    
    const restored = await api(`/apps/${props.appId}/restore`, { method: 'POST', body: JSON.stringify({ version: Number(key) }) })
    flow.nodes = JSON.parse(JSON.stringify(restored.flow?.nodes || []))
    flow.edges = JSON.parse(JSON.stringify(restored.flow?.edges || []))
    appVersion.value = restored.version
    message.success(`已恢复到版本 v${key}`)
  } catch (e: any) {
    message.error(e.message)
  }
}

function clearFlow() {
  flow.nodes = []
  flow.edges = []
  selectedNodeId.value = null
  message.info('已清空画布')
}

onMounted(load)
</script>

<style scoped>
.flow-editor {
  display: flex;
  height: calc(100vh - 280px);
  min-height: 460px;
  border: 1px solid #e8ebf2;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}

.palette {
  width: 170px;
  border-right: 1px solid #f0f1f3;
  padding: 14px 10px;
  flex-shrink: 0;
  overflow-y: auto;
}

.palette-title {
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
  margin-bottom: 10px;
}

.palette-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #1f2329;
  transition: all 0.15s;
}

.palette-item:hover {
  border-color: #3370ff;
  background: #f0f5ff;
}

.palette-tip {
  font-size: 11px;
  color: #a8adb5;
  line-height: 1.7;
}

.canvas-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.canvas-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #f0f1f3;
}

.canvas-hint {
  font-size: 12px;
  color: #f59e0b;
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.canvas {
  flex: 1;
  position: relative;
  overflow: auto;
  background:
    radial-gradient(circle, #d8dde6 1px, transparent 1px) 0 0 / 20px 20px;
  min-height: 300px;
}

.edge-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  width: 100%;
  height: 100%;
}

.edge {
  pointer-events: stroke;
  cursor: pointer;
}

.flow-node {
  position: absolute;
  width: 190px;
  min-height: 62px;
  background: #fff;
  border: 1.5px solid #d8dde6;
  border-radius: 10px;
  padding: 8px 10px;
  cursor: grab;
  user-select: none;
  box-shadow: 0 1px 4px rgba(31, 35, 41, 0.06);
}

.flow-node.selected {
  border-color: #3370ff;
  box-shadow: 0 0 0 2px rgba(51, 112, 255, 0.15);
}

.node-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2329;
}

.node-summary {
  margin-top: 5px;
  font-size: 11px;
  color: #8f959e;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.port {
  position: absolute;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #3370ff;
  cursor: crosshair;
  z-index: 2;
}

.port-in {
  left: -7px;
  top: 32px;
}

.port-out {
  right: -7px;
  top: 32px;
}

.port-true,
.port-false {
  width: 24px;
  height: 16px;
  border-radius: 8px;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  border: none;
}

.port-true {
  right: -13px;
  top: 24px;
  background: #22c55e;
}

.port-false {
  right: -13px;
  top: 48px;
  background: #f59e0b;
}
</style>
