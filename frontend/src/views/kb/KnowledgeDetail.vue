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
                <n-tag v-if="c.qa_pairs?.length" size="small" :bordered="false" type="success">{{ c.qa_pairs.length }} 个问答对</n-tag>
                <span class="chunk-actions">
                  <n-button size="tiny" quaternary type="primary" @click="openChunkEdit(c)">编辑</n-button>
                  <n-button size="tiny" quaternary type="error" @click="removeChunk(c)">删除</n-button>
                </span>
              </div>
              <div class="chunk-text">{{ c.content }}</div>
              <div v-if="c.keywords?.length" class="kw-row">
                <n-tag v-for="k in c.keywords" :key="k" size="tiny" :bordered="false">{{ k }}</n-tag>
              </div>
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

          <div class="test-options">
            <n-radio-group v-model:value="testOptions.mode" size="small">
              <n-radio-button v-for="m in retrievalModes" :key="m.value" :value="m.value">{{ m.label }}</n-radio-button>
            </n-radio-group>
            <span class="mode-hint">{{ retrievalModes.find(m => m.value === testOptions.mode)?.hint }}</span>
            <div class="option-grid">
              <label>召回数 <n-input-number v-model:value="testOptions.top_k" size="small" :min="1" :max="100" style="width: 90px" /></label>
              <label>引用上限 <n-input-number v-model:value="testOptions.top_n" size="small" :min="1" :max="testOptions.top_k" style="width: 90px" /></label>
              <label class="slider-label">最低相关度 {{ testOptions.score_threshold.toFixed(2) }}
                <n-slider v-model:value="testOptions.score_threshold" :min="0" :max="1" :step="0.05" style="width: 140px" />
              </label>
              <label>结果重排 <n-switch v-model:value="testOptions.rerank" size="small" /></label>
              <n-button size="small" @click="openApplyToApp">把这组参数用到应用</n-button>
            </div>
          </div>

          <div v-if="testModels" class="result-tip">
            模式：{{ retrievalModes.find(m => m.value === testUsedMode)?.label }}
            <template v-if="testModels.embedding"> · embedding {{ testModels.embedding }}<template v-if="testModels.embedding_fake">（伪向量）</template></template>
            · Rerank {{ testModels.rerank_used ? testModels.rerank : testOptions.rerank ? '未配置（已降级）' : '已关闭' }}
          </div>
          <div v-if="testResults.length" style="margin-top: 16px">
            <div class="result-tip">召回 {{ testResults.length }} 条结果</div>
            <div v-for="r in testResults" :key="r.id" class="chunk-item">
              <div class="chunk-head">
                <n-tag size="small" :bordered="false" type="info">
                  {{ r.source }}<template v-if="r.page"> · 第 {{ r.page }} 页</template>
                </n-tag>
                <n-tag v-if="r.heading" size="small" :bordered="false">{{ r.heading }}</n-tag>
                <n-tag size="small" type="success" :bordered="false">score {{ r.score }}</n-tag>
              </div>
              <div class="chunk-text">{{ r.content }}</div>
              <div v-if="r.keywords?.length" class="kw-row">
                <n-tag v-for="k in r.keywords" :key="k" size="tiny" :bordered="false">{{ k }}</n-tag>
              </div>
            </div>
          </div>
        </div>
      </n-tab-pane>
    </n-tabs>

    <!-- 导入文档弹窗 -->
    <n-modal
      v-model:show="showImport"
      preset="card"
      title="导入数据"
      style="width: 760px; max-width: calc(100vw - 32px)"
      :mask-closable="false"
    >
      <n-tabs v-model:value="importSource" type="segment" size="small" style="margin-bottom: 14px">
        <n-tab name="file">本地文件</n-tab>
        <n-tab name="web">网页链接</n-tab>
        <n-tab name="text">自定义文本</n-tab>
      </n-tabs>

      <template v-if="importSource === 'file'">
        <n-upload
          multiple
          directory-dnd
          :default-upload="false"
          :show-file-list="false"
          accept=".docx,.doc,.pdf,.md,.markdown,.png,.jpg,.jpeg,.xlsx,.xls,.csv"
          style="width: 100%"
          @change="onFileChange"
        >
          <n-upload-dragger>
            <div style="padding: 22px 0">
              <n-icon size="36" color="#3370ff"><CloudUploadOutline /></n-icon>
              <div style="margin-top: 10px; font-size: 14px; color: #4b5563">点击或拖拽文件到此处上传</div>
              <div style="margin-top: 6px; font-size: 12px; color: #a8adb5">
                按格式自动匹配切块方式（PDF 按页、Markdown/Word 按标题、表格按行），可逐个调整；单文件 ≤ 20MB
              </div>
            </div>
          </n-upload-dragger>
        </n-upload>

        <div v-if="uploadingFiles.length" class="upload-progress-list">
          <div v-for="f in uploadingFiles" :key="f.key" class="upload-progress-item">
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
            <div v-if="f.docId && f.status !== 'failed'" class="file-actions">
              <n-tag size="small" :bordered="false">{{ STRATEGY_NAME[f.config.strategy] }}<template v-if="f.config.enhance_keywords || f.config.enhance_qa"> · 增强</template></n-tag>
              <n-button size="tiny" quaternary type="primary" :disabled="f.status === 'indexed'" @click="openFilePreview(f)">调整切块并预览</n-button>
              <n-button size="tiny" type="primary" :disabled="f.status === 'indexed'" @click="confirmFile(f)">{{ f.status === 'indexed' ? '已入库' : '确认入库' }}</n-button>
            </div>
          </div>
        </div>
      </template>

      <template v-else-if="importSource === 'web'">
        <n-form label-placement="top" size="small">
          <n-form-item label="网页地址（每行一个，最多 20 个）">
            <n-input v-model:value="webUrls" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }" placeholder="https://help.example.com/faq" />
          </n-form-item>
        </n-form>
        <n-collapse>
          <n-collapse-item title="切块与增强设置" name="config">
            <ChunkConfigFields v-model="sharedConfig" />
          </n-collapse-item>
        </n-collapse>
        <n-alert v-if="importErrors.length" type="warning" :show-icon="false" style="margin-top: 12px">
          <div v-for="e in importErrors" :key="e">{{ e }}</div>
        </n-alert>
      </template>

      <template v-else>
        <n-form label-placement="top" size="small">
          <n-form-item label="标题">
            <n-input v-model:value="textTitle" placeholder="例如：新品上市统一口径" maxlength="120" />
          </n-form-item>
          <n-form-item label="内容（支持 Markdown）">
            <n-input v-model:value="textContent" type="textarea" :autosize="{ minRows: 6, maxRows: 14 }" placeholder="粘贴或输入文本" />
          </n-form-item>
        </n-form>
        <n-collapse>
          <n-collapse-item title="切块与增强设置" name="config">
            <ChunkConfigFields v-model="sharedConfig" />
          </n-collapse-item>
        </n-collapse>
      </template>

      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="closeImport">关闭</n-button>
          <n-button
            v-if="importSource === 'file'"
            type="primary"
            :disabled="!pendingFiles.length"
            @click="confirmAllFiles"
          >全部确认入库{{ pendingFiles.length ? `（${pendingFiles.length}）` : '' }}</n-button>
          <n-button
            v-else-if="importSource === 'web'"
            type="primary"
            :loading="importing"
            :disabled="!webUrlList.length"
            @click="submitWeb"
          >抓取并导入</n-button>
          <n-button
            v-else
            type="primary"
            :loading="importing"
            :disabled="!textTitle.trim() || !textContent.trim()"
            @click="submitText"
          >导入</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 切块设置与预览弹窗（导入确认 / 已入库文件重新切块 共用） -->
    <n-modal
      v-model:show="showPreview"
      preset="card"
      :title="`${previewTarget?.mode === 'rechunk' ? '重新切块' : '切块设置'}：${previewTarget?.name || ''}`"
      style="width: 960px; max-width: calc(100vw - 32px)"
      :mask-closable="false"
    >
      <div class="preview-layout">
        <div class="preview-config">
          <ChunkConfigFields v-model="previewConfig" />
          <n-button block secondary type="primary" style="margin-top: 12px" :loading="previewLoading" @click="loadPreview">刷新预览</n-button>
        </div>
        <div class="preview-result">
          <div v-if="previewData" class="preview-stats">
            共 <b>{{ previewData.total }}</b> 块 · 平均 <b>{{ previewData.avg_chars }}</b> 字 · 最长 <b>{{ previewData.max_chars }}</b> 字
            <span v-if="previewData.total > previewData.chunks.length">（展示前 {{ previewData.chunks.length }} 块）</span>
          </div>
          <n-alert v-if="previewData?.warnings?.length" type="warning" :show-icon="false" style="margin-bottom: 8px">
            {{ previewData.warnings.join('；') }}
          </n-alert>
          <n-spin :show="previewLoading">
            <div v-if="previewData" class="chunk-list" style="max-height: 460px; overflow-y: auto">
              <div v-for="(c, i) in previewData.chunks" :key="i" class="chunk-item">
                <div class="chunk-head">
                  <n-space :size="6" align="center">
                    <n-tag size="tiny" :bordered="false" type="info">#{{ i + 1 }} {{ c.kind === 'parent' ? '父块' : c.kind === 'child' ? '子块' : '分块' }}</n-tag>
                    <n-tag v-if="c.page" size="tiny" :bordered="false">第 {{ c.page }} 页</n-tag>
                    <n-tag v-if="c.heading" size="tiny" :bordered="false">{{ c.heading }}</n-tag>
                    <span class="char-count">{{ c.content.length }} 字</span>
                  </n-space>
                </div>
                <div class="chunk-text">{{ c.content }}</div>
              </div>
            </div>
            <n-empty v-if="!previewLoading && previewData && previewData.chunks.length === 0" description="未切分出分块" />
          </n-spin>
        </div>
      </div>
      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap">
          <span class="preview-hint">预览不含分块增强；确认后按当前设置切块、增强并向量化{{ previewTarget?.mode === 'rechunk' ? '，完成后自动替换旧分块（手工编辑过的分块会被覆盖）' : '' }}</span>
          <n-space>
            <n-button v-if="previewTarget?.mode === 'import'" @click="savePreviewConfig">仅保存设置</n-button>
            <n-button @click="showPreview = false">取消</n-button>
            <n-button type="primary" :loading="applying" @click="applyPreviewConfig">{{ previewTarget?.mode === 'rechunk' ? '确认重新切块' : '确认入库' }}</n-button>
          </n-space>
        </div>
      </template>
    </n-modal>

    <!-- 分块编辑 -->
    <n-modal v-model:show="showChunkEdit" preset="card" title="编辑分块" style="width: 680px; max-width: calc(100vw - 32px)" :mask-closable="false">
      <n-form label-placement="top" size="small">
        <n-form-item label="分块内容">
          <n-input v-model:value="chunkForm.content" type="textarea" :autosize="{ minRows: 5, maxRows: 14 }" />
        </n-form-item>
        <n-form-item label="检索关键词">
          <n-dynamic-tags v-model:value="chunkForm.keywords" />
        </n-form-item>
        <n-form-item label="可回答的问题（问答对）">
          <div class="qa-editor">
            <div v-for="(qa, i) in chunkForm.qa_pairs" :key="i" class="qa-row">
              <n-input v-model:value="qa.q" placeholder="用户可能的提问" size="small" />
              <n-input v-model:value="qa.a" placeholder="依据本块的回答" size="small" />
              <n-button size="small" quaternary type="error" @click="chunkForm.qa_pairs.splice(i, 1)">移除</n-button>
            </div>
            <n-button size="small" dashed @click="chunkForm.qa_pairs.push({ q: '', a: '' })">添加问答对</n-button>
          </div>
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span class="preview-hint">保存后立即重新向量化</span>
          <n-space>
            <n-button @click="showChunkEdit = false">取消</n-button>
            <n-button type="primary" :loading="chunkSaving" :disabled="!chunkForm.content.trim()" @click="saveChunk">保存</n-button>
          </n-space>
        </div>
      </template>
    </n-modal>

    <!-- 检索参数用到应用 -->
    <n-modal v-model:show="showApply" preset="card" title="把检索参数用到应用" style="width: 520px; max-width: calc(100vw - 32px)">
      <div class="preview-hint" style="margin-bottom: 10px">
        {{ retrievalModes.find(m => m.value === testOptions.mode)?.label }} · 召回 {{ testOptions.top_k }} · 引用上限 {{ testOptions.top_n }} · 最低相关度 {{ testOptions.score_threshold.toFixed(2) }} · 重排{{ testOptions.rerank ? '开' : '关' }}
      </div>
      <n-select v-model:value="applyAppIds" multiple :options="kbAppOptions" placeholder="选择引用本知识库的应用" />
      <div class="preview-hint" style="margin-top: 8px">修改的是应用草稿，需重新评测并发布后线上生效</div>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="showApply = false">取消</n-button>
          <n-button type="primary" :loading="applyingToApp" :disabled="!applyAppIds.length" @click="applyToApps">应用</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, onMounted, onUnmounted, reactive } from 'vue'
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
  previewChunks,
  listChunks,
  testRetrieval,
  webImport,
  textImport,
  updateChunk,
  deleteChunk,
  listApps,
  updateApp
} from '@/api'
import type {
  Application, ChunkConfig, ChunkPreview, ChunkPreviewResult, Doc, KnowledgeBase, QaPair, RetrievalChunk, RetrievalMode, RetrievalOptions
} from '@/api/types'
import ChunkConfigFields from '@/components/kb/ChunkConfigFields.vue'
import { STRATEGY_NAME, defaultChunkConfig, recommendedConfig } from '@/components/kb/chunkConfig'

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
  {
    title: '切块方式',
    key: 'chunk_config',
    width: 120,
    render: (row: Doc) => STRATEGY_NAME[row.chunk_config?.strategy || kb.value?.chunk_strategy || 'smart'] || '—'
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
          { size: 'tiny', quaternary: true, type: 'primary', onClick: () => openRechunk(row) },
          { default: () => '重新切块' }
        ),
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

