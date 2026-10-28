<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">设置</h2>
        <p class="page-desc">团队、角色与权限、Agent 接入和审计</p>
      </div>
      <n-button type="primary" @click="showCreateUser = true">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        邀请成员
      </n-button>
    </div>

    <n-card size="small">
      <n-tabs v-model:value="activeTab" type="line">
        <!-- 成员 -->
        <n-tab-pane name="members" tab="成员">
          <n-alert type="info" :bordered="false" style="margin-bottom: 12px">
            成员来自企业 SSO（飞书 / 企业微信）自动同步（规划中）。当前使用本地账号管理。
          </n-alert>
          <n-data-table :columns="userColumns" :data="users" :bordered="false" :loading="loading" :row-key="(r: any) => r.id" />
        </n-tab-pane>

        <!-- 角色与权限 -->
        <n-tab-pane name="roles" tab="角色与权限">
          <div style="margin-top: 12px">
            <n-data-table :columns="roleColumns" :data="roleRows" :bordered="false" :pagination="false" />
          </div>
        </n-tab-pane>

        <!-- Agent 接入 -->
        <n-tab-pane name="agent" tab="Agent 接入">
          <div style="margin-top: 12px; max-width: 860px">
            <div class="agent-hint">已发布并开启「对外发布」的应用可嵌入官网或企业微信，支持访客限额。</div>
            <n-data-table :columns="channelColumns" :data="publishedApps" :bordered="false" :loading="loading" :row-key="(r: any) => r.id" />
          </div>
        </n-tab-pane>

        <!-- SSO 配置 -->
        <n-tab-pane name="sso" tab="SSO 配置">
          <div style="margin-top: 12px; max-width: 640px">
            <n-card size="small" title="飞书登录" :bordered="true">
              <n-form label-placement="left" label-width="100">
                <n-form-item label="启用飞书登录">
                  <n-switch v-model:value="ssoForm.feishu_enabled" />
                </n-form-item>
                <n-form-item label="App ID">
                  <n-input v-model:value="ssoForm.feishu_app_id" placeholder="cli_xxxx（飞书开放平台创建企业自建应用后获取）" />
                </n-form-item>
                <n-form-item label="App Secret">
                  <n-input
                    v-model:value="ssoForm.feishu_app_secret"
                    type="password"
                    show-password-on="click"
                    :placeholder="ssoForm.feishu_has_secret ? '已配置（输入新值可覆盖）' : '应用密钥'"
                  />
                </n-form-item>
                <n-form-item label="回调地址">
                  <n-input :value="feishuCallbackUrl" readonly />
                  <div class="field-hint" style="margin-left: 12px">在飞书开放平台「安全设置 → 重定向 URL」中填入此地址</div>
                </n-form-item>
              </n-form>
              <div style="display: flex; justify-content: flex-end">
                <n-button type="primary" size="small" :loading="ssoSaving" @click="saveSso">保存</n-button>
              </div>
            </n-card>
            <n-card size="small" title="企业微信登录" :bordered="true" style="margin-top: 12px">
              <n-form label-placement="left" label-width="100">
                <n-form-item label="启用">
                  <n-switch v-model:value="ssoForm.wecom_enabled" />
                </n-form-item>
                <n-form-item label="企业 ID (CorpID)">
                  <n-input v-model:value="ssoForm.wecom_corp_id" placeholder="wwxxxxxxxx" />
                </n-form-item>
                <n-form-item label="应用 AgentId">
                  <n-input v-model:value="ssoForm.wecom_agent_id" placeholder="1000002" />
                </n-form-item>
                <n-form-item label="应用 Secret">
                  <n-input
                    v-model:value="ssoForm.wecom_secret"
                    type="password"
                    show-password-on="click"
                    :placeholder="ssoForm.wecom_has_secret ? '已配置（输入新值可覆盖）' : '应用密钥'"
                  />
                </n-form-item>
              </n-form>
              <div style="display: flex; justify-content: flex-end">
                <n-button type="primary" size="small" :loading="ssoSaving" @click="saveSso">保存</n-button>
              </div>
              <n-alert type="warning" :bordered="false" style="margin-top: 10px">
                企业微信 OAuth 回调流程规划中，当前先保存凭证；真实登录接入后续版本开放。
              </n-alert>
            </n-card>
          </div>
        </n-tab-pane>

        <!-- 审计日志 -->
        <n-tab-pane name="audit" tab="审计日志">
          <div class="filter-row" style="margin: 12px 0">
            <n-input v-model:value="auditAction" placeholder="按操作过滤，如 user / app / login" style="width: 240px" clearable @keydown.enter="loadAudit" />
            <n-button type="primary" ghost @click="loadAudit">查询</n-button>
          </div>
          <n-data-table
            :columns="auditColumns"
            :data="auditRows"
            :bordered="false"
            :loading="auditLoading"
            :row-key="(r: any) => r.id"
            :pagination="auditPagination"
            remote
            @update:page="onAuditPage"
          />
        </n-tab-pane>
      </n-tabs>
    </n-card>

    <!-- 邀请成员 -->
    <n-modal v-model:show="showCreateUser" preset="card" title="邀请成员" style="width: 520px" :mask-closable="false">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="用户名" required>
          <n-input v-model:value="userForm.username" placeholder="登录账号" />
        </n-form-item>
        <n-form-item label="姓名">
          <n-input v-model:value="userForm.display_name" placeholder="成员姓名" />
        </n-form-item>
        <n-form-item label="部门">
          <n-input v-model:value="userForm.department" placeholder="如：客服中心" />
        </n-form-item>
        <n-form-item label="角色">
          <n-select v-model:value="userForm.role" :options="roleOptions" />
        </n-form-item>
        <n-form-item label="初始密码" required>
          <n-input v-model:value="userForm.password" type="password" show-password-on="click" placeholder="至少 6 位" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <n-button @click="showCreateUser = false">取消</n-button>
          <n-button type="primary" :disabled="!userForm.username.trim() || userForm.password.length < 6" :loading="creating" @click="doCreateUser">
            创建
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, computed, onMounted, reactive } from 'vue'
import { useMessage, useDialog, NTag, NButton, NSwitch } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import { createUser, listAudit, listApps, listUsers, updateApp, updateUser } from '@/api'
import type { Application } from '@/api/types'

