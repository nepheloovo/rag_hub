<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">工具与模型</h2>
        <p class="page-desc">统一管理应用可用的模型和工具。工具一次接入，所有 Chat Flow 与 Agent 都能复用。</p>
      </div>
      <n-button type="primary" @click="showCreate = true">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        新建工具
      </n-button>
    </div>

    <n-card size="small">
      <n-tabs v-model:value="activeTab" type="line">
        <n-tab-pane name="tools" tab="工具库">
          <n-data-table :columns="columns" :data="tools" :bordered="false" :loading="loading" :row-key="(r: ToolItem) => r.id" />
        </n-tab-pane>
        <n-tab-pane name="mcp" tab="MCP 服务">
          <n-empty description="MCP 服务接入规划中（后续版本）" style="padding: 48px 0" />
        </n-tab-pane>
        <n-tab-pane name="models" tab="模型">
          <div style="max-width: 640px; margin-top: 12px">
            <n-alert type="info" :bordered="false">
              模型按用途分组规划中。当前可在
              <n-button text type="primary" size="small" @click="$router.push('/app/models')">模型配置</n-button>
              中管理服务商与 embedding / Rerank / LLM 模型。
            </n-alert>
          </div>
        </n-tab-pane>
      </n-tabs>
    </n-card>

    <!-- 新建工具 -->
    <n-modal v-model:show="showCreate" preset="card" title="新建工具" style="width: 560px" :mask-closable="false">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="名称" required>
          <n-input v-model:value="form.name" placeholder="如：订单查询" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" placeholder="工具用途说明（Agent 规划时参考）" />
        </n-form-item>
        <n-form-item label="接入方式">
          <n-select
            v-model:value="form.tool_type"
            :options="[{ label: 'HTTP 接口', value: 'http' }]"
          />
        </n-form-item>
        <n-form-item label="URL">
          <n-input v-model:value="form.config.url" placeholder="https://api.example.com/order?q={{input}}" />
        </n-form-item>
        <n-form-item label="方法">
          <n-select v-model:value="form.config.method" :options="['GET', 'POST', 'PUT'].map(m => ({ label: m, value: m }))" style="width: 160px" />
        </n-form-item>
        <n-form-item label="Headers">
          <n-input v-model:value="form.headersText" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" placeholder='JSON 对象，如 {"Authorization": "Bearer xxx"}' />
        </n-form-item>
        <n-form-item label="Body">
          <n-input v-model:value="form.config.body" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" placeholder='支持 {{变量}} 插值' />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="showCreate = false">取消</n-button>
          <n-button type="primary" :disabled="!form.name.trim() || !form.config.url.trim()" :loading="creating" @click="doCreate">
            创建
          </n-button>
        </div>
      </template>
    </n-modal>

    <!-- 试运行 -->
    <n-modal v-model:show="showTest" preset="card" title="试运行工具" style="width: 560px">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="输入">
          <n-input v-model:value="testInput" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="作为 {{input}} 变量传入" />
        </n-form-item>
      </n-form>
      <n-button type="primary" :loading="testing" @click="doTest">运行</n-button>
      <div v-if="testResult !== null" class="test-result">
        <div class="test-result-label">返回结果</div>
        <n-scrollbar style="max-height: 200px">
          <pre class="test-result-body">{{ testResult }}</pre>
        </n-scrollbar>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted, reactive } from 'vue'
import { useMessage, useDialog, NTag, NButton } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import { createTool, deleteTool, listTools, testTool } from '@/api'
import type { ToolItem } from '@/api/types'

const message = useMessage()
const dialog = useDialog()
const tools = ref<ToolItem[]>([])
const loading = ref(false)
const activeTab = ref('tools')
const showCreate = ref(false)
const creating = ref(false)
const showTest = ref(false)
const testing = ref(false)
const testInput = ref('测试输入')
const testResult = ref<string | null>(null)
const testingId = ref<string | null>(null)