// ---------- 导入：本地文件 / 网页链接 / 自定义文本 ----------
interface UploadingFile {
  key: number
  name: string
  status: 'uploading' | 'done' | 'failed' | 'indexed'
  progress: number
  statusText: string
  error: string
  docId?: string
  config: ChunkConfig
}

const importSource = ref<'file' | 'web' | 'text'>('file')
const uploadingFiles = ref<UploadingFile[]>([])
const pendingFiles = computed(() => uploadingFiles.value.filter(f => f.status === 'done' && f.docId))
const sharedConfig = ref<ChunkConfig>(defaultChunkConfig())
const webUrls = ref('')
const webUrlList = computed(() => webUrls.value.split('\n').map(u => u.trim()).filter(Boolean).slice(0, 20))
const textTitle = ref('')
const textContent = ref('')
const importing = ref(false)
const importErrors = ref<string[]>([])
let fileSeq = 0

function kbDefaultStrategy() {
  return (kb.value?.chunk_strategy || 'smart') as ChunkConfig['strategy']
}

function onFileChange(data: any) {
  // 只处理本次新增的文件（naive-ui 每次回调给出完整列表）
  const file: File | undefined = data.file?.file
  if (!file || data.file?.status === 'removed') return
  const config = recommendedConfig(file.name)
  uploadingFiles.value.push({ key: ++fileSeq, name: file.name, status: 'uploading', progress: 0, statusText: '上传中…', error: '', config })
  // 通过响应式代理更新进度，避免直接修改原始对象不触发视图
  const item = uploadingFiles.value[uploadingFiles.value.length - 1]
  // auto_index=false：先按推荐配置存储，确认后再切块入库
  uploadDoc(route.params.id as string, file, p => { item.progress = p }, false, config)
    .then(doc => {
      item.status = 'done'
      item.statusText = '已上传，待确认入库'
      item.docId = doc.id
    })
    .catch((e: any) => {
      item.status = 'failed'
      item.statusText = '上传失败'
      item.error = e.message
    })
}