const message = useMessage()
const dialog = useDialog()
const activeTab = ref('members')
const users = ref<any[]>([])
const loading = ref(false)
const showCreateUser = ref(false)
const creating = ref(false)

// ---------- SSO 配置 ----------
const ssoForm = reactive({
  feishu_enabled: false,
  feishu_app_id: '',
  feishu_app_secret: '',
  feishu_has_secret: false,
  wecom_enabled: false,
  wecom_corp_id: '',
  wecom_agent_id: '',
  wecom_secret: '',
  wecom_has_secret: false
})
const ssoSaving = ref(false)
const feishuCallbackUrl = computed(() => `${location.origin}/api/auth/feishu/callback`)

async function loadSso() {
  try {
    const { api } = await import('@/api/client')
    const cfg = await api('/sso')
    Object.assign(ssoForm, cfg)
    ssoForm.feishu_app_secret = ''
    ssoForm.wecom_secret = ''
  } catch {
    /* 静默 */
  }
}

async function saveSso() {
  ssoSaving.value = true
  try {
    const { api } = await import('@/api/client')
    await api('/sso', {
      method: 'PUT',
      body: JSON.stringify({
        feishu_enabled: ssoForm.feishu_enabled,
        feishu_app_id: ssoForm.feishu_app_id,
        feishu_app_secret: ssoForm.feishu_app_secret || null,
        wecom_enabled: ssoForm.wecom_enabled,
        wecom_corp_id: ssoForm.wecom_corp_id,
        wecom_agent_id: ssoForm.wecom_agent_id,
        wecom_secret: ssoForm.wecom_secret || null
      })
    })
    message.success('SSO 配置已保存')
    await loadSso()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    ssoSaving.value = false
  }
}

