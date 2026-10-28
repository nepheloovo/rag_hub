<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">应用</h2>
        <p class="page-desc">搭建、调试和发布 AI 应用。发布后出现在业务人员的工作台。</p>
      </div>
      <n-button v-if="canManage" type="primary" @click="showCreate = true">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        新建应用
      </n-button>
    </div>

    <!-- 筛选 -->
    <div class="filter-row">
      <n-tag
        :type="filterKind === null ? 'primary' : 'default'"
        :bordered="false"
        round
        clickable
        @click="filterKind = null"
      >全部</n-tag>
      <n-tag
        v-for="k in kindList"
        :key="k.value"
        :type="filterKind === k.value ? 'primary' : 'default'"
        :bordered="false"
        round
        clickable
        @click="filterKind = k.value"
      >{{ k.label }}</n-tag>
      <n-divider vertical />
      <n-tag
        v-for="c in categoryList"
        :key="c"
        :type="filterCategory === c ? 'primary' : 'default'"
        :bordered="false"
        round
        clickable
        @click="filterCategory = filterCategory === c ? null : c"
      >{{ c }}</n-tag>
    </div>

    <n-spin :show="loading">
      <div v-if="!loading && apps.length === 0" class="empty-box">
        <n-empty :description="canManage ? '暂无应用，点击右上角新建' : '暂无应用，请联系管理员创建'">
          <template #extra>
            <n-button v-if="canManage" type="primary" size="small" @click="showCreate = true">新建应用</n-button>
          </template>
        </n-empty>
      </div>

      <div class="app-grid">
        <n-card
          v-for="app in filteredApps"
          :key="app.id"
          class="app-card"
          hoverable
          @click="$router.push(`/app/apps/${app.id}`)"
        >
          <div class="app-head">
            <div class="app-icon" :style="{ background: kindMeta[app.app_kind]?.bg }">
              <n-icon size="22" :color="kindMeta[app.app_kind]?.color">
                <component :is="kindMeta[app.app_kind]?.icon" />
              </n-icon>
            </div>
            <div class="app-info">
              <div class="app-name-row">
                <span class="app-name">{{ app.name }}</span>
                <n-tag size="small" :bordered="false" :color="{ color: kindMeta[app.app_kind]?.bg, textColor: kindMeta[app.app_kind]?.color }">
                  {{ kindMeta[app.app_kind]?.label }}
                </n-tag>
              </div>
              <div class="app-time">{{ statusLabel(app.status) }} · v{{ app.version }} · {{ app.category }}</div>
            </div>
          </div>
          <div class="app-desc">{{ app.description || '暂无描述' }}</div>
          <div class="app-foot">
            <span class="app-kb">
              近 7 天 {{ app.call_count_7d }} 次调用 · 绑定 {{ app.kb_ids?.length || 0 }} 个知识库
            </span>
            <n-button
              v-if="canManage"
              text
              type="error"
              size="small"
              @click.stop="removeApp(app)"
            >删除</n-button>
          </div>
        </n-card>
      </div>
    </n-spin>

    <!-- 新建应用 -->
    <n-modal v-model:show="showCreate" preset="card" title="新建应用" style="width: 620px" :mask-closable="false">
      <div class="type-title">选择应用类型</div>
      <div class="type-grid">
        <div
          v-for="t in typeList"
          :key="t.key"
          class="type-item"
          :class="{ active: form.app_type === t.key }"
          @click="form.app_type = t.key"
        >
          <n-icon size="26" :color="form.app_type === t.key ? t.color : '#8f959e'">
            <component :is="t.icon" />
          </n-icon>
          <div class="type-name">{{ t.label }}</div>
          <div class="type-desc">{{ t.desc }}</div>
        </div>
      </div>

      <n-form label-placement="left" label-width="70" style="margin-top: 16px">
        <n-form-item label="名称" required>
          <n-input v-model:value="form.name" placeholder="如：研发知识问答助手" />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" placeholder="应用用途说明（可选）" />
        </n-form-item>
        <n-form-item label="应用形态">
          <n-select
            v-model:value="form.app_kind"
            :options="[
              { label: '简易（提示词 + 知识库 + 表单）', value: 'simple' },
              { label: 'Chat Flow（可视化编排，规划中）', value: 'chatflow', disabled: true },
              { label: 'Agent（自主规划工具，规划中）', value: 'agent', disabled: true }
            ]"
          />
        </n-form-item>
        <n-form-item label="业务分类">
          <n-select v-model:value="form.category" :options="categoryList.map(c => ({ label: c, value: c }))" />
        </n-form-item>
        <n-form-item label="知识库" required>
          <n-select
            v-model:value="form.kb_ids"
            multiple
            :options="kbOptions"
            placeholder="可绑定多个知识库"
            style="width: 100%"
          />
        </n-form-item>
      </n-form>

      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="showCreate = false">取消</n-button>
          <n-button
            type="primary"
            :disabled="!form.name.trim() || !form.kb_ids.length"
            :loading="creating"
            @click="createApp"
          >创建</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, markRaw } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import {
  AddOutline,
  FolderOpenOutline,
  ChatbubblesOutline,
  HeadsetOutline,
  DocumentTextOutline
} from '@vicons/ionicons5'
import { createApp as apiCreateApp, deleteApp, listApps, listKbs } from '@/api'
import type { Application, KnowledgeBase } from '@/api/types'
import { useAppStore } from '@/stores/app'

