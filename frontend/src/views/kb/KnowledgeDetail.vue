<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <n-button quaternary circle size="small" @click="$router.push('/app/knowledge')">
          <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
        </n-button>
        <div>
          <h2 class="page-title">{{ kb?.name || '知识库详情' }}</h2>
          <p class="page-desc">{{ kb?.description || '暂无描述' }}</p>
        </div>
      </div>
      <n-button type="primary" @click="showImport = true">
        <template #icon><n-icon><CloudUploadOutline /></n-icon></template>
        导入文档
      </n-button>
    </div>

    <n-card size="small" style="margin-bottom: 16px">
      <n-space :size="36" align="center">
        <n-tag :bordered="false" size="small" :color="{ color: kbTypeBg, textColor: kbTypeColor }">{{ kbTypeLabel }}</n-tag>
        <span class="meta-item">分块策略：<b>{{ strategyShort }}</b></span>
        <span class="meta-item">embedding：<b>{{ kbEmbedLabel }}</b></span>
        <n-tag :bordered="false" size="small" :type="kbStatusType">{{ kbStatusLabel }}</n-tag>
        <n-statistic label="文档" :value="docs.length" />
        <n-statistic label="分块" :value="totalChunks" />
        <n-statistic label="解析中" :value="docs.filter(d => ['pending', 'parsing'].includes(d.status)).length" />
        <n-statistic label="失败" :value="docs.filter(d => d.status === 'failed').length" />
      </n-space>
    </n-card>

    <n-tabs v-model:value="activeTab" type="line" animated>
      <n-tab-pane name="docs" tab="文档列表">
        <n-data-table
          :columns="docColumns"
          :data="docs"
          :bordered="false"
          :row-key="(row: Doc) => row.id"
          :loading="loading"
        />
      </n-tab-pane>

      <n-tab-pane name="chunks" tab="分块预览">
        <div style="margin-bottom: 12px">
          <n-select
            v-model:value="chunkDocId"
            :options="doneDocOptions"
            placeholder="选择已完成的文档"
            style="width: 320px"
            @update:value="loadChunks"
          />
        </div>
        <n-spin :show="chunksLoading">
          <div class="chunk-list">
            <div v-for="c in chunkList" :key="c.id" class="chunk-item">
              <div class="chunk-head">
                <n-tag size="small" :bordered="false" type="info">
                  {{ c.source }}<template v-if="c.page"> · 第 {{ c.page }} 页</template>
                </n-tag>
                <n-tag v-if="c.heading" size="small" :bordered="false">{{ c.heading }}</n-tag>
              </div>
              <div class="chunk-text">{{ c.content }}</div>
            </div>
            <n-empty v-if="!chunksLoading && chunkList.length === 0" description="暂无分块，请先导入并解析文档" />
          </div>
        </n-spin>
      </n-tab-pane>

      <n-tab-pane name="test" tab="测试检索">
        <div class="test-box">
          <n-input-group>
            <n-input
              v-model:value="testQuery"
              placeholder="输入测试问题，验证检索召回效果"
              @keydown.enter="doTestRetrieval"
            />
            <n-button type="primary" :loading="testing" @click="doTestRetrieval">
              <template #icon><n-icon><SearchOutline /></n-icon></template>
              检索
            </n-button>
          </n-input-group>

          <div v-if="testModels" class="result-tip">
            模型：embedding {{ testModels.embedding }}<template v-if="testModels.embedding_fake">（伪向量）</template>
            · Rerank {{ testModels.rerank_used ? testModels.rerank : '未配置（已降级）' }}
          </div>
          <div v-if="testResults.length" style="margin-top: 16px">
            <div class="result-tip">召回 {{ testResults.length }} 条结果</div>
            <div v-for="r in testResults" :key="r.id" class="chunk-item">
              <div class="chunk-head">
                <n-tag size="small" :bordered="false" type="info">
                  {{ r.source }}<template v-if="r.page"> · 第 {{ r.page }} 页</template>
                </n-tag>
                <n-tag size="small" type="success" :bordered="false">score {{ r.score }}</n-tag>
              </div>
              <div class="chunk-text">{{ r.content }}</div>
            </div>
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>

    <!-- 导入文档弹窗 -->
    <n-modal
      v-model:show="showImport"
      preset="card"
      title="导入文档"
      style="width: 560px"
      :mask-closable="false"
    >
      <n-upload
        multiple
        directory-dnd
        :default-upload="false"
        accept=".docx,.doc,.pdf,.md,.markdown,.png,.jpg,.jpeg,.xlsx,.xls,.csv"
        style="width: 100%"
        @change="onFileChange"
      >
        <n-upload-dragger>
          <div style="padding: 28px 0">
            <n-icon size="40" color="#3370ff"><CloudUploadOutline /></n-icon>
            <div style="margin-top: 12px; font-size: 14px; color: #4b5563">
              点击或拖拽文件到此处上传
            </div>
            <div style="margin-top: 8px; font-size: 12px; color: #a8adb5">
              支持 Word(.docx) / PDF(.pdf) / Markdown(.md) / 图片(.png/.jpg) / 表格(.xlsx/.csv)，单文件 ≤ 20MB
            </div>
          </div>
        </n-upload-dragger>
      </n-upload>

      <div v-if="uploadingFiles.length" class="upload-progress-list">
        <div v-for="f in uploadingFiles" :key="f.name" class="upload-progress-item">
          <div class="file-line">
            <span class="file-name">{{ f.name }}</span>
            <span class="file-status" :class="{ fail: f.status === 'failed' }">{{ f.statusText }}</span>
          </div>
          <n-progress
            v-if="f.status === 'uploading'"
            type="line"
            :percentage="f.progress"
            :height="6"
            :show-indicator="false"
            style="margin-top: 6px"
          />
          <div v-if="f.error" class="file-sub" style="color: #e5484d">{{ f.error }}</div>
          <div v-if="f.docId && f.status === 'done'" class="file-actions">
            <n-button size="tiny" quaternary type="primary" :loading="f.previewing" @click="openPreview(f)">
              预览分块
            </n-button>
            <n-button size="tiny" type="primary" @click="confirmIndex(f)">确认入库</n-button>
          </div>
        </div>
      </div>

      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="closeImport">关闭</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 分块预览弹窗 -->
    <n-modal
      v-model:show="showPreview"
      preset="card"
      :title="`分块预览：${previewFile?.name || ''}`"
      style="width: 760px"
      :mask-closable="false"
    >
      <div class="preview-toolbar">
        <span class="preview-label">分块策略</span>
        <n-select
          v-model:value="previewStrategy"
          :options="strategyOptions"
          style="width: 300px"
          @update:value="loadPreview"
        />
        <n-tag v-if="previewData" size="small" :bordered="false" type="info">
          {{ previewData.total }} 块
        </n-tag>
      </div>
      <n-spin :show="previewLoading">
        <div v-if="previewData" class="chunk-list" style="max-height: 420px; overflow-y: auto">
          <div v-for="(c, i) in previewData.chunks" :key="i" class="chunk-item">
            <div class="chunk-head">
              <n-space :size="6" align="center">
                <n-tag size="tiny" :bordered="false" type="info">{{ c.kind === 'parent' ? '父块' : c.kind === 'child' ? '子块' : '分块' }}</n-tag>
                <n-tag v-if="c.page" size="tiny" :bordered="false">第 {{ c.page }} 页</n-tag>
                <n-tag v-if="c.heading" size="tiny" :bordered="false">{{ c.heading }}</n-tag>
              </n-space>
            </div>
            <div class="chunk-text">{{ c.content }}</div>
          </div>
        </div>
        <n-empty v-if="!previewLoading && previewData && previewData.chunks.length === 0" description="未切分出分块" />
      </n-spin>
      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span class="preview-hint">确认效果后点击「确认入库」，将按当前策略切块并向量化</span>
          <n-space>
            <n-button @click="showPreview = false">取消</n-button>
            <n-button type="primary" @click="confirmIndex(previewFile)">确认入库</n-button>
          </n-space>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage, useDialog, NTag, NButton } from 'naive-ui'