const roleLabels: Record<string, string> = {
  platform_admin: '平台管理员',
  app_developer: '应用开发者',
  kb_admin: '知识库管理员',
  business_user: '业务使用者'
}
const roleOptions = Object.entries(roleLabels).map(([value, label]) => ({ label, value }))

const userForm = reactive({ username: '', display_name: '', department: '', role: 'business_user', password: '' })

const userColumns = [
  { title: '成员', key: 'display_name', width: 140 },
  { title: '用户名', key: 'username', width: 140 },
  { title: '部门', key: 'department', width: 130 },
  {
    title: '角色',
    key: 'role',
    width: 150,
    render: (row: any) => h(NTag, { size: 'small', bordered: false, type: row.role === 'platform_admin' ? 'info' : 'default' }, { default: () => row.role_label || row.role })
  },
  {
    title: '状态',
    key: 'enabled',
    width: 90,
    render: (row: any) =>
      h(NSwitch, {
        size: 'small',
        value: row.enabled,
        onUpdateValue: (v: boolean) => toggleUser(row, v)
      })
  },
  { title: '最近登录', key: 'last_login_at', width: 170, render: (row: any) => (row.last_login_at ? formatTime(row.last_login_at) : '从未登录') },
  {
    title: '操作',
    key: 'actions',
    render: (row: any) =>
      row.username !== 'admin'
        ? h(NButton, { size: 'tiny', quaternary: true, type: 'primary', onClick: () => changeRole(row) }, { default: () => '调整角色' })
        : null
  }
]

const roleColumns = [
  { title: '角色', key: 'name', width: 160 },
  { title: '权限说明', key: 'desc' },
  { title: '状态', key: 'status', width: 110 }
]
const roleRows = [
  { name: '平台管理员', desc: '全部功能：成员/角色/模型配置/审计/日志 + 应用/知识库/工具管理', status: '已启用' },
  { name: '应用开发者', desc: '搭建与编排应用、管理知识库与工具、查看看板', status: '已启用' },
  { name: '知识库管理员', desc: '知识库管理、文档导入、应用搭建', status: '已启用' },
  { name: '业务使用者', desc: '工作台与已发布应用对话', status: '已启用' }
]

// Agent 接入
const publishedApps = ref<Application[]>([])
const channelColumns = [
  { title: '应用', key: 'name', width: 200 },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row: Application) =>
      row.status === 'published'
        ? h(NTag, { size: 'small', type: 'success', bordered: false }, { default: () => '已发布' })
        : h(NTag, { size: 'small', type: 'default', bordered: false }, { default: () => '未发布' })
  },
  {
    title: '官网嵌入',
    key: 'publish_enabled',
    width: 110,
    render: (row: Application) =>
      h(NSwitch, {
        size: 'small',
        value: !!row.publish_enabled,
        disabled: row.status !== 'published',
        onUpdateValue: (v: boolean) => togglePublish(row, v)
      })
  },
  {
    title: '访客每日限额',
    key: 'visitor_daily_limit',
    width: 130,
    render: (row: Application) => (row.visitor_daily_limit || 0) > 0 ? String(row.visitor_daily_limit) + ' 次/日' : '不限'
  },
  {
    title: '近 7 天调用',
    key: 'call_count_7d',
    width: 110,
    render: (row: Application) => row.call_count_7d.toLocaleString()
  },
  {
    title: '操作',
    key: 'actions',
    render: (row: Application) =>
      h(NButton, { size: 'tiny', quaternary: true, type: 'primary', onClick: () => setLimit(row) }, { default: () => '设置限额' })
  }
]