async function confirmFile(f: UploadingFile) {
  if (!f.docId) return
  try {
    await reparseDoc(f.docId, f.config)
    f.status = 'indexed'
    f.statusText = '已提交入库，后台解析中'
    await refreshDocs()
  } catch (e: any) {
    message.error(e.message)
  }
}

async function confirmAllFiles() {
  for (const f of pendingFiles.value) await confirmFile(f)
  message.success('已提交入库，后台解析中')
  closeImport()
  await loadAll()
}

async function submitWeb() {
  importing.value = true
  importErrors.value = []
  try {
    const created = await webImport(route.params.id as string, webUrlList.value, sharedConfig.value)
    const failed = webUrlList.value.length - created.length
    message[failed ? 'warning' : 'success'](failed ? `已导入 ${created.length} 个网页，${failed} 个失败或重复` : `已导入 ${created.length} 个网页，后台解析中`)
    if (!failed) closeImport()
    await loadAll()
  } catch (e: any) {
    importErrors.value = String(e.message || '抓取失败').split('；')
  } finally {
    importing.value = false
  }
}

async function submitText() {
  importing.value = true
  try {
    await textImport(route.params.id as string, { title: textTitle.value.trim(), content: textContent.value, config: sharedConfig.value })
    message.success('已导入，后台解析中')
    closeImport()
    await loadAll()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    importing.value = false
  }
}

