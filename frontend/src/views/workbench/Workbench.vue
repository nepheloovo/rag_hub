<template>
  <div class="page">
    <div class="greet">
      <div>
        <h2 class="page-title">{{ greeting }}，{{ auth.displayName }}</h2>
        <p class="page-desc">选择一个业务应用开始工作，或直接描述你要完成的事。</p>
      </div>
    </div>

    <!-- 业务场景分类 -->
    <div class="cat-grid">
      <n-card
        v-for="c in categories"
        :key="c.name"
        class="cat-card"
        hoverable
        @click="filterCategory = c.name"
      >
        <div class="cat-icon" :style="{ background: c.bg, color: c.color }">
          <n-icon size="22"><component :is="c.icon" /></n-icon>
        </div>
        <div class="cat-name">{{ c.name }}</div>
        <div class="cat-desc">{{ c.desc }}</div>
        <div class="cat-count">{{ c.count }} 个应用</div>
      </n-card>
      <div class="cat-total">
        <div class="cat-total-num">{{ apps.length }}</div>
        <div class="cat-total-label">全部应用</div>
      </div>
    </div>

    <div class="section-head">
      <span class="section-title">全部应用</span>
      <span class="section-tip">点击「开始使用」直接进入对话</span>
    </div>

    <!-- 应用卡片 -->
    <n-spin :show="loading">
      <div class="app-grid">
        <n-card v-for="app in filteredApps" :key="app.id" class="app-card" hoverable>
          <div class="app-card-head">
            <div class="app-name-row">
              <span class="app-name" @click="$router.push(`/app/apps/${app.id}`)">{{ app.name }}</span>
              <n-tag size="small" :bordered="false" :color="{ color: kindMeta[app.app_kind].bg, textColor: kindMeta[app.app_kind].color }">
                {{ kindMeta[app.app_kind].label }}
              </n-tag>
              <n-tag size="small" :type="app.status === 'published' ? 'success' : 'default'" :bordered="false">{{ statusLabel(app.status) }}</n-tag>
            </div>
            <n-button quaternary circle size="tiny" @click="toggleFav(app.id)">
              <template #icon>
                <n-icon :color="isFav(app.id) ? '#faad14' : '#b3b8bf'"><Star /></n-icon>
              </template>
            </n-button>
          </div>
          <div class="app-desc">{{ app.description || '暂无描述' }}</div>
          <div class="app-foot">
            <span class="app-cat">{{ app.category }}</span>
            <span class="app-usage">7 天 {{ app.call_count_7d }} 次调用</span>
            <n-button size="small" type="primary" ghost @click="$router.push(`/app/apps/${app.id}`)">
              开始使用
            </n-button>
          </div>
        </n-card>
        <n-empty v-if="!loading && filteredApps.length === 0" description="该分类下暂无应用" />
      </div>
    </n-spin>

    <!-- 我的收藏 + 最近使用 -->
    <div class="two-col">
      <n-card size="small" title="我的收藏">
        <div v-if="favApps.length === 0" class="mini-empty">点击应用卡片右上角的星标收藏</div>
        <div v-for="a in favApps" :key="a.id" class="mini-item" @click="$router.push(`/app/apps/${a.id}`)">
          <span class="mini-name">{{ a.name }}</span>
          <span class="mini-sub">{{ kindMeta[a.app_kind].label }}</span>
        </div>
      </n-card>
      <n-card size="small" title="最近使用">
        <div v-if="recentItems.length === 0" class="mini-empty">暂无使用记录</div>
        <div
          v-for="(r, i) in recentItems"
          :key="i"
          class="mini-item"
          @click="$router.push(`/app/apps/${r.app_id}`)"
        >
          <span class="mini-name">{{ r.title }}</span>
          <span class="mini-sub">{{ r.app_name }} · {{ r.timeLabel }}</span>
        </div>
      </n-card>
    </div>

    <!-- 本月业务沉淀 -->
    <n-card size="small" title="本月业务沉淀" style="margin-top: 16px">
      <div class="stat-row">
        <n-statistic label="应用调用" :value="stats.month_app_calls" />
        <n-statistic label="覆盖员工" value="—">
          <template #suffix><span class="stat-hint">SSO 接入后开放</span></template>
        </n-statistic>
        <n-statistic label="新增知识" :value="stats.month_new_docs + ' 条'" />
        <n-statistic label="估算节省" :value="estHours + ' h'">
          <template #suffix><span class="stat-hint">按每次 3 分钟估算</span></template>
        </n-statistic>
      </div>
    </n-card>

    <!-- AI 生成应用 -->
    <n-card size="small" title="没有合适的应用？" style="margin-top: 16px">
      <div class="gen-row">
        <div class="gen-desc">描述需求，AI 帮你生成第一版</div>
        <n-input
          v-model:value="genText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 3 }"
          placeholder="例如：做一个储能产品售后客服，能查订单、回答退换货政策，解决不了转人工"
          style="flex: 1"
        />
        <n-button type="primary" :loading="generating" :disabled="!genText.trim()" @click="doGenerate">
          <template #icon><n-icon><SparklesOutline /></n-icon></template>
          生成应用
        </n-button>
      </div>
      <n-spin v-if="generating" size="small" style="margin-top: 12px" />
      <div v-if="genDraft" class="gen-draft">
        <div class="gen-draft-head">
          <span class="gen-draft-name">「{{ genDraft.name }}」</span>
          <n-tag size="small" :bordered="false" type="info">{{ genDraft.category }}</n-tag>
          <n-tag size="small" :bordered="false">{{ typeLabel(genDraft.app_type) }}</n-tag>
          <span v-if="genFake" class="gen-note">（模拟生成，配置服务商后由真实模型生成）</span>
        </div>
        <div class="gen-draft-desc">{{ genDraft.description }}</div>
        <div class="gen-draft-actions">
          <n-button type="primary" size="small" @click="adoptDraft">采纳并创建</n-button>
          <n-button size="small" quaternary @click="genDraft = null">放弃</n-button>
        </div>
      </div>
    </n-card>

    <!-- 采纳后创建弹窗 -->
    <n-modal v-model:show="showCreate" preset="card" title="新建应用" style="width: 620px" :mask-closable="false">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="应用名称" required>
          <n-input v-model:value="createForm.name" />
        </n-form-item>
        <n-form-item label="应用形态">
          <n-select
            v-model:value="createForm.app_kind"
            :options="kindOptions"
            style="width: 240px"
          />
        </n-form-item>
        <n-form-item label="业务分类">
          <n-select
            v-model:value="createForm.category"
            :options="categoryOptions"
            style="width: 240px"
          />
        </n-form-item>
        <n-form-item label="绑定知识库" required>
          <n-select
            v-model:value="createForm.kb_ids"
            multiple
            :options="kbOptions"
            placeholder="可绑定多个知识库"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="showCreate = false">取消</n-button>
          <n-button
            type="primary"
            :disabled="!createForm.name.trim() || !createForm.kb_ids.length"
            :loading="creating"
            @click="doCreate"
          >创建</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, markRaw } from 'vue'