const typeLabel: Record<string, string> = { http: 'HTTP', mcp: 'MCP', plugin: '工作流插件', system: '系统内置' }
const typeColor: Record<string, string> = { http: '#3370ff', mcp: '#8b5cf6', plugin: '#f59e0b', system: '#22c55e' }

const form = reactive({
  name: '',
  description: '',
  tool_type: 'http',
  headersText: '',
  config: { url: '', method: 'GET', body: '' } as Record<string, any>
})

const columns = [
  { title: '名称', key: 'name', width: 180 },
  {
    title: '类型',
    key: 'tool_type',
    width: 110,
    render: (row: ToolItem) =>
      h(NTag, { size: 'small', bordered: false, color: { color: typeLabel[row.tool_type] === '系统内置' ? '#ecfdf3' : '#eef3ff', textColor: typeColor[row.tool_type] } }, { default: () => typeLabel[row.tool_type] || row.tool_type })
  },
  { title: '描述', key: 'description', ellipsis: { tooltip: true } },
  {
    title: '状态',
    key: 'status',
    width: 90,
    render: (row: ToolItem) =>
      row.status === 'beta'
        ? h(NTag, { size: 'small', type: 'warning', bordered: false }, { default: () => 'Beta' })
        : h(NTag, { size: 'small', type: 'success', bordered: false }, { default: () => '可用' })
  },
  {
    title: '近 7 天调用',
    key: 'call_count',
    width: 110,
    render: (row: ToolItem) => h('span', { style: 'font-variant-numeric: tabular-nums' }, (row.call_count || 0).toLocaleString())
  },
  {
    title: '被应用使用',
    key: 'used_by_apps',
    width: 200,
    render: (row: ToolItem) => (row.used_by_apps?.length ? row.used_by_apps.join('、') : '—')
  },
  {
    title: '操作',
    key: 'actions',
    width: 150,
    render: (row: ToolItem) =>
      h('div', { style: 'display:flex;gap:6px' }, [
        h(NButton, { size: 'tiny', quaternary: true, type: 'primary', onClick: () => openTest(row) }, { default: () => '试运行' }),
        row.tool_type !== 'system'
          ? h(NButton, { size: 'tiny', quaternary: true, type: 'error', onClick: () => removeTool(row) }, { default: () => '删除' })
          : null
      ])
  }
]

async function load() {
  loading.value = true
  try {
    tools.value = await listTools()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function doCreate() {
  creating.value = true
  try {
    let headers: { key: string; value: string }[] = []
    try {
      const obj = JSON.parse(form.headersText || '{}')
      headers = Object.entries(obj).map(([key, value]) => ({ key, value: String(value) }))
    } catch {
      /* headers 可空 */
    }
    await createTool({
      name: form.name.trim(),
      description: form.description.trim(),
      tool_type: form.tool_type,
      config: { ...form.config, headers }
    })
    showCreate.value = false
    form.name = ''
    form.description = ''
    form.config.url = ''
    form.config.body = ''
    form.headersText = ''
    message.success('工具已创建')
    await load()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    creating.value = false
  }
}

function openTest(row: ToolItem) {
  testingId.value = row.id
  testResult.value = null
  showTest.value = true
}

async function doTest() {
  if (!testingId.value) return
  testing.value = true
  try {
    const resp = await testTool(testingId.value, testInput.value)
    testResult.value = resp.result
  } catch (e: any) {
    message.error(e.message)
  } finally {
    testing.value = false
  }
}

function removeTool(row: ToolItem) {
  dialog.warning({
    title: '删除工具',
    content: `确定删除「${row.name}」吗？引用该工具的流程节点将执行失败。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteTool(row.id)
        message.success('已删除')
        await load()
      } catch (e: any) {
        message.error(e.message)
      }
    }
  })
}

onMounted(load)
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #1f2329;
}

.page-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: #8f959e;
}

.test-result {
  margin-top: 16px;
}

.test-result-label {
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
  margin-bottom: 8px;
}

.test-result-body {
  font-size: 12px;
  color: #4b5563;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