import {
  ArrowBackOutline,
  CloudUploadOutline,
  SearchOutline,
  RefreshOutline
} from '@vicons/ionicons5'
import {
  getKb,
  listDocs,
  uploadDoc,
  deleteDoc,
  reparseDoc,
  indexDoc,
  previewChunks,
  listChunks,
  testRetrieval
} from '@/api'
import type { ChunkPreview, Doc, KnowledgeBase, RetrievalChunk } from '@/api/types'

const route = useRoute()
const message = useMessage()
const dialog = useDialog()

const kb = ref<KnowledgeBase | null>(null)
const docs = ref<Doc[]>([])
const loading = ref(false)
const activeTab = ref('docs')
const showImport = ref(false)

const totalChunks = computed(() => docs.value.reduce((s, d) => s + (d.chunk_count || 0), 0))

// ---------- 知识库元信息 ----------
const kbTypeMeta: Record<string, { label: string; bg: string; color: string }> = {
  generic: { label: '通用知识库', bg: '#eef3ff', color: '#3370ff' },
  qa_pair: { label: '问答对知识库', bg: '#ecfdf3', color: '#22c55e' },
  table: { label: '表格知识库', bg: '#fff7e8', color: '#f59e0b' },
  website: { label: '网站同步', bg: '#f3efff', color: '#8b5cf6' },
  feishu: { label: '飞书知识库', bg: '#e8f7ff', color: '#0ea5e9' }
}
const kbTypeLabel = computed(() => (kb.value ? kbTypeMeta[kb.value.kb_type]?.label || kb.value.kb_type : '通用知识库'))
const kbTypeBg = computed(() => (kb.value ? kbTypeMeta[kb.value.kb_type]?.bg || '#eef3ff' : '#eef3ff'))
const kbTypeColor = computed(() => (kb.value ? kbTypeMeta[kb.value.kb_type]?.color || '#3370ff' : '#3370ff'))
const strategyShort = computed(() => {
  const m: Record<string, string> = { smart: '智能', heading: '标题层级', separator: '自定义分隔', fixed: '固定长度', parent_child: '父子', semantic: '语义', qa_split: '问答对', page: '按页', table_row: '表格按行' }
  return kb.value ? m[kb.value.chunk_strategy] || kb.value.chunk_strategy : '—'
})
const kbEmbedLabel = computed(() => (kb.value?.embedding_ref ? kb.value.embedding_ref.split(':')[1] || kb.value.embedding_ref : '全局默认'))
const kbStatusLabel = computed(() => ({ available: '可用', indexing: '索引中', failed: '失败' } as any)[kb.value?.status || 'available'])
const kbStatusType = computed(() => (kb.value?.status === 'indexing' ? 'warning' : kb.value?.status === 'failed' ? 'error' : 'success') as any)

