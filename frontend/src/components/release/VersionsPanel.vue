<template>
  <div class="versions-panel">
    <div class="panel-head"><div><h3>发布版本</h3><p>查看已固化的版本，回滚后所有渠道立即使用所选版本。</p></div><n-button size="small" :loading="loading" :disabled="!!rolling" @click="load">刷新</n-button></div>
    <n-alert v-if="error" type="error" :bordered="false" class="error">{{ error }}</n-alert>
    <n-spin :show="loading">
      <div v-if="releases?.versions.length" class="version-list">
        <div v-for="version in releases.versions" :key="version.id" class="version-row">
          <div class="version-number">v{{ version.version }}</div>
          <div class="version-info"><div class="version-notes">{{ version.release_notes || '无版本说明' }}</div><div class="version-meta">{{ formatTime(version.created_at) }}<span v-if="version.created_by"> · {{ version.created_by }}</span></div></div>
          <n-tag v-if="isOnline(version)" size="small" type="success" :bordered="false">线上</n-tag>
          <n-button v-else size="small" :loading="rolling === version.id" :disabled="!!rolling" @click="confirmRollback(version)">{{ releases.status === 'offline' && version.id === releases.published_version_id ? '重新上线此版本' : '回滚到此版本' }}</n-button>
        </div>
      </div>
      <n-empty v-else-if="!loading && !error" description="尚未发布任何版本" class="empty" />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { getAppReleases, rollbackApp } from '@/api'
import type { Application, AppReleases, AppReleaseVersion } from '@/api/types'

const props = defineProps<{ appId: string; refreshKey?: number }>()
const emit = defineEmits<{ changed: [app: Application] }>()
const dialog = useDialog()
const message = useMessage()
const releases = ref<AppReleases | null>(null)
const loading = ref(false)
const rolling = ref('')
const error = ref('')
let request = 0
const isOnline = (version: AppReleaseVersion) => releases.value?.status === 'published' && version.id === releases.value.published_version_id
const formatTime = (value: string) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
async function load() {
  const token = ++request
  loading.value = true
  error.value = ''
  try {
    const data = await getAppReleases(props.appId)
    if (token === request) releases.value = data
  } catch (caught) {
    if (token === request) error.value = caught instanceof Error ? caught.message : '版本加载失败，请刷新重试'
  } finally { if (token === request) loading.value = false }
}
function confirmRollback(version: AppReleaseVersion) {
  dialog.warning({
    title: `切换到 v${version.version}`,
    content: '确认后所有渠道将立即使用该版本；当前草稿保留。回滚不受发布门禁限制。',
    positiveText: '确认切换', negativeText: '取消',
    onPositiveClick: async () => {
      if (rolling.value) return false
      rolling.value = version.id
      try {
        const app = await rollbackApp(props.appId, version.id)
        emit('changed', app)
        message.success(`线上已切换到 v${version.version}`)
        await load()
      } catch (caught) {
        error.value = caught instanceof Error ? caught.message : '回滚失败，请重试'
        message.error(error.value)
        return false
      } finally { rolling.value = '' }
    }
  })
}
watch(() => [props.appId, props.refreshKey], load, { immediate: true })
</script>

<style scoped>
.versions-panel { max-width: 1000px; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; margin-bottom: 16px; }
h3 { margin: 0; font-size: 15px; color: #1f2329; }
p { margin: 6px 0 0; font-size: 12px; color: #646e7d; line-height: 1.7; }
.version-list { background: #fff; border: 1px solid #e5e6eb; border-radius: 10px; padding: 0 16px; }
.version-row { display: flex; align-items: center; gap: 16px; padding: 16px 0; border-bottom: 1px solid #eef0f3; }
.version-row:last-child { border-bottom: 0; }
.version-number { font-size: 16px; font-weight: 600; color: #3370ff; min-width: 40px; font-variant-numeric: tabular-nums; }
.version-info { flex: 1; min-width: 0; }
.version-notes { font-size: 13px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.version-meta { font-size: 12px; color: #646e7d; margin-top: 4px; overflow-wrap: anywhere; }
.empty { padding: 50px 0; }
.error { margin-bottom: 12px; }
@media (max-width: 620px) { .version-row { flex-wrap: wrap; gap: 10px; } .version-info { flex-basis: calc(100% - 60px); } }
</style>