function closeImport() {
  showImport.value = false
  uploadingFiles.value = []
  importErrors.value = []
  webUrls.value = ''
  textTitle.value = ''
  textContent.value = ''
  sharedConfig.value = defaultChunkConfig()
}

// ---------- 切块设置与预览（导入确认 / 重新切块） ----------
const showPreview = ref(false)
const previewTarget = ref<{ mode: 'import' | 'rechunk'; docId: string; name: string; file?: UploadingFile } | null>(null)
const previewConfig = ref<ChunkConfig>(defaultChunkConfig())
const previewData = ref<ChunkPreviewResult | null>(null)
const previewLoading = ref(false)
const applying = ref(false)

function openFilePreview(f: UploadingFile) {
  if (!f.docId) return
  previewTarget.value = { mode: 'import', docId: f.docId, name: f.name, file: f }
  previewConfig.value = { ...f.config }
  previewData.value = null
  showPreview.value = true
  loadPreview()
}

function openRechunk(row: Doc) {
  previewTarget.value = { mode: 'rechunk', docId: row.id, name: row.filename }
  previewConfig.value = row.chunk_config?.strategy
    ? { ...defaultChunkConfig(), ...row.chunk_config } as ChunkConfig
    : recommendedConfig(row.filename, { strategy: kbDefaultStrategy() })
  previewData.value = null
  showPreview.value = true
  loadPreview()
}

