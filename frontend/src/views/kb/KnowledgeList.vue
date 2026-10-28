<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">知识库</h2>
        <p class="page-desc">管理企业知识资产。每个知识库可选用不同的切块方式，构建前先预览效果。</p>
      </div>
      <n-button type="primary" @click="showCreate = true">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        新建知识库
      </n-button>
    </div>

    <n-spin :show="loading" style="min-height: 200px">
      <div v-if="!loading && knowledgeBases.length === 0" class="empty-box">
        <n-empty description="暂无知识库，点击右上角新建">
          <template #extra>
            <n-button type="primary" size="small" @click="showCreate = true">新建知识库</n-button>
          </template>
        </n-empty>
      </div>

      <div class="kb-grid">
        <n-card v-for="kb in knowledgeBases" :key="kb.id" class="kb-card" hoverable>
          <div class="kb-head" @click="$router.push(`/app/knowledge/${kb.id}`)">
            <div class="kb-icon">
              <n-icon size="22" color="#3370ff"><FolderOpenOutline /></n-icon>
            </div>
            <div class="kb-info">
              <div class="kb-name-row">
                <span class="kb-name">{{ kb.name }}</span>
                <n-tag size="small" :bordered="false" :color="{ color: typeMeta[kb.kb_type]?.bg, textColor: typeMeta[kb.kb_type]?.color }">
                  {{ typeMeta[kb.kb_type]?.label || kb.kb_type }}
                </n-tag>
              </div>
              <div class="kb-sub">
                <n-tag size="tiny" :bordered="false" :type="statusType(kb.status)">{{ statusLabel(kb.status) }}</n-tag>
                <span class="kb-strategy">分块：{{ strategyLabel(kb.chunk_strategy) }}</span>
                <span class="kb-embed">embedding：{{ embedLabel(kb.embedding_ref) }}</span>
              </div>
            </div>
          </div>
          <div class="kb-desc" @click="$router.push(`/app/knowledge/${kb.id}`)">
            {{ kb.description || '暂无描述' }}
          </div>
          <div v-if="kb.used_by_apps?.length" class="kb-used">
            被 {{ kb.used_by_apps.length }} 个应用引用：{{ kb.used_by_apps.join('、') }}
          </div>
          <div class="kb-footer">
            <div class="kb-stats">
              <n-statistic label="文件" :value="kb.doc_count" />
              <n-statistic label="分块" :value="kb.chunk_count" />
            </div>
            <n-button text type="error" size="small" @click="removeKb(kb)">删除</n-button>
          </div>
        </n-card>
      </div>
    </n-spin>

    <!-- 新建知识库 -->
    <n-modal v-model:show="showCreate" preset="card" title="新建知识库" style="width: 560px" :mask-closable="false">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="名称" required>
          <n-input v-model:value="form.name" placeholder="如：产品手册与 FAQ" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" placeholder="知识库用途说明（可选）" />
        </n-form-item>
        <n-form-item label="知识库类型">
          <n-select v-model:value="form.kb_type" :options="typeOptions" @update:value="onTypeChange" />
          <div class="field-hint">{{ typeMeta[form.kb_type]?.desc }}</div>
        </n-form-item>
        <n-form-item label="分块策略">
          <n-select v-model:value="form.chunk_strategy" :options="strategyOptions" />
          <div class="field-hint">{{ strategyDesc[form.chunk_strategy] }}</div>
        </n-form-item>
        <n-form-item label="Embedding">
          <n-select v-model:value="form.embedding_ref" :options="embeddingOptions" placeholder="跟随全局默认模型" clearable />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="showCreate = false">取消</n-button>
          <n-button type="primary" :disabled="!form.name.trim()" :loading="creating" @click="createKb">
            创建
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { AddOutline, FolderOpenOutline } from '@vicons/ionicons5'
import { createKb as apiCreateKb, deleteKb, listKbs, listProviders } from '@/api'
import type { KnowledgeBase, Provider } from '@/api/types'