const message = useMessage()
const dialog = useDialog()
const store = useAppStore()

const apps = ref<Application[]>([])
const kbs = ref<KnowledgeBase[]>([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)

const canManage = computed(() => store.role === 'admin' || store.role === 'manager')

const kindMeta: Record<string, { label: string; color: string; bg: string; icon: any }> = {
  simple: { label: '简易', color: '#3370ff', bg: '#eef3ff', icon: markRaw(ChatbubblesOutline) },
  chatflow: { label: 'Chat Flow', color: '#8b5cf6', bg: '#f3efff', icon: markRaw(DocumentTextOutline) },
  agent: { label: 'Agent', color: '#0ea5e9', bg: '#e8f7ff', icon: markRaw(HeadsetOutline) }
}

const typeMeta: Record<string, { label: string; color: string; bg: string; icon: any; desc: string }> = {
  qa: {
    label: '问答应用',
    color: '#3370ff',
    bg: '#eef3ff',
    icon: markRaw(ChatbubblesOutline),
    desc: '基于知识库的标准问答，带引用溯源'
  },
  service: {
    label: '智能客服',
    color: '#22c55e',
    bg: '#ecfdf3',
    icon: markRaw(HeadsetOutline),
    desc: '客服人设对话，含兜底话术与转人工提示'
  },
  report: {
    label: '报告分析',
    color: '#8b5cf6',
    bg: '#f3efff',
    icon: markRaw(DocumentTextOutline),
    desc: '对话式分析，输出结构化报告'
  }
}

const typeList = computed(() =>
  Object.entries(typeMeta).map(([key, v]) => ({ key, ...v }))
)

const kindList = [
  { label: '简易', value: 'simple' },
  { label: 'Chat Flow', value: 'chatflow' },
  { label: 'Agent', value: 'agent' }
]
const categoryList = ['报告撰写', '智能客服', '制度与合同审校', '营销内容', '办公提效']

const filterKind = ref<string | null>(null)
const filterCategory = ref<string | null>(null)

const filteredApps = computed(() =>
  apps.value.filter(a => {
    if (filterKind.value && a.app_kind !== filterKind.value) return false
    if (filterCategory.value && a.category !== filterCategory.value) return false
    return true
  })
)

const statusLabel = (s: string) => ({ draft: '草稿', reviewing: '评测中', published: '已发布' } as any)[s] || s

const kbOptions = computed(() => kbs.value.map(k => ({ label: k.name, value: k.id })))

const form = reactive({
  name: '',
  description: '',
  app_type: 'qa',
  app_kind: 'simple',
  category: '办公提效',
  kb_ids: [] as string[]
})

function formatTime(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function load() {
  loading.value = true
  try {
    const [appList, kbList] = await Promise.all([listApps(), listKbs()])
    apps.value = appList
    kbs.value = kbList
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function createApp() {
  creating.value = true
  try {
    const app = await apiCreateApp({
      name: form.name.trim(),
      description: form.description.trim(),
      app_type: form.app_type,
      app_kind: form.app_kind,
      category: form.category,
      kb_ids: form.kb_ids
    })
    showCreate.value = false
    form.name = ''
    form.description = ''
    form.kb_ids = []
    message.success('应用创建成功（草稿状态）')
    await load()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    creating.value = false
  }
}

function removeApp(app: Application) {
  dialog.warning({
    title: '删除应用',
    content: `确定删除「${app.name}」吗？其下的会话记录将一并删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteApp(app.id)
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

.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.app-card {
  cursor: pointer;
}

.app-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.app-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.app-info {
  flex: 1;
  min-width: 0;
}

.app-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-time {
  font-size: 12px;
  color: #a8adb5;
  margin-top: 2px;
}

.app-desc {
  margin: 12px 0;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.6;
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.app-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid #f0f1f3;
}

.app-kb {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #8f959e;
}

.empty-box {
  padding: 80px 0;
}

.type-title {
  font-size: 13px;
  font-weight: 600;
  color: #4b5563;
  margin-bottom: 10px;
}

.type-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.type-item {
  border: 1.5px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px 12px;
  cursor: pointer;
  text-align: center;
  transition: all 0.2s;
}

.type-item:hover {
  border-color: #b7c8ff;
}

.type-item.active {
  border-color: #3370ff;
  background: #f0f5ff;
}

.type-name {
  margin-top: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2329;
}

.type-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #8f959e;
}
</style>