async function loadPreview() {
  if (!previewTarget.value) return
  previewLoading.value = true
  try {
    previewData.value = await previewChunks(previewTarget.value.docId, previewConfig.value)
  } catch (e: any) {
    message.error(e.message)
  } finally {
    previewLoading.value = false
  }
}

function savePreviewConfig() {
  const file = previewTarget.value?.file
  if (file) file.config = { ...previewConfig.value }
  showPreview.value = false
}

async function applyPreviewConfig() {
  const target = previewTarget.value
  if (!target) return
  applying.value = true
  try {
    if (target.file) {
      target.file.config = { ...previewConfig.value }
      await confirmFile(target.file)
    } else {
      await reparseDoc(target.docId, previewConfig.value)
      message.success('已按新设置重新切块，完成后自动替换旧分块')
      await loadAll()
    }
    showPreview.value = false
  } catch (e: any) {
    message.error(e.message)
  } finally {
    applying.value = false
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

// ---------- 分块编辑 ----------
const showChunkEdit = ref(false)
const chunkSaving = ref(false)
const editingChunkId = ref('')
const chunkForm = reactive({ content: '', keywords: [] as string[], qa_pairs: [] as QaPair[] })

function openChunkEdit(c: ChunkPreview) {
  editingChunkId.value = c.id
  chunkForm.content = c.content
  chunkForm.keywords = [...(c.keywords || [])]
  chunkForm.qa_pairs = (c.qa_pairs || []).map(qa => ({ ...qa }))
  showChunkEdit.value = true
}

async function saveChunk() {
  chunkSaving.value = true
  try {
    const saved = await updateChunk(editingChunkId.value, {
      content: chunkForm.content.trim(),
      keywords: chunkForm.keywords.map(k => k.trim()).filter(Boolean),
      qa_pairs: chunkForm.qa_pairs.filter(qa => qa.q.trim() && qa.a.trim())
    })
    chunkList.value = chunkList.value.map(c => (c.id === saved.id ? saved : c))
    showChunkEdit.value = false
    message.success('分块已保存，向量已更新')
  } catch (e: any) {
    message.error(e.message)
  } finally {
    chunkSaving.value = false
  }
}

function removeChunk(c: ChunkPreview) {
  dialog.warning({
    title: '删除分块',
    content: '删除后该内容将无法被检索到，确定删除？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteChunk(c.id)
        chunkList.value = chunkList.value.filter(item => item.id !== c.id)
        message.success('已删除')
        refreshDocs()
      } catch (e: any) {
        message.error(e.message)
      }
    }
  })
}