import { useMessage } from 'naive-ui'
import {
  DocumentTextOutline,
  HeadsetOutline,
  ShieldCheckmarkOutline,
  MegaphoneOutline,
  BriefcaseOutline,
  Star,
  SparklesOutline
} from '@vicons/ionicons5'
import { generateApp, getStatsOverview, listApps, listKbs, createApp } from '@/api'
import type { AppGenerateDraft, Application, KnowledgeBase, StatsOverview } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const message = useMessage()
const auth = useAuthStore()
const apps = ref<Application[]>([])
const kbs = ref<KnowledgeBase[]>([])
const stats = ref<StatsOverview>({
  month_app_calls: 0, month_new_docs: 0, month_new_apps: 0,
  kb_count: 0, app_count: 0, published_count: 0
})
const loading = ref(false)
const filterCategory = ref<string | null>(null)
const favIds = ref<string[]>(JSON.parse(localStorage.getItem('zhishu-favs') || '[]'))

const kindMeta: Record<string, { label: string; color: string; bg: string }> = {
  simple: { label: '简易', color: '#3370ff', bg: '#eef3ff' },
  chatflow: { label: 'Chat Flow', color: '#8b5cf6', bg: '#f3efff' },
  agent: { label: 'Agent', color: '#0ea5e9', bg: '#e8f7ff' }
}