// ---------- 文档列表 ----------
const docColumns = [
  { title: '文件名', key: 'filename', width: 260 },
  { title: '类型', key: 'file_type', width: 90 },
  { title: '大小', key: 'file_size', width: 90, render: (row: Doc) => formatSize(row.file_size) },
  {
    title: '状态',
    key: 'status',
    width: 200,
    render: (row: Doc) => {
      if (row.status === 'done') return h(NTag, { size: 'small', type: 'success', bordered: false }, { default: () => '已完成' })
      if (row.status === 'failed') {
        return h('span', { style: 'display:flex;align-items:center;gap:6px' }, [
          h(NTag, { size: 'small', type: 'error', bordered: false }, { default: () => '失败' }),
          h('span', { style: 'font-size:12px;color:#e5484d;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap', title: row.error }, row.error || '')
        ])
      }
      return h(NTag, { size: 'small', type: 'warning', bordered: false }, { default: () => row.status === 'pending' ? '排队中' : '解析中' })
    }
  },
  { title: '分块数', key: 'chunk_count', width: 90 },
  { title: '上传时间', key: 'created_at', width: 160, render: (row: Doc) => formatTime(row.created_at) },
  {
    title: '操作',
    key: 'actions',
    render: (row: Doc) =>
      h('div', { style: 'display:flex;gap:8px' }, [
        h(
          NButton,
          { size: 'tiny', quaternary: true, type: 'primary', onClick: () => doReparse(row) },
          { icon: () => h(RefreshOutline), default: () => '重新解析' }
        ),
        h(
          NButton,
          { size: 'tiny', quaternary: true, type: 'error', onClick: () => doDelete(row) },
          { default: () => '删除' }
        )
      ])
  }
]