// ---------- 测试检索 ----------
const retrievalModes: { value: RetrievalMode; label: string; hint: string }[] = [
  { value: 'semantic', label: '语义', hint: '按语义相似度召回，擅长同义表达' },
  { value: 'fulltext', label: '全文', hint: '按关键词匹配，擅长编号、型号、条款号' },
  { value: 'hybrid', label: '混合', hint: '语义 + 全文并行召回，RRF 融合排序，推荐' }
]
const testQuery = ref('')
const testing = ref(false)
const testResults = ref<RetrievalChunk[]>([])
const testModels = ref<any>(null)
const testUsedMode = ref<RetrievalMode>('semantic')
const testOptions = reactive<RetrievalOptions>({ mode: 'hybrid', top_k: 20, top_n: 5, score_threshold: 0, rerank: true })

async function doTestRetrieval() {
  if (!testQuery.value.trim()) return
  testing.value = true
  try {
    const data = await testRetrieval(route.params.id as string, testQuery.value.trim(), { ...testOptions })
    testResults.value = data.chunks
    testModels.value = data.models
    testUsedMode.value = data.options?.mode || testOptions.mode
    if (data.chunks.length === 0) message.info('未检索到相关内容')
  } catch (e: any) {
    message.error(e.message)
  } finally {
    testing.value = false
  }
}

// ---------- 检索参数用到应用 ----------
const showApply = ref(false)
const kbApps = ref<Application[]>([])
const applyAppIds = ref<string[]>([])
const applyingToApp = ref(false)
const kbAppOptions = computed(() => kbApps.value.map(a => ({ label: a.name, value: a.id })))

async function openApplyToApp() {
  try {
    const apps = await listApps()
    kbApps.value = apps.filter(a => (a.kb_ids || []).includes(route.params.id as string))
    applyAppIds.value = []
    if (!kbApps.value.length) {
      message.info('还没有应用引用这个知识库')
      return
    }
    showApply.value = true
  } catch (e: any) {
    message.error(e.message)
  }
}

async function applyToApps() {
  applyingToApp.value = true
  try {
    for (const id of applyAppIds.value) await updateApp(id, { retrieval: { ...testOptions } })
    message.success(`已更新 ${applyAppIds.value.length} 个应用的检索参数（草稿）`)
    showApply.value = false
  } catch (e: any) {
    message.error(e.message)
  } finally {
    applyingToApp.value = false
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

.chunk-actions { margin-left: auto; display: inline-flex; gap: 2px; }
.kw-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.char-count { font-size: 12px; color: #a8adb5; }
.test-options { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
.mode-hint { font-size: 12px; color: #8f959e; }
.option-grid { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; font-size: 13px; color: #4e5969; }
.option-grid label { display: inline-flex; align-items: center; gap: 8px; }
.preview-layout { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 20px; }
.preview-config { border-right: 1px solid #eef0f4; padding-right: 20px; }
.preview-stats { font-size: 13px; color: #4e5969; margin-bottom: 8px; }
.qa-editor { width: 100%; display: flex; flex-direction: column; gap: 8px; }
.qa-row { display: grid; grid-template-columns: 1fr 1.4fr auto; gap: 8px; }
@media (max-width: 760px) {
  .preview-layout { grid-template-columns: 1fr; }
  .preview-config { border-right: 0; padding-right: 0; }
  .qa-row { grid-template-columns: 1fr; }
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