const categories = computed(() => {
  const defs = [
    { name: '报告撰写', desc: '行业研究、经营分析、项目周报', icon: markRaw(DocumentTextOutline), color: '#8b5cf6', bg: '#f3efff' },
    { name: '智能客服', desc: '产品咨询、售后政策、订单问题', icon: markRaw(HeadsetOutline), color: '#22c55e', bg: '#ecfdf3' },
    { name: '制度与合同审校', desc: '合同风险、制度合规、条款比对', icon: markRaw(ShieldCheckmarkOutline), color: '#f59e0b', bg: '#fff7e8' },
    { name: '营销内容', desc: '多渠道文案、活动方案、销售话术', icon: markRaw(MegaphoneOutline), color: '#ef4444', bg: '#fdeeee' },
    { name: '办公提效', desc: '会议纪要、邮件、制度问答', icon: markRaw(BriefcaseOutline), color: '#3370ff', bg: '#eef3ff' }
  ]
  return defs.map(d => ({
    ...d,
    count: apps.value.filter(a => a.category === d.name).length
  }))
})

const filteredApps = computed(() => {
  if (!filterCategory.value) return apps.value
  return apps.value.filter(a => a.category === filterCategory.value)
})

const estHours = computed(() => Math.round((stats.value.month_app_calls * 3) / 60))

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const favApps = computed(() => apps.value.filter(a => favIds.value.includes(a.id)))
const isFav = (id: string) => favIds.value.includes(id)

function toggleFav(id: string) {
  favIds.value = favIds.value.includes(id)
    ? favIds.value.filter(x => x !== id)
    : [...favIds.value, id]
  localStorage.setItem('zhishu-favs', JSON.stringify(favIds.value))
}

// 最近使用（基于会话）
const recentItems = ref<{ app_id: string; app_name: string; title: string; timeLabel: string }[]>([])

