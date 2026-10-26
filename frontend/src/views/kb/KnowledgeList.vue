<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">知识库</h2>
        <p class="page-desc">构建与管理企业知识库，支持 Word、PDF、Markdown、图片、表格</p>
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
              <div class="kb-name">{{ kb.name }}</div>
              <div class="kb-time">更新于 {{ formatTime(kb.updated_at) }}</div>
            </div>
          </div>
          <div class="kb-desc" @click="$router.push(`/app/knowledge/${kb.id}`)">
            {{ kb.description || '暂无描述' }}
          </div>
          <div class="kb-footer">
            <div class="kb-stats">
              <n-statistic label="文档" :value="kb.doc_count" />
              <n-statistic label="分块" :value="kb.chunk_count" />
            </div>
            <n-button text type="error" size="small" @click="removeKb(kb)">删除</n-button>
          </div>
        </n-card>
      </div>
    </n-spin>

    <n-modal
      v-model:show="showCreate"
      preset="card"
      title="新建知识库"
      style="width: 480px"
      :mask-closable="false"
    >
      <n-form label-placement="left" label-width="70">
        <n-form-item label="名称" required>
          <n-input v-model:value="newKbName" placeholder="如：产品研发知识库" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input
            v-model:value="newKbDesc"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="知识库用途说明（可选）"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="showCreate = false">取消</n-button>
          <n-button type="primary" :disabled="!newKbName.trim()" :loading="creating" @click="createKb">
            创建
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { AddOutline, FolderOpenOutline } from '@vicons/ionicons5'
import { createKb as apiCreateKb, deleteKb, listKbs } from '@/api'
import type { KnowledgeBase } from '@/api/types'

const message = useMessage()
const dialog = useDialog()
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const newKbName = ref('')
const newKbDesc = ref('')

function formatTime(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function load() {
  loading.value = true
  try {
    knowledgeBases.value = await listKbs()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function createKb() {
  creating.value = true
  try {
    await apiCreateKb({ name: newKbName.value.trim(), description: newKbDesc.value.trim() })
    showCreate.value = false
    newKbName.value = ''
    newKbDesc.value = ''
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
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.kb-card {
  transition: box-shadow 0.2s;
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

.kb-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
}

.kb-time {
  font-size: 12px;
  color: #a8adb5;
  margin-top: 2px;
}

.kb-desc {
  margin: 12px 0;
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

.empty-box {
  padding: 80px 0;
}
</style>