const message = useMessage()
const dialog = useDialog()
const knowledgeBases = ref<KnowledgeBase[]>([])
const providers = ref<Provider[]>([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)

const typeMeta: Record<string, { label: string; bg: string; color: string; desc: string; disabled?: boolean }> = {
  generic: { label: '通用知识库', bg: '#eef3ff', color: '#3370ff', desc: '上传文件、网页或文本，按切块策略构建索引' },
  qa_pair: { label: '问答对知识库', bg: '#ecfdf3', color: '#22c55e', desc: '以问题-答案为单位，适合 FAQ 和客服（默认问答对拆分）' },
  table: { label: '表格知识库', bg: '#fff7e8', color: '#f59e0b', desc: 'Excel / CSV 按行索引，保留表头语义（默认表格按行）' },
  website: { label: '网站同步', bg: '#f3efff', color: '#8b5cf6', desc: '输入站点地址定时抓取增量更新（规划中，Phase 3 接入）', disabled: true },
  feishu: { label: '飞书知识库', bg: '#e8f7ff', color: '#0ea5e9', desc: '绑定飞书知识空间自动同步（规划中，Phase 3 接入）', disabled: true }
}

const strategyDesc: Record<string, string> = {
  smart: '智能分块：识别标题和段落结构，自动递归切分到合适长度（推荐默认）',
  heading: '按标题层级：按 Markdown/Word 的 H1–H3 切分，每块保留标题路径',
  separator: '自定义分隔符：按指定符号切分，如空行、### 或「第X条」',
  fixed: '固定长度：按字符数和重叠量机械切分',
  parent_child: '父子分块：小块用于精准召回，命中后返回所在大块',
  semantic: '语义分块：相邻段落向量相似度突变处断开，按主题切分',
  qa_split: '问答对拆分：由模型从文档提取「问题-答案」对',
  page: '按页切分：PDF 一页一块，保留页码',
  table_row: '表格按行：Excel/CSV 每行一块，表头作为上下文'
}
const strategyLabel = (s: string) => ({ smart: '智能', heading: '标题层级', separator: '自定义分隔', fixed: '固定长度', parent_child: '父子', semantic: '语义', qa_split: '问答对', page: '按页', table_row: '表格按行' } as any)[s] || s
const statusLabel = (s: string) => ({ available: '可用', indexing: '索引中', failed: '失败' } as any)[s] || s
const statusType = (s: string) => (s === 'indexing' ? 'warning' : s === 'failed' ? 'error' : 'success') as any

const typeOptions = computed(() =>
  Object.entries(typeMeta).map(([value, v]) => ({ label: v.label, value, disabled: !!v.disabled }))
)
const strategyOptions = computed(() =>
  Object.entries(strategyDesc).map(([value, label]) => ({ label: `${strategyLabel(value)} · ${label.split('：')[1] || label}`, value }))
)
const embeddingOptions = computed(() =>
  providers.value
    .filter(p => p.enabled)
    .flatMap(p => p.models.embedding.map(m => ({ label: `${p.name} · ${m}`, value: `${p.id}:${m}` })))
)
const embedLabel = (ref: string) => (ref ? ref.split(':')[1] || ref : '全局默认')

const form = reactive({ name: '', description: '', kb_type: 'generic', chunk_strategy: 'smart', embedding_ref: '' as string | null })

function onTypeChange(t: string) {
  if (t === 'qa_pair') form.chunk_strategy = 'qa_split'
  else if (t === 'table') form.chunk_strategy = 'table_row'
  else if (form.chunk_strategy === 'qa_split' || form.chunk_strategy === 'table_row') form.chunk_strategy = 'smart'
}

async function load() {
  loading.value = true
  try {
    const [kbList, pvList] = await Promise.all([listKbs(), listProviders()])
    knowledgeBases.value = kbList
    providers.value = pvList
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function createKb() {
  creating.value = true
  try {
    await apiCreateKb({
      name: form.name.trim(),
      description: form.description.trim(),
      kb_type: form.kb_type,
      chunk_strategy: form.chunk_strategy,
      embedding_ref: form.embedding_ref || ''
    })
    showCreate.value = false
    form.name = ''
    form.description = ''
    form.kb_type = 'generic'
    form.chunk_strategy = 'smart'
    form.embedding_ref = null
    message.success('知识库创建成功')
    await load()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    creating.value = false
  }
}

function removeKb(kb: KnowledgeBase) {
  dialog.warning({
    title: '删除知识库',
    content: `确定删除「${kb.name}」吗？其中的所有文档与分块将一并删除，且不可恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteKb(kb.id)
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

.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.kb-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  cursor: pointer;
}

.kb-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: #eef3ff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kb-info {
  flex: 1;
  min-width: 0;
}

.kb-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kb-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}

.kb-strategy,
.kb-embed {
  font-size: 12px;
  color: #8f959e;
}

.kb-desc {
  margin: 12px 0 6px;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.6;
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  cursor: pointer;
}

.kb-used {
  margin: 6px 0;
  font-size: 12px;
  color: #3370ff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid #f0f1f3;
}

.kb-stats {
  display: flex;
  gap: 40px;
}

.field-hint {
  font-size: 12px;
  color: #a8adb5;
  line-height: 1.5;
  margin-top: 4px;
  max-width: 400px;
}

.empty-box {
  padding: 80px 0;
}
</style>