// 审计
const auditRows = ref<any[]>([])
const auditLoading = ref(false)
const auditTotal = ref(0)
const auditPage = ref(1)
const auditAction = ref('')
const auditPagination = { page: 1, pageSize: 20, itemCount: 0, showSizePicker: true }
const auditColumns = [
  { title: '时间', key: 'time', width: 170, render: (row: any) => formatTime(row.time) },
  { title: '操作人', key: 'actor', width: 120 },
  { title: '操作', key: 'action', width: 130, render: (row: any) => h(NTag, { size: 'small', bordered: false, type: actionType(row.action) }, { default: () => actionLabel(row.action) }) },
  { title: '对象', key: 'target', width: 180 },
  { title: '详情', key: 'detail', ellipsis: { tooltip: true } }
]

function actionType(a: string) {
  if (a.includes('failed') || a.includes('delete')) return 'error'
  if (a.includes('create') || a.includes('login')) return 'success'
  return 'info'
}
function actionLabel(a: string) {
  const map: Record<string, string> = {
    login: '登录', login_failed: '登录失败', user_create: '创建成员', user_update: '更新成员',
    app_create: '创建应用', app_update: '更新应用', app_delete: '删除应用',
    kb_create: '创建知识库', kb_delete: '删除知识库'
  }
  return map[a] || a
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function load() {
  loading.value = true
  try {
    const [u, a] = await Promise.all([listUsers(), listApps()])
    users.value = u
    publishedApps.value = a
  } catch (e: any) {
    message.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadAudit() {
  auditLoading.value = true
  try {
    const data = await listAudit({ action: auditAction.value || undefined, page: auditPage.value, page_size: 20 })
    auditRows.value = data.items
    auditTotal.value = data.total
    auditPagination.itemCount = data.total
  } finally {
    auditLoading.value = false
  }
}

function onAuditPage(p: number) {
  auditPage.value = p
  loadAudit()
}

async function doCreateUser() {
  creating.value = true
  try {
    await createUser({
      username: userForm.username.trim(),
      display_name: userForm.display_name,
      department: userForm.department,
      role: userForm.role,
      password: userForm.password
    })
    showCreateUser.value = false
    Object.assign(userForm, { username: '', display_name: '', department: '', role: 'business_user', password: '' })
    message.success('成员已创建')
    await load()
  } catch (e: any) {
    message.error(e.message)
  } finally {
    creating.value = false
  }
}

function toggleUser(row: any, enabled: boolean) {
  dialog.info({
    title: enabled ? '启用成员' : '停用成员',
    content: `确定${enabled ? '启用' : '停用'}「${row.display_name || row.username}」吗？`,
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await updateUser(row.id, { enabled })
        message.success('已更新')
        await load()
      } catch (e: any) {
        message.error(e.message)
      }
    }
  })
}

function changeRole(row: any) {
  const current = row.role
  const options = roleOptions.map(o => ({ ...o, disabled: o.value === current }))
  const idx = window.prompt(`输入新角色序号：\n1 平台管理员 2 应用开发者 3 知识库管理员 4 业务使用者（当前：${roleLabels[current]}）`)
  const list = ['platform_admin', 'app_developer', 'kb_admin', 'business_user']
  const i = parseInt(idx || '', 10)
  if (i >= 1 && i <= 4 && list[i - 1] !== current) {
    updateUser(row.id, { role: list[i - 1] }).then(() => {
      message.success('角色已调整')
      load()
    }).catch((e: any) => message.error(e.message))
  }
}

async function togglePublish(row: Application, enabled: boolean) {
  try {
    await updateApp(row.id, { publish_enabled: enabled } as any)
    message.success(enabled ? '已开启官网嵌入' : '已关闭官网嵌入')
    await load()
  } catch (e: any) {
    message.error(e.message)
  }
}

function setLimit(row: Application) {
  const val = window.prompt(`设置「${row.name}」访客每日限额（0=不限）`, String(row.visitor_daily_limit || 0))
  const n = parseInt(val || '0', 10)
  if (!isNaN(n) && n >= 0) {
    updateApp(row.id, { visitor_daily_limit: n } as any).then(() => {
      message.success('限额已设置')
      load()
    }).catch((e: any) => message.error(e.message))
  }
}

onMounted(() => {
  load()
  loadAudit()
  loadSso()
})
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

.filter-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.agent-hint {
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 12px;
}
</style>
