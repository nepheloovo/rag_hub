<template>
  <n-card size="small">
    <template #header>
      <div class="card-title">
        知识缺口 · 未命中问题聚类
        <span class="card-hint">检索无引用或被点踩的问题，按相似问法聚合（近 30 天）</span>
      </div>
    </template>
    <template #header-extra>
      <n-button size="small" quaternary :loading="loading" @click="load">刷新</n-button>
    </template>
    <n-data-table
      :columns="columns"
      :data="gaps"
      :loading="loading"
      :bordered="false"
      :row-key="(row: KnowledgeGap) => row.key"
      :pagination="gaps.length > 10 ? { pageSize: 10 } : false"
      size="small"
    />
  </n-card>

  <n-modal v-model:show="showModal" preset="card" title="补充知识" style="width: 560px; max-width: calc(100vw - 32px)">
    <n-form label-placement="top">
      <n-form-item label="问题">
        <n-input v-model:value="form.question" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" />
      </n-form-item>
      <n-form-item label="标准答案" required>
        <n-input v-model:value="form.answer" type="textarea" placeholder="写下应答的标准内容，会作为文档入库" :autosize="{ minRows: 4, maxRows: 10 }" />
      </n-form-item>
      <n-form-item label="补充到知识库" required>
        <n-select v-model:value="form.kb_id" :options="kbOptions" placeholder="选择知识库" filterable />
      </n-form-item>
    </n-form>
    <template #footer>
      <div class="modal-footer">
        <n-button @click="showModal = false">取消</n-button>
        <n-button type="primary" :loading="saving" :disabled="!canSubmit" @click="submit">提交入库</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from 'vue'
import { NButton, NTag, NTooltip, useMessage } from 'naive-ui'
import { getKnowledgeGaps, listKbs, supplementKnowledge } from '@/api'
import type { KnowledgeBase, KnowledgeGap } from '@/api/types'

const emit = defineEmits<{ supplemented: [] }>()
const message = useMessage()
const gaps = ref<KnowledgeGap[]>([])
const kbs = ref<KnowledgeBase[]>([])
const loading = ref(false)
const saving = ref(false)
const showModal = ref(false)
const form = reactive({ question: '', answer: '', kb_id: null as string | null })

const kbOptions = computed(() => kbs.value.map(kb => ({ label: kb.name, value: kb.id })))
const canSubmit = computed(() => !!form.question.trim() && !!form.answer.trim() && !!form.kb_id)

const columns = [
  {
    title: '问题',
    key: 'question',
    minWidth: 240,
    render: (row: KnowledgeGap) => row.sample_questions.length > 1
      ? h(NTooltip, { placement: 'top-start' }, {
          trigger: () => h('span', { class: 'gap-question' }, [row.question, h('span', { class: 'gap-similar' }, ` +${row.sample_questions.length - 1} 个相似问法`)]),
          default: () => row.sample_questions.map(q => h('div', q))
        })
      : h('span', { class: 'gap-question' }, row.question)
  },
  {
    title: '次数',
    key: 'count',
    width: 130,
    render: (row: KnowledgeGap) => h('span', { class: 'gap-count' }, [
      h('strong', row.count),
      h('span', { class: 'gap-split' }, ` 未命中 ${row.miss_count} · 点踩 ${row.dislike_count}`)
    ])
  },
  { title: '来源应用', key: 'apps', width: 160, render: (row: KnowledgeGap) => row.apps.join('、') || '—' },
  {
    title: '建议补充到',
    key: 'kb_names',
    width: 180,
    render: (row: KnowledgeGap) => row.kb_names.length
      ? row.kb_names.map(name => h(NTag, { size: 'small', bordered: false, style: 'margin: 0 4px 4px 0' }, { default: () => name }))
      : h('span', { class: 'gap-split' }, '应用未绑定知识库')
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: (row: KnowledgeGap) => h(NButton, { size: 'small', type: 'primary', text: true, onClick: () => openSupplement(row) }, { default: () => '补充知识' })
  }
]

function openSupplement(row: KnowledgeGap) {
  form.question = row.question
  form.answer = ''
  form.kb_id = row.kb_ids[0] || kbs.value[0]?.id || null
  showModal.value = true
}

async function submit() {
  if (!canSubmit.value || saving.value) return
  saving.value = true
  try {
    await supplementKnowledge({ kb_id: form.kb_id!, question: form.question.trim(), answer: form.answer.trim() })
    message.success('已提交入库，解析完成后即可检索')
    showModal.value = false
    emit('supplemented')
  } catch (e: any) {
    message.error(e.message || '提交失败')
  } finally {
    saving.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const [g, k] = await Promise.all([getKnowledgeGaps(30), kbs.value.length ? Promise.resolve(kbs.value) : listKbs()])
    gaps.value = g
    kbs.value = k
  } catch (e: any) {
    message.error(e.message || '知识缺口加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.card-title { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.card-hint { font-size: 12px; font-weight: 400; color: #8f959e; }
.gap-question { color: #1f2329; overflow-wrap: anywhere; }
.gap-similar, .gap-split { font-size: 12px; color: #8f959e; }
.gap-count strong { font-variant-numeric: tabular-nums; }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>