function formatSize(bytes: number) {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return bytes + ' B'
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ---------- 轮询解析状态 ----------
let pollTimer: number | null = null

async function loadAll() {
  loading.value = true
  try {
    const [kbData, docData] = await Promise.all([
      getKb(route.params.id as string),
      listDocs(route.params.id as string)
    ])
    kb.value = kbData
    docs.value = docData
    // 默认选中第一个已完成文档用于分块预览
    if (!chunkDocId.value && doneDocOptions.value.length) {
      chunkDocId.value = doneDocOptions.value[0].value
      loadChunks(chunkDocId.value)
    }
    schedulePoll()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

function schedulePoll() {
  const busy = docs.value.some(d => d.status === 'pending' || d.status === 'parsing')
  if (busy && !pollTimer) {
    pollTimer = window.setInterval(refreshDocs, 2500)
  } else if (!busy && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshDocs() {
  try {
    docs.value = await listDocs(route.params.id as string)
    schedulePoll()
  } catch {
    /* 轮询静默失败 */
  }
}

// ---------- 上传 ----------
interface UploadingFile {
  name: string
  status: 'uploading' | 'done' | 'failed'
  progress: number
  statusText: string
  error: string
  docId?: string
  previewing?: boolean
}

const uploadingFiles = ref<UploadingFile[]>([])

function onFileChange(data: any) {
  const files: File[] = (data.fileList || []).map((f: any) => f.file).filter(Boolean)
  files.forEach(file => {
    uploadingFiles.value.push({
      name: file.name,
      status: 'uploading',
      progress: 0,
      statusText: '上传中…',
      error: ''
    })
    // 通过响应式代理更新进度，避免直接修改原始对象不触发视图
    const item = uploadingFiles.value[uploadingFiles.value.length - 1]
    // auto_index=false：先预览分块，确认后再入库
    uploadDoc(route.params.id as string, file, p => {
      item.progress = p
    }, false)
      .then((doc) => {
        item.status = 'done'
        item.statusText = '已上传，待预览确认'
        item.docId = doc.id
      })
      .catch((e: any) => {
        item.status = 'failed'
        item.statusText = '上传失败'
        item.error = e.message
      })
  })
}

function closeImport() {
  showImport.value = false
  uploadingFiles.value = []
}

// ---------- 试切块预览与确认入库 ----------
const showPreview = ref(false)
const previewFile = ref<UploadingFile | null>(null)
const previewStrategy = ref<string>('')
const previewData = ref<{ strategy: string; total: number; chunks: any[]; warnings: string[] } | null>(null)
const previewLoading = ref(false)

const strategyDesc: Record<string, string> = {
  smart: '智能分块：识别标题和段落结构，自动递归切分',
  heading: '按标题层级：H1–H3 切分，保留标题路径',
  separator: '自定义分隔符：按指定符号切分',
  fixed: '固定长度：按字符数和重叠量切分',
  parent_child: '父子分块：小块召回，命中返回大块',
  semantic: '语义分块：段落向量相似度突变处断开',
  qa_split: '问答对拆分：模型提取问题-答案对',
  page: '按页切分：一页一块，保留页码',
  table_row: '表格按行：每行一块，表头作为上下文'
}
const strategyOptions = computed(() =>
  Object.entries(strategyDesc).map(([value, label]) => ({ label: `${strategyShortName(value)} · ${label.split('：')[1] || label}`, value }))
)
const strategyShortName = (s: string) => ({ smart: '智能', heading: '标题层级', separator: '自定义分隔', fixed: '固定长度', parent_child: '父子', semantic: '语义', qa_split: '问答对', page: '按页', table_row: '表格按行' } as any)[s] || s

async function openPreview(f: UploadingFile) {
  previewFile.value = f
  previewData.value = null
  previewStrategy.value = kb.value?.chunk_strategy || 'smart'
  showPreview.value = true
  f.previewing = true
  await loadPreview()
  f.previewing = false
}

async function loadPreview() {
  if (!previewFile.value?.docId) return
  previewLoading.value = true
  try {
    previewData.value = await previewChunks(previewFile.value.docId, previewStrategy.value || undefined)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    previewLoading.value = false
  }
}

async function confirmIndex(f: UploadingFile | null) {
  if (!f?.docId) return
  try {
    await indexDoc(f.docId)
    showPreview.value = false
    showImport.value = false
    uploadingFiles.value = []
    message.success('已提交索引入库，后台解析中')
    await loadAll()
  } catch (e: any) {
    message.error(e.message)
  }
}

function doReparse(row: Doc) {
  dialog.info({
    title: '重新解析',
    content: `将重新解析「${row.filename}」并重建分块，确定继续？`,
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await reparseDoc(row.id)
        message.success('已提交重新解析任务')
        await loadAll()
      } catch (e: any) {
        message.error(e.message)
      }
    }
  })
}

function doDelete(row: Doc) {
  dialog.warning({
    title: '删除文档',
    content: `确定删除「${row.filename}」及其全部分块吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteDoc(row.id)
        message.success('已删除')
        await loadAll()
      } catch (e: any) {
        message.error(e.message)
      }
    }
  })
}

// ---------- 分块预览 ----------
const chunkDocId = ref<string | null>(null)
const chunkList = ref<ChunkPreview[]>([])
const chunksLoading = ref(false)
const doneDocOptions = computed(() =>
  docs.value.filter(d => d.status === 'done').map(d => ({ label: d.filename, value: d.id }))
)

async function loadChunks(docId: string | null) {
  if (!docId) {
    chunkList.value = []
    return
  }
  chunksLoading.value = true
  try {
    chunkList.value = await listChunks(docId, 50)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    chunksLoading.value = false
  }
}

// ---------- 测试检索 ----------
const testQuery = ref('')
const testing = ref(false)
const testResults = ref<RetrievalChunk[]>([])
const testModels = ref<any>(null)

async function doTestRetrieval() {
  if (!testQuery.value.trim()) return
  testing.value = true
  try {
    const data = await testRetrieval(route.params.id as string, testQuery.value.trim())
    testResults.value = data.chunks
    testModels.value = data.models
    if (data.chunks.length === 0) message.info('未检索到相关内容')
  } catch (e: any) {
    message.error(e.message)
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  loadAll()
  // 默认选中第一个已完成文档用于分块预览
  if (doneDocOptions.value.length) chunkDocId.value = doneDocOptions.value[0].value
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 10px;
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

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}

.chunk-item {
  border: 1px solid #e8ebf2;
  border-radius: 10px;
  padding: 14px 16px;
  background: #fff;
}

.chunk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.chunk-text {
  font-size: 13px;
  line-height: 1.8;
  color: #4b5563;
  white-space: pre-wrap;
  word-break: break-word;
}

.result-tip {
  font-size: 13px;
  color: #8f959e;
  margin: 12px 0;
}

.upload-progress-list {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-progress-item {
  border: 1px solid #e8ebf2;
  border-radius: 8px;
  padding: 10px 12px;
}

.file-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.file-name {
  font-size: 13px;
  color: #1f2329;
}

.file-status {
  font-size: 12px;
  color: #22c55e;
}

.file-status.fail {
  color: #e5484d;
}

.file-sub {
  margin-top: 6px;
  font-size: 12px;
  color: #a8adb5;
}

.meta-item {
  font-size: 13px;
  color: #6b7280;
}

.meta-item b {
  color: #1f2329;
}

.file-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.preview-label {
  font-size: 13px;
  color: #6b7280;
}

.preview-hint {
  font-size: 12px;
  color: #a8adb5;
}
</style>