async function load() {
  loading.value = true
  try {
    const [appList, kbList, s] = await Promise.all([listApps(), listKbs(), getStatsOverview()])
    apps.value = auth.role === 'business_user' ? appList.filter(app => app.status === 'published') : appList
    kbs.value = kbList
    stats.value = s
    loadRecent()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadRecent() {
  try {
    const { listConversations } = await import('@/api')
    const convs = await listConversations()
    const appName = (id: string) => apps.value.find(a => a.id === id)?.name || '未知应用'
    recentItems.value = convs
      .filter(c => c.app_id && apps.value.some(app => app.id === c.app_id))
      .slice(0, 6)
      .map(c => ({
        app_id: c.app_id!,
        app_name: appName(c.app_id!),
        title: c.title,
        timeLabel: formatTime(c.created_at)
      }))
  } catch {
    /* 静默 */
  }
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// AI 生成
const genText = ref('')
const generating = ref(false)
const genDraft = ref<AppGenerateDraft | null>(null)
const genFake = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', app_kind: 'simple', category: '办公提效', kb_ids: [] as string[] })

const kindOptions = [
  { label: '简易（提示词 + 知识库 + 表单）', value: 'simple' },
  { label: 'Chat Flow（可视化编排）', value: 'chatflow' },
  { label: 'Agent（自主规划工具）', value: 'agent' }
]
const categoryOptions = ['报告撰写', '智能客服', '制度与合同审校', '营销内容', '办公提效'].map(c => ({ label: c, value: c }))
const kbOptions = computed(() => kbs.value.map(k => ({ label: k.name, value: k.id })))

const typeLabel = (t: string) => ({ qa: '问答应用', service: '智能客服', report: '报告分析' } as any)[t] || t
const statusLabel = (s: string) => ({ published: '已发布', offline: '已下线', draft: '草稿' } as Record<string, string>)[s] || s

async function doGenerate() {
  if (!genText.value.trim()) return
  generating.value = true
  genDraft.value = null
  try {
    const resp = await generateApp(genText.value.trim())
    genDraft.value = resp.draft
    genFake.value = resp.models.fake
  } catch (e: any) {
    message.error(e.message)
  } finally {
    generating.value = false
  }
}

function adoptDraft() {
  if (!genDraft.value) return
  createForm.value = {
    name: genDraft.value.name,
    app_kind: 'simple',
    category: genDraft.value.category,
    kb_ids: []
  }
  showCreate.value = true
}

async function doCreate() {
  creating.value = true
  try {
    const draft = genDraft.value
    await createApp({
      name: createForm.value.name.trim(),
      app_type: draft?.app_type || 'qa',
      app_kind: createForm.value.app_kind,
      category: createForm.value.category,
      kb_ids: createForm.value.kb_ids,
      description: draft?.description || '',
      status: 'draft'
    } as any)
    showCreate.value = false
    genDraft.value = null
    genText.value = ''
    message.success('应用已创建（草稿），可在应用页继续配置')
    await load()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    creating.value = false
  }
}

onMounted(load)
</script>

<style scoped>
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

.greet {
  margin-bottom: 20px;
}

.cat-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.cat-card {
  cursor: pointer;
}

.cat-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cat-name {
  margin-top: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #1f2329;
}

.cat-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #8f959e;
  line-height: 1.5;
  min-height: 34px;
}

.cat-count {
  margin-top: 6px;
  font-size: 12px;
  color: #3370ff;
}

.cat-total {
  border: 1px dashed #c9d4ff;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f8faff;
}

.cat-total-num {
  font-size: 28px;
  font-weight: 700;
  color: #3370ff;
}

.cat-total-label {
  font-size: 13px;
  color: #6b7280;
}

.section-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
}

.section-tip {
  font-size: 12px;
  color: #a8adb5;
}

.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.app-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.app-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.app-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-desc {
  margin: 10px 0;
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
  gap: 12px;
  padding-top: 10px;
  border-top: 1px solid #f0f1f3;
}

.app-cat {
  font-size: 12px;
  color: #8f959e;
}

.app-usage {
  font-size: 12px;
  color: #8f959e;
  flex: 1;
}

.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.mini-empty {
  font-size: 12px;
  color: #a8adb5;
  padding: 10px 0;
}

.mini-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
}

.mini-item:hover {
  background: #f5f7fa;
}

.mini-name {
  font-size: 13px;
  color: #1f2329;
}

.mini-sub {
  font-size: 12px;
  color: #a8adb5;
}

.stat-row {
  display: flex;
  gap: 64px;
}

.stat-hint {
  font-size: 12px;
  color: #a8adb5;
  margin-left: 6px;
}

.gen-row {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.gen-desc {
  font-size: 13px;
  color: #6b7280;
  white-space: nowrap;
  padding-top: 8px;
}

.gen-draft {
  margin-top: 14px;
  border: 1px solid #c9d4ff;
  background: #f8faff;
  border-radius: 10px;
  padding: 12px 14px;
}

.gen-draft-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gen-draft-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2329;
}

.gen-note {
  font-size: 12px;
  color: #a8adb5;
}

.gen-draft-desc {
  margin: 8px 0;
  font-size: 13px;
  color: #6b7280;
}

.gen-draft-actions {
  display: flex;
  gap: 10px;
}
</style>
